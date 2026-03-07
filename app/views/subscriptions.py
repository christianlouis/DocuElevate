"""View routes for subscription-related pages.

Routes:
  GET /pricing          — public marketing pricing page
  GET /subscription     — authenticated user's current plan & usage
"""

import logging

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.utils.subscription import (
    TIER_ORDER,
    apply_pending_subscription_changes,
    get_all_tiers,
    get_tier,
    get_user_tier_id,
    get_user_usage,
)
from app.views.base import APIRouter, get_db, require_login, templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/pricing", include_in_schema=False)
async def pricing_page(request: Request, db: Session = Depends(get_db)):
    """Public-facing pricing and plans page."""
    tiers = get_all_tiers(db)
    return templates.TemplateResponse(
        "pricing.html",
        {
            "request": request,
            "tiers": tiers,
            "tier_order": TIER_ORDER,
        },
    )


@router.get("/subscription", include_in_schema=False)
@require_login
async def my_subscription_page(request: Request, db: Session = Depends(get_db)):
    """Authenticated user's subscription status and usage page."""
    from app.config import settings
    from app.models import UserProfile

    user = request.session.get("user") or {}
    owner_id: str = user.get("username") or user.get("email") or user.get("sub") or ""

    if settings.multi_user_enabled and owner_id:
        # Apply any pending changes that have become due before rendering
        apply_pending_subscription_changes(db, owner_id)

        tier_id = get_user_tier_id(db, owner_id)
        usage = get_user_usage(db, owner_id)
        profile = db.query(UserProfile).filter(UserProfile.user_id == owner_id).first()
        pending_tier_id = profile.subscription_change_pending_tier if profile else None
        pending_date = profile.subscription_change_pending_date if profile else None
        period_start = profile.subscription_period_start if profile else None
    else:
        tier_id = "business"
        usage = None
        pending_tier_id = None
        pending_date = None
        period_start = None

    tier = get_tier(tier_id, db)
    all_tiers = get_all_tiers(db)
    pending_tier = get_tier(pending_tier_id, db) if pending_tier_id else None

    return templates.TemplateResponse(
        "subscription.html",
        {
            "request": request,
            "tier": tier,
            "tier_id": tier_id,
            "usage": usage,
            "all_tiers": all_tiers,
            "multi_user_enabled": settings.multi_user_enabled,
            "owner_id": owner_id,
            "tier_order": TIER_ORDER,
            "pending_tier_id": pending_tier_id,
            "pending_tier": pending_tier,
            "pending_date": pending_date,
            "period_start": period_start,
        },
    )
