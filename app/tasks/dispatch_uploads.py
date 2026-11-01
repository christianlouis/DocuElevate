"""Bounded, lease-based transactional-outbox dispatcher."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, or_, update

from app.celery_app import celery
from app.database import SessionLocal
from app.models import FileProcessingStep, FileRecord, UploadBatch, UploadCapacity, UploadItem, UploadOutbox
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
                # A reconciler may have completed the item while broker
                # acknowledgement was delayed. Never resurrect terminal work.
                done_db.query(UploadItem).filter(UploadItem.id == item.id, UploadItem.state == "accepted").update(
                    {"state": "queued"}
                )
                done_db.commit()
        return {"status": "queued", "file_id": item.file_id, "task_id": task.id}


@celery.task
def dispatch_upload_outbox(limit: int = MAX_DISPATCH_PER_TICK) -> int:
    """Claim and submit a bounded fair slice; safe across multiple beat pods."""
    limit = min(max(1, int(limit)), MAX_DISPATCH_PER_TICK)
    now = datetime.now(timezone.utc)
    age_before = now - timedelta(seconds=AGING_SECONDS)
    with SessionLocal() as db:
        order = case(
            # Aged work comes first.  Without this order, a continual stream
            # of small batches can starve a large batch forever.
            (UploadBatch.created_at <= age_before, 0),
            (UploadBatch.total_files <= SMALL_BATCH_FILES, 1),
            else_=2,
        )
        rows = (
            db.query(UploadOutbox)
            .join(UploadItem, UploadOutbox.item_id == UploadItem.id)
            .join(UploadBatch, UploadItem.batch_id == UploadBatch.id)
            .filter(UploadOutbox.dispatched_at.is_(None))
            # A lease is stale at its expiry, not after another lease window.
            .filter(or_(UploadOutbox.claim_expires_at.is_(None), UploadOutbox.claim_expires_at < now))
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
    """Release capacity only at the pipeline's declared terminal stage.

    ``processed_file_path`` is written by metadata embedding *before*
    ``finalize_document_storage`` queues destinations, so it is not terminal.
    The existing status model defines ``send_to_all_destinations`` (including
    its user-destination alias) as the terminal stage.  A success or failure
    there is a completed attempt; individual provider retries remain governed
    by their own durable retry/outbox policy.
    """
    with SessionLocal() as db:
        terminal = (
            db.query(
                FileProcessingStep.file_id.label("file_id"),
                func.max(case((FileProcessingStep.status == "success", 1), else_=0)).label("succeeded"),
            )
            .filter(FileProcessingStep.step_name.in_(("send_to_all_destinations", "send_to_user_destinations")))
            .filter(FileProcessingStep.status.in_(("success", "failure")))
            .group_by(FileProcessingStep.file_id)
            .subquery()
        )
        candidates = (
            db.query(UploadItem.id, UploadItem.size, UploadItem.state, terminal.c.succeeded)
            .outerjoin(terminal, UploadItem.file_id == terminal.c.file_id)
            .outerjoin(FileRecord, UploadItem.file_id == FileRecord.id)
            .filter(UploadItem.capacity_released.is_(False))
            .filter(UploadItem.state.in_(("accepted", "queued", "processing", "failed")))
            .filter((UploadItem.state == "failed") | (terminal.c.file_id.isnot(None)) | (FileRecord.id.is_(None)))
            .order_by(UploadItem.id.asc())
            .limit(min(max(1, int(limit)), 500))
            .all()
        )
        if not candidates:
            return 0
        if db.get(UploadCapacity, 1) is None:
            logger.error("bulk capacity ledger is missing; leaving items reserved")
            return 0
        released_files = released_bytes = 0
        for item_id, size, current_state, succeeded in candidates:
            # Conditional transition is the winner election on SQLite and
            # protects against overlapping reconcilers on every backend.
            result = db.execute(
                update(UploadItem)
                .where(UploadItem.id == item_id, UploadItem.capacity_released.is_(False))
                .values(
                    capacity_released=True,
                    state=("failed" if current_state == "failed" else ("complete" if succeeded else "failed")),
                )
            )
            if result.rowcount:
                released_files += 1
                released_bytes += int(size)
        if not released_files:
            db.rollback()
            return 0
        # Do not read-modify-write the singleton: concurrent reconcilers may
        # complete independent rows.  This conditional SQL decrement is atomic.
        db.execute(
            update(UploadCapacity)
            .where(UploadCapacity.id == 1)
            .values(
                reserved_bytes=case(
                    (UploadCapacity.reserved_bytes >= released_bytes, UploadCapacity.reserved_bytes - released_bytes),
                    else_=0,
                ),
            )
        )
        db.commit()
        return released_files
