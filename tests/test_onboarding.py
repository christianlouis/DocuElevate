"""Unit tests for the onboarding wizard API (/api/onboarding).

Covers:
- GET /api/onboarding/status (auth required, new user, returning user)
- POST /api/onboarding/profile (saves display_name / contact_email)
- POST /api/onboarding/plan (saves tier + billing cycle, rejects invalid tiers)
- POST /api/onboarding/storage (saves preferred_destination)
- POST /api/onboarding/complete (marks onboarding_completed=True)
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import UserProfile

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TEST_USER = {
    "sub": "user-onb-123",
    "name": "Test User",
    "email": "test@example.com",
    "is_admin": False,
}


@pytest.fixture()
def ob_engine():
    """In-memory SQLite engine for onboarding tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def ob_session(ob_engine):
    """DB session scoped to one test."""
    Session = sessionmaker(bind=ob_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def ob_client_authed(ob_engine):
    """TestClient that bypasses auth by monkey-patching _get_current_user_id."""
    from app.api import onboarding as ob_module
    from app.main import app

    original = ob_module._get_current_user_id

    def override_db():
        Session = sessionmaker(bind=ob_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def fake_user_id(_request):
        return _TEST_USER["sub"]

    ob_module._get_current_user_id = fake_user_id
    app.dependency_overrides[get_db] = override_db

    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
        yield client

    ob_module._get_current_user_id = original
    app.dependency_overrides.clear()


def _make_profile(session, user_id: str, **kwargs) -> UserProfile:
    """Insert a UserProfile row with sensible defaults."""
    kwargs.setdefault("is_blocked", False)
    kwargs.setdefault("onboarding_completed", False)
    profile = UserProfile(user_id=user_id, **kwargs)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


# ---------------------------------------------------------------------------
# TestOnboardingAPI
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOnboardingAPI:
    """Unit tests for the /api/onboarding endpoints."""

    # ------------------------------------------------------------------
    # GET /api/onboarding/status
    # ------------------------------------------------------------------

    def test_status_requires_auth(self, ob_engine):
        """Unauthenticated requests to /status must return 401."""
        from app.main import app

        def override_db():
            Session = sessionmaker(bind=ob_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
            # No session user injected → _get_current_user_id raises 401
            resp = client.get("/api/onboarding/status")
        app.dependency_overrides.clear()

        assert resp.status_code == 401

    def test_status_returns_not_completed_for_new_user(self, ob_client_authed, ob_session):
        """A user with no profile should get completed=False and step=1."""
        resp = ob_client_authed.get("/api/onboarding/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is False
        assert data["step"] == 1
        assert data["profile"] is None

    def test_status_returns_not_completed_for_existing_incomplete_profile(self, ob_client_authed, ob_session):
        """A user with an existing profile but onboarding_completed=False → completed=False."""
        _make_profile(ob_session, _TEST_USER["sub"], display_name="Alice", onboarding_completed=False)
        resp = ob_client_authed.get("/api/onboarding/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is False
        assert data["profile"]["display_name"] == "Alice"

    def test_status_returns_completed_when_done(self, ob_client_authed, ob_session):
        """A user with onboarding_completed=True → completed=True and step=5."""
        _make_profile(ob_session, _TEST_USER["sub"], onboarding_completed=True)
        resp = ob_client_authed.get("/api/onboarding/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is True
        assert data["step"] == 5

    # ------------------------------------------------------------------
    # POST /api/onboarding/profile
    # ------------------------------------------------------------------

    def test_save_profile_updates_display_name(self, ob_client_authed, ob_session):
        """POST /profile should persist display_name to UserProfile."""
        resp = ob_client_authed.post(
            "/api/onboarding/profile",
            json={"display_name": "Jane Doe", "contact_email": "jane@example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["display_name"] == "Jane Doe"
        assert data["contact_email"] == "jane@example.com"

        # Verify DB was actually updated
        profile = ob_session.query(UserProfile).filter(UserProfile.user_id == _TEST_USER["sub"]).first()
        assert profile is not None
        assert profile.display_name == "Jane Doe"
        assert profile.contact_email == "jane@example.com"

    def test_save_profile_requires_auth(self, ob_engine):
        """POST /profile without auth should return 401."""
        from app.main import app

        def override_db():
            Session = sessionmaker(bind=ob_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
            resp = client.post("/api/onboarding/profile", json={"display_name": "x"})
        app.dependency_overrides.clear()

        assert resp.status_code == 401

    def test_save_profile_null_fields_allowed(self, ob_client_authed, ob_session):
        """Sending null for display_name and contact_email should succeed."""
        resp = ob_client_authed.post(
            "/api/onboarding/profile",
            json={"display_name": None, "contact_email": None},
        )
        assert resp.status_code == 200

    # ------------------------------------------------------------------
    # POST /api/onboarding/plan
    # ------------------------------------------------------------------

    def test_save_plan_updates_subscription_tier(self, ob_client_authed, ob_session):
        """POST /plan should persist the chosen tier and billing cycle."""
        resp = ob_client_authed.post(
            "/api/onboarding/plan",
            json={"subscription_tier": "starter", "billing_cycle": "monthly"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["subscription_tier"] == "starter"
        assert data["subscription_billing_cycle"] == "monthly"

        profile = ob_session.query(UserProfile).filter(UserProfile.user_id == _TEST_USER["sub"]).first()
        assert profile.subscription_tier == "starter"

    def test_save_plan_yearly_billing(self, ob_client_authed, ob_session):
        """POST /plan with billing_cycle=yearly should persist correctly."""
        resp = ob_client_authed.post(
            "/api/onboarding/plan",
            json={"subscription_tier": "professional", "billing_cycle": "yearly"},
        )
        assert resp.status_code == 200
        assert resp.json()["subscription_billing_cycle"] == "yearly"

    def test_save_plan_rejects_invalid_tier(self, ob_client_authed):
        """POST /plan with an unknown tier should return 422."""
        resp = ob_client_authed.post(
            "/api/onboarding/plan",
            json={"subscription_tier": "unicorn", "billing_cycle": "monthly"},
        )
        assert resp.status_code == 422
        assert "Invalid subscription_tier" in resp.json()["detail"]

    def test_save_plan_rejects_invalid_billing_cycle(self, ob_client_authed):
        """POST /plan with an invalid billing_cycle value should return 422."""
        resp = ob_client_authed.post(
            "/api/onboarding/plan",
            json={"subscription_tier": "free", "billing_cycle": "weekly"},
        )
        assert resp.status_code == 422

    # ------------------------------------------------------------------
    # POST /api/onboarding/storage
    # ------------------------------------------------------------------

    def test_save_storage_updates_preferred_destination(self, ob_client_authed, ob_session):
        """POST /storage should persist the preferred_destination."""
        resp = ob_client_authed.post(
            "/api/onboarding/storage",
            json={"preferred_destination": "dropbox"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["preferred_destination"] == "dropbox"

        profile = ob_session.query(UserProfile).filter(UserProfile.user_id == _TEST_USER["sub"]).first()
        assert profile.preferred_destination == "dropbox"

    def test_save_storage_accepts_null_destination(self, ob_client_authed, ob_session):
        """POST /storage with null preferred_destination should succeed (skip storage)."""
        resp = ob_client_authed.post(
            "/api/onboarding/storage",
            json={"preferred_destination": None},
        )
        assert resp.status_code == 200
        assert resp.json()["preferred_destination"] is None

    # ------------------------------------------------------------------
    # POST /api/onboarding/complete
    # ------------------------------------------------------------------

    def test_complete_sets_onboarding_completed(self, ob_client_authed, ob_session):
        """POST /complete should set onboarding_completed=True on the profile."""
        _make_profile(ob_session, _TEST_USER["sub"])
        resp = ob_client_authed.post("/api/onboarding/complete")
        assert resp.status_code == 200
        assert resp.json() == {"success": True}

        # Re-query to see persisted value
        ob_session.expire_all()
        profile = ob_session.query(UserProfile).filter(UserProfile.user_id == _TEST_USER["sub"]).first()
        assert profile.onboarding_completed is True
        assert profile.onboarding_completed_at is not None

    def test_complete_creates_profile_if_missing(self, ob_client_authed, ob_session):
        """POST /complete should create a profile when none exists and mark it done."""
        resp = ob_client_authed.post("/api/onboarding/complete")
        assert resp.status_code == 200

        profile = ob_session.query(UserProfile).filter(UserProfile.user_id == _TEST_USER["sub"]).first()
        assert profile is not None
        assert profile.onboarding_completed is True

    def test_complete_requires_auth(self, ob_engine):
        """POST /complete without auth should return 401."""
        from app.main import app

        def override_db():
            Session = sessionmaker(bind=ob_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
            resp = client.post("/api/onboarding/complete")
        app.dependency_overrides.clear()

        assert resp.status_code == 401
