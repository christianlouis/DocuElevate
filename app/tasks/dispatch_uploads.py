"""Outbox dispatcher for accepted bulk uploads."""
from __future__ import annotations

import logging

from app.celery_app import celery
from app.database import SessionLocal
from app.models import UploadItem, UploadOutbox
from app.tasks.convert_to_pdf import convert_to_pdf
from app.tasks.process_document import process_document

logger = logging.getLogger(__name__)


@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def dispatch_upload_item(self, outbox_id: int) -> dict[str, object]:
    with SessionLocal() as db:
        outbox = db.query(UploadOutbox).filter(UploadOutbox.id == outbox_id).one_or_none()
        if outbox is None or outbox.dispatched_at is not None:
            return {"status": "already_dispatched"}
        item = db.query(UploadItem).filter(UploadItem.id == outbox.item_id).one_or_none()
        if item is None or item.file_id is None:
            return {"status": "missing_item"}
        from app.models import FileRecord

        record = db.query(FileRecord).filter(FileRecord.id == item.file_id).one()
        owner_id = record.owner_id
        outbox.attempts += 1
        db.commit()
        extension = record.original_filename.rsplit(".", 1)[-1].lower() if "." in record.original_filename else ""
        try:
            if record.mime_type == "application/pdf" or extension == "pdf":
                task = process_document.delay(record.original_file_path or record.local_filename, original_filename=record.original_filename, file_id=record.id, owner_id=owner_id)
            else:
                task = convert_to_pdf.delay(record.original_file_path or record.local_filename, original_filename=record.original_filename, file_id=record.id, owner_id=owner_id)
        except Exception as exc:
            with SessionLocal() as retry_db:
                failed = retry_db.query(UploadOutbox).filter(UploadOutbox.id == outbox_id).one_or_none()
                if failed:
                    failed.last_error = str(exc)[:1000]
                    retry_db.commit()
            raise
        with SessionLocal() as done_db:
            done = done_db.query(UploadOutbox).filter(UploadOutbox.id == outbox_id).one()
            done.dispatched_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            done_db.query(UploadItem).filter(UploadItem.id == item.id).update({"state": "queued"})
            done_db.commit()
        return {"status": "queued", "file_id": item.file_id, "task_id": task.id}


@celery.task
def dispatch_upload_outbox(limit: int = 50) -> int:
    """Drain a bounded number; old bulk items age naturally by created_at."""
    with SessionLocal() as db:
        ids = [row.id for row in db.query(UploadOutbox).filter(UploadOutbox.dispatched_at.is_(None)).order_by(UploadOutbox.created_at.asc()).limit(limit).all()]
    for outbox_id in ids:
        dispatch_upload_item.delay(outbox_id)
    return len(ids)
