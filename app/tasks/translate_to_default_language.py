#!/usr/bin/env python3
"""Celery task to translate extracted document text into the default target language.

This task is triggered after metadata extraction when the detected document
language differs from the user's (or system) default document language.  The
translated text is persisted in ``FileRecord.default_language_text`` so that
users can always read a reference copy in their preferred language.

Other ad-hoc translations are generated on the fly via the ``/api/files/{id}/translate``
endpoint and are NOT persisted.
"""

import logging

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import FileRecord, UserProfile
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import log_task_progress
from app.utils.ai_provider import get_ai_provider

logger = logging.getLogger(__name__)


def _resolve_default_language(owner_id: str | None) -> str:
    """Return the default document language for the given owner.

    Resolution order:
    1. ``UserProfile.default_document_language`` (per-user override)
    2. ``settings.default_document_language`` (global setting)
    """
    if owner_id:
        with SessionLocal() as db:
            profile = db.query(UserProfile).filter_by(user_id=owner_id).first()
            if profile and profile.default_document_language:
                return profile.default_document_language
    return settings.default_document_language


@celery.task(base=BaseTaskWithRetry, bind=True)
def translate_to_default_language(
    self,
    file_id: int,
    extracted_text: str,
    detected_language: str,
    owner_id: str | None = None,
) -> dict:
    """Translate *extracted_text* into the default document language and persist the result.

    Args:
        file_id: Primary key of the :class:`FileRecord`.
        extracted_text: The OCR / refined text in the document's original language.
        detected_language: ISO 639-1 code of the document's detected language.
        owner_id: Owner identifier used to resolve per-user language preference.

    Returns:
        A dict with ``status``, ``target_language``, and the translated text length.
    """
    task_id = self.request.id
    target_language = _resolve_default_language(owner_id)

    # Nothing to do when the document is already in the target language.
    if detected_language == target_language:
        logger.info(
            f"[{task_id}] Document {file_id} already in target language '{target_language}', skipping translation"
        )
        log_task_progress(
            task_id,
            "translate_to_default_language",
            "skipped",
            f"Document already in {target_language}",
            file_id=file_id,
        )
        return {"status": "skipped", "reason": "already_in_target_language"}

    logger.info(f"[{task_id}] Translating document {file_id} from '{detected_language}' to '{target_language}'")
    log_task_progress(
        task_id,
        "translate_to_default_language",
        "in_progress",
        f"Translating from {detected_language} to {target_language}",
        file_id=file_id,
    )

    try:
        provider = get_ai_provider()
        model = settings.ai_model or settings.openai_model
        translated_text = provider.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a professional translator. Translate the following text "
                        f"from {detected_language} to {target_language}. "
                        f"Preserve the original formatting, paragraph structure, and meaning. "
                        f"Do not add any commentary or explanation — output ONLY the translated text."
                    ),
                },
                {"role": "user", "content": extracted_text},
            ],
            model=model,
            temperature=0.3,
        )

        # Persist the translation.
        with SessionLocal() as db:
            record = db.query(FileRecord).filter_by(id=file_id).first()
            if record:
                record.default_language_text = translated_text
                record.default_language_code = target_language
                record.detected_language = detected_language
                db.commit()
                logger.info(
                    f"[{task_id}] Stored default-language translation ({len(translated_text)} chars) for file {file_id}"
                )

        log_task_progress(
            task_id,
            "translate_to_default_language",
            "success",
            f"Translated {len(extracted_text)} → {len(translated_text)} chars ({detected_language} → {target_language})",
            file_id=file_id,
        )

        return {
            "status": "success",
            "target_language": target_language,
            "translated_length": len(translated_text),
        }

    except Exception as exc:
        logger.exception(f"[{task_id}] Translation failed for file {file_id}: {exc}")
        log_task_progress(
            task_id,
            "translate_to_default_language",
            "failure",
            f"Exception: {exc}",
            file_id=file_id,
        )
        raise
