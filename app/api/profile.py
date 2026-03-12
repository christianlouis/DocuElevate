"""User self-service profile API.

Provides endpoints for the authenticated user to view and update their own
profile settings without requiring admin access.

Routes:
  GET    /api/profile          — read current user's profile
  PATCH  /api/profile          — update display name, language, theme
  POST   /api/profile/avatar   — upload a new profile picture (JPEG/PNG/GIF/WebP, max 2 MB)
  DELETE /api/profile/avatar   — remove custom avatar (reverts to Gravatar)
  POST   /api/profile/change-password — change password (local-auth users only)
"""

from __future__ import annotations

import base64
import logging
from hashlib import md5
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import LocalUser, UserProfile
from app.utils.i18n import SUPPORTED_LANGUAGE_CODES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])

DbSession = Annotated[Session, Depends(get_db)]

# Maximum avatar upload size: 2 MB
_MAX_AVATAR_BYTES = 2 * 1024 * 1024

# Allowed MIME types for avatar uploads
_ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# Valid theme values
_VALID_THEMES = {"light", "dark", "system"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_user_id(request: Request) -> str:
    """Return the stable user identifier from the session.

    Raises HTTP 401 if no user is logged in.
    """
    user = request.session.get("user")
    if not user or not isinstance(user, dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    uid = user.get("sub") or user.get("preferred_username") or user.get("email") or user.get("id")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cannot determine user identity")
    return uid


def _gravatar_url(email: str | None) -> str:
    """Generate a Gravatar URL for *email*, falling back to identicon."""
    if not email:
        return "https://www.gravatar.com/avatar/?d=identicon"
    # MD5 used for Gravatar URL generation only — not for security
    h = md5(email.strip().lower().encode(), usedforsecurity=False).hexdigest()
    return f"https://www.gravatar.com/avatar/{h}?d=identicon"


def _get_or_create_profile(db: Session, user_id: str) -> UserProfile:
    """Return the UserProfile for *user_id*, creating a stub if one doesn't exist."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        try:
            db.commit()
            db.refresh(profile)
        except Exception:
            db.rollback()
            raise
    return profile


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ProfileResponse(BaseModel):
    """Response body for GET /api/profile."""

    user_id: str
    display_name: str | None
    contact_email: str | None
    preferred_language: str | None
    preferred_theme: str | None
    avatar_url: str
    """Gravatar URL or ``data:`` URI for a custom uploaded avatar."""
    is_local_user: bool
    """True when the account was created via local email/password sign-up."""


class ProfileUpdateRequest(BaseModel):
    """Request body for PATCH /api/profile."""

    display_name: str | None = Field(default=None, max_length=255, description="Human-readable display name")
    contact_email: str | None = Field(default=None, max_length=255, description="Contact / notification e-mail")
    preferred_language: str | None = Field(default=None, description="ISO 639-1 language code, e.g. 'en', 'de'")
    preferred_theme: str | None = Field(default=None, description="Colour scheme: 'light', 'dark', or 'system'")


class ChangePasswordRequest(BaseModel):
    """Request body for POST /api/profile/change-password."""

    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)
    new_password_confirm: str = Field(..., min_length=8, max_length=128)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ProfileResponse)
@require_login
async def get_profile(request: Request, db: DbSession) -> ProfileResponse:
    """Return the current user's profile settings."""
    user_id = _get_user_id(request)
    profile = _get_or_create_profile(db, user_id)

    session_user = request.session.get("user", {})
    email = session_user.get("email") if isinstance(session_user, dict) else None

    # Determine avatar: prefer stored data, fall back to Gravatar
    avatar_url = profile.avatar_data if profile.avatar_data else _gravatar_url(email)  # type: ignore[attr-defined]

    # Check whether this is a local (email/password) account
    is_local = db.query(LocalUser).filter(LocalUser.username == user_id).first() is not None

    return ProfileResponse(
        user_id=user_id,
        display_name=profile.display_name,  # type: ignore[arg-type]
        contact_email=profile.contact_email,  # type: ignore[arg-type]
        preferred_language=profile.preferred_language,  # type: ignore[arg-type]
        preferred_theme=profile.preferred_theme,  # type: ignore[arg-type]
        avatar_url=avatar_url,
        is_local_user=is_local,
    )


@router.patch("", response_model=ProfileResponse)
@require_login
async def update_profile(body: ProfileUpdateRequest, request: Request, db: DbSession) -> ProfileResponse:
    """Update the current user's editable profile settings."""
    user_id = _get_user_id(request)
    profile = _get_or_create_profile(db, user_id)

    # Validate language code
    if body.preferred_language is not None:
        lang = body.preferred_language.lower().strip()
        if lang and lang not in SUPPORTED_LANGUAGE_CODES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported language code: {lang}",
            )
        profile.preferred_language = lang or None  # type: ignore[assignment]

    # Validate theme
    if body.preferred_theme is not None:
        theme = body.preferred_theme.lower().strip()
        if theme and theme not in _VALID_THEMES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid theme: {theme}. Must be one of: {', '.join(sorted(_VALID_THEMES))}",
            )
        profile.preferred_theme = theme or None  # type: ignore[assignment]

    if body.display_name is not None:
        profile.display_name = body.display_name.strip() or None  # type: ignore[assignment]

    if body.contact_email is not None:
        profile.contact_email = body.contact_email.strip() or None  # type: ignore[assignment]

    try:
        db.commit()
        db.refresh(profile)
    except Exception:
        db.rollback()
        raise

    session_user = request.session.get("user", {})
    email = session_user.get("email") if isinstance(session_user, dict) else None
    avatar_url = profile.avatar_data if profile.avatar_data else _gravatar_url(email)  # type: ignore[attr-defined]
    is_local = db.query(LocalUser).filter(LocalUser.username == user_id).first() is not None

    return ProfileResponse(
        user_id=user_id,
        display_name=profile.display_name,  # type: ignore[arg-type]
        contact_email=profile.contact_email,  # type: ignore[arg-type]
        preferred_language=profile.preferred_language,  # type: ignore[arg-type]
        preferred_theme=profile.preferred_theme,  # type: ignore[arg-type]
        avatar_url=avatar_url,
        is_local_user=is_local,
    )


@router.post("/avatar", status_code=status.HTTP_200_OK)
@require_login
async def upload_avatar(
    request: Request,
    db: DbSession,
    file: UploadFile = File(..., description="Profile picture (JPEG, PNG, GIF or WebP; max 2 MB)"),
) -> dict:
    """Upload a new profile picture.

    The image is stored as a base64-encoded data URL in ``UserProfile.avatar_data``.
    Accepts JPEG, PNG, GIF, or WebP files up to 2 MB.
    """
    user_id = _get_user_id(request)

    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_AVATAR_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type '{content_type}'. Allowed: JPEG, PNG, GIF, WebP.",
        )

    # Check declared size first (available when the client sends a Content-Length header)
    if file.size is not None and file.size > _MAX_AVATAR_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Avatar image must be 2 MB or smaller.",
        )

    # Read up to one byte past the limit so we can detect oversized uploads
    raw = await file.read(_MAX_AVATAR_BYTES + 1)
    if len(raw) > _MAX_AVATAR_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Avatar image must be 2 MB or smaller.",
        )

    b64 = base64.b64encode(raw).decode("ascii")
    data_url = f"data:{content_type};base64,{b64}"

    profile = _get_or_create_profile(db, user_id)
    profile.avatar_data = data_url  # type: ignore[assignment]
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"avatar_url": data_url}


@router.delete("/avatar", status_code=status.HTTP_200_OK)
@require_login
async def delete_avatar(request: Request, db: DbSession) -> dict:
    """Remove the custom avatar and revert to the Gravatar fallback."""
    user_id = _get_user_id(request)
    profile = _get_or_create_profile(db, user_id)
    profile.avatar_data = None  # type: ignore[assignment]
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    session_user = request.session.get("user", {})
    email = session_user.get("email") if isinstance(session_user, dict) else None
    return {"avatar_url": _gravatar_url(email)}


@router.post("/change-password", status_code=status.HTTP_200_OK)
@require_login
async def change_password(body: ChangePasswordRequest, request: Request, db: DbSession) -> dict:
    """Change the password for local (email/password) accounts.

    Raises 403 if the account is not a local account or the current password is wrong.
    Raises 422 if the new passwords do not match.
    """
    from app.utils.local_auth import hash_password, verify_password

    user_id = _get_user_id(request)

    local_user = db.query(LocalUser).filter(LocalUser.username == user_id).first()
    if local_user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change is only available for local accounts.",
        )

    if not verify_password(body.current_password, local_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Current password is incorrect.",
        )

    if body.new_password != body.new_password_confirm:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New passwords do not match.",
        )

    local_user.hashed_password = hash_password(body.new_password)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("Password changed for local user: %s", user_id)
    return {"detail": "Password changed successfully."}
