"""API endpoints for document sharing via expiring links.

Authenticated users can create time-limited or view-limited shareable
links for their documents.  Each link has a cryptographically random
token that forms a public ``/share/<token>`` URL.  Optional password
protection is supported; only a PBKDF2-HMAC-SHA256 hash is stored.

Public consumers access files through the ``/share/<token>/download``
and ``/share/<token>/info`` endpoints — no authentication required.
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FileRecord, SharedLink
from app.utils.user_scope import apply_owner_filter, get_current_owner_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shared-links", tags=["shared-links"])
public_router = APIRouter(tags=["shared-links-public"])

DbSession = Annotated[Session, Depends(get_db)]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: PBKDF2 salt for shared-link password hashing (not secret, but fixed).
_PWD_HASH_SALT = b"shared-link-v1"
#: PBKDF2 iteration count.
_PWD_HASH_ITERATIONS = 100_000

# Valid expiry durations (in hours) presented in the UI.
EXPIRY_OPTIONS: dict[str, int] = {
    "1h": 1,
    "6h": 6,
    "12h": 12,
    "24h": 24,
    "3d": 72,
    "7d": 168,
    "14d": 336,
    "30d": 720,
}


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _get_owner_id(request: Request) -> str:
    """Return the current user's owner ID, raising 401 if unauthenticated."""
    owner_id = get_current_owner_id(request)
    if not owner_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return owner_id


CurrentOwner = Annotated[str, Depends(_get_owner_id)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_token() -> str:
    """Generate a 43-character URL-safe random token."""
    return secrets.token_urlsafe(32)


def _hash_password(password: str) -> str:
    """Return a PBKDF2-HMAC-SHA256 hex digest of *password*.

    Args:
        password: Plaintext password string.

    Returns:
        128-character lowercase hex string.
    """
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        _PWD_HASH_SALT,
        _PWD_HASH_ITERATIONS,
    )
    return dk.hex()


def _verify_password(password: str, stored_hash: str) -> bool:
    """Check *password* against *stored_hash* using constant-time comparison."""
    return secrets.compare_digest(_hash_password(password), stored_hash)


def _is_link_valid(link: SharedLink) -> bool:
    """Return True when *link* is active, unexpired, and within view limit."""
    if not link.is_active:
        return False
    now = datetime.now(timezone.utc)
    if link.expires_at is not None:
        exp = link.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now > exp:
            return False
    if link.max_views is not None and link.view_count >= link.max_views:
        return False
    return True


def _resolve_file_path(file_record: FileRecord) -> str | None:
    """Return the best available file path for *file_record*.

    Checks processed path first, then original, then local (tmp) path.
    Returns ``None`` when no file exists on disk.
    """
    from app.config import settings

    workdir = os.path.realpath(settings.workdir)
    candidates = [
        file_record.processed_file_path,
        file_record.original_file_path,
        file_record.local_filename,
    ]
    for path in candidates:
        if not path:
            continue
        # Guard against path traversal in DB values.
        real = os.path.realpath(path)
        if not real.startswith(workdir + os.sep) and real != workdir:
            logger.warning("Shared link file path outside workdir rejected: %s", path)
            continue
        if os.path.exists(real):
            return real
    return None


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class SharedLinkCreate(BaseModel):
    """Schema for creating a new shared link."""

    file_id: int = Field(..., description="ID of the file to share")
    expires_in_hours: int | None = Field(
        None,
        ge=1,
        le=720,
        description="Expiry in hours (1–720). NULL means the link never expires.",
    )
    max_views: int | None = Field(
        None,
        ge=1,
        le=10_000,
        description="Maximum number of downloads/views. NULL means unlimited.",
    )
    password: str | None = Field(
        None,
        min_length=1,
        max_length=128,
        description="Optional password protecting the link.",
    )
    label: str | None = Field(
        None,
        max_length=255,
        description="Optional human-readable label for the link.",
    )

    @field_validator("expires_in_hours")
    @classmethod
    def validate_expiry(cls, v: int | None) -> int | None:
        if v is not None and v not in range(1, 721):
            raise ValueError("expires_in_hours must be between 1 and 720")
        return v


class SharedLinkResponse(BaseModel):
    """Shared link info returned to the authenticated owner."""

    id: int
    token: str
    file_id: int
    label: str | None
    expires_at: datetime | None
    max_views: int | None
    view_count: int
    has_password: bool
    is_active: bool
    created_at: datetime | None
    revoked_at: datetime | None
    # Filled in by the endpoint, not stored in DB.
    share_url: str = ""
    original_filename: str | None = None

    model_config = {"from_attributes": True}


class SharedLinkInfoResponse(BaseModel):
    """Public metadata about a shared link (used on the share landing page)."""

    token: str
    label: str | None
    original_filename: str | None
    expires_at: datetime | None
    max_views: int | None
    view_count: int
    has_password: bool
    is_valid: bool


# ---------------------------------------------------------------------------
# Private (authenticated) endpoints
# ---------------------------------------------------------------------------


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=SharedLinkResponse)
async def create_shared_link(
    body: SharedLinkCreate,
    request: Request,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, Any]:
    """Create a new shareable link for a document.

    The caller must own the file (or be in single-user mode).
    Returns the full link metadata including the generated token.
    """
    # Verify the file exists and belongs to the caller.
    q = db.query(FileRecord).filter(FileRecord.id == body.file_id)
    q = apply_owner_filter(q, request)
    file_record = q.first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    token = _generate_token()
    expires_at = None
    if body.expires_in_hours is not None:
        expires_at = datetime.now(timezone.utc).replace(microsecond=0)
        from datetime import timedelta

        expires_at = expires_at + timedelta(hours=body.expires_in_hours)

    password_hash = _hash_password(body.password) if body.password else None

    db_link = SharedLink(
        token=token,
        file_id=body.file_id,
        owner_id=owner_id,
        label=body.label,
        expires_at=expires_at,
        max_views=body.max_views,
        view_count=0,
        password_hash=password_hash,
    )
    try:
        db.add(db_link)
        db.commit()
        db.refresh(db_link)
    except Exception:
        db.rollback()
        raise

    logger.info("Shared link created: id=%s owner=%s file_id=%s", db_link.id, owner_id, body.file_id)

    base_url = str(request.base_url).rstrip("/")
    return _link_to_dict(db_link, base_url, file_record.original_filename)


@router.get("/", response_model=list[SharedLinkResponse])
async def list_shared_links(
    request: Request,
    owner_id: CurrentOwner,
    db: DbSession,
    active_only: bool = Query(False, description="When true, only return active (non-revoked) links"),
) -> list[dict[str, Any]]:
    """List all shared links created by the authenticated user."""
    q = db.query(SharedLink).filter(SharedLink.owner_id == owner_id)
    if active_only:
        q = q.filter(SharedLink.is_active.is_(True))
    links = q.order_by(SharedLink.created_at.desc()).all()

    base_url = str(request.base_url).rstrip("/")
    result = []
    for link in links:
        file_record = db.query(FileRecord).filter(FileRecord.id == link.file_id).first()
        filename = file_record.original_filename if file_record else None
        result.append(_link_to_dict(link, base_url, filename))
    return result


@router.delete("/{link_id}", status_code=status.HTTP_200_OK)
async def revoke_shared_link(
    link_id: int,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, str]:
    """Revoke (soft-delete) a shared link.

    The record is kept for audit purposes but the link immediately
    stops working for recipients.
    """
    db_link = db.query(SharedLink).filter(SharedLink.id == link_id, SharedLink.owner_id == owner_id).first()
    if not db_link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared link not found")

    if not db_link.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Link is already revoked")

    try:
        db_link.is_active = False
        db_link.revoked_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("Shared link revoked: id=%s owner=%s", link_id, owner_id)
    return {"detail": "Link revoked"}


# ---------------------------------------------------------------------------
# Public endpoints (no authentication required)
# ---------------------------------------------------------------------------


@public_router.get("/share/{token}/info", response_model=SharedLinkInfoResponse)
def get_shared_link_info(
    token: str,
    db: DbSession,
) -> dict[str, Any]:
    """Return public metadata about a shared link.

    Used by the share landing page to decide whether to show a password
    prompt or a direct download button.  Never returns sensitive data.
    """
    link = db.query(SharedLink).filter(SharedLink.token == token).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    file_record = db.query(FileRecord).filter(FileRecord.id == link.file_id).first()
    filename = file_record.original_filename if file_record else None

    return {
        "token": link.token,
        "label": link.label,
        "original_filename": filename,
        "expires_at": link.expires_at,
        "max_views": link.max_views,
        "view_count": link.view_count,
        "has_password": link.password_hash is not None,
        "is_valid": _is_link_valid(link),
    }


@public_router.get("/share/{token}/download")
def download_via_shared_link(
    token: str,
    db: DbSession,
    password: str | None = Query(None, description="Password (if the link is password-protected)"),
) -> FileResponse:
    """Download a file via a shared link (no authentication required).

    Increments the view counter and validates expiry / view limit before
    serving the file.
    """
    link = db.query(SharedLink).filter(SharedLink.token == token).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found or expired")

    if not _is_link_valid(link):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Link has expired or reached its view limit")

    # Password check
    if link.password_hash is not None:
        if not password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This link requires a password",
            )
        if not _verify_password(password, link.password_hash):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Incorrect password")

    file_record = db.query(FileRecord).filter(FileRecord.id == link.file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    file_path = _resolve_file_path(file_record)
    if not file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not available on disk")

    # Increment view count (best-effort — don't fail the request if this errors).
    try:
        link.view_count = (link.view_count or 0) + 1
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to increment view_count for shared link id=%s", link.id)

    return FileResponse(
        path=file_path,
        media_type=file_record.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{file_record.original_filename or "document"}"',
        },
    )


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _link_to_dict(link: SharedLink, base_url: str, original_filename: str | None) -> dict[str, Any]:
    """Serialise a ``SharedLink`` ORM row to a plain dict."""
    return {
        "id": link.id,
        "token": link.token,
        "file_id": link.file_id,
        "label": link.label,
        "expires_at": link.expires_at,
        "max_views": link.max_views,
        "view_count": link.view_count,
        "has_password": link.password_hash is not None,
        "is_active": link.is_active,
        "created_at": link.created_at,
        "revoked_at": link.revoked_at,
        "share_url": f"{base_url}/share/{link.token}",
        "original_filename": original_filename,
    }
