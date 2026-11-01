"""Bounded, lease-based transactional-outbox dispatcher."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, or_

from app.celery_app import celery
from app.database import SessionLocal
from app.models import FileRecord, UploadBatch, UploadCapacity, UploadItem, UploadOutbox
from app.tasks.convert_to_pdf import convert_to_pdf
from app.tasks.process_document import process_document

logger = logging.getLogger(__name__)
CLAIM_SECONDS = 120
SMALL_BATCH_FILES = 100
AGING_SECONDS = 15 * 60
MAX_DISPATCH_PER_TICK = 10


def _priority(batch: UploadBatch | None) -> int:
    return 2 if batch and batch.total_files <= SMALL_BATCH_FILES else 6


@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def dispatch_upload_item(self, outbox_id: int, claim_token: str) -> dict[str, object]:
    """Publish one claimed entry.

    Publishing and marking dispatched cannot be one atomic operation with an
    external broker.  A timed claim gives at-least-once recovery; downstream
    processing receives a deterministic task id and must remain idempotent by
    FileRecord id.  We deliberately do not promise exactly-once delivery.
    """
    with SessionLocal() as db:
        outbox = db.query(UploadOutbox).filter(UploadOutbox.id == outbox_id).one_or_none()
        if outbox is None or outbox.dispatched_at is not None or outbox.claim_token != claim_token:
            return {"status": "not_claimed"}
        item = db.query(UploadItem).filter(UploadItem.id == outbox.item_id).one_or_none()
        if item is None or item.file_id is None:
            return {"status": "missing_item"}
        record = db.query(FileRecord).filter(FileRecord.id == item.file_id).one()
        batch = db.query(UploadBatch).filter(UploadBatch.id == item.batch_id).one_or_none()
        outbox.attempts += 1
        # Persist the dispatch intent before broker I/O.  A lease expiry may
        # re-publish after a crash, which is why file-idempotent pipeline work
        # is required; it cannot silently lose an accepted document.
        outbox.pipeline_started_at = outbox.pipeline_started_at or datetime.now(timezone.utc)
        db.commit()
        extension = record.original_filename.rsplit(".", 1)[-1].lower() if "." in record.original_filename else ""
        headers = {
            "bulk_upload": True,
            "bulk_accepted_at": batch.created_at.isoformat() if batch and batch.created_at else None,
            "bulk_batch_id": item.batch_id,
        }
        kwargs = {"original_filename": record.original_filename, "file_id": record.id, "owner_id": record.owner_id}
        try:
            if record.mime_type == "application/pdf" or extension == "pdf":
                task = process_document.apply_async(
                    args=[record.original_file_path or record.local_filename],
                    kwargs=kwargs,
                    priority=_priority(batch),
                    headers=headers,
                    task_id=f"bulk-upload-{outbox.id}",
                )
            else:
                task = convert_to_pdf.apply_async(
                    args=[record.original_file_path or record.local_filename],
                    kwargs=kwargs,
                    priority=_priority(batch),
                    headers=headers,
                    task_id=f"bulk-upload-{outbox.id}",
                )
        except Exception as exc:
            with SessionLocal() as retry_db:
                failed = (
                    retry_db.query(UploadOutbox)
                    .filter(UploadOutbox.id == outbox_id, UploadOutbox.claim_token == claim_token)
                    .one_or_none()
                )
                if failed:
                    failed.last_error = str(exc)[:1000]
                    failed.claim_token = None
                    failed.claim_expires_at = None
                    retry_db.commit()
            raise
        with SessionLocal() as done_db:
            done = (
                done_db.query(UploadOutbox)
                .filter(UploadOutbox.id == outbox_id, UploadOutbox.claim_token == claim_token)
                .one_or_none()
            )
            if done:
                done.dispatched_at = datetime.now(timezone.utc)
                done.claim_token = None
                done.claim_expires_at = None
                done_db.query(UploadItem).filter(UploadItem.id == item.id).update({"state": "queued"})
                done_db.commit()
        return {"status": "queued", "file_id": item.file_id, "task_id": task.id}


@celery.task
def dispatch_upload_outbox(limit: int = MAX_DISPATCH_PER_TICK) -> int:
    """Claim and submit a bounded fair slice; safe across multiple beat pods."""
    limit = min(max(1, int(limit)), MAX_DISPATCH_PER_TICK)
    now, stale_before = datetime.now(timezone.utc), datetime.now(timezone.utc) - timedelta(seconds=CLAIM_SECONDS)
    age_before = now - timedelta(seconds=AGING_SECONDS)
    with SessionLocal() as db:
        order = case(
            (UploadBatch.total_files <= SMALL_BATCH_FILES, 0),
            (UploadBatch.created_at <= age_before, 1),
            else_=2,
        )
        rows = (
            db.query(UploadOutbox)
            .join(UploadItem, UploadOutbox.item_id == UploadItem.id)
            .join(UploadBatch, UploadItem.batch_id == UploadBatch.id)
            .filter(UploadOutbox.dispatched_at.is_(None))
            .filter(or_(UploadOutbox.claim_expires_at.is_(None), UploadOutbox.claim_expires_at < stale_before))
            .order_by(order, UploadOutbox.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(limit)
            .all()
        )
        claims = []
        for row in rows:
            token = str(uuid.uuid4())
            row.claim_token = token
            row.claim_expires_at = now + timedelta(seconds=CLAIM_SECONDS)
            claims.append((row.id, token))
        db.commit()
    for outbox_id, token in claims:
        dispatch_upload_item.delay(outbox_id, token)
    return len(claims)


@celery.task
def reconcile_upload_states(limit: int = 100) -> int:
    """Release accepted-work capacity once the normal pipeline stored output.

    The processing pipeline predates bulk intake and has no callback hook.
    Its durable ``processed_file_path`` is the conservative success marker;
    keeping the reservation until then intentionally applies backpressure to
    slow upstream providers instead of admitting an unbounded backlog.
    """
    with SessionLocal() as db:
        rows = (
            db.query(UploadItem)
            .join(FileRecord, UploadItem.file_id == FileRecord.id)
            .filter(UploadItem.state.in_(("accepted", "queued", "processing")))
            .filter(FileRecord.processed_file_path.isnot(None))
            .with_for_update(skip_locked=True)
            .limit(min(max(1, int(limit)), 500))
            .all()
        )
        if not rows:
            return 0
        ledger = db.get(UploadCapacity, 1)
        if ledger is None:
            logger.error("bulk capacity ledger is missing; leaving items reserved")
            return 0
        released_files = len(rows)
        released_bytes = sum(int(row.size) for row in rows)
        for row in rows:
            row.state = "complete"
        ledger.reserved_files = max(0, ledger.reserved_files - released_files)
        ledger.reserved_bytes = max(0, ledger.reserved_bytes - released_bytes)
        db.commit()
        return released_files
