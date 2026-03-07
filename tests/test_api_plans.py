"""Tests for the subscription plans API endpoints (app/api/plans.py).

Covers:
- Unit tests for _require_admin, _plan_to_response, _apply_body helpers
- Auth enforcement (403 for non-admins on admin-only endpoints)
- GET /api/plans/            — list active plans (public)
- GET /api/plans/admin       — list all plans inc. inactive (admin only)
- POST /api/plans/seed       — seed default plans (admin only)
- POST /api/plans/reorder    — reorder plans (admin only)
- POST /api/plans/           — create plan (admin only)
- GET /api/plans/{plan_id}   — get single active plan (public)
- PUT /api/plans/{plan_id}   — update plan (admin only)
- DELETE /api/plans/{plan_id}— delete plan (admin only)
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import SubscriptionPlan

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ADMIN_USER = {"email": "admin@test.com", "is_admin": True, "name": "Admin"}
NONADMIN_USER = {"email": "user@test.com", "is_admin": False, "name": "User"}


@pytest.fixture()
def plans_engine():
    """In-memory SQLite engine for plans tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def plans_session(plans_engine):
    """DB session scoped to one test."""
    Session = sessionmaker(bind=plans_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def admin_client(plans_engine):
    """TestClient that uses an in-memory DB and overrides _require_admin to allow admin access."""
    from app.api.plans import _require_admin
    from app.main import app

    def override_db():
        Session = sessionmaker(bind=plans_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def override_require_admin():
        return ADMIN_USER

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[_require_admin] = override_require_admin
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def nonadmin_client(plans_engine):
    """TestClient without admin override — _require_admin will raise 403."""
    from app.main import app

    def override_db():
        Session = sessionmaker(bind=plans_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def public_client(plans_engine):
    """TestClient without any session override (no admin, no session user)."""
    from app.main import app

    def override_db():
        Session = sessionmaker(bind=plans_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _make_plan(
    session, plan_id: str, name: str = "Test Plan", is_active: bool = True, sort_order: int = 0
) -> SubscriptionPlan:
    """Helper to insert a SubscriptionPlan row."""
    plan = SubscriptionPlan(
        plan_id=plan_id,
        name=name,
        price_monthly=9.99,
        price_yearly=99.99,
        is_active=is_active,
        sort_order=sort_order,
    )
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


# ---------------------------------------------------------------------------
# Unit tests — _require_admin helper
# ---------------------------------------------------------------------------


class TestRequireAdmin:
    """Unit tests for the _require_admin dependency function."""

    @pytest.mark.unit
    def test_require_admin_raises_403_when_no_user_in_session(self):
        """_require_admin raises 403 when session has no user key."""
        from app.api.plans import _require_admin

        mock_request = MagicMock()
        mock_request.session = {}
        with pytest.raises(HTTPException) as exc_info:
            _require_admin(mock_request)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_require_admin_raises_403_for_non_admin_user(self):
        """_require_admin raises 403 when user.is_admin is False."""
        from app.api.plans import _require_admin

        mock_request = MagicMock()
        mock_request.session = {"user": NONADMIN_USER}
        with pytest.raises(HTTPException) as exc_info:
            _require_admin(mock_request)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_require_admin_returns_user_dict_for_admin(self):
        """_require_admin returns the user dict when is_admin is True."""
        from app.api.plans import _require_admin

        mock_request = MagicMock()
        mock_request.session = {"user": ADMIN_USER}
        result = _require_admin(mock_request)
        assert result == ADMIN_USER

    @pytest.mark.unit
    def test_require_admin_raises_403_when_user_is_none(self):
        """_require_admin raises 403 when session user is None."""
        from app.api.plans import _require_admin

        mock_request = MagicMock()
        mock_request.session = {"user": None}
        with pytest.raises(HTTPException) as exc_info:
            _require_admin(mock_request)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Unit tests — _plan_to_response helper
# ---------------------------------------------------------------------------


class TestPlanToResponse:
    """Unit tests for _plan_to_response."""

    @pytest.mark.unit
    def test_plan_to_response_returns_all_fields(self):
        """_plan_to_response includes all expected keys."""
        from app.api.plans import _plan_to_response

        plan = MagicMock(spec=SubscriptionPlan)
        plan.id = 1
        plan.plan_id = "free"
        plan.name = "Free"
        plan.tagline = "Always free"
        plan.price_monthly = 0.0
        plan.price_yearly = 0.0
        plan.trial_days = 0
        plan.lifetime_file_limit = 50
        plan.daily_upload_limit = 5
        plan.monthly_upload_limit = 20
        plan.max_storage_destinations = 1
        plan.max_ocr_pages_monthly = 150
        plan.max_file_size_mb = 10
        plan.max_mailboxes = 0
        plan.overage_percent = 20
        plan.allow_overage_billing = False
        plan.overage_price_per_doc = None
        plan.overage_price_per_ocr_page = None
        plan.is_active = True
        plan.is_highlighted = False
        plan.badge_text = None
        plan.cta_text = "Get started"
        plan.sort_order = 0
        plan.features = json.dumps(["feature1", "feature2"])
        plan.api_access = False
        plan.created_at = None
        plan.updated_at = None

        result = _plan_to_response(plan)
        expected_keys = [
            "id",
            "plan_id",
            "name",
            "tagline",
            "price_monthly",
            "price_yearly",
            "trial_days",
            "lifetime_file_limit",
            "daily_upload_limit",
            "monthly_upload_limit",
            "max_storage_destinations",
            "max_ocr_pages_monthly",
            "max_file_size_mb",
            "max_mailboxes",
            "overage_percent",
            "allow_overage_billing",
            "overage_price_per_doc",
            "overage_price_per_ocr_page",
            "is_active",
            "is_highlighted",
            "badge_text",
            "cta_text",
            "sort_order",
            "features",
            "api_access",
            "created_at",
            "updated_at",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

        assert result["features"] == ["feature1", "feature2"]
        assert result["plan_id"] == "free"

    @pytest.mark.unit
    def test_plan_to_response_handles_null_features(self):
        """_plan_to_response returns empty list when features is None."""
        from app.api.plans import _plan_to_response

        plan = MagicMock(spec=SubscriptionPlan)
        plan.id = 1
        plan.plan_id = "free"
        plan.name = "Free"
        plan.tagline = None
        plan.price_monthly = 0.0
        plan.price_yearly = 0.0
        plan.trial_days = 0
        plan.lifetime_file_limit = 0
        plan.daily_upload_limit = 0
        plan.monthly_upload_limit = 0
        plan.max_storage_destinations = 0
        plan.max_ocr_pages_monthly = 0
        plan.max_file_size_mb = 0
        plan.max_mailboxes = 0
        plan.overage_percent = 20
        plan.allow_overage_billing = False
        plan.overage_price_per_doc = None
        plan.overage_price_per_ocr_page = None
        plan.is_active = True
        plan.is_highlighted = False
        plan.badge_text = None
        plan.cta_text = "Get started"
        plan.sort_order = 0
        plan.features = None
        plan.api_access = False
        plan.created_at = None
        plan.updated_at = None

        result = _plan_to_response(plan)
        assert result["features"] == []

    @pytest.mark.unit
    def test_plan_to_response_handles_invalid_json_features(self):
        """_plan_to_response returns empty list when features JSON is invalid."""
        from app.api.plans import _plan_to_response

        plan = MagicMock(spec=SubscriptionPlan)
        plan.id = 1
        plan.plan_id = "free"
        plan.name = "Free"
        plan.tagline = None
        plan.price_monthly = 0.0
        plan.price_yearly = 0.0
        plan.trial_days = 0
        plan.lifetime_file_limit = 0
        plan.daily_upload_limit = 0
        plan.monthly_upload_limit = 0
        plan.max_storage_destinations = 0
        plan.max_ocr_pages_monthly = 0
        plan.max_file_size_mb = 0
        plan.max_mailboxes = 0
        plan.overage_percent = 20
        plan.allow_overage_billing = False
        plan.overage_price_per_doc = None
        plan.overage_price_per_ocr_page = None
        plan.is_active = True
        plan.is_highlighted = False
        plan.badge_text = None
        plan.cta_text = "Get started"
        plan.sort_order = 0
        plan.features = "not-valid-json{"
        plan.api_access = False
        plan.created_at = None
        plan.updated_at = None

        result = _plan_to_response(plan)
        assert result["features"] == []

    @pytest.mark.unit
    def test_plan_to_response_formats_datetimes_as_isoformat(self):
        """_plan_to_response calls .isoformat() on created_at/updated_at when set."""
        from datetime import datetime, timezone

        from app.api.plans import _plan_to_response

        plan = MagicMock(spec=SubscriptionPlan)
        plan.id = 2
        plan.plan_id = "starter"
        plan.name = "Starter"
        plan.tagline = None
        plan.price_monthly = 2.99
        plan.price_yearly = 29.99
        plan.trial_days = 30
        plan.lifetime_file_limit = 0
        plan.daily_upload_limit = 0
        plan.monthly_upload_limit = 50
        plan.max_storage_destinations = 2
        plan.max_ocr_pages_monthly = 300
        plan.max_file_size_mb = 25
        plan.max_mailboxes = 1
        plan.overage_percent = 20
        plan.allow_overage_billing = False
        plan.overage_price_per_doc = None
        plan.overage_price_per_ocr_page = None
        plan.is_active = True
        plan.is_highlighted = False
        plan.badge_text = None
        plan.cta_text = "Get started"
        plan.sort_order = 1
        plan.features = "[]"
        plan.api_access = True
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        plan.created_at = now
        plan.updated_at = now

        result = _plan_to_response(plan)
        assert result["created_at"] == now.isoformat()
        assert result["updated_at"] == now.isoformat()


# ---------------------------------------------------------------------------
# Unit tests — _apply_body helper
# ---------------------------------------------------------------------------


class TestApplyBody:
    """Unit tests for the _apply_body helper."""

    @pytest.mark.unit
    def test_apply_body_sets_all_fields(self):
        """_apply_body copies all PlanUpsert fields onto the plan ORM object."""
        from app.api.plans import PlanUpsert, _apply_body

        plan = MagicMock(spec=SubscriptionPlan)
        body = PlanUpsert(
            name="Pro Plan",
            tagline="Best value",
            price_monthly=9.99,
            price_yearly=99.99,
            trial_days=14,
            lifetime_file_limit=0,
            daily_upload_limit=10,
            monthly_upload_limit=100,
            max_storage_destinations=5,
            max_ocr_pages_monthly=500,
            max_file_size_mb=50,
            max_mailboxes=3,
            overage_percent=15,
            allow_overage_billing=True,
            overage_price_per_doc=0.10,
            overage_price_per_ocr_page=0.05,
            is_active=True,
            is_highlighted=True,
            badge_text="Popular",
            cta_text="Start now",
            sort_order=2,
            features=["Feature A", "Feature B"],
            api_access=True,
        )
        _apply_body(plan, body)

        assert plan.name == "Pro Plan"
        assert plan.tagline == "Best value"
        assert plan.price_monthly == 9.99
        assert plan.price_yearly == 99.99
        assert plan.trial_days == 14
        assert plan.lifetime_file_limit == 0
        assert plan.daily_upload_limit == 10
        assert plan.monthly_upload_limit == 100
        assert plan.max_storage_destinations == 5
        assert plan.max_ocr_pages_monthly == 500
        assert plan.max_file_size_mb == 50
        assert plan.max_mailboxes == 3
        assert plan.overage_percent == 15
        assert plan.allow_overage_billing is True
        assert plan.overage_price_per_doc == 0.10
        assert plan.overage_price_per_ocr_page == 0.05
        assert plan.is_active is True
        assert plan.is_highlighted is True
        assert plan.badge_text == "Popular"
        assert plan.cta_text == "Start now"
        assert plan.sort_order == 2
        assert plan.features == json.dumps(["Feature A", "Feature B"])
        assert plan.api_access is True


# ---------------------------------------------------------------------------
# Auth enforcement tests
# ---------------------------------------------------------------------------


class TestPlansAuth:
    """Admin-only endpoints must return 403 for non-admin requests."""

    @pytest.mark.integration
    def test_list_all_plans_requires_admin(self, nonadmin_client):
        """GET /api/plans/admin returns 403 for non-admins."""
        resp = nonadmin_client.get("/api/plans/admin")
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_seed_plans_requires_admin(self, nonadmin_client):
        """POST /api/plans/seed returns 403 for non-admins."""
        resp = nonadmin_client.post("/api/plans/seed")
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_reorder_plans_requires_admin(self, nonadmin_client):
        """POST /api/plans/reorder returns 403 for non-admins."""
        resp = nonadmin_client.post("/api/plans/reorder", json={"order": []})
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_create_plan_requires_admin(self, nonadmin_client):
        """POST /api/plans/ returns 403 for non-admins."""
        resp = nonadmin_client.post(
            "/api/plans/",
            params={"plan_id": "test"},
            json={"name": "Test", "features": []},
        )
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_update_plan_requires_admin(self, nonadmin_client):
        """PUT /api/plans/{plan_id} returns 403 for non-admins."""
        resp = nonadmin_client.put(
            "/api/plans/free",
            json={"name": "Free Updated", "features": []},
        )
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_delete_plan_requires_admin(self, nonadmin_client):
        """DELETE /api/plans/{plan_id} returns 403 for non-admins."""
        resp = nonadmin_client.delete("/api/plans/free")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/plans/ — list active plans (public)
# ---------------------------------------------------------------------------


class TestListActivePlans:
    """Tests for the public list-active-plans endpoint."""

    @pytest.mark.integration
    def test_list_active_plans_empty(self, public_client):
        """Returns empty list when no plans exist."""
        resp = public_client.get("/api/plans/")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"plans": []}

    @pytest.mark.integration
    def test_list_active_plans_returns_only_active(self, public_client, plans_session):
        """Only active plans are returned."""
        _make_plan(plans_session, "active_plan", "Active Plan", is_active=True)
        _make_plan(plans_session, "inactive_plan", "Inactive Plan", is_active=False)

        resp = public_client.get("/api/plans/")
        assert resp.status_code == 200
        data = resp.json()
        ids = [p["plan_id"] for p in data["plans"]]
        assert "active_plan" in ids
        assert "inactive_plan" not in ids

    @pytest.mark.integration
    def test_list_active_plans_sorted_by_sort_order(self, public_client, plans_session):
        """Plans are returned in ascending sort_order."""
        _make_plan(plans_session, "plan_b", "Plan B", sort_order=2)
        _make_plan(plans_session, "plan_a", "Plan A", sort_order=1)
        _make_plan(plans_session, "plan_c", "Plan C", sort_order=3)

        resp = public_client.get("/api/plans/")
        assert resp.status_code == 200
        ids = [p["plan_id"] for p in resp.json()["plans"]]
        assert ids == ["plan_a", "plan_b", "plan_c"]

    @pytest.mark.integration
    def test_list_active_plans_response_fields(self, public_client, plans_session):
        """Each plan in response has expected fields."""
        _make_plan(plans_session, "free", "Free Plan")
        resp = public_client.get("/api/plans/")
        plan = resp.json()["plans"][0]
        for field in ("plan_id", "name", "price_monthly", "is_active", "features"):
            assert field in plan, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# GET /api/plans/admin — list all plans (admin only)
# ---------------------------------------------------------------------------


class TestListAllPlans:
    """Tests for the admin list-all-plans endpoint."""

    @pytest.mark.integration
    def test_list_all_plans_empty(self, admin_client):
        """Returns empty list when no plans exist."""
        resp = admin_client.get("/api/plans/admin")
        assert resp.status_code == 200
        assert resp.json() == {"plans": []}

    @pytest.mark.integration
    def test_list_all_plans_includes_inactive(self, admin_client, plans_session):
        """Admin endpoint returns both active and inactive plans."""
        _make_plan(plans_session, "active_plan", "Active", is_active=True)
        _make_plan(plans_session, "inactive_plan", "Inactive", is_active=False)

        resp = admin_client.get("/api/plans/admin")
        assert resp.status_code == 200
        ids = [p["plan_id"] for p in resp.json()["plans"]]
        assert "active_plan" in ids
        assert "inactive_plan" in ids

    @pytest.mark.integration
    def test_list_all_plans_sorted_by_sort_order(self, admin_client, plans_session):
        """Plans are returned in ascending sort_order."""
        _make_plan(plans_session, "plan_z", "Plan Z", sort_order=10)
        _make_plan(plans_session, "plan_a", "Plan A", sort_order=1)

        resp = admin_client.get("/api/plans/admin")
        ids = [p["plan_id"] for p in resp.json()["plans"]]
        assert ids.index("plan_a") < ids.index("plan_z")


# ---------------------------------------------------------------------------
# POST /api/plans/seed — seed default plans (admin only)
# ---------------------------------------------------------------------------


class TestSeedPlans:
    """Tests for the seed-plans endpoint."""

    @pytest.mark.integration
    def test_seed_plans_inserts_defaults_when_empty(self, admin_client):
        """Seeding on an empty table inserts default plans."""
        with patch("app.utils.subscription.seed_default_plans", return_value=4) as mock_seed:
            resp = admin_client.post("/api/plans/seed")
            assert resp.status_code == 200
            data = resp.json()
            assert data["inserted"] == 4
            assert "4" in data["message"]
            mock_seed.assert_called_once()

    @pytest.mark.integration
    def test_seed_plans_noop_when_already_seeded(self, admin_client):
        """Seeding returns 0 inserted when plans already exist."""
        with patch("app.utils.subscription.seed_default_plans", return_value=0) as mock_seed:
            resp = admin_client.post("/api/plans/seed")
            assert resp.status_code == 200
            data = resp.json()
            assert data["inserted"] == 0
            mock_seed.assert_called_once()


# ---------------------------------------------------------------------------
# POST /api/plans/reorder — reorder plans (admin only)
# ---------------------------------------------------------------------------


class TestReorderPlans:
    """Tests for the reorder-plans endpoint."""

    @pytest.mark.integration
    def test_reorder_updates_sort_order(self, admin_client, plans_session):
        """Reordering updates sort_order of existing plans."""
        _make_plan(plans_session, "plan_a", "Plan A", sort_order=0)
        _make_plan(plans_session, "plan_b", "Plan B", sort_order=1)

        resp = admin_client.post(
            "/api/plans/reorder",
            json={"order": ["plan_b", "plan_a"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated"] == 2

        plans_session.expire_all()
        plan_b = plans_session.query(SubscriptionPlan).filter_by(plan_id="plan_b").first()
        plan_a = plans_session.query(SubscriptionPlan).filter_by(plan_id="plan_a").first()
        assert plan_b.sort_order == 0
        assert plan_a.sort_order == 1

    @pytest.mark.integration
    def test_reorder_skips_unknown_plan_ids(self, admin_client, plans_session):
        """Unknown plan IDs in the order list are silently skipped."""
        _make_plan(plans_session, "real_plan", "Real Plan", sort_order=5)

        resp = admin_client.post(
            "/api/plans/reorder",
            json={"order": ["real_plan", "nonexistent_plan"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated"] == 1

    @pytest.mark.integration
    def test_reorder_empty_order_list(self, admin_client):
        """Empty order list returns 0 updated."""
        resp = admin_client.post("/api/plans/reorder", json={"order": []})
        assert resp.status_code == 200
        assert resp.json()["updated"] == 0

    @pytest.mark.integration
    def test_reorder_db_error_returns_500(self, admin_client, plans_session):
        """Database commit failure returns 500."""
        _make_plan(plans_session, "plan_x", "Plan X")
        with patch("sqlalchemy.orm.Session.commit", side_effect=Exception("DB error")):
            resp = admin_client.post(
                "/api/plans/reorder",
                json={"order": ["plan_x"]},
            )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /api/plans/ — create plan (admin only)
# ---------------------------------------------------------------------------


class TestCreatePlan:
    """Tests for the create-plan endpoint."""

    _plan_body = {
        "name": "New Plan",
        "tagline": "A great plan",
        "price_monthly": 4.99,
        "price_yearly": 49.99,
        "trial_days": 14,
        "lifetime_file_limit": 0,
        "daily_upload_limit": 0,
        "monthly_upload_limit": 50,
        "max_storage_destinations": 3,
        "max_ocr_pages_monthly": 300,
        "max_file_size_mb": 25,
        "max_mailboxes": 1,
        "overage_percent": 20,
        "allow_overage_billing": False,
        "overage_price_per_doc": None,
        "overage_price_per_ocr_page": None,
        "is_active": True,
        "is_highlighted": False,
        "badge_text": None,
        "cta_text": "Get started",
        "sort_order": 0,
        "features": ["Feature 1", "Feature 2"],
        "api_access": False,
    }

    @pytest.mark.integration
    def test_create_plan_success(self, admin_client):
        """POST /api/plans/ creates a new plan and returns 201."""
        resp = admin_client.post(
            "/api/plans/",
            params={"plan_id": "new_plan"},
            json=self._plan_body,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["plan_id"] == "new_plan"
        assert data["name"] == "New Plan"
        assert data["features"] == ["Feature 1", "Feature 2"]
        assert data["monthly_upload_limit"] == 50

    @pytest.mark.integration
    def test_create_plan_conflict_returns_409(self, admin_client, plans_session):
        """Creating a plan with an existing plan_id returns 409."""
        _make_plan(plans_session, "existing_plan", "Existing")

        resp = admin_client.post(
            "/api/plans/",
            params={"plan_id": "existing_plan"},
            json=self._plan_body,
        )
        assert resp.status_code == 409

    @pytest.mark.integration
    def test_create_plan_returns_all_fields(self, admin_client):
        """Created plan response includes all expected fields."""
        resp = admin_client.post(
            "/api/plans/",
            params={"plan_id": "full_plan"},
            json=self._plan_body,
        )
        assert resp.status_code == 201
        data = resp.json()
        for field in (
            "id",
            "plan_id",
            "name",
            "tagline",
            "price_monthly",
            "price_yearly",
            "is_active",
            "features",
            "sort_order",
            "api_access",
        ):
            assert field in data, f"Missing field: {field}"

    @pytest.mark.integration
    def test_create_plan_with_empty_features(self, admin_client):
        """Plan can be created with an empty features list."""
        body = dict(self._plan_body)
        body["features"] = []
        resp = admin_client.post(
            "/api/plans/",
            params={"plan_id": "no_features_plan"},
            json=body,
        )
        assert resp.status_code == 201
        assert resp.json()["features"] == []

    @pytest.mark.integration
    def test_create_plan_api_access_flag(self, admin_client):
        """Plan can be created with api_access=True."""
        body = dict(self._plan_body)
        body["api_access"] = True
        resp = admin_client.post(
            "/api/plans/",
            params={"plan_id": "api_plan"},
            json=body,
        )
        assert resp.status_code == 201
        assert resp.json()["api_access"] is True

    @pytest.mark.integration
    def test_create_plan_db_commit_error_returns_500(self, admin_client):
        """A database commit failure during create returns 500."""
        with patch("sqlalchemy.orm.Session.commit", side_effect=Exception("DB failure")):
            resp = admin_client.post(
                "/api/plans/",
                params={"plan_id": "bad_plan"},
                json=self._plan_body,
            )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/plans/{plan_id} — get single active plan (public)
# ---------------------------------------------------------------------------


class TestGetPlan:
    """Tests for the get-single-plan endpoint."""

    @pytest.mark.integration
    def test_get_active_plan(self, public_client, plans_session):
        """Returns plan data for an existing active plan."""
        _make_plan(plans_session, "starter", "Starter Plan", is_active=True)

        resp = public_client.get("/api/plans/starter")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan_id"] == "starter"
        assert data["name"] == "Starter Plan"

    @pytest.mark.integration
    def test_get_inactive_plan_returns_404(self, public_client, plans_session):
        """Inactive plans are not found by the public endpoint."""
        _make_plan(plans_session, "hidden_plan", "Hidden", is_active=False)

        resp = public_client.get("/api/plans/hidden_plan")
        assert resp.status_code == 404

    @pytest.mark.integration
    def test_get_nonexistent_plan_returns_404(self, public_client):
        """Non-existent plan_id returns 404."""
        resp = public_client.get("/api/plans/does_not_exist")
        assert resp.status_code == 404

    @pytest.mark.integration
    def test_get_plan_returns_features_list(self, public_client, plans_session):
        """Plan response includes a features list."""
        plan = _make_plan(plans_session, "featured_plan", "Featured")
        plan.features = json.dumps(["Alpha", "Beta"])
        plans_session.commit()

        resp = public_client.get("/api/plans/featured_plan")
        assert resp.status_code == 200
        assert resp.json()["features"] == ["Alpha", "Beta"]


# ---------------------------------------------------------------------------
# PUT /api/plans/{plan_id} — update plan (admin only)
# ---------------------------------------------------------------------------


class TestUpdatePlan:
    """Tests for the update-plan endpoint."""

    _update_body = {
        "name": "Updated Name",
        "tagline": "New tagline",
        "price_monthly": 19.99,
        "price_yearly": 199.99,
        "trial_days": 30,
        "lifetime_file_limit": 0,
        "daily_upload_limit": 0,
        "monthly_upload_limit": 100,
        "max_storage_destinations": 5,
        "max_ocr_pages_monthly": 500,
        "max_file_size_mb": 50,
        "max_mailboxes": 3,
        "overage_percent": 10,
        "allow_overage_billing": True,
        "overage_price_per_doc": 0.05,
        "overage_price_per_ocr_page": 0.02,
        "is_active": True,
        "is_highlighted": True,
        "badge_text": "Best",
        "cta_text": "Upgrade now",
        "sort_order": 2,
        "features": ["Updated Feature"],
        "api_access": True,
    }

    @pytest.mark.integration
    def test_update_plan_success(self, admin_client, plans_session):
        """PUT /api/plans/{plan_id} updates the plan and returns 200."""
        _make_plan(plans_session, "starter", "Starter")

        resp = admin_client.put("/api/plans/starter", json=self._update_body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Name"
        assert data["price_monthly"] == 19.99
        assert data["monthly_upload_limit"] == 100
        assert data["features"] == ["Updated Feature"]
        assert data["api_access"] is True

    @pytest.mark.integration
    def test_update_nonexistent_plan_returns_404(self, admin_client):
        """Updating a plan that doesn't exist returns 404."""
        resp = admin_client.put("/api/plans/no_such_plan", json=self._update_body)
        assert resp.status_code == 404

    @pytest.mark.integration
    def test_update_plan_persists_changes(self, admin_client, plans_session):
        """Changes made via PUT are persisted in the database."""
        _make_plan(plans_session, "mutable_plan", "Original Name")

        admin_client.put("/api/plans/mutable_plan", json=self._update_body)

        plans_session.expire_all()
        updated = plans_session.query(SubscriptionPlan).filter_by(plan_id="mutable_plan").first()
        assert updated.name == "Updated Name"
        assert updated.overage_percent == 10

    @pytest.mark.integration
    def test_update_plan_can_deactivate(self, admin_client, plans_session):
        """A plan can be deactivated via PUT."""
        _make_plan(plans_session, "active_plan", "Active", is_active=True)
        body = dict(self._update_body)
        body["is_active"] = False

        resp = admin_client.put("/api/plans/active_plan", json=body)
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    @pytest.mark.integration
    def test_update_plan_db_commit_error_returns_500(self, admin_client, plans_session):
        """A database commit failure during update returns 500."""
        _make_plan(plans_session, "fail_plan", "Fail Plan")
        with patch("sqlalchemy.orm.Session.commit", side_effect=Exception("DB failure")):
            resp = admin_client.put("/api/plans/fail_plan", json=self._update_body)
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# DELETE /api/plans/{plan_id} — delete plan (admin only)
# ---------------------------------------------------------------------------


class TestDeletePlan:
    """Tests for the delete-plan endpoint."""

    @pytest.mark.integration
    def test_delete_plan_success(self, admin_client, plans_session):
        """DELETE /api/plans/{plan_id} removes the plan and returns 204."""
        _make_plan(plans_session, "to_delete", "To Delete")

        resp = admin_client.delete("/api/plans/to_delete")
        assert resp.status_code == 204

    @pytest.mark.integration
    def test_delete_plan_actually_removed(self, admin_client, plans_session):
        """After deletion the plan no longer exists in the DB."""
        _make_plan(plans_session, "goodbye_plan", "Goodbye")

        admin_client.delete("/api/plans/goodbye_plan")

        plans_session.expire_all()
        plan = plans_session.query(SubscriptionPlan).filter_by(plan_id="goodbye_plan").first()
        assert plan is None

    @pytest.mark.integration
    def test_delete_nonexistent_plan_returns_404(self, admin_client):
        """Deleting a plan that doesn't exist returns 404."""
        resp = admin_client.delete("/api/plans/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.integration
    def test_delete_plan_does_not_affect_other_plans(self, admin_client, plans_session):
        """Deleting one plan does not remove other plans."""
        _make_plan(plans_session, "plan_keep", "Keep This", sort_order=0)
        _make_plan(plans_session, "plan_delete", "Delete This", sort_order=1)

        admin_client.delete("/api/plans/plan_delete")

        plans_session.expire_all()
        kept = plans_session.query(SubscriptionPlan).filter_by(plan_id="plan_keep").first()
        assert kept is not None

    @pytest.mark.integration
    def test_delete_plan_db_commit_error_returns_500(self, admin_client, plans_session):
        """A database commit failure during delete returns 500."""
        _make_plan(plans_session, "fail_delete_plan", "Fail Delete")
        with patch("sqlalchemy.orm.Session.commit", side_effect=Exception("DB failure")):
            resp = admin_client.delete("/api/plans/fail_delete_plan")
        assert resp.status_code == 500
