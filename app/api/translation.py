"""
API endpoints for document translation.

Provides on-the-fly translation via the AI provider and access to the
persisted default-language translation.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_login
from app.config import settings
from app.database import get_db
from app.models import FileRecord
from app.utils.ai_provider import get_ai_provider
from app.utils.user_scope import apply_owner_filter, get_current_owner_id

logger = logging.getLogger(__name__)

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]

# Maximum characters sent to the AI provider for a single translation request.
_MAX_TRANSLATION_INPUT = 50_000


def _get_file_or_404(db: Session, file_id: int, request: Request) -> FileRecord:
    """Fetch a FileRecord visible to the current user or raise 404."""
    query = db.query(FileRecord).filter(FileRecord.id == file_id)
    owner_id = get_current_owner_id(request, db)
    if owner_id:
        query = apply_owner_filter(query, owner_id, FileRecord)
    record = query.first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return record


@router.get("/files/{file_id}/translation/default")
@require_login
def get_default_translation(
    request: Request,
    file_id: int,
    db: DbSession,
) -> JSONResponse:
    """Return the persisted default-language translation for a document.

    Returns 404 if no default-language translation has been generated yet
    (e.g. because the document is already in the default language).
    """
    record = _get_file_or_404(db, file_id, request)

    if not record.default_language_text:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No default-language translation available for this file",
        )

    return JSONResponse(
        content={
            "file_id": record.id,
            "detected_language": record.detected_language,
            "default_language_code": record.default_language_code,
            "text": record.default_language_text,
        }
    )


@router.get("/files/{file_id}/translate")
@require_login
def translate_on_the_fly(
    request: Request,
    file_id: int,
    db: DbSession,
    lang: str = Query(..., min_length=2, max_length=10, description="Target language ISO 639-1 code"),
) -> JSONResponse:
    """Translate a document's extracted text into an arbitrary language on the fly.

    The translation is generated via the configured AI provider and is **not**
    persisted.  For the default-language translation, use the
    ``/files/{file_id}/translation/default`` endpoint instead.
    """
    record = _get_file_or_404(db, file_id, request)

    source_text = record.ocr_text
    if not source_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No extracted text available for this file — translation requires OCR text",
        )

    # If the requested language matches what is already stored, return it directly.
    if record.default_language_code and lang == record.default_language_code and record.default_language_text:
        return JSONResponse(
            content={
                "file_id": record.id,
                "source_language": record.detected_language,
                "target_language": lang,
                "text": record.default_language_text,
                "cached": True,
            }
        )

    # If the detected language already matches, return the original text.
    detected = record.detected_language
    if detected and detected == lang:
        return JSONResponse(
            content={
                "file_id": record.id,
                "source_language": detected,
                "target_language": lang,
                "text": source_text,
                "cached": True,
            }
        )

    # Truncate to keep AI costs bounded.
    text_to_translate = source_text[:_MAX_TRANSLATION_INPUT]

    try:
        provider = get_ai_provider()
        model = settings.ai_model or settings.openai_model
        translated = provider.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a professional translator. Translate the following text "
                        f"into {lang}. Preserve the original formatting, paragraph structure, "
                        f"and meaning. Do not add any commentary — output ONLY the translated text."
                    ),
                },
                {"role": "user", "content": text_to_translate},
            ],
            model=model,
            temperature=0.3,
        )
    except Exception as exc:
        logger.exception(f"On-the-fly translation failed for file {file_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Translation failed — the AI provider returned an error",
        )

    return JSONResponse(
        content={
            "file_id": record.id,
            "source_language": detected or "unknown",
            "target_language": lang,
            "text": translated,
            "cached": False,
        }
    )
