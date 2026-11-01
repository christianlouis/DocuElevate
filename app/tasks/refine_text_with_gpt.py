#!/usr/bin/env python3

import logging

# Import the shared Celery instance
from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import FileRecord
from app.services.account_deletion import DeletionBlocked, assert_account_active
from app.services.account_lifecycle_lock import account_lifecycle_lock
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import log_task_progress
from app.utils.ai_provider import get_ai_provider

logger = logging.getLogger(__name__)


@celery.task(base=BaseTaskWithRetry, bind=True)
def refine_text_with_gpt(self, filename: str, raw_text: str, file_id: int | None = None):
    """Refine a current file while coordinating with account deletion."""
    with SessionLocal() as db:
        query = db.query(FileRecord)
        if file_id is not None:
            matches = query.filter(FileRecord.id == file_id).all()
        else:
            matches = query.filter(FileRecord.local_filename == filename).limit(2).all()
        if len(matches) != 1:
            if not settings.multi_user_enabled and file_id is None and not matches:
                return _refine(self, filename, raw_text, None)
            return {"status": "skipped", "reason": "file_not_found_or_ambiguous"}
        record = matches[0]
        owner = record.owner_id
        resolved_id = record.id
        if not owner:
            if settings.multi_user_enabled:
                return {"status": "skipped", "reason": "owner_unavailable"}
            return _refine(self, filename, raw_text, resolved_id)
        with account_lifecycle_lock(db, owner, exclusive=False):
            db.expire_all()
            try:
                assert_account_active(db, owner)
            except DeletionBlocked:
                return {"status": "skipped", "reason": "account_deletion"}
            record = db.query(FileRecord).filter(FileRecord.id == resolved_id, FileRecord.owner_id == owner).first()
            if not record:
                return {"status": "skipped", "reason": "file_not_found"}
            return _refine(self, filename, raw_text, resolved_id)


def _refine(self, filename: str, raw_text: str, file_id: int | None):
    """Call the AI provider and queue metadata extraction."""
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting OCR text refinement for: {filename}")
    log_task_progress(task_id, "refine_text_with_gpt", "in_progress", f"Refining OCR text for {filename}")

    try:
        log_task_progress(task_id, "call_ai_provider", "in_progress", "Calling AI provider for text refinement")

        provider = get_ai_provider()
        model = settings.ai_model or settings.openai_model
        cleaned_text = provider.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Clean and format the following text. The idea is that the text you see comes from an OCR "
                        "system and your task is to eliminate OCR errors. Keep the original language when doing so."
                    ),
                },
                {"role": "user", "content": raw_text},
            ],
            model=model,
        )

        logger.info(f"[{task_id}] Text refinement complete for {filename}: {len(cleaned_text)} characters")
        log_task_progress(
            task_id,
            "call_ai_provider",
            "success",
            "Received refined text from AI provider",
            detail=f"Input: {len(raw_text)} chars → Output: {len(cleaned_text)} chars",
        )

        # Trigger next task (import locally if needed to avoid circular imports)
        from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt

        if file_id is None:
            extract_metadata_with_gpt.delay(filename, cleaned_text)
        else:
            extract_metadata_with_gpt.delay(filename, cleaned_text, file_id=file_id)

        logger.info(f"[{task_id}] Queueing metadata extraction for {filename}")
        log_task_progress(task_id, "refine_text_with_gpt", "success", "Text refined, queuing metadata extraction")

        return {"filename": filename, "cleaned_text": cleaned_text}
    except Exception as e:
        logger.exception(f"[{task_id}] Text refinement failed for {filename}: {e}")
        log_task_progress(
            task_id,
            "refine_text_with_gpt",
            "failure",
            f"Exception: {str(e)}",
            detail=f"Text refinement failed for {filename}.\nException: {str(e)}",
        )
        raise
