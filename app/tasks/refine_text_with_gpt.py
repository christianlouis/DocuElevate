#!/usr/bin/env python3

import logging

# Import the shared Celery instance
from app.celery_app import celery
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import log_task_progress
from app.utils.ai_provider import get_ai_provider

logger = logging.getLogger(__name__)


@celery.task(base=BaseTaskWithRetry, bind=True)
def refine_text_with_gpt(self, filename: str, raw_text: str):
    """Uses the configured AI provider to clean and refine OCR text."""
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

        extract_metadata_with_gpt.delay(filename, cleaned_text)

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
