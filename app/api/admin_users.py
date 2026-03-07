"""API endpoints for admin user management.

Provides CRUD operations for user profiles and aggregate statistics so that
administrators can inspect, configure, and manage users in multi-user mode.
"""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FileRecord, UserProfile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/users", tags=["admin-users"])

DbSession = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _require_admin(request: Request) -> dict:
    """Ensure the caller is an admin. Raises 403 otherwise."""
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


AdminUser = Annotated[dict, Depends(_require_admin)]


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class UserProfileUpsert(BaseModel):
    """Body for creating or updating a user profile."""

    display_name: str | None = Field(default=None, max_length=255, description="Human-readable display name")
    daily_upload_limit: int | None = Field(
        default=None, ge=0, description="Per-user daily upload cap; null = use global default"
    )
    notes: str | None = Field(default=None, max_length=4096, description="Admin notes about this user")
    is_blocked: bool = Field(default=False, description="Block this user from uploading")
    subscription_tier: str | None = Field(
        default="free",
        description="Subscription tier: free | starter | professional | business",
    )
    subscription_billing_cycle: str = Field(default="monthly", pattern="^(monthly|yearly)$")
    subscription_period_start: datetime | None = None
    allow_overage: bool = False
    is_complimentary: bool = Field(
        default=False,
        description="When True the user is on a complimentary (uncharged) plan — they keep all tier "
        "quota benefits but are never billed via Stripe.",
    )


class UserProfileResponse(BaseModel):
    """Response schema for a user profile record."""

    id: int
    user_id: str
    display_name: str | None
    daily_upload_limit: int | None
    notes: str | None
    is_blocked: bool
    subscription_tier: str | None
    subscription_billing_cycle: str
    subscription_period_start: str | None
    allow_overage: bool
    is_complimentary: bool
    created_at: str | None
    updated_at: str | None

    model_config = {"from_attributes": True}


class UserSummary(BaseModel):
    """Per-user summary combining profile data with document statistics."""

    user_id: str
    display_name: str | None
    daily_upload_limit: int | None
    notes: str | None
    is_blocked: bool
    subscription_tier: str | None
    subscription_billing_cycle: str | None
    subscription_period_start: str | None
    allow_overage: bool
    is_complimentary: bool
    profile_id: int | None
    document_count: int
    last_upload: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_or_none(db: Session, user_id: str) -> UserProfile | None:
    """Return the UserProfile row for *user_id*, or None if it doesn't exist."""
    return db.query(UserProfile).filter(UserProfile.user_id == user_id).first()


def _profile_to_dict(profile: UserProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "display_name": profile.display_name,
        "daily_upload_limit": profile.daily_upload_limit,
        "notes": profile.notes,
        "is_blocked": profile.is_blocked,
        "subscription_tier": profile.subscription_tier or "free",
        "subscription_billing_cycle": profile.subscription_billing_cycle or "monthly",
        "subscription_period_start": profile.subscription_period_start.isoformat()
        if profile.subscription_period_start
        else None,
        "allow_overage": bool(profile.allow_overage),
        "is_complimentary": bool(profile.is_complimentary),
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", summary="List all known users with statistics")
def list_users(
    db: DbSession,
    _admin: AdminUser,
    q: str = Query("", description="Filter by user_id substring (case-insensitive)"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
) -> dict[str, Any]:
    """Return every distinct user_id that has at least one document or an explicit profile,
    enriched with aggregate document statistics and the admin-managed profile.

    Supports substring filtering (``q``) and pagination.
    """
    # 1. Collect every distinct owner_id from documents
    doc_stats_query = (
        db.query(
            FileRecord.owner_id.label("user_id"),
            func.count(FileRecord.id).label("doc_count"),
            func.max(FileRecord.created_at).label("last_upload"),
        )
        .filter(FileRecord.owner_id.isnot(None))
        .group_by(FileRecord.owner_id)
    )

    # 2. Collect all user_ids that have explicit profiles (may not have docs yet)
    profile_query = db.query(UserProfile)

    # Build a unified set of user_ids
    doc_rows = {row.user_id: row for row in doc_stats_query.all()}
    profile_rows = {p.user_id: p for p in profile_query.all()}

    all_user_ids = set(doc_rows.keys()) | set(profile_rows.keys())

    # Apply optional substring filter
    if q.strip():
        q_lower = q.strip().lower()
        all_user_ids = {uid for uid in all_user_ids if q_lower in uid.lower()}

    # Sort and paginate
    sorted_ids = sorted(all_user_ids)
    total = len(sorted_ids)
    start = (page - 1) * per_page
    page_ids = sorted_ids[start : start + per_page]

    users: list[dict[str, Any]] = []
    for uid in page_ids:
        doc_row = doc_rows.get(uid)
        profile = profile_rows.get(uid)
        users.append(
            {
                "user_id": uid,
                "display_name": profile.display_name if profile else None,
                "daily_upload_limit": profile.daily_upload_limit if profile else None,
                "notes": profile.notes if profile else None,
                "is_blocked": profile.is_blocked if profile else False,
                "subscription_tier": (profile.subscription_tier or "free") if profile else "free",
                "subscription_billing_cycle": (profile.subscription_billing_cycle or "monthly")
                if profile
                else "monthly",
                "subscription_period_start": profile.subscription_period_start.isoformat()
                if (profile and profile.subscription_period_start)
                else None,
                "allow_overage": bool(profile.allow_overage) if profile else False,
                "is_complimentary": bool(profile.is_complimentary) if profile else False,
                "profile_id": profile.id if profile else None,
                "document_count": doc_row.doc_count if doc_row else 0,
                "last_upload": doc_row.last_upload.isoformat() if (doc_row and doc_row.last_upload) else None,
            }
        )

    return {
        "users": users,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/{user_id:path}", summary="Get details for a single user")
def get_user(user_id: str, db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Return profile and document statistics for a specific user."""
    doc_count = db.query(func.count(FileRecord.id)).filter(FileRecord.owner_id == user_id).scalar() or 0
    last_row = (
        db.query(FileRecord.created_at)
        .filter(FileRecord.owner_id == user_id)
        .order_by(FileRecord.created_at.desc())
        .first()
    )
    last_upload = last_row[0].isoformat() if last_row and last_row[0] else None

    profile = _get_or_none(db, user_id)

    return {
        "user_id": user_id,
        "display_name": profile.display_name if profile else None,
        "daily_upload_limit": profile.daily_upload_limit if profile else None,
        "notes": profile.notes if profile else None,
        "is_blocked": profile.is_blocked if profile else False,
        "subscription_tier": (profile.subscription_tier or "free") if profile else "free",
        "subscription_billing_cycle": (profile.subscription_billing_cycle or "monthly") if profile else "monthly",
        "subscription_period_start": profile.subscription_period_start.isoformat()
        if (profile and profile.subscription_period_start)
        else None,
        "allow_overage": bool(profile.allow_overage) if profile else False,
        "is_complimentary": bool(profile.is_complimentary) if profile else False,
        "profile_id": profile.id if profile else None,
        "document_count": doc_count,
        "last_upload": last_upload,
        "profile": _profile_to_dict(profile) if profile else None,
    }


@router.put("/{user_id:path}", summary="Create or update a user profile")
def upsert_user_profile(
    user_id: str,
    body: UserProfileUpsert,
    db: DbSession,
    _admin: AdminUser,
) -> dict[str, Any]:
    """Create a new profile or update an existing one for *user_id*.

    Returns the persisted profile.
    """
    profile = _get_or_none(db, user_id)
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)

    profile.display_name = body.display_name
    profile.daily_upload_limit = body.daily_upload_limit
    profile.notes = body.notes
    profile.is_blocked = body.is_blocked
    profile.subscription_billing_cycle = body.subscription_billing_cycle
    profile.subscription_period_start = body.subscription_period_start
    profile.allow_overage = body.allow_overage
    profile.is_complimentary = body.is_complimentary
    if body.subscription_tier is not None:
        from app.utils.subscription import TIERS

        if body.subscription_tier not in TIERS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid subscription_tier '{body.subscription_tier}'. Valid values: {list(TIERS.keys())}",
            )
        profile.subscription_tier = body.subscription_tier

    try:
        db.commit()
        db.refresh(profile)
    except Exception:
        db.rollback()
        raise

    logger.info("Admin upserted profile for user %s", user_id)
    return _profile_to_dict(profile)


@router.delete("/{user_id:path}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a user profile")
def delete_user_profile(user_id: str, db: DbSession, _admin: AdminUser) -> None:
    """Delete the admin-managed profile for *user_id*.

    Documents owned by this user are **not** removed; only the profile record
    is deleted.  To reassign or purge documents use the files API.
    """
    profile = _get_or_none(db, user_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found")

    try:
        db.delete(profile)
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("Admin deleted profile for user %s", user_id)
