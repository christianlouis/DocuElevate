"""Celery task for pre-computing document text embeddings.

Runs after document processing to ensure embeddings are available for
the similarity feature without requiring a user to trigger them on first
access.
"""

import logging
from datetime import datetime, timezone

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import FileRecord
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import log_task_progress
from app.utils.step_manager import update_step_status

logger = logging.getLogger(__name__)


@celery.task(base=BaseTaskWithRetry, bind=True, name="compute_document_embedding")
def compute_document_embedding(self, file_id: int) -> dict:
    """Compute and cache the text embedding for a single document.

    Skips silently when the file has no OCR text or already has a cached
    embedding.  The result is stored in ``FileRecord.embedding`` for
    subsequent similarity queries.

    Args:
        file_id: Primary key of the :class:`~app.models.FileRecord`.

    Returns:
        A dict with ``status`` (``"success"`` / ``"skipped"`` / ``"error"``)
        and optional ``detail`` message.
    """
    task_id = self.request.id
    logger.info("[%s] Computing embedding for file %s", task_id, file_id)
    log_task_progress(
        task_id,
        "compute_embedding",
        "in_progress",
        f"Computing text embedding for file {file_id}",
        file_id=file_id,
    )

    with SessionLocal() as db:
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not file_record:
            logger.warning("[%s] File %s not found, skipping embedding", task_id, file_id)
            return {"status": "skipped", "detail": "File not found"}

        now = datetime.now(timezone.utc)
        update_step_status(db, file_id, "compute_embedding", "in_progress", started_at=now)

        # Already has a cached embedding – nothing to do
        if file_record.embedding:
            logger.info("[%s] File %s already has a cached embedding", task_id, file_id)
            log_task_progress(
                task_id,
                "compute_embedding",
                "success",
                "Embedding already cached",
                file_id=file_id,
            )
            update_step_status(db, file_id, "compute_embedding", "success", completed_at=now)
            return {"status": "skipped", "detail": "Embedding already cached"}

        if not file_record.ocr_text or not file_record.ocr_text.strip():
            logger.info("[%s] File %s has no OCR text, skipping embedding", task_id, file_id)
            log_task_progress(
                task_id,
                "compute_embedding",
                "skipped",
                "No OCR text available",
                file_id=file_id,
            )
            update_step_status(db, file_id, "compute_embedding", "skipped", completed_at=now)
            return {"status": "skipped", "detail": "No OCR text available"}

        try:
            from app.utils.similarity import compute_and_store_embedding

            embedding = compute_and_store_embedding(db, file_record)
            completed = datetime.now(timezone.utc)
            if embedding:
                log_task_progress(
                    task_id,
                    "compute_embedding",
                    "success",
                    f"Embedding computed ({len(embedding)} dimensions)",
                    file_id=file_id,
                )
                update_step_status(db, file_id, "compute_embedding", "success", completed_at=completed)
                return {
                    "status": "success",
                    "detail": f"Embedding computed ({len(embedding)} dimensions)",
                }
            else:
                log_task_progress(
                    task_id,
                    "compute_embedding",
                    "failure",
                    "Embedding computation returned None",
                    file_id=file_id,
                )
                update_step_status(
                    db,
                    file_id,
                    "compute_embedding",
                    "failure",
                    error_message="Embedding computation returned None",
                    completed_at=completed,
                )
                return {"status": "error", "detail": "Embedding computation returned None"}
        except Exception as exc:
            logger.exception("[%s] Embedding computation failed for file %s: %s", task_id, file_id, exc)
            log_task_progress(
                task_id,
                "compute_embedding",
                "failure",
                f"Exception: {exc}",
                file_id=file_id,
            )
            update_step_status(
                db,
                file_id,
                "compute_embedding",
                "failure",
                error_message=str(exc),
                completed_at=datetime.now(timezone.utc),
            )
            return {"status": "error", "detail": str(exc)}


@celery.task(bind=True, name="backfill_missing_embeddings")
def backfill_missing_embeddings(self) -> dict:
    """Periodic task that computes embeddings for documents that lack them.

    Iterates over all ``FileRecord`` rows that have OCR text but no
    cached embedding and queues a :func:`compute_document_embedding`
    task for each one.  A configurable ``batch_size`` caps the number
    of tasks queued per run to avoid overwhelming the worker or the
    embedding API.

    Returns:
        A dict with the number of tasks ``queued``.
    """
    batch_size = settings.embedding_backfill_batch_size
    task_id = self.request.id
    logger.info("[%s] Backfill: scanning for files missing embeddings (batch_size=%d)", task_id, batch_size)

    with SessionLocal() as db:
        candidates = (
            db.query(FileRecord.id)
            .filter(
                FileRecord.ocr_text.isnot(None),
                FileRecord.ocr_text != "",
                (FileRecord.embedding.is_(None)) | (FileRecord.embedding == ""),
            )
            .limit(batch_size)
            .all()
        )

    queued = 0
    for (file_id,) in candidates:
        try:
            compute_document_embedding.delay(file_id)
            queued += 1
        except Exception as exc:
            logger.warning("[%s] Could not queue embedding for file %s: %s", task_id, file_id, exc)

    logger.info("[%s] Backfill: queued %d embedding tasks", task_id, queued)
    return {"queued": queued}
