#!/usr/bin/env python3
"""Celery task to translate extracted document text into the default target language.

This task is triggered after metadata extraction when the detected document
language differs from the user's (or system) default document language.  The
translated text is persisted in ``FileRecord.default_language_text`` so that
users can always read a reference copy in their preferred language.

Other ad-hoc translations are generated on the fly via the ``/api/files/{id}/translate``
endpoint and are NOT persisted.
"""

import hashlib
import json
import logging
import re
from typing import Any

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import FileRecord, UserProfile
from app.tasks.retry_config import ProviderTaskWithRetry
from app.utils import log_task_progress
from app.utils.ai_provider import get_ai_provider
from app.utils.provider_limits import ProviderQuotaExceeded
from app.services.translation_file_lock import TranslationFileBusy, translation_file_lock

logger = logging.getLogger(__name__)

TRANSLATION_CHECKPOINT_VERSION = "1"
TRANSLATION_CHUNK_MAX_CHARS = 12_000


def _split_translation_text(text: str, max_chars: int = TRANSLATION_CHUNK_MAX_CHARS) -> list[str]:
    """Split text losslessly, preferring paragraph/line/word boundaries."""
    if not text:
        return []
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    chunks: list[str] = []
    offset = 0
    while offset < len(text):
        end = min(offset + max_chars, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n\n", offset + 1, end + 1), text.rfind("\n", offset + 1, end + 1))
            if boundary <= offset:
                boundary = text.rfind(" ", offset + 1, end + 1)
            if boundary > offset:
                separator_length = 2 if text.startswith("\n\n", boundary) else 1
                end = min(boundary + separator_length, offset + max_chars)
        chunks.append(text[offset:end])
        offset = end
    assert "".join(chunks) == text
    return chunks


def _preserve_chunk_boundaries(source: str, translated: str) -> str:
    """Keep source whitespace at chunk edges when a provider trims it."""
    if not translated:
        return translated
    leading = re.match(r"\s*", source).group(0)
    trailing = re.search(r"\s*$", source).group(0)
    body = translated.strip()
    if not body:
        raise ValueError("AI provider returned an empty translation chunk")
    return leading + body + trailing


def _translation_fingerprint(text: str, source: str, target: str, provider: str, model: str) -> str:
    payload = "\x1f".join((TRANSLATION_CHECKPOINT_VERSION, source, target, provider, model, text))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _checkpoint_for(
    record: FileRecord, fingerprint: str, chunks: list[str], *, allow_reset: bool = True
) -> dict[str, Any]:
    try:
        current = json.loads(record.translation_checkpoint or "")
    except (TypeError, ValueError):
        current = None
    if (
        isinstance(current, dict)
        and current.get("fingerprint") == fingerprint
        and current.get("chunk_count") == len(chunks)
        and isinstance(current.get("translated_chunks"), list)
    ):
        return current
    if isinstance(current, dict) and current.get("fingerprint") and not allow_reset:
        raise RuntimeError("Translation checkpoint changed while translation was in progress")
    if (
        isinstance(current, dict)
        and current.get("fingerprint")
        and current.get("translated_chunks")
        and not current.get("completed")
    ):
        raise RuntimeError("A different translation is already in progress for this file")
    return {
        "version": TRANSLATION_CHECKPOINT_VERSION,
        "fingerprint": fingerprint,
        "chunk_count": len(chunks),
        "translated_chunks": [],
        "completed": False,
    }


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


@celery.task(base=ProviderTaskWithRetry, bind=True)
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

    if not extracted_text:
        log_task_progress(
            task_id,
            "translate_to_default_language",
            "skipped",
            "No extracted text to translate",
            file_id=file_id,
        )
        return {"status": "skipped", "reason": "empty_source_text"}

    lock_db = None
    lock_context = None
    lock_acquired = False
    try:
        model = settings.ai_model or settings.openai_model
        chunks = _split_translation_text(extracted_text)
        fingerprint = _translation_fingerprint(
            extracted_text, detected_language, target_language, settings.ai_provider, model
        )
        lock_db = SessionLocal()
        lock_context = translation_file_lock(lock_db, file_id)
        lock_context.__enter__()
        lock_acquired = True
        provider = get_ai_provider()
        with SessionLocal() as db:
            record = db.query(FileRecord).filter_by(id=file_id).with_for_update().first()
            if not record:
                raise RuntimeError(f"FileRecord {file_id} disappeared during translation")
            if record.ocr_text is not None and record.ocr_text != extracted_text:
                return {"status": "skipped", "reason": "source_changed"}
            checkpoint = _checkpoint_for(record, fingerprint, chunks)
            if (
                checkpoint.get("completed")
                and record.default_language_code == target_language
                and record.default_language_text
            ):
                log_task_progress(
                    task_id, "translate_to_default_language", "success", "Cached translation reused", file_id=file_id
                )
                return {
                    "status": "success",
                    "target_language": target_language,
                    "translated_length": len(record.default_language_text),
                }
            checkpoint["completed"] = False
            record.translation_checkpoint = json.dumps(checkpoint, ensure_ascii=False, separators=(",", ":"))
            db.commit()

        logger.info(f"[{task_id}] Translating document {file_id} from '{detected_language}' to '{target_language}'")
        log_task_progress(
            task_id,
            "translate_to_default_language",
            "in_progress",
            f"Translating from {detected_language} to {target_language}",
            file_id=file_id,
        )

        translated_chunks = list(checkpoint["translated_chunks"])
        if len(translated_chunks) > len(chunks):
            translated_chunks = []
        translated_chunks.extend([None] * (len(chunks) - len(translated_chunks)))
        for index, chunk in enumerate(chunks):
            if isinstance(translated_chunks[index], str) and translated_chunks[index]:
                continue
            translated_chunk = provider.chat_completion(
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
                    {"role": "user", "content": chunk},
                ],
                model=model,
                temperature=0.3,
            )
            if not isinstance(translated_chunk, str) or not translated_chunk:
                raise ValueError(f"AI provider returned empty translation chunk {index + 1}")
            translated_chunk = _preserve_chunk_boundaries(chunk, translated_chunk)
            translated_chunks[index] = translated_chunk
            with SessionLocal() as db:
                record = db.query(FileRecord).filter_by(id=file_id).with_for_update().first()
                if not record:
                    raise RuntimeError(f"FileRecord {file_id} disappeared during translation")
                current = _checkpoint_for(record, fingerprint, chunks, allow_reset=False)
                completed = list(current["translated_chunks"])
                completed.extend([None] * (len(chunks) - len(completed)))
                completed[index] = translated_chunk
                current["translated_chunks"] = completed
                record.translation_checkpoint = json.dumps(current, ensure_ascii=False, separators=(",", ":"))
                db.commit()

        translated_text = "".join(translated_chunks)

        # Persist the translation.
        with SessionLocal() as db:
            record = db.query(FileRecord).filter_by(id=file_id).with_for_update().first()
            if record:
                current = _checkpoint_for(record, fingerprint, chunks, allow_reset=False)
                completed = current.get("translated_chunks", [])
                if len(completed) != len(chunks) or any(
                    not isinstance(chunk, str) or not chunk for chunk in completed
                ):
                    raise RuntimeError("Translation checkpoint is incomplete")
                record.default_language_text = translated_text
                record.default_language_code = target_language
                record.detected_language = detected_language
                current["translated_chunks"] = []
                current["completed"] = True
                record.translation_checkpoint = json.dumps(current, ensure_ascii=False, separators=(",", ":"))
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
        if isinstance(exc, TranslationFileBusy):
            raise ProviderQuotaExceeded("Local translation capacity is busy", retry_after=30) from exc
        if isinstance(exc, ProviderQuotaExceeded):
            raise
        logger.exception(f"[{task_id}] Translation failed for file {file_id}: {exc}")
        log_task_progress(
            task_id,
            "translate_to_default_language",
            "failure",
            f"Exception: {exc}",
            file_id=file_id,
        )
        raise
    finally:
        if lock_acquired and lock_context is not None:
            lock_context.__exit__(None, None, None)
        if lock_db is not None:
            lock_db.close()
