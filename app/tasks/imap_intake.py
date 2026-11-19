"""Durable IMAP attachment handoff with an idempotent consumer.

The database reservation precedes broker publication. Reconciliation republishes
pending and expired work; a row lock and a processing lease prevent simultaneous
consumers from creating different file records for the same attachment.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import mimetypes
import os
import tempfile
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import redis
from celery import shared_task
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import SessionLocal
from app.models import DocumentIntake, FileRecord
from app.services.account_deletion import assert_account_active
from app.services.account_lifecycle_lock import account_lifecycle_lock
from app.tasks.convert_to_pdf import PermanentConversionError, convert_to_pdf
from app.tasks.process_document import _trusted_source_integration_id, process_document
from app.utils.tribe_scope import ensure_document_scope

CLAIM_SECONDS = 600
# A broker-accepted task can spend considerably longer than the consumer lease
# waiting behind a large historical catch-up.  Do not republish that handoff
# after the short processing lease; the dispatch token below makes a genuinely
# stale delivery a no-op when recovery eventually republishes it.
DISPATCH_RECOVERY_SECONDS = CLAIM_SECONDS * 6
FAILED_RETRY_BASE_SECONDS = 300
FAILED_RETRY_MAX_SECONDS = 3600
BROKER_INVENTORY_MAX_MESSAGES = 50_000
BROKER_INVENTORY_MAX_BYTES = 25 * 1024 * 1024
BROKER_QUEUE_NAMES = ("document_processor",) + tuple(f"document_processor\x06\x16{i}" for i in range(1, 10))
_broker_client = None
_broker_client_url = None

# Redis executes each script without interleaving another command.  The count
# checks therefore cover the exact queue/unacked snapshot being parsed below;
# a separate LLEN/LRANGE/HVALS sequence could otherwise briefly prove a task
# absent while a worker moves it to Kombu's unacked hash.
_BROKER_INVENTORY_SCRIPT = """
local maximum_messages = tonumber(ARGV[1])
local maximum_bytes = tonumber(ARGV[2])
local total = 0
for index, key in ipairs(KEYS) do
    local count
    if index == #KEYS then
        count = redis.call('HLEN', key)
    else
        count = redis.call('LLEN', key)
    end
    total = total + count
    if total > maximum_messages then
        return {0, total, 0}
    end
end

local result = {1, total, 0}
local bytes = 0
for index, key in ipairs(KEYS) do
    local entries
    if index == #KEYS then
        entries = redis.call('HVALS', key)
    else
        entries = redis.call('LRANGE', key, 0, -1)
    end
    for _, entry in ipairs(entries) do
        bytes = bytes + string.len(entry)
        if bytes > maximum_bytes then
            return {0, total, bytes}
        end
        result[#result + 1] = entry
    end
end
result[3] = bytes
return result
"""


def _now():
    return datetime.now(timezone.utc)


def _expired(value):
    if value is None:
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= _now() - timedelta(seconds=CLAIM_SECONDS)


def _retry_due(row, now=None):
    """Return whether a failed intake has reached its durable retry time."""
    metadata = json.loads(row.metadata_json or "{}")
    if metadata.get("suppress_automatic_retry"):
        return False
    retry_at = metadata.get("next_retry_at")
    if not retry_at:
        return True
    try:
        due = datetime.fromisoformat(retry_at)
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        return due <= (now or _now())
    except (TypeError, ValueError):
        # A malformed backoff marker must not strand a durable intake forever.
        return True


def _celery_intake_id(raw):
    """Extract an intake ID from one Redis-backed Celery message."""
    try:
        message = json.loads(raw)
        # Kombu's Redis unacked hash stores [envelope, exchange, routing_key],
        # whereas ready queues store the envelope directly.
        if isinstance(message, list):
            message = message[0]
        if not isinstance(message, dict):
            return None
        task = (message.get("headers") or {}).get("task") or (message.get("properties") or {}).get("task")
        if task != "app.tasks.imap_intake.process_imap_intake":
            return None
        body = message.get("body")
        if isinstance(body, str):
            body = json.loads(base64.b64decode(body))
        args = body[0] if isinstance(body, (list, tuple)) else []
        return int(args[0]) if args else None
    except (TypeError, ValueError, KeyError, IndexError, json.JSONDecodeError, UnicodeDecodeError, binascii.Error):
        return None


def _broker_intake_inventory():
    """Return queued/unacked IMAP IDs, or None when bounded proof is unavailable.

    Reconciliation must fail closed: it is safer to wait for a later poll than
    to enqueue another copy while Redis contains an unknown amount of work.
    """
    global _broker_client, _broker_client_url
    try:
        broker_url = settings.effective_celery_broker_url
        if urlparse(broker_url).scheme not in {"redis", "rediss"}:
            return None
        if _broker_client is None or _broker_client_url != broker_url:
            _broker_client = redis.StrictRedis.from_url(
                broker_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=5
            )
            _broker_client_url = broker_url
        snapshot = _broker_client.eval(
            _BROKER_INVENTORY_SCRIPT,
            len(BROKER_QUEUE_NAMES) + 1,
            *BROKER_QUEUE_NAMES,
            "unacked",
            BROKER_INVENTORY_MAX_MESSAGES,
            BROKER_INVENTORY_MAX_BYTES,
        )
        if not snapshot or int(snapshot[0]) != 1:
            return None
        return {intake_id for raw in snapshot[3:] if (intake_id := _celery_intake_id(raw)) is not None}
    except Exception:
        return None


def _record_intake_failure(row, metadata, error):
    """Persist a bounded retry marker for every failed first-stage attempt."""
    attempts = int(metadata.get("intake_attempts") or 0) + 1
    delay = min(FAILED_RETRY_MAX_SECONDS, FAILED_RETRY_BASE_SECONDS * (2 ** min(attempts - 1, 4)))
    metadata["intake_attempts"] = attempts
    metadata["next_retry_at"] = (_now() + timedelta(seconds=delay)).isoformat()
    row.metadata_json = json.dumps(metadata)
    row.state, row.error = "failed", str(error)[:500]


def _stage_payload(path, staging, payload, digest):
    """Create an immutable stage without replacing an existing stage."""
    os.makedirs(staging, exist_ok=True)
    if os.path.exists(path):
        with open(path, "rb") as existing_stream:
            if hashlib.file_digest(existing_stream, "sha256").hexdigest() != digest:
                raise ValueError("IMAP staging path collision with different content")
        return False
    fd, temp_path = tempfile.mkstemp(prefix=".imap-", dir=staging)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        directory_fd = os.open(staging, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return True
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _cleanup_unreserved_stage(db, path):
    """Remove only a stage that no committed intake row owns.

    A commit exception can be ambiguous.  Confirming that no intake persisted
    the generated path avoids deleting the payload of a successful commit.
    """
    if not path or not os.path.exists(path):
        return
    try:
        reserved = db.query(DocumentIntake.id).filter_by(local_path=path).first()
    except Exception:
        # Leave the payload for reconciliation when commit visibility is unknown.
        return
    if reserved is None:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


@contextmanager
def _owner_lifecycle_lock(db, owner):
    with account_lifecycle_lock(db, owner, exclusive=False) if owner else nullcontext():
        yield


def prepare_imap_attachment(
    *, owner_id, source_integration_id, idempotency_key, filename, payload, mime_type, is_pdf, background=False
):
    """Persist an immutable staged attachment and enqueue its intake ID.

    Publication may be repeated safely; the consumer claims the database row.
    """
    owner = owner_id or settings.default_owner_id or None
    principal = str(owner or "legacy")
    digest = hashlib.sha256(payload).hexdigest()
    key = hashlib.sha256(idempotency_key.encode()).hexdigest()
    original_filename = os.path.basename(str(filename).replace("\\", "/"))
    if original_filename in {"", ".", ".."}:
        original_filename = "attachment"
    extension = os.path.splitext(original_filename)[1].lower()[:32]
    staging = os.path.join(settings.workdir, "imap-staging")
    path = None
    metadata = {
        "sha256": digest,
        "owner_id": owner,
        "source_integration_id": source_integration_id,
        "mime_type": mime_type,
        "is_pdf": bool(is_pdf),
        "background": bool(background),
    }
    with SessionLocal() as db, _owner_lifecycle_lock(db, owner):
        if owner:
            # Authorization must precede any durable or filesystem staging.
            assert_account_active(db, owner)
        row = db.query(DocumentIntake).filter_by(principal_id=principal, idempotency_key=key).with_for_update().first()
        if row is None:
            # The row owns this unique path.  It prevents a losing reservation
            # from ever deleting a winner's shared deterministic path.
            path = os.path.join(staging, f"{uuid.uuid4().hex}{extension}")
            existing = None
            if settings.enable_deduplication:
                existing = (
                    db.query(FileRecord).filter_by(owner_id=owner, filehash=digest).order_by(FileRecord.id).first()
                )
            if existing:
                metadata["file_id"] = existing.id
            row = DocumentIntake(
                principal_id=principal,
                idempotency_key=key,
                source="imap",
                original_filename=original_filename,
                local_path=path,
                metadata_json=json.dumps(metadata),
                state="completed" if existing else "pending",
            )
            db.add(row)
            try:
                db.flush()
                # Keep the reservation/account transaction open while staging.
                # A second check closes the gap between the precheck and commit.
                if owner:
                    assert_account_active(db, owner)
                if not existing:
                    _stage_payload(path, staging, payload, digest)
                db.commit()
            except IntegrityError:
                db.rollback()
                _cleanup_unreserved_stage(db, path)
                winner = db.query(DocumentIntake).filter_by(principal_id=principal, idempotency_key=key).one_or_none()
                if winner is None:
                    raise
                row = winner
            except Exception:
                db.rollback()
                _cleanup_unreserved_stage(db, path)
                raise
        stored = json.loads(row.metadata_json or "{}")
        path = row.local_path
        if stored.get("sha256") != digest:
            raise ValueError("IMAP intake identity reused for different attachment content")
        intake_id, state = row.id, row.state
        if state != "completed" and not os.path.exists(path):
            # Keep restoration under the same lifecycle fence as reservation.
            _stage_payload(path, staging, payload, digest)
    if state != "completed":
        _dispatch_intake(intake_id)
    return intake_id


def _dispatch_intake(intake_id, *, broker_inventory=None):
    """Persist a dispatch lease before publishing; recover ambiguous publishes."""
    token = uuid.uuid4().hex
    with SessionLocal() as db:
        row = db.query(DocumentIntake).filter_by(id=intake_id, source="imap").with_for_update().one_or_none()
        if row is None or row.state == "completed":
            return False
        if row.state == "failed" and not _retry_due(row):
            return False
        if row.state in {"processing", "dispatched"} and not _expired(row.updated_at):
            return False
        if row.state == "dispatched" and (broker_inventory is None or intake_id in broker_inventory):
            # The existing broker/unacked copy is still present, or inventory
            # could not prove its absence.  Fail closed to avoid queue storms.
            return False
        metadata = json.loads(row.metadata_json or "{}")
        metadata["dispatch_token"] = token
        row.metadata_json, row.state, row.updated_at, row.error = json.dumps(metadata), "dispatched", _now(), None
        db.commit()
    try:
        delivery_options = {"headers": {"imap_backlog": True}, "priority": 6} if metadata.get("background") else {}
        process_imap_intake.apply_async(
            args=[intake_id],
            kwargs={"dispatch_token": token},
            task_id=f"imap-intake-{intake_id}-{token}",
            **delivery_options,
        )
    except Exception as exc:
        with SessionLocal() as db:
            row = db.query(DocumentIntake).filter_by(id=intake_id).with_for_update().one()
            metadata = json.loads(row.metadata_json or "{}")
            if row.state == "dispatched" and metadata.get("dispatch_token") == token:
                row.state, row.error = "pending", str(exc)[:500]
                db.commit()
        raise
    return True


@shared_task(bind=True, soft_time_limit=480, time_limit=540, acks_late=True, reject_on_worker_lost=True)
def process_imap_intake(self, intake_id, dispatch_token=None):
    """Reserve one FileRecord and run the first pipeline stage under a lease."""
    with SessionLocal() as db:
        initial = db.query(DocumentIntake).filter_by(id=intake_id, source="imap").one_or_none()
        if initial is None or initial.state == "completed":
            return {"status": "already_completed"}
        owner = json.loads(initial.metadata_json or "{}").get("owner_id")
        # Re-read under the same shared lifecycle fence used by reservation and
        # staging.  The document pipeline runs after this scope has committed.
        with _owner_lifecycle_lock(db, owner):
            db.expire_all()
            row = db.query(DocumentIntake).filter_by(id=intake_id, source="imap").with_for_update().one_or_none()
            if row is None or row.state == "completed":
                return {"status": "already_completed"}
            current_token = json.loads(row.metadata_json or "{}").get("dispatch_token")
            if dispatch_token and current_token and dispatch_token != current_token:
                # A task that was waiting in the broker past its recovery lease
                # must not steal the newer dispatch or run the pipeline twice.
                return {"status": "stale_dispatch"}
            if row.state == "failed" and not _retry_due(row):
                # Legacy one-argument deliveries must obey the same durable
                # backoff as tokenized deliveries; otherwise old broker
                # messages can hot-loop a poison attachment.
                return {"status": "retry_backoff"}
            if row.state == "processing" and not _expired(row.updated_at):
                return {"status": "already_processing"}
            metadata = json.loads(row.metadata_json or "{}")
            # This must identify the *claim*, not the current dispatch.  A
            # legacy delivery has no dispatch token and can otherwise read a
            # replacement token at completion, allowing a lost old claim to
            # commit over a newer worker's claim.
            claim_token = uuid.uuid4().hex
            path = row.local_path
            if not path or not os.path.isfile(path):
                _record_intake_failure(row, metadata, "Staged attachment missing")
                db.commit()
                return {"error": row.error}
            with open(path, "rb") as stream:
                actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual_hash != metadata["sha256"]:
                _record_intake_failure(row, metadata, "Staged attachment hash mismatch")
                db.commit()
                return {"error": row.error}
            owner = metadata.get("owner_id")
            if owner:
                assert_account_active(db, owner)
            file_id = metadata.get("file_id")
            if file_id is None:
                existing = None
                if settings.enable_deduplication:
                    existing = (
                        db.query(FileRecord)
                        .filter_by(owner_id=owner, filehash=actual_hash)
                        .order_by(FileRecord.id)
                        .first()
                    )
                if existing:
                    metadata["file_id"] = existing.id
                    row.metadata_json, row.state, row.error = json.dumps(metadata), "completed", None
                    db.commit()
                    return {"status": "existing", "file_id": existing.id}
                tenant_id, tribe_id = ensure_document_scope(db, owner)
                source_id = _trusted_source_integration_id(
                    db, self.request.id, owner, metadata.get("source_integration_id")
                )
                record = FileRecord(
                    filehash=actual_hash,
                    original_filename=row.original_filename,
                    local_filename=path,
                    original_file_path=path,
                    file_size=os.path.getsize(path),
                    mime_type=metadata.get("mime_type") or mimetypes.guess_type(path)[0],
                    owner_id=owner,
                    tenant_id=tenant_id,
                    tribe_id=tribe_id,
                    source_integration_id=source_id,
                    is_duplicate=False,
                )
                db.add(record)
                db.flush()
                file_id = record.id
                metadata["file_id"] = file_id
            metadata["claim_token"] = claim_token
            row.metadata_json = json.dumps(metadata)
            row.state, row.error, row.updated_at = "processing", None, _now()
            filename = row.original_filename
            db.commit()
    try:
        kwargs = {
            "original_filename": filename,
            "file_id": file_id,
            "owner_id": owner,
            "source_integration_id": metadata.get("source_integration_id"),
        }
        task = process_document if metadata["is_pdf"] else convert_to_pdf
        delivery_options = {"headers": {"imap_backlog": True}, "priority": 6} if metadata.get("background") else {}
        if task is convert_to_pdf:
            kwargs["raise_on_error"] = True
        result = task.apply(args=[path], kwargs=kwargs, throw=True, **delivery_options).result
        if result is None or (isinstance(result, dict) and (result.get("error") or result.get("status") == "skipped")):
            raise RuntimeError(f"First ingestion stage failed: {result}")
    except PermanentConversionError as exc:
        with SessionLocal() as db:
            row = db.query(DocumentIntake).filter_by(id=intake_id).with_for_update().one()
            metadata = json.loads(row.metadata_json or "{}")
            if metadata.get("claim_token") != claim_token:
                return {"status": "stale_dispatch"}
            # Preserve the staged file and visible failed state for operator
            # action, but do not turn an unsupported/corrupt input into an
            # automatic recovery loop.
            metadata["suppress_automatic_retry"] = True
            metadata.pop("next_retry_at", None)
            row.metadata_json = json.dumps(metadata)
            row.state, row.error = "failed", str(exc)[:500]
            db.commit()
        return {"status": "permanent_failure", "file_id": file_id}
    except Exception as exc:
        with SessionLocal() as db:
            row = db.query(DocumentIntake).filter_by(id=intake_id).with_for_update().one()
            metadata = json.loads(row.metadata_json or "{}")
            if metadata.get("claim_token") != claim_token:
                return {"status": "stale_dispatch"}
            _record_intake_failure(row, metadata, exc)
            db.commit()
        raise
    with SessionLocal() as db:
        row = db.query(DocumentIntake).filter_by(id=intake_id).with_for_update().one()
        metadata = json.loads(row.metadata_json or "{}")
        if metadata.get("claim_token") != claim_token:
            return {"status": "stale_dispatch"}
        metadata.pop("next_retry_at", None)
        row.metadata_json = json.dumps(metadata)
        row.state, row.error = "completed", None
        db.commit()
    return {"status": "completed", "file_id": file_id}


def reconcile_imap_intakes(limit=50):
    """Republish unfinished handoffs after a broker loss or expired consumer."""
    now = _now()
    cutoff = now - timedelta(seconds=CLAIM_SECONDS)
    dispatch_cutoff = now - timedelta(seconds=DISPATCH_RECOVERY_SECONDS)
    broker_inventory = None
    with SessionLocal() as db:
        # Pending and failed rows are selected separately so a poison document
        # with an exponential retry delay cannot consume the whole batch.
        pending_ids = [
            row[0]
            for row in db.query(DocumentIntake.id)
            .filter(
                DocumentIntake.source == "imap",
                DocumentIntake.state == "pending",
            )
            .order_by(DocumentIntake.updated_at, DocumentIntake.id)
            .limit(limit // 2 or 1)
            .all()
        ]
        processing_ids = [
            row[0]
            for row in db.query(DocumentIntake.id)
            .filter(
                DocumentIntake.source == "imap",
                DocumentIntake.state == "processing",
                DocumentIntake.updated_at < cutoff,
            )
            .order_by(DocumentIntake.updated_at, DocumentIntake.id)
            .limit(limit - len(pending_ids))
            .all()
        ]
        failed_rows = (
            db.query(DocumentIntake)
            .filter(
                DocumentIntake.source == "imap",
                DocumentIntake.state == "failed",
                # Keep terminal conversion failures out of the bounded query
                # itself: filtering only after ``limit`` lets old suppressed
                # rows permanently starve due transient failures behind them.
                or_(
                    DocumentIntake.metadata_json.is_(None),
                    and_(
                        ~DocumentIntake.metadata_json.like('%"suppress_automatic_retry": true%'),
                        ~DocumentIntake.metadata_json.like('%"suppress_automatic_retry":true%'),
                    ),
                ),
            )
            .order_by(DocumentIntake.updated_at, DocumentIntake.id)
            .limit(limit)
            .all()
        )
        failed_ids = [row.id for row in failed_rows if _retry_due(row, now)]
        # Dispatched tasks are only recovered after the longer broker grace
        # period.  Their token makes an older queued delivery harmless.
        dispatched_ids = [
            row[0]
            for row in db.query(DocumentIntake.id)
            .filter(
                DocumentIntake.source == "imap",
                DocumentIntake.state == "dispatched",
                DocumentIntake.updated_at < dispatch_cutoff,
            )
            .order_by(DocumentIntake.updated_at, DocumentIntake.id)
            .limit(limit)
            .all()
        ]
        if dispatched_ids:
            broker_inventory = _broker_intake_inventory()
    ids = pending_ids + processing_ids + failed_ids + dispatched_ids
    return sum(bool(_dispatch_intake(intake_id, broker_inventory=broker_inventory)) for intake_id in ids[:limit])
