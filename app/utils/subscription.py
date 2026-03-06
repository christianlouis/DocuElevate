"""
Subscription tier definitions and enforcement utilities for DocuElevate SaaS.

Four tiers:
  - free        $0/mo  — 25 lifetime files, 1 destination, 50 OCR pages/mo
  - starter     $9/mo  — 10/day, 100/mo, 3 destinations, 500 OCR pages/mo
  - professional $29/mo — 50/day, 500/mo, 10 destinations, 2 500 OCR pages/mo
  - business    $79/mo  — unlimited, unlimited destinations, unlimited OCR

Limits use 0 to represent "unlimited".
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier catalogue
# ---------------------------------------------------------------------------

TIERS: dict[str, dict[str, Any]] = {
    "free": {
        "id": "free",
        "name": "Free",
        "tagline": "Explore DocuElevate at no cost",
        "price_monthly": 0,
        "price_yearly": 0,
        "highlight": False,
        # Hard caps — 0 = unlimited
        "lifetime_file_limit": 25,  # total files ever processed
        "daily_upload_limit": 0,  # no per-day cap (capped by lifetime)
        "monthly_upload_limit": 0,  # no per-month cap (capped by lifetime)
        "max_storage_destinations": 1,
        "max_ocr_pages_monthly": 50,
        "max_file_size_mb": 10,
        "api_access": False,
        # Marketing feature list (shown on pricing page)
        "features": [
            "25 documents – lifetime total",
            "1 storage destination",
            "50 OCR pages / month",
            "10 MB max file size",
            "Basic AI metadata extraction",
            "Community support",
        ],
        "cta": "Get started free",
        "badge": None,
    },
    "starter": {
        "id": "starter",
        "name": "Starter",
        "tagline": "Perfect for individuals & small teams",
        "price_monthly": 9,
        "price_yearly": 90,
        "highlight": False,
        "lifetime_file_limit": 0,
        "daily_upload_limit": 10,
        "monthly_upload_limit": 100,
        "max_storage_destinations": 3,
        "max_ocr_pages_monthly": 500,
        "max_file_size_mb": 50,
        "api_access": True,
        "features": [
            "10 documents / day",
            "100 documents / month",
            "3 storage destinations",
            "500 OCR pages / month",
            "50 MB max file size",
            "Full AI metadata extraction",
            "Email ingestion",
            "API access",
            "Email support",
        ],
        "cta": "Start with Starter",
        "badge": None,
    },
    "professional": {
        "id": "professional",
        "name": "Professional",
        "tagline": "For growing teams that need more power",
        "price_monthly": 29,
        "price_yearly": 290,
        "highlight": True,  # shown as "Most popular"
        "lifetime_file_limit": 0,
        "daily_upload_limit": 50,
        "monthly_upload_limit": 500,
        "max_storage_destinations": 10,
        "max_ocr_pages_monthly": 2500,
        "max_file_size_mb": 200,
        "api_access": True,
        "features": [
            "50 documents / day",
            "500 documents / month",
            "10 storage destinations",
            "2 500 OCR pages / month",
            "200 MB max file size",
            "Advanced AI workflows",
            "Email & URL ingestion",
            "Webhooks",
            "Priority email support",
        ],
        "cta": "Go Professional",
        "badge": "Most Popular",
    },
    "business": {
        "id": "business",
        "name": "Business",
        "tagline": "Unlimited processing for organisations",
        "price_monthly": 79,
        "price_yearly": 790,
        "highlight": False,
        "lifetime_file_limit": 0,
        "daily_upload_limit": 0,
        "monthly_upload_limit": 0,
        "max_storage_destinations": 0,
        "max_ocr_pages_monthly": 0,
        "max_file_size_mb": 0,
        "api_access": True,
        "features": [
            "Unlimited documents",
            "Unlimited storage destinations",
            "Unlimited OCR pages",
            "Unlimited file size",
            "All AI processing steps",
            "All ingestion methods",
            "Webhooks & full API access",
            "Custom integrations",
            "Dedicated support",
        ],
        "cta": "Contact Sales",
        "badge": "Best Value",
    },
}

# Display order for the pricing page
TIER_ORDER = ["free", "starter", "professional", "business"]

# Default tier assigned to new users
DEFAULT_TIER = "free"


# ---------------------------------------------------------------------------
# Getters
# ---------------------------------------------------------------------------


def get_tier(tier_id: str) -> dict[str, Any]:
    """Return tier config dict; falls back to *free* for unknown ids."""
    return TIERS.get(tier_id, TIERS["free"])


def get_all_tiers() -> list[dict[str, Any]]:
    """Return tiers in display order."""
    return [TIERS[tid] for tid in TIER_ORDER]


# ---------------------------------------------------------------------------
# Usage queries
# ---------------------------------------------------------------------------


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def get_lifetime_file_count(db: Session, owner_id: str) -> int:
    """Total files ever processed by this user (not counting duplicates)."""
    from app.models import FileRecord

    return (
        db.query(func.count(FileRecord.id))
        .filter(FileRecord.owner_id == owner_id, FileRecord.is_duplicate.is_(False))
        .scalar()
        or 0
    )


def get_today_file_count(db: Session, owner_id: str) -> int:
    """Files processed by this user today (UTC, not counting duplicates)."""
    from app.models import FileRecord

    today = _today_utc()
    return (
        db.query(func.count(FileRecord.id))
        .filter(
            FileRecord.owner_id == owner_id,
            FileRecord.is_duplicate.is_(False),
            func.date(FileRecord.created_at) == today,
        )
        .scalar()
        or 0
    )


def get_month_file_count(db: Session, owner_id: str) -> int:
    """Files processed by this user this calendar month (UTC, not counting duplicates)."""
    from app.models import FileRecord

    today = _today_utc()
    return (
        db.query(func.count(FileRecord.id))
        .filter(
            FileRecord.owner_id == owner_id,
            FileRecord.is_duplicate.is_(False),
            func.strftime("%Y-%m", FileRecord.created_at) == today.strftime("%Y-%m"),
        )
        .scalar()
        or 0
    )


# ---------------------------------------------------------------------------
# Limit enforcement
# ---------------------------------------------------------------------------


class QuotaExceeded(Exception):
    """Raised when a user has hit a subscription limit."""

    def __init__(self, message: str, limit_type: str, limit_value: int, current_value: int) -> None:
        super().__init__(message)
        self.limit_type = limit_type
        self.limit_value = limit_value
        self.current_value = current_value


def check_upload_allowed(db: Session, owner_id: str | None, tier_id: str | None) -> None:
    """Raise :class:`QuotaExceeded` if this user is not allowed to upload another file.

    When *owner_id* or *tier_id* is ``None`` (e.g. single-user mode) the check
    is skipped entirely.
    """
    if owner_id is None or tier_id is None:
        return

    tier = get_tier(tier_id)

    # 1. Lifetime file cap (free tier)
    lifetime_limit = tier["lifetime_file_limit"]
    if lifetime_limit > 0:
        count = get_lifetime_file_count(db, owner_id)
        if count >= lifetime_limit:
            raise QuotaExceeded(
                f"Lifetime file limit of {lifetime_limit} reached for the {tier['name']} plan. "
                "Please upgrade to continue processing documents.",
                limit_type="lifetime",
                limit_value=lifetime_limit,
                current_value=count,
            )

    # 2. Daily cap
    daily_limit = tier["daily_upload_limit"]
    if daily_limit > 0:
        count = get_today_file_count(db, owner_id)
        if count >= daily_limit:
            raise QuotaExceeded(
                f"Daily file limit of {daily_limit} reached for the {tier['name']} plan. "
                "Please try again tomorrow or upgrade your plan.",
                limit_type="daily",
                limit_value=daily_limit,
                current_value=count,
            )

    # 3. Monthly cap
    monthly_limit = tier["monthly_upload_limit"]
    if monthly_limit > 0:
        count = get_month_file_count(db, owner_id)
        if count >= monthly_limit:
            raise QuotaExceeded(
                f"Monthly file limit of {monthly_limit} reached for the {tier['name']} plan. "
                "Please upgrade your plan for more documents this month.",
                limit_type="monthly",
                limit_value=monthly_limit,
                current_value=count,
            )


def get_user_tier_id(db: Session, owner_id: str | None) -> str:
    """Return the subscription tier id for *owner_id*, defaulting to 'free'."""
    if owner_id is None:
        return DEFAULT_TIER
    from app.models import UserProfile

    profile = db.query(UserProfile).filter(UserProfile.user_id == owner_id).first()
    if profile and profile.subscription_tier:
        return profile.subscription_tier
    return DEFAULT_TIER


def get_user_usage(db: Session, owner_id: str) -> dict[str, int]:
    """Return a dict with lifetime / daily / monthly file counts for *owner_id*."""
    return {
        "lifetime": get_lifetime_file_count(db, owner_id),
        "today": get_today_file_count(db, owner_id),
        "month": get_month_file_count(db, owner_id),
    }
