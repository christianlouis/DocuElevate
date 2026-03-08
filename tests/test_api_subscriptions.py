"""Tests for the subscription API endpoints (app/api/subscriptions.py).

Covers:
- _get_owner_id helper (username / email / sub extraction)
- _require_authenticated helper (raises 401 when unauthenticated)
- GET  /api/subscriptions/tiers        — public endpoint, all tiers returned
- GET  /api/subscriptions/my           — single-user mode, multi-user authenticated,
                                         multi-user unauthenticated, with/without
                                         UserProfile, with/without pending change
- POST /api/subscriptions/change       — single-user mode, unauthenticated, success,
                                         SubscriptionChangeError
- DELETE /api/subscriptions/change     — single-user mode, unauthenticated, success,
                                         no pending change found
- GET  /api/subscriptions/platform     — admin-only aggregate statistics
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin_users import _require_admin
from app.api.subscriptions import _get_owner_id, _require_authenticated
from app.config import settings as app_settings
from app.database import Base, get_db
from app.models import FileRecord, UserProfile
from app.utils.subscription import SubscriptionChangeError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ADMIN_USER = {"email": "admin@test.com", "is_admin": True, "name": "Admin"}


@pytest.fixture()
def sub_engine():
    """In-memory SQLite engine scoped to one test function."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def sub_session(sub_engine):
    """DB session scoped to one test function."""
    Session = sessionmaker(bind=sub_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def anon_client(sub_engine):
    """TestClient without any session user or admin override."""
    from app.main import app

    Session = sessionmaker(bind=sub_engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def admin_client(sub_engine):
    """TestClient with the admin dependency overridden."""
    from app.main import app

    Session = sessionmaker(bind=sub_engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_require_admin] = lambda: ADMIN_USER
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(_require_admin, None)


def _patch_multi_user(enabled: bool):
    """Return a patch context manager for settings.multi_user_enabled."""
    return patch.object(app_settings, "multi_user_enabled", enabled)


# ---------------------------------------------------------------------------
# Unit tests — _get_owner_id helper
# ---------------------------------------------------------------------------


class TestGetOwnerId:
    """Unit tests for _get_owner_id."""

    @pytest.mark.unit
    def test_returns_username_when_present(self):
        """Should prefer 'username' over other fields."""
        request = MagicMock()
        request.session = {"user": {"username": "alice", "email": "alice@example.com", "sub": "sub123"}}
        assert _get_owner_id(request) == "alice"

    @pytest.mark.unit
    def test_returns_email_when_no_username(self):
        """Falls back to email when username is absent."""
        request = MagicMock()
        request.session = {"user": {"email": "alice@example.com", "sub": "sub123"}}
        assert _get_owner_id(request) == "alice@example.com"

    @pytest.mark.unit
    def test_returns_sub_when_no_username_or_email(self):
        """Falls back to sub when username and email are absent."""
        request = MagicMock()
        request.session = {"user": {"sub": "sub123"}}
        assert _get_owner_id(request) == "sub123"

    @pytest.mark.unit
    def test_returns_empty_string_when_no_user_in_session(self):
        """Returns '' when session has no 'user' key."""
        request = MagicMock()
        request.session = {}
        assert _get_owner_id(request) == ""

    @pytest.mark.unit
    def test_returns_empty_string_when_user_dict_is_empty(self):
        """Returns '' when the user dict has no recognisable fields."""
        request = MagicMock()
        request.session = {"user": {}}
        assert _get_owner_id(request) == ""


# ---------------------------------------------------------------------------
# Unit tests — _require_authenticated helper
# ---------------------------------------------------------------------------


class TestRequireAuthenticated:
    """Unit tests for _require_authenticated."""

    @pytest.mark.unit
    def test_returns_owner_id_when_authenticated(self):
        """Should return the owner_id string when user is in session."""
        request = MagicMock()
        request.session = {"user": {"email": "bob@example.com"}}
        assert _require_authenticated(request) == "bob@example.com"

    @pytest.mark.unit
    def test_raises_401_when_not_authenticated(self):
        """Should raise 401 when no session user is present."""
        request = MagicMock()
        request.session = {}
        with pytest.raises(HTTPException) as exc_info:
            _require_authenticated(request)
        assert exc_info.value.status_code == 401

    @pytest.mark.unit
    def test_raises_401_when_user_dict_empty(self):
        """Should raise 401 when session user dict has no recognizable fields."""
        request = MagicMock()
        request.session = {"user": {}}
        with pytest.raises(HTTPException) as exc_info:
            _require_authenticated(request)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/subscriptions/tiers
# ---------------------------------------------------------------------------


class TestListTiers:
    """Tests for the public list-tiers endpoint."""

    @pytest.mark.integration
    def test_returns_200_with_tiers(self, anon_client):
        """Should return 200 with a tiers dict, order list, and default."""
        resp = anon_client.get("/api/subscriptions/tiers")
        assert resp.status_code == 200
        data = resp.json()
        assert "tiers" in data
        assert "order" in data
        assert data["default"] == "free"
        assert len(data["tiers"]) == 4

    @pytest.mark.integration
    def test_order_matches_tier_keys(self, anon_client):
        """The 'order' list should contain exactly the four tier IDs."""
        resp = anon_client.get("/api/subscriptions/tiers")
        data = resp.json()
        assert set(data["order"]) == {"free", "starter", "professional", "business"}


# ---------------------------------------------------------------------------
# GET /api/subscriptions/my
# ---------------------------------------------------------------------------


class TestMySubscription:
    """Tests for the my-subscription endpoint."""

    @pytest.mark.integration
    def test_single_user_mode_returns_business_tier(self, anon_client):
        """In single-user mode the endpoint should return the unrestricted business tier."""
        with _patch_multi_user(False):
            resp = anon_client.get("/api/subscriptions/my")
        assert resp.status_code == 200
        data = resp.json()
        assert data["multi_user_mode"] is False
        assert data["tier"]["id"] == "business"
        assert data["usage"] is None

    @pytest.mark.integration
    def test_unauthenticated_returns_401_in_multi_user_mode(self, anon_client):
        """In multi-user mode an unauthenticated request should get 401."""
        with _patch_multi_user(True):
            resp = anon_client.get("/api/subscriptions/my")
        assert resp.status_code == 401

    @pytest.mark.unit
    def test_my_subscription_multi_user_with_profile_and_pending_change(self):
        """Authenticated user with a pending downgrade sees pending_change in response."""
        from app.api.subscriptions import my_subscription

        profile_mock = MagicMock()
        profile_mock.subscription_tier = "professional"
        profile_mock.subscription_change_pending_tier = "starter"
        profile_mock.subscription_change_pending_date = datetime(2026, 4, 1, tzinfo=timezone.utc)
        profile_mock.subscription_period_start = datetime(2026, 3, 1, tzinfo=timezone.utc)

        db_mock = MagicMock()
        # query for UserProfile returns profile_mock
        db_mock.query.return_value.filter.return_value.first.return_value = profile_mock

        request_mock = MagicMock()
        request_mock.session = {"user": {"email": "pro@example.com"}}

        with (
            patch.object(app_settings, "multi_user_enabled", True),
            patch("app.api.subscriptions.apply_pending_subscription_changes"),
            patch("app.api.subscriptions.get_user_tier_id", return_value="professional"),
            patch("app.api.subscriptions.get_tier", side_effect=lambda tid, db=None: {"id": tid}),
            patch("app.api.subscriptions.get_user_usage", return_value={"files_this_month": 10}),
        ):
            result = my_subscription(request=request_mock, db=db_mock)

        assert result["multi_user_mode"] is True
        assert result["owner_id"] == "pro@example.com"
        assert result["pending_change"] is not None
        assert result["pending_change"]["tier_id"] == "starter"
        assert result["pending_change"]["effective_date"] == "2026-04-01T00:00:00+00:00"
        assert result["period_start"] == "2026-03-01T00:00:00+00:00"

    @pytest.mark.unit
    def test_my_subscription_multi_user_without_profile(self):
        """Authenticated user without a UserProfile row returns None pending_change."""
        from app.api.subscriptions import my_subscription

        db_mock = MagicMock()
        db_mock.query.return_value.filter.return_value.first.return_value = None

        request_mock = MagicMock()
        request_mock.session = {"user": {"email": "new@example.com"}}

        with (
            patch.object(app_settings, "multi_user_enabled", True),
            patch("app.api.subscriptions.apply_pending_subscription_changes"),
            patch("app.api.subscriptions.get_user_tier_id", return_value="free"),
            patch("app.api.subscriptions.get_tier", side_effect=lambda tid, db=None: {"id": tid}),
            patch("app.api.subscriptions.get_user_usage", return_value={}),
        ):
            result = my_subscription(request=request_mock, db=db_mock)

        assert result["pending_change"] is None
        assert result["period_start"] is None

    @pytest.mark.unit
    def test_my_subscription_multi_user_profile_no_pending_date(self):
        """Profile with pending tier but no pending date returns None effective_date."""
        from app.api.subscriptions import my_subscription

        profile_mock = MagicMock()
        profile_mock.subscription_tier = "starter"
        profile_mock.subscription_change_pending_tier = "free"
        profile_mock.subscription_change_pending_date = None
        profile_mock.subscription_period_start = None

        db_mock = MagicMock()
        db_mock.query.return_value.filter.return_value.first.return_value = profile_mock

        request_mock = MagicMock()
        request_mock.session = {"user": {"sub": "sub-xyz"}}

        with (
            patch.object(app_settings, "multi_user_enabled", True),
            patch("app.api.subscriptions.apply_pending_subscription_changes"),
            patch("app.api.subscriptions.get_user_tier_id", return_value="starter"),
            patch("app.api.subscriptions.get_tier", side_effect=lambda tid, db=None: {"id": tid}),
            patch("app.api.subscriptions.get_user_usage", return_value={}),
        ):
            result = my_subscription(request=request_mock, db=db_mock)

        assert result["pending_change"]["effective_date"] is None


# ---------------------------------------------------------------------------
# POST /api/subscriptions/change
# ---------------------------------------------------------------------------


class TestChangeSubscription:
    """Tests for the POST /change endpoint."""

    @pytest.mark.unit
    def test_single_user_mode_raises_400(self):
        """In single-user mode a change request should raise 400."""
        from app.api.subscriptions import SubscriptionChangeRequest, change_subscription

        body = SubscriptionChangeRequest(plan_id="starter")
        request_mock = MagicMock()
        request_mock.session = {"user": {"email": "u@example.com"}}
        db_mock = MagicMock()

        with patch.object(app_settings, "multi_user_enabled", False):
            with pytest.raises(HTTPException) as exc_info:
                change_subscription(request=request_mock, body=body, db=db_mock)
        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_unauthenticated_raises_401(self):
        """Unauthenticated request in multi-user mode should raise 401."""
        from app.api.subscriptions import SubscriptionChangeRequest, change_subscription

        body = SubscriptionChangeRequest(plan_id="starter")
        request_mock = MagicMock()
        request_mock.session = {}  # no user
        db_mock = MagicMock()

        with patch.object(app_settings, "multi_user_enabled", True):
            with pytest.raises(HTTPException) as exc_info:
                change_subscription(request=request_mock, body=body, db=db_mock)
        assert exc_info.value.status_code == 401

    @pytest.mark.unit
    def test_successful_change_returns_result(self):
        """A valid change request should return the result dict from request_subscription_change."""
        from app.api.subscriptions import SubscriptionChangeRequest, change_subscription

        expected = {"status": "upgraded", "tier": "professional"}
        body = SubscriptionChangeRequest(plan_id="professional", billing_cycle="yearly")
        request_mock = MagicMock()
        request_mock.session = {"user": {"email": "u@example.com"}}
        db_mock = MagicMock()

        with (
            patch.object(app_settings, "multi_user_enabled", True),
            patch("app.api.subscriptions.request_subscription_change", return_value=expected) as mock_change,
        ):
            result = change_subscription(request=request_mock, body=body, db=db_mock)

        assert result == expected
        mock_change.assert_called_once_with(db_mock, "u@example.com", "professional", "yearly")

    @pytest.mark.unit
    def test_subscription_change_error_raises_400(self):
        """A SubscriptionChangeError from the util should surface as HTTP 400."""
        from app.api.subscriptions import SubscriptionChangeRequest, change_subscription

        body = SubscriptionChangeRequest(plan_id="free")
        request_mock = MagicMock()
        request_mock.session = {"user": {"email": "u@example.com"}}
        db_mock = MagicMock()

        with (
            patch.object(app_settings, "multi_user_enabled", True),
            patch(
                "app.api.subscriptions.request_subscription_change",
                side_effect=SubscriptionChangeError("Already on that tier"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                change_subscription(request=request_mock, body=body, db=db_mock)

        assert exc_info.value.status_code == 400
        assert "Already on that tier" in exc_info.value.detail


# ---------------------------------------------------------------------------
# DELETE /api/subscriptions/change
# ---------------------------------------------------------------------------


class TestCancelSubscriptionChange:
    """Tests for the DELETE /change endpoint."""

    @pytest.mark.unit
    def test_single_user_mode_raises_400(self):
        """In single-user mode a cancel request should raise 400."""
        from app.api.subscriptions import cancel_subscription_change

        request_mock = MagicMock()
        request_mock.session = {"user": {"email": "u@example.com"}}
        db_mock = MagicMock()

        with patch.object(app_settings, "multi_user_enabled", False):
            with pytest.raises(HTTPException) as exc_info:
                cancel_subscription_change(request=request_mock, db=db_mock)
        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_unauthenticated_raises_401(self):
        """Unauthenticated request should raise 401."""
        from app.api.subscriptions import cancel_subscription_change

        request_mock = MagicMock()
        request_mock.session = {}
        db_mock = MagicMock()

        with patch.object(app_settings, "multi_user_enabled", True):
            with pytest.raises(HTTPException) as exc_info:
                cancel_subscription_change(request=request_mock, db=db_mock)
        assert exc_info.value.status_code == 401

    @pytest.mark.unit
    def test_no_pending_change_raises_404(self):
        """When cancel_pending_subscription_change returns False, endpoint raises 404."""
        from app.api.subscriptions import cancel_subscription_change

        request_mock = MagicMock()
        request_mock.session = {"user": {"email": "u@example.com"}}
        db_mock = MagicMock()

        with (
            patch.object(app_settings, "multi_user_enabled", True),
            patch("app.api.subscriptions.cancel_pending_subscription_change", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                cancel_subscription_change(request=request_mock, db=db_mock)
        assert exc_info.value.status_code == 404

    @pytest.mark.unit
    def test_successful_cancel_returns_confirmation(self):
        """When a pending change exists, endpoint returns cancelled=True."""
        from app.api.subscriptions import cancel_subscription_change

        request_mock = MagicMock()
        request_mock.session = {"user": {"email": "u@example.com"}}
        db_mock = MagicMock()

        with (
            patch.object(app_settings, "multi_user_enabled", True),
            patch("app.api.subscriptions.cancel_pending_subscription_change", return_value=True),
        ):
            result = cancel_subscription_change(request=request_mock, db=db_mock)

        assert result["cancelled"] is True
        assert "message" in result


# ---------------------------------------------------------------------------
# GET /api/subscriptions/platform
# ---------------------------------------------------------------------------


class TestPlatformStats:
    """Tests for the admin-only platform stats endpoint."""

    @pytest.mark.integration
    def test_returns_stats_with_empty_db(self, admin_client):
        """Admin endpoint with empty database should return zero counts."""
        with _patch_multi_user(True):
            resp = admin_client.get("/api/subscriptions/platform")
        assert resp.status_code == 200
        data = resp.json()
        assert data["files"]["total"] == 0
        assert data["files"]["today"] == 0
        assert data["files"]["this_month"] == 0
        assert data["files"]["with_ocr"] == 0
        assert data["users"]["unique_uploaders"] == 0
        assert "tier_distribution" in data["users"]
        assert "generated_at" in data

    @pytest.mark.integration
    def test_platform_stats_tier_distribution_has_all_tiers(self, admin_client):
        """tier_distribution should include all four tiers even when zero users."""
        with _patch_multi_user(True):
            resp = admin_client.get("/api/subscriptions/platform")
        data = resp.json()
        dist = data["users"]["tier_distribution"]
        for tid in ["free", "starter", "professional", "business"]:
            assert tid in dist

    @pytest.mark.integration
    def test_platform_stats_counts_files(self, admin_client, sub_session):
        """Platform stats should count FileRecord rows correctly."""
        # Add a FileRecord
        rec = FileRecord(
            filehash="abc",
            original_filename="doc.pdf",
            local_filename="/tmp/doc.pdf",
            file_size=512,
            mime_type="application/pdf",
            is_duplicate=False,
            owner_id="user1@example.com",
            ocr_text="some text",
        )
        sub_session.add(rec)
        sub_session.commit()

        with _patch_multi_user(True):
            resp = admin_client.get("/api/subscriptions/platform")
        data = resp.json()
        assert data["files"]["total"] >= 1
        assert data["files"]["with_ocr"] >= 1
        assert data["users"]["unique_uploaders"] >= 1

    @pytest.mark.integration
    def test_platform_stats_tier_distribution_counts_profiles(self, admin_client, sub_session):
        """tier_distribution should reflect UserProfile subscription_tier values."""
        p1 = UserProfile(user_id="u1@example.com", subscription_tier="starter")
        p2 = UserProfile(user_id="u2@example.com", subscription_tier="starter")
        p3 = UserProfile(user_id="u3@example.com", subscription_tier="professional")
        sub_session.add_all([p1, p2, p3])
        sub_session.commit()

        with _patch_multi_user(True):
            resp = admin_client.get("/api/subscriptions/platform")
        data = resp.json()
        dist = data["users"]["tier_distribution"]
        assert dist["starter"] >= 2
        assert dist["professional"] >= 1

    @pytest.mark.integration
    def test_platform_stats_forbidden_without_admin(self, anon_client):
        """Non-admin request should be rejected with 403."""
        resp = anon_client.get("/api/subscriptions/platform")
        assert resp.status_code == 403
