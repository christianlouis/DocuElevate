"""API endpoints for subscription tiers and usage statistics.

Public endpoints:
  GET /api/subscriptions/tiers        — list all available plans
  GET /api/subscriptions/my           — current user's plan + usage (auth required)
  GET /api/subscriptions/platform     — platform-wide stats (admin only)
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.utils.subscription import (
    TIER_ORDER,
    TIERS,
    get_all_tiers,
    get_tier,
    get_user_tier_id,
    get_user_usage,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

DbSession = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _get_current_user(request: Request) -> dict | None:
    return request.session.get("user")


def _require_admin(request: Request) -> dict:
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


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
    """Return the authenticated user's subscription tier and current usage counts."""
    from app.config import settings

    user = _get_current_user(request)

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
    tier_id = get_user_tier_id(db, owner_id)
    tier = get_tier(tier_id)
    usage = get_user_usage(db, owner_id)

    return {
        "multi_user_mode": True,
        "owner_id": owner_id,
        "tier": tier,
        "usage": usage,
    }


@router.get("/platform", summary="Platform-wide usage statistics (admin only)")
def platform_stats(request: Request, db: DbSession) -> dict[str, Any]:
    """Return aggregate statistics across all users and tiers (admin only)."""
    _require_admin(request)

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
