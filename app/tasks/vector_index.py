"""Celery tasks for the optional chunk-level vector index."""

import logging
from typing import TYPE_CHECKING

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import DocumentIntake, DropboxImportObject, FileRecord
from app.tasks.retry_config import BaseTaskWithRetry

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _set_source_state(db: "Session", source_task_id: str | None, state: str, error: str | None = None) -> None:
    if not source_task_id:
        return
    intake = db.query(DocumentIntake).filter(DocumentIntake.task_id == source_task_id).first()
    if intake:
        intake.state = state
        intake.error = error
    imported = db.query(DropboxImportObject).filter(DropboxImportObject.task_id == source_task_id).first()
    if imported:
        imported.state = state


@celery.task(base=BaseTaskWithRetry, bind=True, name="index_document_vectors")
def index_document_vectors(self, file_id: int, source_task_id: str | None = None) -> dict:
    if not settings.vector_index_enabled:
        if source_task_id:
            with SessionLocal() as db:
                _set_source_state(db, source_task_id, "failed", "Vector index disabled")
                db.commit()
        return {"status": "skipped", "detail": "Vector index disabled"}

    with SessionLocal() as db:
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not file_record:
            _set_source_state(db, source_task_id, "failed", "File not found")
            db.commit()
            return {"status": "skipped", "detail": "File not found"}
        if not file_record.ocr_text or not file_record.ocr_text.strip():
            _set_source_state(db, source_task_id, "needs_ocr", "No OCR text available")
            db.commit()
            return {"status": "skipped", "detail": "No OCR text available"}

        from app.utils.vector_index import QdrantVectorIndex

        try:
            count = QdrantVectorIndex().index_document(file_record)
        except Exception as exc:
            _set_source_state(db, source_task_id, "failed", type(exc).__name__)
            db.commit()
            raise
        _set_source_state(db, source_task_id, "indexed")
        db.commit()
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
