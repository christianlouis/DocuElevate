"""API endpoints for internationalization (i18n).

Provides endpoints for:
* Listing available languages
* Getting/setting user language preference (persisted in session + cookie + DB)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UserProfile
from app.utils.i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGE_CODES,
    SUPPORTED_LANGUAGES,
    detect_language,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/i18n", tags=["i18n"])


class LanguageInfo(BaseModel):
    """Schema for a supported language."""

    code: str
    name: str
    native: str
    flag: str


class LanguageListResponse(BaseModel):
    """Response for the list-languages endpoint."""

    languages: list[LanguageInfo]
    current: str
    default: str


class SetLanguageRequest(BaseModel):
    """Request body for setting the preferred language."""

    language: str


class SetLanguageResponse(BaseModel):
    """Response after changing the language."""

    language: str
    message: str


@router.get("/languages", response_model=LanguageListResponse)
async def list_languages(request: Request) -> LanguageListResponse:
    """Return all supported UI languages and the current active language."""
    current = detect_language(request)
    return LanguageListResponse(
        languages=[LanguageInfo(**lang) for lang in SUPPORTED_LANGUAGES],
        current=current,
        default=DEFAULT_LANGUAGE,
    )


@router.post("/language", response_model=SetLanguageResponse)
async def set_language(
    body: SetLanguageRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> SetLanguageResponse:
    """Set the preferred UI language.

    Persists the choice in:
    1. The server-side session
    2. A ``docuelevate_lang`` cookie (30-day expiry)
    3. The ``UserProfile.preferred_language`` column (if authenticated)
    """
    lang = body.language.lower().strip()
    if lang not in SUPPORTED_LANGUAGE_CODES:
        lang = DEFAULT_LANGUAGE

    # 1. Session
    if hasattr(request, "session"):
        request.session["preferred_language"] = lang

    # 2. Cookie (30 days)
    response.set_cookie(
        key="docuelevate_lang",
        value=lang,
        max_age=30 * 24 * 60 * 60,
        httponly=False,
        samesite="lax",
    )

    # 3. Database (if user is authenticated)
    _persist_language_to_profile(request, db, lang)

    language_name = next(
        (entry["native"] for entry in SUPPORTED_LANGUAGES if entry["code"] == lang),
        lang,
    )
    logger.info("Language preference set to '%s'", lang)
    return SetLanguageResponse(
        language=lang,
        message=f"Language changed to {language_name}",
    )


def _persist_language_to_profile(request: Request, db: Session, lang: str) -> None:
    """Write language preference to the UserProfile row, if the user is logged in."""
    user_id: str | None = None
    if hasattr(request, "session"):
        user = request.session.get("user")
        if isinstance(user, dict):
            user_id = user.get("preferred_username") or user.get("email") or user.get("id")
        elif isinstance(user, str):
            user_id = user

    if not user_id:
        return

    try:
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if profile:
            profile.preferred_language = lang  # type: ignore[attr-defined]
            db.commit()
    except Exception:
        db.rollback()
        logger.debug("Could not persist language preference for user_id=%s", user_id)
