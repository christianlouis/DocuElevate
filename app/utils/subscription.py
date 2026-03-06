"""
Subscription tier definitions and enforcement utilities for DocuElevate SaaS.

Four tiers (prices ex-VAT; German customers +19 % MwSt):
  - free         $0/mo    — 50 lifetime docs, 150 lifetime OCR pages, 1 dest
  - starter      $2.99/mo — 50/mo, 300 OCR pp/mo, 2 dests, 1 mailbox
  - professional $5.99/mo — 150/mo, 750 OCR pp/mo, 5 dests, 3 mailboxes
  - business     $7.99/mo — 300/mo, 1500 OCR pp/mo, 10 dests, unlimited mailboxes

Limits use 0 to represent "unlimited".
All paid tiers include a 30-day free trial (trial_days field).

--- Cost analysis at maximum usage (Hetzner Option-A infra, Azure Read + GPT-4o mini) ---
Infrastructure: CX32 (app+Redis €7.59) + CX22 (worker €3.79) + BX21 (storage €7.22) ≈ $24/mo
At 100 users infra share ≈ $0.24/user/mo.

  Starter  : OCR $0.45 + AI $0.012 + infra $0.24 + Stripe $0.34 = $1.04 → 65 % gross margin
  Professional: OCR $1.13 + AI $0.035 + infra $0.24 + Stripe $0.42 = $1.82 → 70 % gross margin
  Business : OCR $2.25 + AI $0.069 + infra $0.24 + Stripe $0.48 = $3.04 → 62 % gross margin

After ~30 % German corporate tax: Starter 45 %, Professional 49 %, Business 43 %.
At average usage (~40 % of quota) margins improve to 55-65 % after tax.

⚠ If GPT-4o (not mini) is configured, Business AI cost at max rises to ~$1.92/user,
  reducing after-tax margin to ~33 %. Recommend GPT-4o mini as default in production.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier catalogue
# ---------------------------------------------------------------------------

TIER_DEFAULTS: dict[str, dict[str, Any]] = {
    "free": {
        "id": "free",
        "name": "Free",
        "tagline": "Explore DocuElevate at no cost",
        "price_monthly": 0,
        "price_yearly": 0,
        "trial_days": 0,
        "highlight": False,
        # Hard caps — 0 = unlimited
        "lifetime_file_limit": 50,  # total docs ever processed (enforced at upload)
        "daily_upload_limit": 0,  # no per-day cap (lifetime cap applies instead)
        "monthly_upload_limit": 0,  # no per-month cap (lifetime cap applies instead)
        "max_storage_destinations": 1,
        "max_ocr_pages_monthly": 150,  # informational; enforced when OCR quota tracking lands
        "max_file_size_mb": 5,
        "max_mailboxes": 0,  # no email ingestion on free tier
        "api_access": False,
        # Marketing feature list (shown on pricing page)
        "features": [
            "50 documents — lifetime total",
            "150 OCR pages — lifetime total",
            "1 storage destination",
            "5 MB max file size",
            "Basic AI metadata extraction",
            "Community support",
        ],
        "cta": "Get started free",
        "badge": None,
    },
    "starter": {
        "id": "starter",
        "name": "Starter",
        "tagline": "Perfect for individuals getting started",
        "price_monthly": 2.99,
        "price_yearly": 28.99,  # ≈ 80 % of monthly × 12 — save ~19 % (≈ 2½ months free)
        "trial_days": 30,
        "highlight": False,
        "lifetime_file_limit": 0,
        "daily_upload_limit": 0,  # no daily cap
        "monthly_upload_limit": 50,
        "max_storage_destinations": 2,
        "max_ocr_pages_monthly": 300,
        "max_file_size_mb": 25,
        "max_mailboxes": 1,
        "api_access": True,
        "features": [
            "50 documents / month",
            "2 storage destinations",
            "300 OCR pages / month",
            "25 MB max file size",
            "Full AI metadata extraction",
            "1 email ingestion mailbox",
            "API access",
            "Email support",
        ],
        "cta": "Start free trial",
        "badge": None,
    },
    "professional": {
        "id": "professional",
        "name": "Professional",
        "tagline": "For growing teams that need more power",
        "price_monthly": 5.99,
        "price_yearly": 57.99,  # ≈ 80 % of monthly × 12 — save ~19 %
        "trial_days": 30,
        "highlight": True,  # shown as "Most popular"
        "lifetime_file_limit": 0,
        "daily_upload_limit": 0,  # no daily cap
        "monthly_upload_limit": 150,
        "max_storage_destinations": 5,
        "max_ocr_pages_monthly": 750,
        "max_file_size_mb": 100,
        "max_mailboxes": 3,
        "api_access": True,
        "features": [
            "150 documents / month",
            "5 storage destinations",
            "750 OCR pages / month",
            "100 MB max file size",
            "Advanced AI workflows",
            "3 email ingestion mailboxes",
            "Email & URL ingestion",
            "Webhooks",
            "Priority email support",
        ],
        "cta": "Start free trial",
        "badge": "Most Popular",
    },
    "business": {
        "id": "business",
        "name": "Business",
        "tagline": "High-volume processing for organisations",
        "price_monthly": 7.99,
        "price_yearly": 76.99,  # ≈ 80 % of monthly × 12 — save ~20 %
        "trial_days": 30,
        "highlight": False,
        "lifetime_file_limit": 0,
        "daily_upload_limit": 0,  # no daily cap
        "monthly_upload_limit": 300,
        "max_storage_destinations": 10,
        "max_ocr_pages_monthly": 1500,
        "max_file_size_mb": 0,  # unlimited file size
        "max_mailboxes": 0,  # unlimited mailboxes
        "api_access": True,
        "features": [
            "300 documents / month",
            "10 storage destinations",
            "1,500 OCR pages / month",
            "Unlimited file size",
            "All AI processing steps",
            "Unlimited email ingestion mailboxes",
            "All ingestion methods",
            "Webhooks & full API access",
            "Dedicated support",
        ],
        "cta": "Start free trial",
        "badge": "Best Value",
    },
}

# Backward-compatible alias
TIERS = TIER_DEFAULTS

# Display order for the pricing page
TIER_ORDER = ["free", "starter", "professional", "business"]

# Default tier assigned to new users
DEFAULT_TIER = "free"


# ---------------------------------------------------------------------------
# DB → dict conversion
# ---------------------------------------------------------------------------


def _plan_to_dict(plan: Any) -> dict[str, Any]:
    """Convert a SubscriptionPlan ORM object to the same dict shape as TIER_DEFAULTS entries."""
    import json

    features: list[str] = []
    if plan.features:
        try:
            features = json.loads(plan.features)
        except (json.JSONDecodeError, TypeError):
            features = []
    return {
        "id": plan.plan_id,
        "name": plan.name,
        "tagline": plan.tagline or "",
        "price_monthly": plan.price_monthly,
        "price_yearly": plan.price_yearly,
        "trial_days": plan.trial_days,
        "highlight": plan.is_highlighted,
        "lifetime_file_limit": plan.lifetime_file_limit,
        "daily_upload_limit": plan.daily_upload_limit,
        "monthly_upload_limit": plan.monthly_upload_limit,
        "max_storage_destinations": plan.max_storage_destinations,
        "max_ocr_pages_monthly": plan.max_ocr_pages_monthly,
        "max_file_size_mb": plan.max_file_size_mb,
        "max_mailboxes": plan.max_mailboxes,
        "api_access": plan.api_access,
        "features": features,
        "cta": plan.cta_text or "Get started",
        "badge": plan.badge_text,
        "overage_percent": plan.overage_percent,
        "allow_overage_billing": plan.allow_overage_billing,
    }


# ---------------------------------------------------------------------------
# Getters
# ---------------------------------------------------------------------------


def get_tier(tier_id: str, db: Session | None = None) -> dict[str, Any]:
    """Return plan config dict; DB-first when db is provided, falls back to TIER_DEFAULTS."""
    if db is not None:
        from app.models import SubscriptionPlan

        plan = (
            db.query(SubscriptionPlan)
            .filter(
                SubscriptionPlan.plan_id == tier_id,
                SubscriptionPlan.is_active.is_(True),
            )
            .first()
        )
        if plan is not None:
            return _plan_to_dict(plan)
    return TIER_DEFAULTS.get(tier_id, TIER_DEFAULTS["free"])


def get_all_tiers(db: Session | None = None) -> list[dict[str, Any]]:
    """Return plans in display order; DB-first when db is provided."""
    if db is not None:
        from app.models import SubscriptionPlan

        plans = (
            db.query(SubscriptionPlan)
            .filter(SubscriptionPlan.is_active.is_(True))
            .order_by(SubscriptionPlan.sort_order)
            .all()
        )
        if plans:
            return [_plan_to_dict(p) for p in plans]
    return [TIER_DEFAULTS[tid] for tid in TIER_ORDER]


def seed_default_plans(db: Session) -> int:
    """Seed subscription_plans table from TIER_DEFAULTS if the table is empty.

    Called at application startup. Returns the number of plans inserted (0 if already seeded).
    """
    import json

    from app.models import SubscriptionPlan

    try:
        if db.query(SubscriptionPlan).count() > 0:
            return 0
    except Exception:
        return 0  # table may not exist yet during first migration

    inserted = 0
    for sort_order, (_, tier) in enumerate(TIER_DEFAULTS.items()):
        plan = SubscriptionPlan(
            plan_id=tier["id"],
            name=tier["name"],
            tagline=tier.get("tagline", ""),
            price_monthly=tier["price_monthly"],
            price_yearly=tier["price_yearly"],
            trial_days=tier.get("trial_days", 0),
            is_highlighted=tier.get("highlight", False),
            badge_text=tier.get("badge"),
            cta_text=tier.get("cta", "Get started"),
            lifetime_file_limit=tier["lifetime_file_limit"],
            daily_upload_limit=tier["daily_upload_limit"],
            monthly_upload_limit=tier["monthly_upload_limit"],
            max_storage_destinations=tier["max_storage_destinations"],
            max_ocr_pages_monthly=tier["max_ocr_pages_monthly"],
            max_file_size_mb=tier["max_file_size_mb"],
            max_mailboxes=tier.get("max_mailboxes", 0),
            api_access=tier.get("api_access", False),
            features=json.dumps(tier.get("features", [])),
            overage_percent=20,
            allow_overage_billing=False,
            sort_order=sort_order,
            is_active=True,
        )
        db.add(plan)
        inserted += 1
    try:
        db.commit()
        logger.info("Seeded %d default subscription plans", inserted)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to seed subscription plans: %s", exc)
        inserted = 0
    return inserted


# ---------------------------------------------------------------------------
# Usage queries
# ---------------------------------------------------------------------------


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _scalar_count(query) -> int:
    """Execute a count query and return an int, defaulting to 0 for NULL."""
    return query.scalar() or 0


def get_lifetime_file_count(db: Session, owner_id: str) -> int:
    """Total files ever processed by this user (not counting duplicates)."""
    from app.models import FileRecord

    return _scalar_count(
        db.query(func.count(FileRecord.id)).filter(FileRecord.owner_id == owner_id, FileRecord.is_duplicate.is_(False))
    )


def get_today_file_count(db: Session, owner_id: str) -> int:
    """Files processed by this user today (UTC, not counting duplicates)."""
    from app.models import FileRecord

    today = _today_utc()
    return _scalar_count(
        db.query(func.count(FileRecord.id)).filter(
            FileRecord.owner_id == owner_id,
            FileRecord.is_duplicate.is_(False),
            func.date(FileRecord.created_at) == today,
        )
    )


def get_month_file_count(db: Session, owner_id: str) -> int:
    """Files processed by this user this calendar month (UTC, not counting duplicates)."""
    from app.models import FileRecord

    today = _today_utc()
    return _scalar_count(
        db.query(func.count(FileRecord.id)).filter(
            FileRecord.owner_id == owner_id,
            FileRecord.is_duplicate.is_(False),
            func.strftime("%Y-%m", FileRecord.created_at) == today.strftime("%Y-%m"),
        )
    )


def get_year_file_count(db: Session, owner_id: str, period_start: datetime) -> int:
    """Files processed since the start of the current annual subscription period."""
    from app.models import FileRecord

    return _scalar_count(
        db.query(func.count(FileRecord.id)).filter(
            FileRecord.owner_id == owner_id,
            FileRecord.is_duplicate.is_(False),
            FileRecord.created_at >= period_start,
        )
    )


def _months_elapsed(period_start: datetime, now: datetime) -> int:
    """Calendar months elapsed since *period_start*, clamped to [1, 12]."""
    elapsed = (now.year - period_start.year) * 12 + (now.month - period_start.month) + 1
    return max(1, min(elapsed, 12))


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

    Skipped entirely when *owner_id* or *tier_id* is ``None`` (single-user mode).

    Enforcement model
    -----------------
    * **Announced limit** — the quota shown on the pricing page
      (``monthly_upload_limit`` in the plan).
    * **Overage buffer** — each plan stores ``overage_percent`` (default 20).
      Enforcement = announced × (1 + overage_percent / 100). A 150-doc/month
      plan with 20 % buffer is enforced at 180 docs.
    * **Overage flag** — if ``UserProfile.allow_overage`` is ``True``, quota
      checks are bypassed entirely so usage can be billed retroactively.
      (Not yet exposed in the admin UI — baked in for future billing.)
    * **Yearly carry-over** — yearly subscribers have cumulative quota:
      effective limit = monthly_limit × months_elapsed × overage_factor.
      Unused quota from earlier months rolls forward automatically.
    * **No daily cap** — ``daily_upload_limit`` is kept for display purposes
      only; it is never enforced.
    """
    if owner_id is None or tier_id is None:
        return

    tier = get_tier(tier_id, db)

    # Per-plan overage_percent overrides global config default
    overage_percent: int = tier.get("overage_percent", settings.subscription_overage_percent)
    overage_factor: float = 1.0 + overage_percent / 100.0

    from app.models import UserProfile

    profile = db.query(UserProfile).filter(UserProfile.user_id == owner_id).first()
    allow_overage: bool = bool(profile.allow_overage) if profile else False
    billing_cycle: str = (profile.subscription_billing_cycle if profile else None) or "monthly"
    period_start: datetime | None = profile.subscription_period_start if profile else None

    # 1. Lifetime file cap (free tier) — always enforced regardless of overage flag
    lifetime_limit: int = tier["lifetime_file_limit"]
    if lifetime_limit > 0:
        enforcement_limit = int(lifetime_limit * overage_factor)
        count = get_lifetime_file_count(db, owner_id)
        if count >= enforcement_limit:
            raise QuotaExceeded(
                f"Lifetime file limit of {lifetime_limit} reached for the {tier['name']} plan. "
                "Please upgrade to continue processing documents.",
                limit_type="lifetime",
                limit_value=lifetime_limit,
                current_value=count,
            )

    # 2. Monthly cap — bypassed when allow_overage is True (future billing)
    if allow_overage:
        return

    monthly_limit: int = tier["monthly_upload_limit"]
    if monthly_limit > 0:
        if billing_cycle == "yearly" and period_start is not None:
            now = datetime.now(timezone.utc)
            months = _months_elapsed(period_start, now)
            cumulative_budget = int(monthly_limit * months * overage_factor)
            cumulative_used = get_year_file_count(db, owner_id, period_start)
            if cumulative_used >= cumulative_budget:
                raise QuotaExceeded(
                    f"Annual document quota for the {tier['name']} plan has been reached. "
                    "Unused monthly quota carries forward — your limit resets on your annual "
                    "renewal date, or you can upgrade your plan.",
                    limit_type="monthly",
                    limit_value=monthly_limit,
                    current_value=cumulative_used,
                )
        else:
            count = get_month_file_count(db, owner_id)
            enforcement_limit = int(monthly_limit * overage_factor)
            if count >= enforcement_limit:
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
    """Return file counts for *owner_id*, including carry-over data for yearly plans."""
    from app.models import UserProfile

    profile = db.query(UserProfile).filter(UserProfile.user_id == owner_id).first()
    result: dict[str, int] = {
        "lifetime": get_lifetime_file_count(db, owner_id),
        "today": get_today_file_count(db, owner_id),
        "month": get_month_file_count(db, owner_id),
    }
    if profile and (profile.subscription_billing_cycle or "monthly") == "yearly" and profile.subscription_period_start:
        result["year_to_date"] = get_year_file_count(db, owner_id, profile.subscription_period_start)
    return result
