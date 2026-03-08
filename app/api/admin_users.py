"""API endpoints for admin user management.

Provides CRUD operations for user profiles and aggregate statistics so that
administrators can inspect, configure, and manage users in multi-user mode.
Also provides endpoints for admins to create and manage local (email/password)
user accounts directly, without requiring email verification.
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FileRecord, LocalUser, UserProfile
from app.utils.local_auth import generate_token, hash_password, send_password_reset_email

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


class PaymentIssueBody(BaseModel):
    """Body for reporting a payment issue for a user."""

    issue: str = Field(..., min_length=1, max_length=2048, description="Description of the payment issue")


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


class LocalUserCreate(BaseModel):
    """Body for admin-creating a local (email/password) user account."""

    email: str = Field(..., max_length=255, description="Email address for the new user")
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str | None = Field(default=None, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    is_admin: bool = Field(default=False, description="Grant admin privileges")


class LocalUserUpdate(BaseModel):
    """Body for admin-updating a local (email/password) user account."""

    email: str | None = Field(default=None, max_length=255, description="New email address")
    display_name: str | None = Field(default=None, max_length=255, description="New display name")
    is_admin: bool | None = Field(default=None, description="Grant or revoke admin privileges")
    is_active: bool | None = Field(default=None, description="Activate or deactivate the account")


class LocalUserSetPassword(BaseModel):
    """Body for admin setting a temporary password for a local user."""

    password: str = Field(..., min_length=8, max_length=128, description="New temporary password")


class LocalUserResponse(BaseModel):
    """Summary of a local user account."""

    id: int
    email: str
    username: str
    display_name: str | None
    is_active: bool
    is_admin: bool
    created_at: str | None

    model_config = {"from_attributes": True}


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


# ---------------------------------------------------------------------------
# Local user management (admin-only)
# ---------------------------------------------------------------------------
# NOTE: These routes MUST be defined before /{user_id:path} to avoid being
# swallowed by the catch-all path parameter.
# ---------------------------------------------------------------------------


@router.get("/local", summary="List all local (email/password) user accounts")
def list_local_users(db: DbSession, _admin: AdminUser) -> list[dict[str, Any]]:
    """Return every local user account with basic metadata."""
    users = db.query(LocalUser).order_by(LocalUser.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "username": u.username,
            "display_name": u.display_name,
            "is_active": u.is_active,
            "is_admin": u.is_admin,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/local", status_code=status.HTTP_201_CREATED, summary="Create a local user account")
def create_local_user(body: LocalUserCreate, db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Create a new local (email/password) user account.

    The account is immediately active — no email verification is required when
    created by an administrator.  A matching UserProfile row is also created.

    Raises:
        409: Email or username already registered.
    """
    if db.query(LocalUser).filter(LocalUser.email == body.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")
    if db.query(LocalUser).filter(LocalUser.username == body.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken.")

    user = LocalUser(
        email=body.email,
        username=body.username,
        display_name=body.display_name,
        hashed_password=hash_password(body.password),
        is_active=True,
        is_admin=body.is_admin,
    )
    db.add(user)

    # Ensure a UserProfile exists for the new user
    if not db.query(UserProfile).filter(UserProfile.user_id == body.email).first():
        db.add(UserProfile(user_id=body.email, display_name=body.display_name or body.username))

    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise

    logger.info("Admin created local user account: %s", body.email)
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "display_name": user.display_name,
        "is_active": user.is_active,
        "is_admin": user.is_admin,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.delete(
    "/local/{local_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a local user account",
)
def delete_local_user(local_user_id: int, db: DbSession, _admin: AdminUser) -> None:
    """Delete a local user account by its numeric ID.

    The associated UserProfile is also removed.  Documents owned by this user
    are **not** deleted.
    """
    user = db.query(LocalUser).filter(LocalUser.id == local_user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local user not found.")

    # Remove associated profile if present
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.email).first()
    if profile:
        db.delete(profile)

    try:
        db.delete(user)
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("Admin deleted local user account: %s", user.email)


@router.patch("/local/{local_user_id}", summary="Update a local user account")
def update_local_user(local_user_id: int, body: LocalUserUpdate, db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Update the email address, display name, admin flag, or active status of a local user account.

    Only fields explicitly provided (non-None) are modified.  If the email is changed
    the associated UserProfile row is also updated to keep ``user_id`` in sync.

    Raises:
        404: Local user not found.
        409: The new email is already taken by another account.
    """
    user = db.query(LocalUser).filter(LocalUser.id == local_user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local user not found.")

    old_email = user.email

    if body.email is not None and body.email != user.email:
        if db.query(LocalUser).filter(LocalUser.email == body.email, LocalUser.id != local_user_id).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")
        user.email = body.email

    if body.display_name is not None:
        user.display_name = body.display_name

    if body.is_admin is not None:
        user.is_admin = body.is_admin

    if body.is_active is not None:
        user.is_active = body.is_active

    try:
        db.flush()
        # Keep UserProfile.user_id in sync when email changes
        if body.email is not None and body.email != old_email:
            profile = db.query(UserProfile).filter(UserProfile.user_id == old_email).first()
            if profile:
                profile.user_id = body.email
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise

    logger.info("Admin updated local user %s (id=%d)", user.email, user.id)
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "display_name": user.display_name,
        "is_active": user.is_active,
        "is_admin": user.is_admin,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.post(
    "/local/{local_user_id}/send-password-reset",
    status_code=status.HTTP_200_OK,
    summary="Send a password reset email to a local user",
)
def admin_send_password_reset(
    local_user_id: int, request: Request, db: DbSession, _admin: AdminUser
) -> dict[str, Any]:
    """Generate a password reset token and email the reset link to the local user.

    This is a last-resort tool for admins to help users who are locked out.
    Returns ``{"sent": true}`` on success and ``{"sent": false, "reason": "..."}`` when
    SMTP is not configured or sending fails.

    Raises:
        404: Local user not found.
    """
    from app.config import settings as _settings

    user = db.query(LocalUser).filter(LocalUser.id == local_user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local user not found.")

    if not _settings.email_host:
        logger.warning("Admin requested password reset for %s but SMTP is not configured", user.email)
        return {"sent": False, "reason": "SMTP is not configured on this server."}

    token = generate_token()
    user.password_reset_token = token
    user.password_reset_sent_at = datetime.now(tz=timezone.utc)
    db.commit()

    base_url = str(request.base_url).rstrip("/")
    try:
        send_password_reset_email(user.email, user.username, token, base_url)
    except Exception as exc:
        logger.warning("Admin-triggered password reset email failed for %s: %s", user.email, exc)
        return {"sent": False, "reason": str(exc)}

    logger.info("[SECURITY] ADMIN_PASSWORD_RESET_EMAIL user=%s admin=%s", user.email, _admin.get("email", "unknown"))
    return {"sent": True, "email": user.email}


@router.post(
    "/local/{local_user_id}/set-password",
    status_code=status.HTTP_200_OK,
    summary="Set a temporary password for a local user account",
)
def admin_set_password(
    local_user_id: int, body: LocalUserSetPassword, db: DbSession, _admin: AdminUser
) -> dict[str, Any]:
    """Directly set a new password for a local user without requiring an email token.

    Use this as a last resort when email delivery is unavailable.  The user
    should be advised to change their password after logging in.

    Raises:
        404: Local user not found.
    """
    user = db.query(LocalUser).filter(LocalUser.id == local_user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local user not found.")

    user.hashed_password = hash_password(body.password)
    # Clear any outstanding reset tokens
    user.password_reset_token = None
    user.password_reset_sent_at = None

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info(
        "[SECURITY] ADMIN_SET_PASSWORD user=%s admin=%s", user.email, _admin.get("email", "unknown")
    )
    return {"updated": True, "email": user.email}
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

    old_tier = (profile.subscription_tier or "free") if profile.id else None  # None means brand-new profile
    profile.display_name = body.display_name
    profile.daily_upload_limit = body.daily_upload_limit
    profile.notes = body.notes
    profile.is_blocked = body.is_blocked
    profile.subscription_billing_cycle = body.subscription_billing_cycle
    profile.subscription_period_start = body.subscription_period_start
    profile.allow_overage = body.allow_overage
    profile.is_complimentary = body.is_complimentary
    tier_changed = False
    new_tier: str | None = None
    if body.subscription_tier is not None:
        from app.utils.subscription import TIERS

        if body.subscription_tier not in TIERS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid subscription_tier '{body.subscription_tier}'. Valid values: {list(TIERS.keys())}",
            )
        # Detect a real change only for existing profiles (old_tier is not None)
        if old_tier is not None and old_tier != body.subscription_tier:
            tier_changed = True
            new_tier = body.subscription_tier
        profile.subscription_tier = body.subscription_tier

    try:
        db.commit()
        db.refresh(profile)
    except Exception:
        db.rollback()
        raise

    logger.info("Admin upserted profile for user %s", user_id)

    # Notify admins and fire webhook when plan is changed by an admin
    if tier_changed and new_tier is not None:
        try:
            from app.utils.notification import notify_plan_changed
            from app.utils.webhook import dispatch_webhook_event

            notify_plan_changed(user_id, old_tier=old_tier, new_tier=new_tier, changed_by="admin")  # type: ignore[arg-type]
            dispatch_webhook_event(
                "user.plan_changed",
                {
                    "user_id": user_id,
                    "old_tier": old_tier,
                    "new_tier": new_tier,
                    "billing_cycle": body.subscription_billing_cycle,
                    "changed_by": "admin",
                },
            )
        except Exception:
            logger.exception("Failed to send plan-change notification/webhook for user %s", user_id)

    return _profile_to_dict(profile)


@router.post(
    "/{user_id:path}/payment-issue", status_code=status.HTTP_200_OK, summary="Report a payment issue for a user"
)
def report_payment_issue(user_id: str, body: PaymentIssueBody, db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Notify admins and fire a webhook for a payment issue reported against *user_id*.

    The user profile must exist.  Use this endpoint when a payment processor
    webhook or manual review identifies a billing problem (e.g. failed charge,
    expired card, disputed transaction).

    Returns the user profile dict alongside an acknowledgement flag.
    """
    profile = _get_or_none(db, user_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found")

    logger.warning("Payment issue reported for user %s: %s", user_id, body.issue)

    try:
        from app.utils.notification import notify_payment_issue
        from app.utils.webhook import dispatch_webhook_event

        notify_payment_issue(user_id, issue=body.issue)
        dispatch_webhook_event(
            "user.payment_issue",
            {
                "user_id": user_id,
                "issue": body.issue,
            },
        )
    except Exception:
        logger.exception("Failed to send payment-issue notification/webhook for user %s", user_id)

    return {"acknowledged": True, "user_id": user_id, "profile": _profile_to_dict(profile)}


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
