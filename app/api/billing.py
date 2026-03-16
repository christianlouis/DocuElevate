"""Stripe billing integration for DocuElevate.

Provides three endpoints:
- POST /api/billing/create-checkout-session — starts Stripe Checkout for a plan upgrade
- POST /api/billing/create-portal-session   — opens Stripe Customer Portal (manage/cancel)
- POST /api/billing/webhook                 — handles Stripe webhook events
- GET  /api/billing/success                 — success landing page after checkout

Stripe Python SDK license: MIT (compatible with this project's Apache 2.0 license).

GDPR:  Stripe acts as a data processor under a Data Processing Agreement (DPA).
       Stripe is SOC 2 Type II certified and supports EU data residency.
SOC2:  Stripe is SOC 2 Type II certified.
EU VAT: Configure Stripe Tax in the Stripe Dashboard for automatic VAT collection.
"""

import json
import logging
import pathlib
from datetime import datetime, timezone
from typing import Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_login
from app.config import settings
from app.database import get_db
from app.models import SubscriptionPlan, UserProfile
from app.utils.i18n import translate as _translate
from app.utils.user_scope import get_current_owner_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])

_templates_dir = pathlib.Path(__file__).parents[2] / "frontend" / "templates"
_templates = Jinja2Templates(directory=str(_templates_dir))
_templates.env.globals["_"] = lambda key, **kwargs: _translate(key, "en", **kwargs)


def _get_stripe() -> stripe.StripeClient | None:
    """Return a configured Stripe client, or None when not configured."""
    if not settings.stripe_secret_key:
        return None
    return stripe.StripeClient(settings.stripe_secret_key)


def _get_or_create_stripe_customer(
    client: stripe.StripeClient,
    db: Session,
    owner_id: str,
    email: str | None,
    name: str | None,
) -> str:
    """Return the Stripe customer_id for *owner_id*, creating one if needed.

    Args:
        client: Configured Stripe client.
        db: Database session.
        owner_id: Stable user identifier.
        email: User's email for the Stripe customer record.
        name: User's display name for the Stripe customer record.

    Returns:
        The Stripe customer ID string.
    """
    profile = db.query(UserProfile).filter(UserProfile.user_id == owner_id).first()
    if profile and profile.stripe_customer_id:
        return profile.stripe_customer_id

    customer = client.customers.create(
        params={
            "email": email or "",
            "name": name or "",
            "metadata": {"docuelevate_user_id": owner_id},
        }
    )
    if profile:
        profile.stripe_customer_id = customer.id
        db.commit()
    return customer.id


class CheckoutSessionBody(BaseModel):
    """Request body for creating a Stripe Checkout session."""

    plan_id: str
    billing_cycle: str = "monthly"  # "monthly" | "yearly"


class PortalSessionBody(BaseModel):
    """Request body for creating a Stripe Customer Portal session."""

    return_url: str | None = None


@router.post("/create-checkout-session", summary="Create a Stripe Checkout session for a plan upgrade")
@require_login
async def create_checkout_session(
    request: Request,
    body: CheckoutSessionBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a Stripe Checkout session.

    The client should redirect the user to the returned ``checkout_url``.

    Raises:
        503: Stripe is not configured.
        404: Plan not found or has no Stripe price configured.
    """
    client = _get_stripe()
    if not client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing is not configured.")

    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.plan_id == body.plan_id).first()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan {body.plan_id!r} not found.")

    price_id = plan.stripe_price_id_yearly if body.billing_cycle == "yearly" else plan.stripe_price_id_monthly
    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Stripe price ID not configured for plan {body.plan_id!r} ({body.billing_cycle}). "
                "Please set it in the Admin Plan Designer."
            ),
        )

    user = request.session.get("user") or {}
    owner_id = get_current_owner_id(request) or user.get("email") or ""
    email = user.get("email")
    name = user.get("name")

    customer_id = _get_or_create_stripe_customer(client, db, owner_id, email, name)

    base = str(request.base_url).rstrip("/")
    success_url = settings.stripe_success_url or f"{base}/api/billing/success"
    cancel_url = settings.stripe_cancel_url or f"{base}/pricing"

    trial_days = plan.trial_days if plan.trial_days > 0 else None

    session_params: dict[str, Any] = {
        "customer": customer_id,
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url + "?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": cancel_url,
        "subscription_data": {
            "metadata": {
                "docuelevate_user_id": owner_id,
                "plan_id": body.plan_id,
                "billing_cycle": body.billing_cycle,
            },
        },
        "metadata": {"docuelevate_user_id": owner_id, "plan_id": body.plan_id},
        "allow_promotion_codes": True,
        "billing_address_collection": "auto",
        "tax_id_collection": {"enabled": True},
        "automatic_tax": {"enabled": True},
    }
    if trial_days:
        session_params["subscription_data"]["trial_period_days"] = trial_days

    checkout_session = client.checkout.sessions.create(params=session_params)

    logger.info(
        "Created Stripe checkout session %s for user plan %s",
        checkout_session.id,
        body.plan_id,
    )
    return {"checkout_url": checkout_session.url, "session_id": checkout_session.id}


@router.post("/create-portal-session", summary="Create a Stripe Customer Portal session")
@require_login
async def create_portal_session(
    request: Request,
    body: PortalSessionBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a Stripe Customer Portal session for subscription self-management.

    Raises:
        503: Stripe not configured.
        404: No Stripe customer found for this user.
    """
    client = _get_stripe()
    if not client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing is not configured.")

    user = request.session.get("user") or {}
    owner_id = get_current_owner_id(request) or user.get("email") or ""

    profile = db.query(UserProfile).filter(UserProfile.user_id == owner_id).first()
    if not profile or not profile.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No billing account found. Please subscribe to a plan first.",
        )

    base = str(request.base_url).rstrip("/")
    return_url = body.return_url or f"{base}/subscription"

    portal = client.billing_portal.sessions.create(
        params={
            "customer": profile.stripe_customer_id,
            "return_url": return_url,
        }
    )

    logger.info("Created Stripe portal session for user")
    return {"portal_url": portal.url}


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    """Handle Stripe webhook events.

    Syncs subscription status to UserProfile.subscription_tier.

    Events handled:

    - ``checkout.session.completed``    — activate subscription after payment
    - ``customer.subscription.updated`` — sync tier change
    - ``customer.subscription.deleted`` — downgrade to free on cancellation
    - ``invoice.payment_failed``        — log failed payment
    """
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing not configured.")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        if settings.stripe_webhook_secret:
            event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
        else:
            logger.warning(
                "[SECURITY] STRIPE_WEBHOOK_SECRET is not configured. "
                "Webhook events are accepted without signature verification. "
                "Set STRIPE_WEBHOOK_SECRET in production to prevent spoofed events."
            )
            event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)
    except stripe.SignatureVerificationError:
        logger.warning("[SECURITY] Stripe webhook signature verification failed")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature.")
    except Exception as exc:
        logger.warning("Failed to parse Stripe webhook: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload.")

    _handle_stripe_event(db, event)
    return {"status": "ok"}


@router.get("/success", include_in_schema=False)
@require_login
async def billing_success(request: Request) -> Any:
    """Show a success page after a completed Stripe Checkout."""
    return _templates.TemplateResponse("billing_success.html", {"request": request})


# ---------------------------------------------------------------------------
# Admin: Stripe status + sync helpers
# ---------------------------------------------------------------------------


def _require_admin(request: Request) -> None:
    """Raise 403 if the current session user is not an admin."""
    user = request.session.get("user") or {}
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")


@router.get("/stripe/status", summary="Check Stripe connection and plan sync status (admin only)")
@require_login
async def stripe_status(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return Stripe connection health and per-plan price-ID sync status.

    Returns a JSON object with:
    - ``configured``: whether STRIPE_SECRET_KEY is set
    - ``connection``: ``"ok"`` or an error string (live/test mode label)
    - ``mode``: ``"live"`` | ``"test"`` | ``null``
    - ``plans``: list of plan objects with ``plan_id``, ``name``,
      ``stripe_price_id_monthly``, ``stripe_price_id_yearly``, ``synced``

    Raises:
        403: Not admin.
        503: Stripe not configured.
    """
    _require_admin(request)

    if not settings.stripe_secret_key:
        return {
            "configured": False,
            "connection": "not_configured",
            "mode": None,
            "plans": [],
        }

    client = _get_stripe()
    # Probe Stripe with a lightweight account fetch
    mode: str | None = None
    connection_status = "ok"
    try:
        account = client.accounts.retrieve("me")  # type: ignore[arg-type]
        livemode = getattr(account, "livemode", None)
        if livemode is True:
            mode = "live"
        elif livemode is False:
            mode = "test"
        else:
            mode = "test" if settings.stripe_secret_key.startswith("sk_test_") else "live"
    except Exception:
        logger.exception("Stripe connection check failed")
        connection_status = "error"
        mode = "test" if settings.stripe_secret_key.startswith("sk_test_") else "live"

    plans = db.query(SubscriptionPlan).order_by(SubscriptionPlan.sort_order).all()
    plan_statuses = []
    for plan in plans:
        has_monthly = bool(plan.stripe_price_id_monthly)
        has_yearly = bool(plan.stripe_price_id_yearly)
        is_paid = plan.price_monthly > 0 or plan.price_yearly > 0
        synced = (not is_paid) or (has_monthly and (not plan.price_yearly or has_yearly))
        plan_statuses.append(
            {
                "plan_id": plan.plan_id,
                "name": plan.name,
                "price_monthly": plan.price_monthly,
                "price_yearly": plan.price_yearly,
                "stripe_price_id_monthly": plan.stripe_price_id_monthly,
                "stripe_price_id_yearly": plan.stripe_price_id_yearly,
                "synced": synced,
            }
        )

    return {
        "configured": True,
        "connection": connection_status,
        "mode": mode,
        "webhook_secret_configured": bool(settings.stripe_webhook_secret),
        "plans": plan_statuses,
        "webhook_endpoint": str(request.base_url).rstrip("/") + "/api/billing/webhook",
    }


@router.post("/stripe/sync-plans", summary="Auto-create Stripe products and prices for all plans (admin only)")
@require_login
async def stripe_sync_plans(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Create Stripe Product + Price objects for every paid plan that is missing them.

    For each paid plan (``price_monthly > 0``) that lacks a ``stripe_price_id_monthly``,
    this endpoint:

    1. Creates a Stripe *Product* named after the plan.
    2. Creates a Stripe *Price* for the monthly amount.
    3. Optionally creates a yearly Price if ``price_yearly > 0``.
    4. Persists the resulting ``price_id`` values back into ``SubscriptionPlan``.

    Already-synced plans (those that already have ``stripe_price_id_monthly``) are
    skipped — existing prices in Stripe are never modified.

    Raises:
        403: Not admin.
        503: Stripe not configured.
    """
    _require_admin(request)

    client = _get_stripe()
    if not client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing is not configured.")

    plans = db.query(SubscriptionPlan).order_by(SubscriptionPlan.sort_order).all()
    results: list[dict[str, Any]] = []

    for plan in plans:
        is_paid = plan.price_monthly > 0 or plan.price_yearly > 0
        if not is_paid:
            results.append({"plan_id": plan.plan_id, "name": plan.name, "status": "skipped_free"})
            continue

        already_has_monthly = bool(plan.stripe_price_id_monthly)
        already_has_yearly = bool(plan.stripe_price_id_yearly)

        if already_has_monthly and (not plan.price_yearly or already_has_yearly):
            results.append({"plan_id": plan.plan_id, "name": plan.name, "status": "already_synced"})
            continue

        try:
            # Create (or look up) the Stripe Product for this plan
            product = client.products.create(
                params={
                    "name": str(plan.name),
                    "metadata": {"docuelevate_plan_id": plan.plan_id},
                }
            )

            changed = False

            # Monthly price
            if not already_has_monthly and plan.price_monthly > 0:
                monthly_price = client.prices.create(
                    params={
                        "product": product.id,
                        "unit_amount": int(round(plan.price_monthly * 100)),
                        "currency": "usd",
                        "recurring": {"interval": "month"},
                        "metadata": {"docuelevate_plan_id": plan.plan_id, "billing_cycle": "monthly"},
                    }
                )
                plan.stripe_price_id_monthly = monthly_price.id
                changed = True

            # Yearly price
            if not already_has_yearly and plan.price_yearly > 0:
                yearly_price = client.prices.create(
                    params={
                        "product": product.id,
                        "unit_amount": int(round(plan.price_yearly * 100)),
                        "currency": "usd",
                        "recurring": {"interval": "year"},
                        "metadata": {"docuelevate_plan_id": plan.plan_id, "billing_cycle": "yearly"},
                    }
                )
                plan.stripe_price_id_yearly = yearly_price.id
                changed = True

            if changed:
                db.commit()
                logger.info(
                    "Stripe sync: created product/prices for plan %s (product %s)",
                    plan.plan_id,
                    product.id,
                )

            results.append(
                {
                    "plan_id": plan.plan_id,
                    "name": plan.name,
                    "status": "created",
                    "stripe_price_id_monthly": plan.stripe_price_id_monthly,
                    "stripe_price_id_yearly": plan.stripe_price_id_yearly,
                }
            )

        except Exception as exc:
            db.rollback()
            logger.error("Stripe sync failed for plan %s: %s", plan.plan_id, exc)
            results.append(
                {
                    "plan_id": plan.plan_id,
                    "name": str(plan.name),
                    "status": "error",
                    "detail": str(exc),
                }
            )

    return {"results": results}


def _handle_stripe_event(db: Session, event: Any) -> None:
    """Dispatch Stripe event to the appropriate handler.

    Args:
        db: Database session.
        event: Parsed Stripe event object.
    """
    etype = event.get("type", "") if isinstance(event, dict) else getattr(event, "type", "")
    data_obj = (
        event.get("data", {}).get("object", {})
        if isinstance(event, dict)
        else getattr(getattr(event, "data", None), "object", {})
    )

    if etype == "checkout.session.completed":
        _on_checkout_completed(db, data_obj)
    elif etype == "customer.subscription.updated":
        _on_subscription_updated(db, data_obj)
    elif etype == "customer.subscription.deleted":
        _on_subscription_deleted(db, data_obj)
    elif etype == "invoice.payment_failed":
        customer_id = data_obj.get("customer", "") if isinstance(data_obj, dict) else getattr(data_obj, "customer", "")
        logger.warning("Stripe invoice payment failed for customer %s", customer_id)
    else:
        logger.debug("Unhandled Stripe event type: %s", etype)


def _resolve_user_id_from_customer(db: Session, customer_id: str) -> str | None:
    """Look up the DocuElevate user_id for a Stripe customer_id.

    Args:
        db: Database session.
        customer_id: Stripe customer ID.

    Returns:
        The matching ``UserProfile.user_id``, or ``None`` if not found.
    """
    profile = db.query(UserProfile).filter(UserProfile.stripe_customer_id == customer_id).first()
    return profile.user_id if profile else None


def _resolve_plan_id_from_price(db: Session, price_id: str) -> str | None:
    """Map a Stripe price_id to a DocuElevate plan_id via SubscriptionPlan.

    Args:
        db: Database session.
        price_id: Stripe price ID.

    Returns:
        The matching ``SubscriptionPlan.plan_id``, or ``None`` if not found.
    """
    plan = (
        db.query(SubscriptionPlan)
        .filter(
            (SubscriptionPlan.stripe_price_id_monthly == price_id)
            | (SubscriptionPlan.stripe_price_id_yearly == price_id)
        )
        .first()
    )
    return plan.plan_id if plan else None


def _on_checkout_completed(db: Session, data: Any) -> None:
    """Activate a subscription after a successful checkout.

    Args:
        db: Database session.
        data: Stripe ``checkout.session`` object.
    """
    meta = data.get("metadata") or {} if isinstance(data, dict) else getattr(data, "metadata", {}) or {}
    user_id = meta.get("docuelevate_user_id") if isinstance(meta, dict) else getattr(meta, "docuelevate_user_id", None)
    plan_id = meta.get("plan_id") if isinstance(meta, dict) else getattr(meta, "plan_id", None)
    billing_cycle = (
        meta.get("billing_cycle", "monthly") if isinstance(meta, dict) else getattr(meta, "billing_cycle", "monthly")
    )
    if not user_id:
        return

    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile and plan_id:
        profile.subscription_tier = plan_id
        profile.subscription_billing_cycle = billing_cycle
        profile.subscription_period_start = datetime.now(tz=timezone.utc)
        customer_id = data.get("customer", "") if isinstance(data, dict) else getattr(data, "customer", "")
        if customer_id:
            profile.stripe_customer_id = customer_id
        db.commit()
        logger.info("Activated plan %s/%s after checkout", plan_id, billing_cycle)


def _on_subscription_updated(db: Session, data: Any) -> None:
    """Sync tier change when a subscription is updated.

    Args:
        db: Database session.
        data: Stripe ``customer.subscription`` object.
    """
    customer_id = data.get("customer", "") if isinstance(data, dict) else getattr(data, "customer", "")
    user_id = _resolve_user_id_from_customer(db, customer_id)
    if not user_id:
        return

    items_data = data.get("items") or {} if isinstance(data, dict) else getattr(data, "items", None) or {}
    items = items_data.get("data") or [] if isinstance(items_data, dict) else getattr(items_data, "data", []) or []
    if not items:
        return

    first_item = items[0]
    price_obj = (
        first_item.get("price") or {} if isinstance(first_item, dict) else getattr(first_item, "price", {}) or {}
    )
    price_id = price_obj.get("id") if isinstance(price_obj, dict) else getattr(price_obj, "id", None)
    if not price_id:
        return

    plan_id = _resolve_plan_id_from_price(db, price_id)
    if not plan_id:
        logger.warning("Unknown Stripe price_id %s on subscription.updated", price_id)
        return

    recurring = (
        price_obj.get("recurring", {}) if isinstance(price_obj, dict) else getattr(price_obj, "recurring", {}) or {}
    )
    interval = (
        recurring.get("interval", "month") if isinstance(recurring, dict) else getattr(recurring, "interval", "month")
    )
    billing_cycle = "yearly" if interval == "year" else "monthly"

    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile:
        profile.subscription_tier = plan_id
        profile.subscription_billing_cycle = billing_cycle
        db.commit()
        logger.info("Updated subscription to %s/%s", plan_id, billing_cycle)


def _on_subscription_deleted(db: Session, data: Any) -> None:
    """Downgrade user to free tier after subscription cancellation.

    Args:
        db: Database session.
        data: Stripe ``customer.subscription`` object.
    """
    customer_id = data.get("customer", "") if isinstance(data, dict) else getattr(data, "customer", "")
    user_id = _resolve_user_id_from_customer(db, customer_id)
    if not user_id:
        return

    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile:
        profile.subscription_tier = "free"
        profile.subscription_billing_cycle = "monthly"
        db.commit()
        logger.info("Downgraded user %s to free tier after subscription cancellation", user_id)
