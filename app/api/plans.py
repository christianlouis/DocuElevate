"""REST API for subscription plan CRUD.

Endpoints:
  GET  /api/plans/          — list active plans (public)
  GET  /api/plans/admin     — list all plans inc. inactive (admin only)
  POST /api/plans/          — create plan (admin only)
  GET  /api/plans/{plan_id} — get single active plan (public)
  PUT  /api/plans/{plan_id} — update plan (admin only)
  DELETE /api/plans/{plan_id} — delete plan (admin only)
  POST /api/plans/seed      — seed default plans (admin only)
  POST /api/plans/reorder   — set sort_order for multiple plans (admin only)
"""

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SubscriptionPlan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/plans", tags=["plans"])

DbSession = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Auth helper (admin-only)
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


class PlanUpsert(BaseModel):
    """Body for creating or updating a subscription plan."""

    name: str
    tagline: str | None = None
    price_monthly: float = 0.0
    price_yearly: float = 0.0
    trial_days: int = 0
    lifetime_file_limit: int = 0
    daily_upload_limit: int = 0
    monthly_upload_limit: int = 0
    max_storage_destinations: int = 0
    max_ocr_pages_monthly: int = 0
    max_file_size_mb: int = 0
    max_mailboxes: int = 0
    overage_percent: int = Field(default=20, ge=0, le=200)
    allow_overage_billing: bool = False
    overage_price_per_doc: float | None = None
    overage_price_per_ocr_page: float | None = None
    is_active: bool = True
    is_highlighted: bool = False
    badge_text: str | None = None
    cta_text: str = "Get started"
    sort_order: int = 0
    features: list[str] = []
    api_access: bool = False
    stripe_price_id_monthly: str | None = None
    stripe_price_id_yearly: str | None = None


class ReorderBody(BaseModel):
    """Body for reordering plans."""

    order: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _plan_to_response(plan: SubscriptionPlan) -> dict[str, Any]:
    features: list[str] = []
    if plan.features:
        try:
            features = json.loads(plan.features)
        except (json.JSONDecodeError, TypeError):
            features = []
    return {
        "id": plan.id,
        "plan_id": plan.plan_id,
        "name": plan.name,
        "tagline": plan.tagline,
        "price_monthly": plan.price_monthly,
        "price_yearly": plan.price_yearly,
        "trial_days": plan.trial_days,
        "lifetime_file_limit": plan.lifetime_file_limit,
        "daily_upload_limit": plan.daily_upload_limit,
        "monthly_upload_limit": plan.monthly_upload_limit,
        "max_storage_destinations": plan.max_storage_destinations,
        "max_ocr_pages_monthly": plan.max_ocr_pages_monthly,
        "max_file_size_mb": plan.max_file_size_mb,
        "max_mailboxes": plan.max_mailboxes,
        "overage_percent": plan.overage_percent,
        "allow_overage_billing": plan.allow_overage_billing,
        "overage_price_per_doc": plan.overage_price_per_doc,
        "overage_price_per_ocr_page": plan.overage_price_per_ocr_page,
        "is_active": plan.is_active,
        "is_highlighted": plan.is_highlighted,
        "badge_text": plan.badge_text,
        "cta_text": plan.cta_text,
        "sort_order": plan.sort_order,
        "features": features,
        "api_access": plan.api_access,
        "stripe_price_id_monthly": plan.stripe_price_id_monthly,
        "stripe_price_id_yearly": plan.stripe_price_id_yearly,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }


def _apply_body(plan: SubscriptionPlan, body: PlanUpsert) -> None:
    """Apply PlanUpsert fields onto a SubscriptionPlan ORM object."""
    plan.name = body.name
    plan.tagline = body.tagline
    plan.price_monthly = body.price_monthly
    plan.price_yearly = body.price_yearly
    plan.trial_days = body.trial_days
    plan.lifetime_file_limit = body.lifetime_file_limit
    plan.daily_upload_limit = body.daily_upload_limit
    plan.monthly_upload_limit = body.monthly_upload_limit
    plan.max_storage_destinations = body.max_storage_destinations
    plan.max_ocr_pages_monthly = body.max_ocr_pages_monthly
    plan.max_file_size_mb = body.max_file_size_mb
    plan.max_mailboxes = body.max_mailboxes
    plan.overage_percent = body.overage_percent
    plan.allow_overage_billing = body.allow_overage_billing
    plan.overage_price_per_doc = body.overage_price_per_doc
    plan.overage_price_per_ocr_page = body.overage_price_per_ocr_page
    plan.is_active = body.is_active
    plan.is_highlighted = body.is_highlighted
    plan.badge_text = body.badge_text
    plan.cta_text = body.cta_text
    plan.sort_order = body.sort_order
    plan.features = json.dumps(body.features)
    plan.api_access = body.api_access
    plan.stripe_price_id_monthly = body.stripe_price_id_monthly or None
    plan.stripe_price_id_yearly = body.stripe_price_id_yearly or None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", summary="List active plans (public)")
def list_active_plans(db: DbSession) -> dict[str, Any]:
    """Return all active plans in sort order. Public endpoint — no auth required."""
    plans = (
        db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.is_active.is_(True))
        .order_by(SubscriptionPlan.sort_order)
        .all()
    )
    return {"plans": [_plan_to_response(p) for p in plans]}


@router.get("/admin", summary="List all plans including inactive (admin only)")
def list_all_plans(db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Return all plans (active and inactive) in sort order. Admin only."""
    plans = db.query(SubscriptionPlan).order_by(SubscriptionPlan.sort_order).all()
    return {"plans": [_plan_to_response(p) for p in plans]}


@router.post("/seed", summary="Seed default plans (admin only)", status_code=status.HTTP_200_OK)
def seed_plans(db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Seed the subscription_plans table from TIER_DEFAULTS. No-op if plans already exist."""
    from app.utils.subscription import seed_default_plans

    inserted = seed_default_plans(db)
    return {"inserted": inserted, "message": f"Seeded {inserted} default plan(s)."}


@router.post("/reorder", summary="Reorder plans (admin only)")
def reorder_plans(body: ReorderBody, db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Update sort_order for each plan_id in *body.order* (position = index in list)."""
    updated = 0
    for sort_order, plan_id in enumerate(body.order):
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.plan_id == plan_id).first()
        if plan:
            plan.sort_order = sort_order
            updated += 1
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reorder plans")
    return {"updated": updated}


@router.post("/", summary="Create a new plan (admin only)", status_code=status.HTTP_201_CREATED)
def create_plan(plan_id: str, body: PlanUpsert, db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Create a new subscription plan with the given *plan_id* slug."""
    existing = db.query(SubscriptionPlan).filter(SubscriptionPlan.plan_id == plan_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Plan '{plan_id}' already exists.",
        )
    plan = SubscriptionPlan(plan_id=plan_id)
    _apply_body(plan, body)
    db.add(plan)
    try:
        db.commit()
        db.refresh(plan)
    except Exception:
        db.rollback()
        raise
    logger.info("Admin created subscription plan '%s'", plan_id)
    return _plan_to_response(plan)


@router.get("/{plan_id}", summary="Get a single active plan (public)")
def get_plan(plan_id: str, db: DbSession) -> dict[str, Any]:
    """Return a single active plan by plan_id. Public endpoint."""
    plan = (
        db.query(SubscriptionPlan)
        .filter(
            SubscriptionPlan.plan_id == plan_id,
            SubscriptionPlan.is_active.is_(True),
        )
        .first()
    )
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan '{plan_id}' not found.")
    return _plan_to_response(plan)


@router.put("/{plan_id}", summary="Update an existing plan (admin only)")
def update_plan(plan_id: str, body: PlanUpsert, db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Update an existing subscription plan. Admin only."""
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.plan_id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan '{plan_id}' not found.")
    _apply_body(plan, body)
    try:
        db.commit()
        db.refresh(plan)
    except Exception:
        db.rollback()
        raise
    logger.info("Admin updated subscription plan '%s'", plan_id)
    return _plan_to_response(plan)


@router.delete("/{plan_id}", summary="Delete a plan (admin only)", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: str, db: DbSession, _admin: AdminUser) -> None:
    """Delete a subscription plan. Admin only."""
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.plan_id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan '{plan_id}' not found.")
    try:
        db.delete(plan)
        db.commit()
    except Exception:
        db.rollback()
        raise
    logger.info("Admin deleted subscription plan '%s'", plan_id)
