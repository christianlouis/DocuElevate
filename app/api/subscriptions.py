"""API endpoints for subscription tiers and usage statistics.

Public endpoints:
  GET  /api/subscriptions/tiers        — list all available plans
  GET  /api/subscriptions/my           — current user's plan + usage (auth required)
  POST /api/subscriptions/change       — request a plan change (auth required)
  DELETE /api/subscriptions/change     — cancel a pending plan change (auth required)
  GET  /api/subscriptions/platform     — platform-wide stats (admin only)
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.admin_users import _require_admin
from app.database import get_db
from app.utils.subscription import (
    TIER_ORDER,
    TIERS,
    SubscriptionChangeError,
    apply_pending_subscription_changes,
    cancel_pending_subscription_change,
    get_all_tiers,
    get_tier,
    get_user_tier_id,
    get_user_usage,
    request_subscription_change,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

DbSession = Annotated[Session, Depends(get_db)]
AdminUser = Annotated[dict, Depends(_require_admin)]


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class SubscriptionChangeRequest(BaseModel):
    """Request body for a subscription plan change."""

    plan_id: str
    billing_cycle: str = "monthly"  # "monthly" | "yearly"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_owner_id(request: Request) -> str:
    """Extract the authenticated user's owner_id from the session."""
    user = request.session.get("user") or {}
    return user.get("username") or user.get("email") or user.get("sub") or ""


def _require_authenticated(request: Request) -> str:
    """Return the owner_id or raise 401."""
    owner_id = _get_owner_id(request)
    if not owner_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return owner_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/tiers", summary="List all subscription tiers")
def list_tiers() -> dict[str, Any]:
    """Return the full list of subscription plans in display order."""
    return {
        "tiers": get_all_tiers(),
        "order": TIER_ORDER,
        "default": "free",
    }


@router.get("/my", summary="Get current user's subscription and usage")
def my_subscription(request: Request, db: DbSession) -> dict[str, Any]:
    """Return the authenticated user's subscription tier and current usage counts.

    Also applies any pending subscription changes that have become due.
    """
    from app.config import settings
    from app.models import UserProfile

    user = request.session.get("user")

    if not settings.multi_user_enabled:
        # In single-user mode there is no concept of a subscription plan
        return {
            "multi_user_mode": False,
            "tier": TIERS["business"],  # unrestricted
            "usage": None,
        }

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    owner_id: str = user.get("username") or user.get("email") or user.get("sub") or ""

    # Apply any pending change that has become due
    apply_pending_subscription_changes(db, owner_id)

    tier_id = get_user_tier_id(db, owner_id)
    tier = get_tier(tier_id, db)
    usage = get_user_usage(db, owner_id)

    profile = db.query(UserProfile).filter(UserProfile.user_id == owner_id).first()
    pending_tier_id: str | None = profile.subscription_change_pending_tier if profile else None
    pending_date: str | None = (
        profile.subscription_change_pending_date.isoformat()
        if profile and profile.subscription_change_pending_date
        else None
    )
    period_start: str | None = (
        profile.subscription_period_start.isoformat() if profile and profile.subscription_period_start else None
    )

    return {
        "multi_user_mode": True,
        "owner_id": owner_id,
        "tier": tier,
        "usage": usage,
        "period_start": period_start,
        "pending_change": (
            {
                "tier_id": pending_tier_id,
                "tier": get_tier(pending_tier_id, db),
                "effective_date": pending_date,
            }
            if pending_tier_id
            else None
        ),
    }


@router.post("/change", summary="Request a subscription plan change", status_code=status.HTTP_200_OK)
def change_subscription(request: Request, body: SubscriptionChangeRequest, db: DbSession) -> dict[str, Any]:
    """Request a subscription tier change.

    **Upgrades** (moving to a higher-ranked plan) take effect immediately.

    **Downgrades** (moving to a lower-ranked plan) are scheduled for the end
    of the current billing period to prevent gaming.  The user keeps their
    current plan benefits until the scheduled date.

    Requesting the currently active tier while a downgrade is pending cancels
    that pending change.
    """
    from app.config import settings

    if not settings.multi_user_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription management is not available in single-user mode.",
        )

    owner_id = _require_authenticated(request)

    try:
        result = request_subscription_change(db, owner_id, body.plan_id, body.billing_cycle)
    except SubscriptionChangeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return result


@router.delete("/change", summary="Cancel a pending subscription change", status_code=status.HTTP_200_OK)
def cancel_subscription_change(request: Request, db: DbSession) -> dict[str, Any]:
    """Cancel a scheduled future subscription change.

    Only downgrades can be pending; upgrades always take effect immediately.
    Returns 404 when there is no pending change to cancel.
    """
    from app.config import settings

    if not settings.multi_user_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription management is not available in single-user mode.",
        )

    owner_id = _require_authenticated(request)

    cancelled = cancel_pending_subscription_change(db, owner_id)
    if not cancelled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending subscription change found.")

    return {"cancelled": True, "message": "Your pending subscription change has been cancelled."}


@router.get("/platform", summary="Platform-wide usage statistics (admin only)")
def platform_stats(request: Request, db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Return aggregate statistics across all users and tiers (admin only)."""
    from app.models import FileRecord, UserProfile

    today = datetime.now(timezone.utc).date()

    # Total files
    total_files: int = db.query(func.count(FileRecord.id)).scalar() or 0

    # Files today
    files_today: int = (
        db.query(func.count(FileRecord.id)).filter(func.date(FileRecord.created_at) == today).scalar() or 0
    )

    # Files this month
    files_this_month: int = (
        db.query(func.count(FileRecord.id))
        .filter(func.strftime("%Y-%m", FileRecord.created_at) == today.strftime("%Y-%m"))
        .scalar()
        or 0
    )

    # Files with OCR text (proxy for pages OCRed — approximation)
    files_with_ocr: int = db.query(func.count(FileRecord.id)).filter(FileRecord.ocr_text.isnot(None)).scalar() or 0

    # Unique active users (ever uploaded)
    unique_users: int = (
        db.query(func.count(func.distinct(FileRecord.owner_id))).filter(FileRecord.owner_id.isnot(None)).scalar() or 0
    )

    # Users per subscription tier
    profiles = (
        db.query(UserProfile.subscription_tier, func.count(UserProfile.id))
        .group_by(UserProfile.subscription_tier)
        .all()
    )
    tier_distribution: dict[str, int] = {row[0] or "free": row[1] for row in profiles}

    # Fill in zeros for tiers with no users
    for tid in TIER_ORDER:
        tier_distribution.setdefault(tid, 0)

    return {
        "files": {
            "total": total_files,
            "today": files_today,
            "this_month": files_this_month,
            "with_ocr": files_with_ocr,
        },
        "users": {
            "unique_uploaders": unique_users,
            "tier_distribution": tier_distribution,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
