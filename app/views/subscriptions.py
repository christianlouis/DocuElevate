"""View routes for subscription-related pages.

Routes:
  GET /pricing          — public marketing pricing page
  GET /subscription     — authenticated user's current plan & usage
"""

import logging

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.utils.subscription import TIER_ORDER, get_all_tiers, get_tier, get_user_tier_id, get_user_usage
from app.views.base import APIRouter, get_db, require_login, templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/pricing", include_in_schema=False)
async def pricing_page(request: Request):
    """Public-facing pricing and plans page."""
    tiers = get_all_tiers()
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

    user = request.session.get("user") or {}
    owner_id: str = user.get("username") or user.get("email") or user.get("sub") or ""

    if settings.multi_user_enabled and owner_id:
        tier_id = get_user_tier_id(db, owner_id)
        usage = get_user_usage(db, owner_id)
    else:
        tier_id = "business"
        usage = None

    tier = get_tier(tier_id)
    all_tiers = get_all_tiers()

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
        },
    )
