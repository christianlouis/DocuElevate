"""API endpoints for managing IMAP ingestion profiles.

Ingestion profiles allow fine-grained control over which attachment types are
accepted when ingesting emails via IMAP.  Each profile carries a list of enabled
file-type categories (e.g. ``["pdf", "office", "images"]``) drawn from the
canonical set defined in :mod:`app.utils.allowed_types`.

Built-in system profiles (``is_builtin=True``) are read-only and cannot be
deleted or modified.  Users may create their own profiles which are private to
their ``owner_id``.  System-level global profiles (``owner_id=None``) are visible
to all users but can only be created by administrators.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ImapIngestionProfile
from app.utils.allowed_types import FILE_TYPE_CATEGORIES
from app.utils.user_scope import get_current_owner_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/imap-profiles", tags=["imap-profiles"])

DbSession = Annotated[Session, Depends(get_db)]

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _get_owner_id(request: Request) -> str:
    """Return the current user's owner ID, raising 401 if unauthenticated."""
    owner_id = get_current_owner_id(request)
    if owner_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return owner_id


CurrentOwner = Annotated[str, Depends(_get_owner_id)]

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

_VALID_CATEGORIES = set(FILE_TYPE_CATEGORIES.keys())


class ImapProfileCreate(BaseModel):
    """Schema for creating a new ingestion profile."""

    name: str = Field(..., min_length=1, max_length=255, description="Human-readable profile name")
    description: str | None = Field(default=None, description="Optional description")
    allowed_categories: list[str] = Field(
        ...,
        min_length=1,
        description=(f"List of enabled file-type category keys.  Valid values: {sorted(_VALID_CATEGORIES)}"),
    )


class ImapProfileUpdate(BaseModel):
    """Schema for updating an existing profile (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    allowed_categories: list[str] | None = Field(default=None, min_length=1)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_categories(categories: list[str]) -> list[str]:
    """Raise 422 if any category key is unknown; return the cleaned list."""
    unknown = [c for c in categories if c not in _VALID_CATEGORIES]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown category key(s): {unknown}. Valid keys: {sorted(_VALID_CATEGORIES)}",
        )
    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for cat in categories:
        if cat not in seen:
            seen.add(cat)
            result.append(cat)
    return result


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _to_response(profile: ImapIngestionProfile) -> dict[str, Any]:
    """Serialize a profile row to a response dict."""
    try:
        categories = json.loads(profile.allowed_categories)
    except (ValueError, TypeError):
        categories = []

    # Enrich categories with display metadata
    categories_detail = [
        {
            "key": cat,
            "label": FILE_TYPE_CATEGORIES[cat]["label"] if cat in FILE_TYPE_CATEGORIES else cat,
            "description": FILE_TYPE_CATEGORIES[cat]["description"] if cat in FILE_TYPE_CATEGORIES else "",
        }
        for cat in categories
    ]

    return {
        "id": profile.id,
        "name": profile.name,
        "description": profile.description,
        "owner_id": profile.owner_id,
        "allowed_categories": categories,
        "categories_detail": categories_detail,
        "is_builtin": profile.is_builtin,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/categories", summary="List available file-type categories")
def list_categories(request: Request, owner_id: CurrentOwner) -> list[dict[str, Any]]:
    """Return the full list of file-type categories that can be used in profiles."""
    return [
        {
            "key": key,
            "label": info["label"],
            "description": info["description"],
        }
        for key, info in FILE_TYPE_CATEGORIES.items()
    ]


@router.get("/", summary="List ingestion profiles visible to the current user")
def list_profiles(request: Request, db: DbSession, owner_id: CurrentOwner) -> list[dict[str, Any]]:
    """Return all profiles: system-global (owner_id=NULL) and the user's own profiles."""
    profiles = (
        db.query(ImapIngestionProfile)
        .filter(
            # SQLAlchemy requires `== None` for IS NULL comparison in ORM filters
            (ImapIngestionProfile.owner_id == None) | (ImapIngestionProfile.owner_id == owner_id)  # noqa: E711
        )
        .order_by(ImapIngestionProfile.is_builtin.desc(), ImapIngestionProfile.id)
        .all()
    )
    return [_to_response(p) for p in profiles]


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create a new ingestion profile")
def create_profile(request: Request, body: ImapProfileCreate, db: DbSession, owner_id: CurrentOwner) -> dict[str, Any]:
    """Create a new ingestion profile owned by the current user."""
    categories = _validate_categories(body.allowed_categories)

    profile = ImapIngestionProfile(
        name=body.name,
        description=body.description,
        owner_id=owner_id,
        allowed_categories=json.dumps(categories),
        is_builtin=False,
    )
    try:
        db.add(profile)
        db.commit()
        db.refresh(profile)
    except Exception:
        db.rollback()
        raise

    logger.info("User %s created IMAP ingestion profile %d ('%s')", owner_id, profile.id, body.name)
    return _to_response(profile)


@router.get("/{profile_id}", summary="Get a single ingestion profile")
def get_profile(profile_id: int, request: Request, db: DbSession, owner_id: CurrentOwner) -> dict[str, Any]:
    """Return a single profile by ID.  Only the owner or system profiles are accessible."""
    profile = db.query(ImapIngestionProfile).filter(ImapIngestionProfile.id == profile_id).first()
    if not profile or (profile.owner_id is not None and profile.owner_id != owner_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion profile not found")
    return _to_response(profile)


@router.put("/{profile_id}", summary="Update an ingestion profile")
def update_profile(
    profile_id: int,
    request: Request,
    body: ImapProfileUpdate,
    db: DbSession,
    owner_id: CurrentOwner,
) -> dict[str, Any]:
    """Update an existing ingestion profile.  Built-in profiles cannot be modified."""
    profile = db.query(ImapIngestionProfile).filter(ImapIngestionProfile.id == profile_id).first()
    if not profile or (profile.owner_id is not None and profile.owner_id != owner_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion profile not found")
    if profile.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Built-in profiles cannot be modified.",
        )

    if body.name is not None:
        profile.name = body.name
    if "description" in body.model_fields_set:
        profile.description = body.description
    if body.allowed_categories is not None:
        categories = _validate_categories(body.allowed_categories)
        profile.allowed_categories = json.dumps(categories)

    profile.updated_at = datetime.now(timezone.utc)

    try:
        db.commit()
        db.refresh(profile)
    except Exception:
        db.rollback()
        raise

    logger.info("User %s updated IMAP ingestion profile %d", owner_id, profile_id)
    return _to_response(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an ingestion profile")
def delete_profile(profile_id: int, request: Request, db: DbSession, owner_id: CurrentOwner) -> None:
    """Delete an ingestion profile.  Built-in profiles cannot be deleted."""
    profile = db.query(ImapIngestionProfile).filter(ImapIngestionProfile.id == profile_id).first()
    if not profile or (profile.owner_id is not None and profile.owner_id != owner_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion profile not found")
    if profile.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Built-in profiles cannot be deleted.",
        )

    try:
        db.delete(profile)
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("User %s deleted IMAP ingestion profile %d", owner_id, profile_id)
