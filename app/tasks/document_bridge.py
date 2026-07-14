"""Retryable outbound document bridge task."""

import logging
import os

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import FileRecord
from app.tasks.retry_config import UploadTaskWithRetry

logger = logging.getLogger(__name__)


@celery.task(base=UploadTaskWithRetry, bind=True, name="deliver_document_bridge")
def deliver_document_bridge(self, file_id: int) -> dict:
    if not settings.document_bridge_enabled:
        return {"status": "skipped", "detail": "Document bridge disabled"}

    with SessionLocal() as db:
        record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not record:
            return {"status": "skipped", "detail": "File not found"}
        candidates = [record.processed_file_path, record.original_file_path, record.local_filename]
        file_path = next((path for path in candidates if path and os.path.isfile(path)), None)
        if not file_path:
            raise FileNotFoundError(f"No bridge source file exists for document {file_id}")

        from app.utils.document_bridge import deliver_document

        status_code = deliver_document(record, file_path)
        logger.info("Document %s delivered through bridge (HTTP %s)", file_id, status_code)
        return {"status": "success", "file_id": file_id, "response_status": status_code}
