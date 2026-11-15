"""Durable IMAP attachment handoff with an idempotent consumer.

The database reservation precedes broker publication. Reconciliation republishes
pending and expired work; a row lock and a processing lease prevent simultaneous
consumers from creating different file records for the same attachment.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import tempfile
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone

from celery import shared_task
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import SessionLocal
from app.models import DocumentIntake, FileRecord
from app.services.account_deletion import assert_account_active
from app.services.account_lifecycle_lock import account_lifecycle_lock
from app.tasks.convert_to_pdf import convert_to_pdf
from app.tasks.process_document import _trusted_source_integration_id, process_document
from app.utils.tribe_scope import ensure_document_scope

CLAIM_SECONDS = 600


def _now():
    return datetime.now(timezone.utc)


def _expired(value):
    if value is None:
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= _now() - timedelta(seconds=CLAIM_SECONDS)


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


@contextmanager
def _owner_lifecycle_lock(db, owner):
    with (account_lifecycle_lock(db, owner, exclusive=False) if owner else nullcontext()):
        yield


def prepare_imap_attachment(*, owner_id, source_integration_id, idempotency_key, filename, payload, mime_type, is_pdf):
    """Persist an immutable staged attachment and enqueue its intake ID.

    Publication may be repeated safely; the consumer claims the database row.
    """
    owner = owner_id or settings.default_owner_id or None
    principal = str(owner or "legacy")
    digest = hashlib.sha256(payload).hexdigest()
    key = hashlib.sha256(idempotency_key.encode()).hexdigest()
    original_filename = os.path.basename(str(filename).replace("\\", "/")) or "attachment"
    extension = os.path.splitext(original_filename)[1].lower()[:32]
    staging = os.path.join(settings.workdir, "imap-staging")
    path = None
    metadata = {
        "sha256": digest,
        "owner_id": owner,
        "source_integration_id": source_integration_id,
        "mime_type": mime_type,
        "is_pdf": bool(is_pdf),
    }
    created = False
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
                existing = db.query(FileRecord).filter_by(owner_id=owner, filehash=digest).order_by(FileRecord.id).first()
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
                created = _stage_payload(path, staging, payload, digest)
                db.commit()
            except IntegrityError:
                db.rollback()
                winner = db.query(DocumentIntake).filter_by(principal_id=principal, idempotency_key=key).one_or_none()
                if winner is None and created and os.path.exists(path):
                    os.unlink(path)
                if winner is None:
                    raise
                row = winner
            except Exception:
                db.rollback()
                if created and os.path.exists(path):
                    os.unlink(path)
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


def _dispatch_intake(intake_id):
    """Persist a dispatch lease before publishing; recover ambiguous publishes."""
    token = uuid.uuid4().hex
    with SessionLocal() as db:
        row = db.query(DocumentIntake).filter_by(id=intake_id, source="imap").with_for_update().one_or_none()
        if row is None or row.state == "completed":
            return False
        if row.state in {"processing", "dispatched"} and not _expired(row.updated_at):
            return False
        metadata = json.loads(row.metadata_json or "{}")
        metadata["dispatch_token"] = token
        row.metadata_json, row.state, row.updated_at, row.error = json.dumps(metadata), "dispatched", _now(), None
        db.commit()
    try:
        process_imap_intake.delay(intake_id)
    except Exception as exc:
        with SessionLocal() as db:
            row = db.query(DocumentIntake).filter_by(id=intake_id).with_for_update().one()
            metadata = json.loads(row.metadata_json or "{}")
            if row.state == "dispatched" and metadata.get("dispatch_token") == token:
                row.state, row.error = "pending", str(exc)[:500]
                db.commit()
        raise
    return True


@shared_task(bind=True, soft_time_limit=480, time_limit=540)
def process_imap_intake(self, intake_id):
    """Reserve one FileRecord and run the first pipeline stage under a lease."""
    with SessionLocal() as db:
        row = db.query(DocumentIntake).filter_by(id=intake_id, source="imap").with_for_update().one_or_none()
        if row is None or row.state == "completed":
            return {"status": "already_completed"}
        if row.state == "processing" and not _expired(row.updated_at):
            return {"status": "already_processing"}
        metadata = json.loads(row.metadata_json or "{}")
        path = row.local_path
        if not path or not os.path.isfile(path):
            row.state, row.error = "failed", "Staged attachment missing"
            db.commit()
            return {"error": row.error}
        with open(path, "rb") as stream:
            actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual_hash != metadata["sha256"]:
            row.state, row.error = "failed", "Staged attachment hash mismatch"
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
                    db.query(FileRecord).filter_by(owner_id=owner, filehash=actual_hash).order_by(FileRecord.id).first()
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
        result = task.apply(args=[path], kwargs=kwargs, throw=True).result
        if result is None or (isinstance(result, dict) and (result.get("error") or result.get("status") == "skipped")):
            raise RuntimeError(f"First ingestion stage failed: {result}")
    except Exception as exc:
        with SessionLocal() as db:
            row = db.query(DocumentIntake).filter_by(id=intake_id).with_for_update().one()
            row.state, row.error = "failed", str(exc)[:500]
            db.commit()
        raise
    with SessionLocal() as db:
        row = db.query(DocumentIntake).filter_by(id=intake_id).with_for_update().one()
        row.state, row.error = "completed", None
        db.commit()
    return {"status": "completed", "file_id": file_id}


def reconcile_imap_intakes(limit=50):
    """Republish unfinished handoffs after a broker loss or expired consumer."""
    cutoff = _now() - timedelta(seconds=CLAIM_SECONDS)
    with SessionLocal() as db:
        ids = [
            row[0]
            for row in db.query(DocumentIntake.id)
            .filter(
                DocumentIntake.source == "imap",
                or_(
                    DocumentIntake.state.in_(("pending", "failed")),
                    (DocumentIntake.state.in_(("processing", "dispatched"))) & (DocumentIntake.updated_at < cutoff),
                ),
            )
            .order_by(DocumentIntake.updated_at, DocumentIntake.id)
            .limit(limit)
            .all()
        ]
    return sum(bool(_dispatch_intake(intake_id)) for intake_id in ids)
