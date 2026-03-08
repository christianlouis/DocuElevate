"""Tests for the Stripe billing API endpoints.

Covers:
- POST /api/billing/create-checkout-session
- POST /api/billing/create-portal-session
- POST /api/billing/webhook (all event types)
- GET  /api/billing/success
- Internal helpers: _handle_stripe_event, _on_checkout_completed,
  _on_subscription_updated, _on_subscription_deleted
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.billing import (
    _handle_stripe_event,
    _on_checkout_completed,
    _on_subscription_deleted,
    _on_subscription_updated,
    _resolve_plan_id_from_price,
    _resolve_user_id_from_customer,
)
from app.database import Base, get_db
from app.models import SubscriptionPlan, UserProfile

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def bill_engine():
    """In-memory SQLite engine for billing tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def bill_session(bill_engine):
    """DB session for one test."""
    Session = sessionmaker(bind=bill_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def bill_client(bill_engine):
    """TestClient with DB dependency overridden and a logged-in session."""
    from app.main import app

    Session = sessionmaker(bind=bill_engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def starter_plan(bill_session):
    """A SubscriptionPlan with Stripe price IDs in the DB."""
    plan = SubscriptionPlan(
        plan_id="starter",
        name="Starter",
        price_monthly=9.0,
        price_yearly=90.0,
        trial_days=0,
        stripe_price_id_monthly="price_monthly_starter",
        stripe_price_id_yearly="price_yearly_starter",
    )
    bill_session.add(plan)
    bill_session.commit()
    return plan


@pytest.fixture()
def user_profile(bill_session):
    """A UserProfile for user1@example.com."""
    profile = UserProfile(
        user_id="user1@example.com",
        display_name="Test User",
        stripe_customer_id=None,
    )
    bill_session.add(profile)
    bill_session.commit()
    return profile


# ---------------------------------------------------------------------------
# Tests: _get_stripe returns None when not configured
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_stripe_returns_none_when_not_configured():
    """_get_stripe returns None when stripe_secret_key is not set."""
    from app.api.billing import _get_stripe

    with patch("app.api.billing.settings") as mock_settings:
        mock_settings.stripe_secret_key = None
        result = _get_stripe()
    assert result is None


@pytest.mark.unit
def test_get_stripe_returns_client_when_configured():
    """_get_stripe returns a StripeClient when key is configured."""
    from app.api.billing import _get_stripe

    with patch("app.api.billing.settings") as mock_settings:
        mock_settings.stripe_secret_key = "sk_test_fake"
        result = _get_stripe()
    assert result is not None


# ---------------------------------------------------------------------------
# Tests: create-checkout-session
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_create_checkout_session_stripe_not_configured(bill_client):
    """POST /api/billing/create-checkout-session returns 503 when Stripe not set."""
    with patch("app.api.billing._get_stripe", return_value=None):
        resp = bill_client.post(
            "/api/billing/create-checkout-session",
            json={"plan_id": "starter", "billing_cycle": "monthly"},
        )
    assert resp.status_code == 503


@pytest.mark.integration
def test_create_checkout_session_plan_not_found(bill_client):
    """POST /api/billing/create-checkout-session returns 404 for unknown plan."""
    mock_client = MagicMock()
    with patch("app.api.billing._get_stripe", return_value=mock_client):
        resp = bill_client.post(
            "/api/billing/create-checkout-session",
            json={"plan_id": "nonexistent", "billing_cycle": "monthly"},
        )
    assert resp.status_code == 404


@pytest.mark.integration
def test_create_checkout_session_no_price_id(bill_client, bill_session):
    """POST /api/billing/create-checkout-session returns 404 when price ID not set."""
    plan = SubscriptionPlan(
        plan_id="noprice",
        name="No Price",
        price_monthly=5.0,
        price_yearly=50.0,
        trial_days=0,
        stripe_price_id_monthly=None,
        stripe_price_id_yearly=None,
    )
    bill_session.add(plan)
    bill_session.commit()

    mock_client = MagicMock()
    with patch("app.api.billing._get_stripe", return_value=mock_client):
        resp = bill_client.post(
            "/api/billing/create-checkout-session",
            json={"plan_id": "noprice", "billing_cycle": "monthly"},
        )
    assert resp.status_code == 404


@pytest.mark.integration
def test_create_checkout_session_success(bill_client, starter_plan, user_profile):
    """POST /api/billing/create-checkout-session returns checkout_url on success."""
    mock_client = MagicMock()
    mock_customer = MagicMock()
    mock_customer.id = "cus_test123"
    mock_session = MagicMock()
    mock_session.id = "cs_test456"
    mock_session.url = "https://checkout.stripe.com/test"

    mock_client.customers.create.return_value = mock_customer
    mock_client.checkout.sessions.create.return_value = mock_session

    with (
        patch("app.api.billing._get_stripe", return_value=mock_client),
        patch("app.api.billing.get_current_owner_id", return_value="user1@example.com"),
    ):
        resp = bill_client.post(
            "/api/billing/create-checkout-session",
            json={"plan_id": "starter", "billing_cycle": "monthly"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "checkout_url" in data
    assert data["checkout_url"] == "https://checkout.stripe.com/test"


@pytest.mark.integration
def test_create_checkout_session_yearly(bill_client, starter_plan, user_profile):
    """POST /api/billing/create-checkout-session uses yearly price ID for yearly cycle."""
    mock_client = MagicMock()
    mock_customer = MagicMock()
    mock_customer.id = "cus_test123"
    mock_session = MagicMock()
    mock_session.id = "cs_test456"
    mock_session.url = "https://checkout.stripe.com/yearly"

    mock_client.customers.create.return_value = mock_customer
    mock_client.checkout.sessions.create.return_value = mock_session

    with (
        patch("app.api.billing._get_stripe", return_value=mock_client),
        patch("app.api.billing.get_current_owner_id", return_value="user1@example.com"),
    ):
        resp = bill_client.post(
            "/api/billing/create-checkout-session",
            json={"plan_id": "starter", "billing_cycle": "yearly"},
        )
    assert resp.status_code == 200
    # Verify yearly price ID was used
    call_params = mock_client.checkout.sessions.create.call_args[1]["params"]
    assert call_params["line_items"][0]["price"] == "price_yearly_starter"


# ---------------------------------------------------------------------------
# Tests: create-portal-session
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_create_portal_session_stripe_not_configured(bill_client):
    """POST /api/billing/create-portal-session returns 503 when not configured."""
    with patch("app.api.billing._get_stripe", return_value=None):
        resp = bill_client.post("/api/billing/create-portal-session", json={})
    assert resp.status_code == 503


@pytest.mark.integration
def test_create_portal_session_no_customer(bill_client, user_profile):
    """POST /api/billing/create-portal-session returns 404 when no Stripe customer."""
    mock_client = MagicMock()
    with (
        patch("app.api.billing._get_stripe", return_value=mock_client),
        patch("app.api.billing.get_current_owner_id", return_value="user1@example.com"),
    ):
        resp = bill_client.post("/api/billing/create-portal-session", json={})
    assert resp.status_code == 404


@pytest.mark.integration
def test_create_portal_session_success(bill_client, bill_session, user_profile):
    """POST /api/billing/create-portal-session returns portal_url on success."""
    user_profile.stripe_customer_id = "cus_existing"
    bill_session.commit()

    mock_client = MagicMock()
    mock_portal = MagicMock()
    mock_portal.url = "https://billing.stripe.com/portal/test"
    mock_client.billing_portal.sessions.create.return_value = mock_portal

    with (
        patch("app.api.billing._get_stripe", return_value=mock_client),
        patch("app.api.billing.get_current_owner_id", return_value="user1@example.com"),
    ):
        resp = bill_client.post("/api/billing/create-portal-session", json={})
    assert resp.status_code == 200
    assert resp.json()["portal_url"] == "https://billing.stripe.com/portal/test"


# ---------------------------------------------------------------------------
# Tests: webhook
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_webhook_not_configured(bill_client):
    """POST /api/billing/webhook returns 503 when billing not configured."""
    with patch("app.api.billing.settings") as mock_settings:
        mock_settings.stripe_secret_key = None
        mock_settings.stripe_webhook_secret = None
        resp = bill_client.post(
            "/api/billing/webhook",
            content=b"{}",
            headers={"content-type": "application/json"},
        )
    assert resp.status_code == 503


@pytest.mark.integration
def test_webhook_invalid_signature(bill_client):
    """POST /api/billing/webhook returns 400 on invalid Stripe signature."""
    import stripe

    with (
        patch("app.api.billing.settings") as mock_settings,
        patch("stripe.Webhook.construct_event", side_effect=stripe.SignatureVerificationError("bad", "sig")),
    ):
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_webhook_secret = "whsec_test"
        resp = bill_client.post(
            "/api/billing/webhook",
            content=b'{"type":"test"}',
            headers={"stripe-signature": "bad_sig", "content-type": "application/json"},
        )
    assert resp.status_code == 400


@pytest.mark.integration
def test_webhook_checkout_completed(bill_client, bill_session, starter_plan, user_profile):
    """POST /api/billing/webhook activates plan on checkout.session.completed."""
    payload = json.dumps(
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": "cus_new",
                    "metadata": {
                        "docuelevate_user_id": "user1@example.com",
                        "plan_id": "starter",
                        "billing_cycle": "monthly",
                    },
                }
            },
        }
    ).encode()

    with (
        patch("app.api.billing.settings") as mock_settings,
        patch("stripe.Event.construct_from", return_value=json.loads(payload)),
    ):
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_webhook_secret = None
        resp = bill_client.post(
            "/api/billing/webhook",
            content=payload,
            headers={"content-type": "application/json"},
        )
    assert resp.status_code == 200

    bill_session.expire_all()
    profile = bill_session.query(UserProfile).filter(UserProfile.user_id == "user1@example.com").first()
    assert profile.subscription_tier == "starter"


@pytest.mark.integration
def test_webhook_subscription_deleted(bill_client, bill_session, user_profile):
    """POST /api/billing/webhook downgrades to free on subscription deleted."""
    user_profile.stripe_customer_id = "cus_del"
    user_profile.subscription_tier = "starter"
    bill_session.commit()

    payload = json.dumps(
        {
            "type": "customer.subscription.deleted",
            "data": {"object": {"customer": "cus_del"}},
        }
    ).encode()

    with (
        patch("app.api.billing.settings") as mock_settings,
        patch("stripe.Event.construct_from", return_value=json.loads(payload)),
    ):
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_webhook_secret = None
        resp = bill_client.post(
            "/api/billing/webhook",
            content=payload,
            headers={"content-type": "application/json"},
        )
    assert resp.status_code == 200

    bill_session.expire_all()
    profile = bill_session.query(UserProfile).filter(UserProfile.user_id == "user1@example.com").first()
    assert profile.subscription_tier == "free"


# ---------------------------------------------------------------------------
# Unit tests: internal helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_user_id_from_customer(bill_session, user_profile):
    """_resolve_user_id_from_customer returns user_id for known Stripe customer."""
    user_profile.stripe_customer_id = "cus_known"
    bill_session.commit()
    result = _resolve_user_id_from_customer(bill_session, "cus_known")
    assert result == "user1@example.com"


@pytest.mark.unit
def test_resolve_user_id_from_customer_unknown(bill_session):
    """_resolve_user_id_from_customer returns None for unknown customer."""
    result = _resolve_user_id_from_customer(bill_session, "cus_unknown")
    assert result is None


@pytest.mark.unit
def test_resolve_plan_id_from_price(bill_session, starter_plan):
    """_resolve_plan_id_from_price finds plan by monthly price ID."""
    result = _resolve_plan_id_from_price(bill_session, "price_monthly_starter")
    assert result == "starter"


@pytest.mark.unit
def test_resolve_plan_id_from_price_yearly(bill_session, starter_plan):
    """_resolve_plan_id_from_price finds plan by yearly price ID."""
    result = _resolve_plan_id_from_price(bill_session, "price_yearly_starter")
    assert result == "starter"


@pytest.mark.unit
def test_resolve_plan_id_from_price_unknown(bill_session):
    """_resolve_plan_id_from_price returns None for unknown price."""
    result = _resolve_plan_id_from_price(bill_session, "price_unknown")
    assert result is None


@pytest.mark.unit
def test_on_checkout_completed_missing_user_id(bill_session):
    """_on_checkout_completed does nothing when user_id is absent."""
    data = {"metadata": {}, "customer": "cus_test"}
    _on_checkout_completed(bill_session, data)  # Should not raise


@pytest.mark.unit
def test_on_subscription_updated_no_items(bill_session, user_profile):
    """_on_subscription_updated does nothing when items list is empty."""
    user_profile.stripe_customer_id = "cus_upd"
    bill_session.commit()
    data = {"customer": "cus_upd", "items": {"data": []}}
    _on_subscription_updated(bill_session, data)  # Should not raise


@pytest.mark.unit
def test_on_subscription_deleted_unknown_customer(bill_session):
    """_on_subscription_deleted does nothing for unknown customer."""
    data = {"customer": "cus_nobody"}
    _on_subscription_deleted(bill_session, data)  # Should not raise


@pytest.mark.unit
def test_handle_stripe_event_unhandled_type(bill_session):
    """_handle_stripe_event logs but does not raise for unknown event types."""
    event = {"type": "unknown.event.type", "data": {"object": {}}}
    _handle_stripe_event(bill_session, event)  # Should not raise


@pytest.mark.unit
def test_handle_stripe_event_payment_failed(bill_session):
    """_handle_stripe_event handles invoice.payment_failed without raising."""
    event = {
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_fail"}},
    }
    _handle_stripe_event(bill_session, event)  # Should not raise


# ---------------------------------------------------------------------------
# Tests: billing success page
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_billing_success_page(bill_client):
    """GET /api/billing/success returns 200 for logged-in user."""
    resp = bill_client.get("/api/billing/success")
    assert resp.status_code == 200
    assert b"subscription" in resp.content.lower() or b"success" in resp.content.lower()


# ---------------------------------------------------------------------------
# Tests: GET /api/billing/stripe/status (admin only)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_stripe_status_not_admin(bill_client):
    """GET /api/billing/stripe/status returns 403 for non-admin."""
    with patch("app.api.billing.settings") as mock_settings:
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_webhook_secret = "whsec_test"
        # bill_client session has no is_admin flag
        resp = bill_client.get("/api/billing/stripe/status")
    assert resp.status_code == 403


@pytest.mark.integration
def test_stripe_status_not_configured(bill_client):
    """GET /api/billing/stripe/status returns configured=False when key is missing."""
    with (
        patch("app.api.billing.settings") as mock_settings,
        patch(
            "app.api.billing._require_admin",
            return_value=None,
        ),
    ):
        mock_settings.stripe_secret_key = None
        mock_settings.stripe_webhook_secret = None
        resp = bill_client.get("/api/billing/stripe/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["connection"] == "not_configured"


@pytest.mark.integration
def test_stripe_status_configured_ok(bill_client, starter_plan):
    """GET /api/billing/stripe/status returns plan list with sync status when configured."""
    mock_account = MagicMock()
    mock_account.livemode = False  # test mode

    mock_client = MagicMock()
    mock_client.accounts.retrieve.return_value = mock_account

    with (
        patch("app.api.billing._get_stripe", return_value=mock_client),
        patch("app.api.billing.settings") as mock_settings,
        patch("app.api.billing._require_admin", return_value=None),
    ):
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_webhook_secret = "whsec_test"
        resp = bill_client.get("/api/billing/stripe/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert data["connection"] == "ok"
    assert data["mode"] == "test"
    assert data["webhook_secret_configured"] is True
    assert "plans" in data
    assert "webhook_endpoint" in data
    # starter_plan has price IDs set → synced
    plan_entry = next((p for p in data["plans"] if p["plan_id"] == "starter"), None)
    assert plan_entry is not None
    assert plan_entry["stripe_price_id_monthly"] == "price_monthly_starter"
    assert plan_entry["synced"] is True


@pytest.mark.integration
def test_stripe_status_plan_not_synced(bill_client, bill_session):
    """GET /api/billing/stripe/status shows synced=False for paid plan without price IDs."""
    plan = SubscriptionPlan(
        plan_id="unsynced",
        name="Unsynced",
        price_monthly=5.0,
        price_yearly=50.0,
        trial_days=0,
        stripe_price_id_monthly=None,
        stripe_price_id_yearly=None,
    )
    bill_session.add(plan)
    bill_session.commit()

    mock_account = MagicMock()
    mock_account.livemode = False
    mock_client = MagicMock()
    mock_client.accounts.retrieve.return_value = mock_account

    with (
        patch("app.api.billing._get_stripe", return_value=mock_client),
        patch("app.api.billing.settings") as mock_settings,
        patch("app.api.billing._require_admin", return_value=None),
    ):
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_webhook_secret = None
        resp = bill_client.get("/api/billing/stripe/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["webhook_secret_configured"] is False
    entry = next((p for p in data["plans"] if p["plan_id"] == "unsynced"), None)
    assert entry is not None
    assert entry["synced"] is False


# ---------------------------------------------------------------------------
# Tests: POST /api/billing/stripe/sync-plans (admin only)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_stripe_sync_plans_not_configured(bill_client):
    """POST /api/billing/stripe/sync-plans returns 503 when billing not configured."""
    with (
        patch("app.api.billing._get_stripe", return_value=None),
        patch("app.api.billing._require_admin", return_value=None),
    ):
        resp = bill_client.post("/api/billing/stripe/sync-plans")
    assert resp.status_code == 503


@pytest.mark.integration
def test_stripe_sync_plans_not_admin(bill_client):
    """POST /api/billing/stripe/sync-plans returns 403 for non-admin."""
    mock_client = MagicMock()
    with patch("app.api.billing._get_stripe", return_value=mock_client):
        resp = bill_client.post("/api/billing/stripe/sync-plans")
    assert resp.status_code == 403


@pytest.mark.integration
def test_stripe_sync_plans_creates_prices(bill_client, bill_session):
    """POST /api/billing/stripe/sync-plans creates Stripe products and prices for paid plans."""
    plan = SubscriptionPlan(
        plan_id="pro",
        name="Professional",
        price_monthly=19.0,
        price_yearly=190.0,
        trial_days=0,
        stripe_price_id_monthly=None,
        stripe_price_id_yearly=None,
    )
    bill_session.add(plan)
    bill_session.commit()

    mock_client = MagicMock()
    mock_product = MagicMock()
    mock_product.id = "prod_test123"
    mock_monthly_price = MagicMock()
    mock_monthly_price.id = "price_monthly_pro_new"
    mock_yearly_price = MagicMock()
    mock_yearly_price.id = "price_yearly_pro_new"

    mock_client.products.create.return_value = mock_product
    mock_client.prices.create.side_effect = [mock_monthly_price, mock_yearly_price]

    with (
        patch("app.api.billing._get_stripe", return_value=mock_client),
        patch("app.api.billing._require_admin", return_value=None),
    ):
        resp = bill_client.post("/api/billing/stripe/sync-plans")

    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data

    result = next((r for r in data["results"] if r["plan_id"] == "pro"), None)
    assert result is not None
    assert result["status"] == "created"
    assert result["stripe_price_id_monthly"] == "price_monthly_pro_new"
    assert result["stripe_price_id_yearly"] == "price_yearly_pro_new"

    # Verify DB was updated
    bill_session.expire_all()
    db_plan = bill_session.query(SubscriptionPlan).filter(SubscriptionPlan.plan_id == "pro").first()
    assert db_plan.stripe_price_id_monthly == "price_monthly_pro_new"
    assert db_plan.stripe_price_id_yearly == "price_yearly_pro_new"

    # Verify correct amounts were passed to Stripe
    price_calls = mock_client.prices.create.call_args_list
    assert price_calls[0][1]["params"]["unit_amount"] == 1900  # $19.00 → 1900 cents
    assert price_calls[1][1]["params"]["unit_amount"] == 19000  # $190.00 → 19000 cents
    assert price_calls[0][1]["params"]["recurring"]["interval"] == "month"
    assert price_calls[1][1]["params"]["recurring"]["interval"] == "year"


@pytest.mark.integration
def test_stripe_sync_plans_skips_free(bill_client, bill_session):
    """POST /api/billing/stripe/sync-plans skips free plans."""
    free_plan = SubscriptionPlan(
        plan_id="free_test",
        name="Free",
        price_monthly=0.0,
        price_yearly=0.0,
        trial_days=0,
        stripe_price_id_monthly=None,
        stripe_price_id_yearly=None,
    )
    bill_session.add(free_plan)
    bill_session.commit()

    mock_client = MagicMock()
    with (
        patch("app.api.billing._get_stripe", return_value=mock_client),
        patch("app.api.billing._require_admin", return_value=None),
    ):
        resp = bill_client.post("/api/billing/stripe/sync-plans")

    assert resp.status_code == 200
    data = resp.json()
    result = next((r for r in data["results"] if r["plan_id"] == "free_test"), None)
    assert result is not None
    assert result["status"] == "skipped_free"
    # Products.create should NOT have been called for a free plan
    mock_client.products.create.assert_not_called()


@pytest.mark.integration
def test_stripe_sync_plans_skips_already_synced(bill_client, starter_plan):
    """POST /api/billing/stripe/sync-plans skips plans that already have price IDs."""
    mock_client = MagicMock()
    with (
        patch("app.api.billing._get_stripe", return_value=mock_client),
        patch("app.api.billing._require_admin", return_value=None),
    ):
        resp = bill_client.post("/api/billing/stripe/sync-plans")

    assert resp.status_code == 200
    data = resp.json()
    result = next((r for r in data["results"] if r["plan_id"] == "starter"), None)
    assert result is not None
    assert result["status"] == "already_synced"
    mock_client.products.create.assert_not_called()


@pytest.mark.integration
def test_stripe_sync_plans_handles_stripe_error(bill_client, bill_session):
    """POST /api/billing/stripe/sync-plans returns error status when Stripe API fails."""
    plan = SubscriptionPlan(
        plan_id="errplan",
        name="Error Plan",
        price_monthly=9.99,
        price_yearly=0.0,
        trial_days=0,
        stripe_price_id_monthly=None,
        stripe_price_id_yearly=None,
    )
    bill_session.add(plan)
    bill_session.commit()

    mock_client = MagicMock()
    mock_client.products.create.side_effect = Exception("Stripe connection error")

    with (
        patch("app.api.billing._get_stripe", return_value=mock_client),
        patch("app.api.billing._require_admin", return_value=None),
    ):
        resp = bill_client.post("/api/billing/stripe/sync-plans")

    assert resp.status_code == 200
    data = resp.json()
    result = next((r for r in data["results"] if r["plan_id"] == "errplan"), None)
    assert result is not None
    assert result["status"] == "error"
    assert "Stripe connection error" in result["detail"]


# ---------------------------------------------------------------------------
# Tests: plans API now exposes stripe_price_id fields
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_plan_to_response_includes_stripe_ids(bill_session, starter_plan):
    """_plan_to_response includes stripe_price_id_monthly and stripe_price_id_yearly."""
    from app.api.plans import _plan_to_response

    result = _plan_to_response(starter_plan)
    assert result["stripe_price_id_monthly"] == "price_monthly_starter"
    assert result["stripe_price_id_yearly"] == "price_yearly_starter"


@pytest.mark.integration
def test_plan_api_returns_stripe_ids(bill_client, starter_plan):
    """GET /api/plans/{plan_id} returns Stripe price IDs in the response."""
    resp = bill_client.get("/api/plans/starter")
    assert resp.status_code == 200
    data = resp.json()
    assert data["stripe_price_id_monthly"] == "price_monthly_starter"
    assert data["stripe_price_id_yearly"] == "price_yearly_starter"


@pytest.mark.integration
def test_plan_api_update_sets_stripe_ids(bill_client, bill_engine, starter_plan):
    """PUT /api/plans/{plan_id} can update Stripe price IDs."""
    from app.api.plans import _require_admin
    from app.main import app

    def override_admin():
        return {"email": "admin@test.com", "is_admin": True}

    app.dependency_overrides[_require_admin] = override_admin
    try:
        resp = bill_client.put(
            "/api/plans/starter",
            json={
                "name": "Starter",
                "price_monthly": 9.0,
                "price_yearly": 90.0,
                "stripe_price_id_monthly": "price_new_monthly",
                "stripe_price_id_yearly": "price_new_yearly",
                "features": [],
            },
        )
    finally:
        app.dependency_overrides.pop(_require_admin, None)
    assert resp.status_code == 200
    data = resp.json()
    assert data["stripe_price_id_monthly"] == "price_new_monthly"
    assert data["stripe_price_id_yearly"] == "price_new_yearly"


@pytest.mark.integration
def test_plan_api_update_clears_stripe_ids(bill_client, bill_engine, starter_plan):
    """PUT /api/plans/{plan_id} clears Stripe price IDs when empty string is passed."""
    from app.api.plans import _require_admin
    from app.main import app

    def override_admin():
        return {"email": "admin@test.com", "is_admin": True}

    app.dependency_overrides[_require_admin] = override_admin
    try:
        resp = bill_client.put(
            "/api/plans/starter",
            json={
                "name": "Starter",
                "price_monthly": 9.0,
                "price_yearly": 90.0,
                "stripe_price_id_monthly": "",
                "stripe_price_id_yearly": "",
                "features": [],
            },
        )
    finally:
        app.dependency_overrides.pop(_require_admin, None)
    assert resp.status_code == 200
    data = resp.json()
    assert data["stripe_price_id_monthly"] is None
    assert data["stripe_price_id_yearly"] is None
