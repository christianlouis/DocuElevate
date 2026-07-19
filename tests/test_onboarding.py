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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import DEFAULT_TENANT_ID, Tribe, TribeMembership, UserProfile
from app.utils.tribe_scope import personal_tribe_id

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
        """A user with onboarding_completed=True → completed=True and final journey step."""
        _make_profile(ob_session, _TEST_USER["sub"], onboarding_completed=True)
        resp = ob_client_authed.get("/api/onboarding/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is True
        assert data["step"] == 8

    def test_progress_persists_resume_and_skipped_topic(self, ob_client_authed, ob_session):
        resp = ob_client_authed.post(
            "/api/onboarding/progress",
            json={"current_step": 6, "skipped_topic": "sources"},
        )
        assert resp.status_code == 200
        assert resp.json()["step"] == 6
        assert resp.json()["journey"]["skipped"] == ["sources"]

        status_response = ob_client_authed.get("/api/onboarding/status")
        assert status_response.json()["step"] == 6
        assert status_response.json()["profile"]["onboarding_journey"]["skipped"] == ["sources"]

    def test_progress_rejects_unknown_topic(self, ob_client_authed):
        resp = ob_client_authed.post(
            "/api/onboarding/progress",
            json={"current_step": 2, "completed_topic": "credentials"},
        )
        assert resp.status_code == 422

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

        personal = ob_session.get(Tribe, personal_tribe_id(_TEST_USER["sub"]))
        assert personal is not None
        membership = ob_session.query(TribeMembership).filter_by(tribe_id=personal.id, user_id=_TEST_USER["sub"]).one()
        assert membership.role == "admin"
        assert data["spaces"] == [
            {
                "tenant_id": DEFAULT_TENANT_ID,
                "tribe_id": personal.id,
                "name": f"Personal space for {_TEST_USER['sub']}",
                "role": "admin",
                "is_personal": True,
            }
        ]
        assert data["onboarding_journey"]["space_mode"] == "personal"
        assert data["onboarding_journey"]["selected_tribe_id"] == personal.id

    def test_save_profile_can_create_shared_tribe_idempotently(self, ob_client_authed, ob_session):
        payload = {
            "display_name": "Jane Doe",
            "space_mode": "shared",
            "tribe_name": "  Family   Example  ",
        }
        first = ob_client_authed.post("/api/onboarding/profile", json=payload)
        second = ob_client_authed.post("/api/onboarding/profile", json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        shared = ob_session.query(Tribe).filter(Tribe.name == "Family Example").one()
        assert ob_session.query(Tribe).filter(Tribe.name == "Family Example").count() == 1
        membership = ob_session.query(TribeMembership).filter_by(tribe_id=shared.id, user_id=_TEST_USER["sub"]).one()
        assert membership.role == "admin"
        assert sum(not space["is_personal"] for space in second.json()["spaces"]) == 1
        assert second.json()["onboarding_journey"]["space_mode"] == "shared"
        assert second.json()["onboarding_journey"]["selected_tribe_id"] == shared.id

    def test_save_profile_reuses_unicode_equivalent_shared_name(self, ob_client_authed, ob_session):
        first = ob_client_authed.post(
            "/api/onboarding/profile",
            json={"space_mode": "shared", "tribe_name": "Familie Straße"},
        )
        second = ob_client_authed.post(
            "/api/onboarding/profile",
            json={"space_mode": "shared", "tribe_name": "Familie STRASSE"},
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert ob_session.query(Tribe).filter(Tribe.name.like("Familie%")).count() == 1
        assert (
            second.json()["onboarding_journey"]["selected_tribe_id"]
            == first.json()["onboarding_journey"]["selected_tribe_id"]
        )

    def test_save_profile_rejects_joining_existing_tribe_by_name(self, ob_client_authed, ob_session):
        from app.models import Tenant

        ob_session.add(Tenant(id=DEFAULT_TENANT_ID, name="Default tenant"))
        ob_session.flush()
        ob_session.add(Tribe(id="existing-shared", tenant_id=DEFAULT_TENANT_ID, name="Family Example"))
        ob_session.commit()

        response = ob_client_authed.post(
            "/api/onboarding/profile",
            json={"space_mode": "shared", "tribe_name": "family example"},
        )

        assert response.status_code == 409
        assert "invitation" in response.json()["detail"]
        assert (
            ob_session.query(TribeMembership).filter_by(tribe_id="existing-shared", user_id=_TEST_USER["sub"]).count()
            == 0
        )

    def test_save_profile_requires_shared_tribe_name(self, ob_client_authed):
        response = ob_client_authed.post(
            "/api/onboarding/profile",
            json={"space_mode": "shared", "tribe_name": "   "},
        )
        assert response.status_code == 422

    def test_save_profile_reserves_generated_personal_space_names(self, ob_client_authed):
        response = ob_client_authed.post(
            "/api/onboarding/profile",
            json={"space_mode": "shared", "tribe_name": "Personal space for future-user"},
        )
        assert response.status_code == 422

    def test_save_profile_maps_concurrent_shared_insert_conflict_to_invitation(
        self,
        ob_client_authed,
        ob_session,
        monkeypatch,
    ):
        """A unique conflict after lookup stays a safe 409 instead of becoming a 500."""
        original_flush = Session.flush
        collision_seen = False

        def flush_with_shared_collision(self, objects=None):
            nonlocal collision_seen
            if not collision_seen and any(isinstance(obj, Tribe) and obj.name == "Family Race" for obj in self.new):
                collision_seen = True
                raise IntegrityError(
                    "INSERT INTO tribes",
                    {},
                    RuntimeError("simulated concurrent unique conflict"),
                )
            return original_flush(self, objects)

        monkeypatch.setattr(Session, "flush", flush_with_shared_collision)

        response = ob_client_authed.post(
            "/api/onboarding/profile",
            json={"space_mode": "shared", "tribe_name": "Family Race"},
        )

        assert collision_seen is True
        assert response.status_code == 409
        assert "invitation" in response.json()["detail"]
        assert ob_session.query(Tribe).filter(Tribe.name == "Family Race").count() == 0

    def test_progress_preserves_explicit_space_selection(self, ob_client_authed):
        profile_response = ob_client_authed.post(
            "/api/onboarding/profile",
            json={"space_mode": "shared", "tribe_name": "Family Example"},
        )
        selected_tribe_id = profile_response.json()["onboarding_journey"]["selected_tribe_id"]

        progress_response = ob_client_authed.post(
            "/api/onboarding/progress",
            json={"current_step": 3, "completed_topic": "profile"},
        )

        assert progress_response.status_code == 200
        journey = progress_response.json()["journey"]
        assert journey["space_mode"] == "shared"
        assert journey["selected_tribe_id"] == selected_tribe_id

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
        data = resp.json()
        assert data["success"] is True
        assert data["redirect_url"] == "/upload?onboarding=first-document"

        # Re-query to see persisted value
        ob_session.expire_all()
        profile = ob_session.query(UserProfile).filter(UserProfile.user_id == _TEST_USER["sub"]).first()
        assert profile.onboarding_completed is True
        assert profile.onboarding_completed_at is not None
        assert profile.onboarding_current_step == 8

    def test_complete_uses_session_redirect_url(self, ob_client_authed, ob_session):
        """POST /complete should return the redirect_url from the session."""
        from unittest.mock import patch

        _make_profile(ob_session, _TEST_USER["sub"])

        # We patch FastAPI's Request.session property to simulate an active session
        with patch("fastapi.Request.session", new_callable=lambda: {"post_onboarding_redirect": "/custom-dashboard"}):
            resp = ob_client_authed.post("/api/onboarding/complete")

        assert resp.status_code == 200
        assert resp.json()["redirect_url"] == "/custom-dashboard"

        ob_session.expire_all()
        profile = ob_session.query(UserProfile).filter(UserProfile.user_id == _TEST_USER["sub"]).first()
        assert profile.onboarding_completed is True

    def test_complete_db_error_triggers_rollback(self, ob_client_authed, ob_session):
        """POST /complete should rollback and raise 500 if DB commit fails."""
        from unittest.mock import patch

        with patch("sqlalchemy.orm.Session.commit", side_effect=Exception("DB Error")):
            resp = ob_client_authed.post("/api/onboarding/complete")
            assert resp.status_code == 500

    def test_complete_creates_profile_if_missing(self, ob_client_authed, ob_session):
        """POST /complete should create a profile when none exists and mark it done."""
        resp = ob_client_authed.post("/api/onboarding/complete")
        assert resp.status_code == 200

        profile = ob_session.query(UserProfile).filter(UserProfile.user_id == _TEST_USER["sub"]).first()
        assert profile is not None
        assert profile.onboarding_completed is True
        assert ob_session.get(Tribe, personal_tribe_id(_TEST_USER["sub"])) is not None

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

    def test_complete_uses_post_onboarding_redirect(self, ob_client_authed, ob_session):
        """POST /complete should read and clear the post_onboarding_redirect session key."""
        _make_profile(ob_session, _TEST_USER["sub"])

        # Send a request using a custom TestClient request builder that can intercept and inject session
        from unittest.mock import patch

        # Since Starlette uses session dictionaries added to the request scope,
        # we can patch the complete_onboarding endpoint's access to request.session
        with patch("app.api.onboarding.Request.session", new_callable=dict) as mock_session:
            mock_session.update({"post_onboarding_redirect": "/dashboard"})

            resp = ob_client_authed.post("/api/onboarding/complete")

        assert resp.status_code == 200
        assert resp.json()["redirect_url"] == "/dashboard"
        # Verify it was popped
        assert "post_onboarding_redirect" not in mock_session

    def test_complete_normalizes_plain_upload_redirect(self, ob_client_authed, ob_session):
        """The auth flow's plain upload target should retain first-document guidance."""
        from unittest.mock import patch

        with patch("app.api.onboarding.Request.session", new_callable=dict) as mock_session:
            mock_session.update({"post_onboarding_redirect": "/upload"})
            response = ob_client_authed.post("/api/onboarding/complete")

        assert response.status_code == 200
        assert response.json()["redirect_url"] == "/upload?onboarding=first-document"

    def test_complete_exception_rollback(self, ob_client_authed, ob_session):
        """POST /complete should rollback and re-raise if commit fails."""
        _make_profile(ob_session, _TEST_USER["sub"])

        # Patch db.commit to raise an exception
        from unittest.mock import patch

        with patch("sqlalchemy.orm.Session.commit", side_effect=Exception("DB error")) as mock_commit:
            with patch("sqlalchemy.orm.Session.rollback") as mock_rollback:
                resp = ob_client_authed.post("/api/onboarding/complete")

                # Fast API error handler handles the exception and returns a 500 error
                assert resp.status_code == 500

                mock_commit.assert_called_once()
                mock_rollback.assert_called_once()
