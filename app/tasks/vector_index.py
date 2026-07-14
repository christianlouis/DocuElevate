"""Celery tasks for the optional chunk-level vector index."""

import logging

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import FileRecord
from app.tasks.retry_config import BaseTaskWithRetry

logger = logging.getLogger(__name__)


@celery.task(base=BaseTaskWithRetry, bind=True, name="index_document_vectors")
def index_document_vectors(self, file_id: int) -> dict:
    if not settings.vector_index_enabled:
        return {"status": "skipped", "detail": "Vector index disabled"}

    with SessionLocal() as db:
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not file_record:
            return {"status": "skipped", "detail": "File not found"}
        if not file_record.ocr_text or not file_record.ocr_text.strip():
            return {"status": "skipped", "detail": "No OCR text available"}

        from app.utils.vector_index import QdrantVectorIndex

        count = QdrantVectorIndex().index_document(file_record)
        logger.info("Indexed %d vector chunks for file %s", count, file_id)
        return {"status": "success", "file_id": file_id, "chunks_indexed": count}


@celery.task(bind=True, name="reindex_document_vectors")
def reindex_document_vectors(self, limit: int | None = None) -> dict:
    """Queue an idempotent index refresh for every OCR-backed document."""
    if not settings.vector_index_enabled:
        return {"status": "skipped", "detail": "Vector index disabled", "queued": 0}

    with SessionLocal() as db:
        query = (
            db.query(FileRecord.id)
            .filter(FileRecord.ocr_text.isnot(None), FileRecord.ocr_text != "")
            .order_by(FileRecord.id)
        )
        if limit is not None:
            query = query.limit(limit)
        file_ids = [row[0] for row in query.all()]

    for file_id in file_ids:
        index_document_vectors.delay(file_id)
    return {"status": "success", "queued": len(file_ids)}
