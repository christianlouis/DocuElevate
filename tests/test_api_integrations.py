"""Tests for the per-user integrations API (app/api/integrations.py)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import SubscriptionPlan, UserIntegration, UserProfile

# ---------------------------------------------------------------------------
# Test data constants
# ---------------------------------------------------------------------------

_OWNER = "test_user@example.com"
_OTHER_OWNER = "other_user@example.com"

_IMAP_SOURCE = {
    "direction": "SOURCE",
    "integration_type": "IMAP",
    "name": "Work Gmail",
    "config": {"host": "imap.gmail.com", "port": 993, "username": "work@example.com", "use_ssl": True},
    "credentials": {"password": "s3cr3t"},
    "is_active": True,
}

_S3_DESTINATION = {
    "direction": "DESTINATION",
    "integration_type": "S3",
    "name": "Archive Bucket",
    "config": {"bucket": "my-bucket", "region": "us-east-1"},
    "credentials": {
        "access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    },
    "is_active": True,
}


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _make_profile(session, owner: str = _OWNER, tier: str = "business") -> UserProfile:
    """Create a UserProfile row for the given user and tier."""
    profile = UserProfile(user_id=owner, subscription_tier=tier)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def _make_plan(
    session,
    tier: str = "business",
    max_storage_destinations: int = 10,
    max_mailboxes: int = 0,
) -> SubscriptionPlan:
    """Create a SubscriptionPlan row."""
    plan = SubscriptionPlan(
        plan_id=tier,
        name=tier.title(),
        price_monthly=7.99,
        price_yearly=76.99,
        max_storage_destinations=max_storage_destinations,
        max_mailboxes=max_mailboxes,
        is_active=True,
    )
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


@pytest.fixture()
def int_engine():
    """In-memory SQLite engine for integration tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def int_session(int_engine):
    """DB session scoped to one test."""
    Session = sessionmaker(bind=int_engine)
    session = Session()
    yield session
    session.close()


def _seed_default_plan(engine, owner_id: str = _OWNER) -> None:
    """Seed a generous (business-tier) plan and profile for the given user.

    Called automatically by ``_make_client`` so that existing CRUD tests keep
    working after quota enforcement was added.
    """
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        if not session.query(SubscriptionPlan).filter(SubscriptionPlan.plan_id == "business").first():
            session.add(
                SubscriptionPlan(
                    plan_id="business",
                    name="Power",
                    price_monthly=7.99,
                    price_yearly=76.99,
                    max_storage_destinations=10,
                    max_mailboxes=0,  # 0 = unlimited for paid tiers
                    is_active=True,
                )
            )
        if not session.query(UserProfile).filter(UserProfile.user_id == owner_id).first():
            session.add(UserProfile(user_id=owner_id, subscription_tier="business"))
        session.commit()
    finally:
        session.close()


def _make_client(int_engine, owner_id: str = _OWNER):
    """Return a TestClient with *owner_id* injected as the authenticated user."""
    from app.api.integrations import _get_owner_id
    from app.main import app

    _seed_default_plan(int_engine, owner_id)

    def override_db():
        Session = sessionmaker(bind=int_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def override_owner():
        return owner_id

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[_get_owner_id] = override_owner
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def int_client(int_engine):
    """TestClient authenticated as _OWNER."""
    yield from _make_client(int_engine, _OWNER)


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCreateIntegration:
    """Tests for POST /api/integrations/."""

    def test_create_source_integration(self, int_client):
        """Create a SOURCE integration and verify the response."""
        resp = int_client.post("/api/integrations/", json=_IMAP_SOURCE)
        assert resp.status_code == 201
        data = resp.json()
        assert data["direction"] == "SOURCE"
        assert data["integration_type"] == "IMAP"
        assert data["name"] == "Work Gmail"
        assert data["config"]["host"] == "imap.gmail.com"
        assert data["has_credentials"] is True
        # Credentials must never appear in the response
        assert "credentials" not in data
        assert "password" not in data

    def test_create_destination_integration(self, int_client):
        """Create a DESTINATION integration and verify the response."""
        resp = int_client.post("/api/integrations/", json=_S3_DESTINATION)
        assert resp.status_code == 201
        data = resp.json()
        assert data["direction"] == "DESTINATION"
        assert data["integration_type"] == "S3"
        assert data["has_credentials"] is True

    def test_create_without_credentials(self, int_client):
        """Integration without credentials sets has_credentials to False."""
        payload = dict(_IMAP_SOURCE)
        payload["credentials"] = None
        resp = int_client.post("/api/integrations/", json=payload)
        assert resp.status_code == 201
        assert resp.json()["has_credentials"] is False

    def test_create_invalid_direction(self, int_client):
        """An unknown direction returns 400."""
        payload = dict(_IMAP_SOURCE, direction="INVALID")
        resp = int_client.post("/api/integrations/", json=payload)
        assert resp.status_code == 400

    def test_create_invalid_type(self, int_client):
        """An unknown integration_type returns 400."""
        payload = dict(_IMAP_SOURCE, integration_type="UNKNOWN_TYPE")
        resp = int_client.post("/api/integrations/", json=payload)
        assert resp.status_code == 400

    def test_credentials_are_encrypted_in_db(self, int_client, int_session):
        """Stored credentials must be encrypted (enc: prefix)."""
        resp = int_client.post("/api/integrations/", json=_IMAP_SOURCE)
        assert resp.status_code == 201
        rec = int_session.query(UserIntegration).first()
        assert rec is not None
        assert rec.credentials is not None
        assert rec.credentials.startswith("enc:")


@pytest.mark.integration
class TestListIntegrations:
    """Tests for GET /api/integrations/."""

    def test_list_empty(self, int_client):
        """No integrations returns empty list."""
        resp = int_client.get("/api/integrations/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_own_records(self, int_client, int_session):
        """Users only see their own integrations."""
        # Create an integration for _OWNER via the API client
        int_client.post("/api/integrations/", json=_IMAP_SOURCE)

        # Create an integration for a different owner directly in the DB
        other_integration = UserIntegration(
            owner_id=_OTHER_OWNER,
            direction="DESTINATION",
            integration_type="S3",
            name="Archive Bucket",
            config='{"bucket": "other-bucket"}',
            is_active=True,
        )
        int_session.add(other_integration)
        int_session.commit()

        resp = int_client.get("/api/integrations/")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["integration_type"] == "IMAP"

    def test_filter_by_direction(self, int_client):
        """direction query param filters results."""
        int_client.post("/api/integrations/", json=_IMAP_SOURCE)
        int_client.post("/api/integrations/", json=_S3_DESTINATION)

        resp = int_client.get("/api/integrations/?direction=SOURCE")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["direction"] == "SOURCE"

    def test_filter_by_integration_type(self, int_client):
        """integration_type query param filters results."""
        int_client.post("/api/integrations/", json=_IMAP_SOURCE)
        int_client.post("/api/integrations/", json=_S3_DESTINATION)

        resp = int_client.get("/api/integrations/?integration_type=S3")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["integration_type"] == "S3"

    def test_filter_invalid_direction_returns_400(self, int_client):
        """Unknown direction filter returns 400."""
        resp = int_client.get("/api/integrations/?direction=BAD")
        assert resp.status_code == 400

    def test_filter_invalid_type_returns_400(self, int_client):
        """Unknown integration_type filter returns 400."""
        resp = int_client.get("/api/integrations/?integration_type=BAD")
        assert resp.status_code == 400


@pytest.mark.integration
class TestGetIntegration:
    """Tests for GET /api/integrations/{id}."""

    def test_get_existing(self, int_client):
        """Retrieve a single integration by ID."""
        created = int_client.post("/api/integrations/", json=_IMAP_SOURCE).json()
        resp = int_client.get(f"/api/integrations/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_get_not_found(self, int_client):
        """Non-existent ID returns 404."""
        resp = int_client.get("/api/integrations/9999")
        assert resp.status_code == 404

    def test_get_other_users_integration(self, int_client, int_session):
        """Cannot retrieve another user's integration."""
        other_integration = UserIntegration(
            owner_id=_OTHER_OWNER,
            direction="SOURCE",
            integration_type="IMAP",
            name="Other Mailbox",
            is_active=True,
        )
        int_session.add(other_integration)
        int_session.commit()
        resp = int_client.get(f"/api/integrations/{other_integration.id}")
        assert resp.status_code == 404


@pytest.mark.integration
class TestUpdateIntegration:
    """Tests for PUT /api/integrations/{id}."""

    def test_update_name(self, int_client):
        """Update the name of an integration."""
        created = int_client.post("/api/integrations/", json=_IMAP_SOURCE).json()
        resp = int_client.put(f"/api/integrations/{created['id']}", json={"name": "Personal Gmail"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Personal Gmail"

    def test_update_config(self, int_client):
        """Update the config dict."""
        created = int_client.post("/api/integrations/", json=_IMAP_SOURCE).json()
        new_config = {"host": "imap.new.com", "port": 143, "username": "new@example.com", "use_ssl": False}
        resp = int_client.put(f"/api/integrations/{created['id']}", json={"config": new_config})
        assert resp.status_code == 200
        assert resp.json()["config"]["host"] == "imap.new.com"

    def test_update_credentials_re_encrypts(self, int_client, int_session):
        """Updating credentials stores the new value encrypted."""
        created = int_client.post("/api/integrations/", json=_IMAP_SOURCE).json()
        first_enc = int_session.query(UserIntegration).get(created["id"]).credentials

        resp = int_client.put(f"/api/integrations/{created['id']}", json={"credentials": {"password": "new_password"}})
        assert resp.status_code == 200
        int_session.expire_all()
        second_enc = int_session.query(UserIntegration).get(created["id"]).credentials
        # Both must be encrypted
        assert second_enc.startswith("enc:")
        # They should be different ciphertexts (Fernet uses random IV)
        assert first_enc != second_enc

    def test_update_is_active(self, int_client):
        """Deactivate an integration."""
        created = int_client.post("/api/integrations/", json=_IMAP_SOURCE).json()
        resp = int_client.put(f"/api/integrations/{created['id']}", json={"is_active": False})
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_update_not_found(self, int_client):
        """Updating a non-existent integration returns 404."""
        resp = int_client.put("/api/integrations/9999", json={"name": "Ghost"})
        assert resp.status_code == 404

    def test_update_clears_last_error(self, int_client, int_session):
        """Updating an integration resets last_error."""
        created = int_client.post("/api/integrations/", json=_IMAP_SOURCE).json()
        rec = int_session.query(UserIntegration).get(created["id"])
        rec.last_error = "Previous failure"
        int_session.commit()

        int_client.put(f"/api/integrations/{created['id']}", json={"name": "Updated"})
        int_session.expire_all()
        rec = int_session.query(UserIntegration).get(created["id"])
        assert rec.last_error is None


@pytest.mark.integration
class TestDeleteIntegration:
    """Tests for DELETE /api/integrations/{id}."""

    def test_delete_existing(self, int_client, int_session):
        """Delete an integration and confirm it is removed from the DB."""
        created = int_client.post("/api/integrations/", json=_IMAP_SOURCE).json()
        resp = int_client.delete(f"/api/integrations/{created['id']}")
        assert resp.status_code == 204
        assert int_session.query(UserIntegration).get(created["id"]) is None

    def test_delete_not_found(self, int_client):
        """Deleting a non-existent integration returns 404."""
        resp = int_client.delete("/api/integrations/9999")
        assert resp.status_code == 404

    def test_delete_other_users_integration(self, int_client, int_session):
        """Cannot delete another user's integration."""
        other_integration = UserIntegration(
            owner_id=_OTHER_OWNER,
            direction="SOURCE",
            integration_type="IMAP",
            name="Other Mailbox",
            is_active=True,
        )
        int_session.add(other_integration)
        int_session.commit()
        resp = int_client.delete(f"/api/integrations/{other_integration.id}")
        assert resp.status_code == 404


@pytest.mark.integration
class TestTestSavedIntegrationConnection:
    """Tests for POST /api/integrations/{id}/test."""

    @patch("app.api.integrations._CONNECTION_TESTERS")
    def test_test_saved_integration_success(self, mock_testers, int_client):
        """Test a saved integration successfully."""
        mock_tester = MagicMock(return_value={"success": True, "message": "OK"})
        mock_testers.get.return_value = mock_tester

        created = int_client.post("/api/integrations/", json=_IMAP_SOURCE).json()
        resp = int_client.post(f"/api/integrations/{created['id']}/test")

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_testers.get.assert_called_with("IMAP")
        mock_tester.assert_called_once()
        args = mock_tester.call_args[0]
        assert args[0]["host"] == "imap.gmail.com"
        assert args[1]["password"] == "s3cr3t"

    def test_not_found(self, int_client):
        """Non-existent integration returns 404."""
        resp = int_client.post("/api/integrations/9999/test")
        assert resp.status_code == 404

    def test_other_users_integration_returns_404(self, int_client, int_session):
        """Cannot test another user's integration."""
        other_integration = UserIntegration(
            owner_id=_OTHER_OWNER,
            direction="SOURCE",
            integration_type="IMAP",
            name="Other Mailbox",
            credentials='{"password": "secret"}',
            is_active=True,
        )
        int_session.add(other_integration)
        int_session.commit()
        resp = int_client.post(f"/api/integrations/{other_integration.id}/test")
        assert resp.status_code == 404


@pytest.mark.unit
class TestIntegrationModel:
    """Unit tests for the UserIntegration model and helper constants."""

    def test_integration_direction_constants(self):
        """IntegrationDirection has expected values."""
        from app.models import IntegrationDirection

        assert IntegrationDirection.SOURCE == "SOURCE"
        assert IntegrationDirection.DESTINATION == "DESTINATION"
        assert "SOURCE" in IntegrationDirection.ALL
        assert "DESTINATION" in IntegrationDirection.ALL

    def test_integration_type_constants(self):
        """IntegrationType has expected values."""
        from app.models import IntegrationType

        assert IntegrationType.IMAP == "IMAP"
        assert IntegrationType.S3 == "S3"
        assert IntegrationType.DROPBOX == "DROPBOX"
        assert IntegrationType.GOOGLE_DRIVE == "GOOGLE_DRIVE"
        assert IntegrationType.ONEDRIVE == "ONEDRIVE"
        assert IntegrationType.WEBDAV == "WEBDAV"
        assert IntegrationType.NEXTCLOUD == "NEXTCLOUD"
        assert IntegrationType.WATCH_FOLDER == "WATCH_FOLDER"
        assert IntegrationType.WEBHOOK == "WEBHOOK"
        assert IntegrationType.FTP == "FTP"
        assert IntegrationType.SFTP == "SFTP"
        assert IntegrationType.EMAIL == "EMAIL"
        assert IntegrationType.PAPERLESS == "PAPERLESS"
        assert IntegrationType.RCLONE == "RCLONE"

    def test_user_integration_tablename(self):
        """UserIntegration uses the correct table name."""
        assert UserIntegration.__tablename__ == "user_integrations"

    def test_user_integration_fields(self):
        """UserIntegration has all required columns."""
        cols = {c.key for c in UserIntegration.__table__.columns}
        expected = {
            "id",
            "owner_id",
            "direction",
            "integration_type",
            "name",
            "config",
            "credentials",
            "is_active",
            "last_used_at",
            "last_error",
            "created_at",
            "updated_at",
        }
        assert expected <= cols


@pytest.mark.unit
class TestCredentialHelpers:
    """Unit tests for the credential encode/decode helpers in integrations.py."""

    def test_encode_decode_round_trip(self):
        """Encoding then decoding returns the original dict."""
        from app.api.integrations import _decode_credentials, _encode_credentials

        original = {"password": "super_secret", "token": "abc123"}
        encoded = _encode_credentials(original)
        assert encoded is not None
        decoded = _decode_credentials(encoded)
        assert decoded == original

    def test_encode_none_returns_none(self):
        """Encoding None returns None."""
        from app.api.integrations import _encode_credentials

        assert _encode_credentials(None) is None

    def test_encode_empty_dict_returns_none(self):
        """Encoding an empty dict returns None."""
        from app.api.integrations import _encode_credentials

        assert _encode_credentials({}) is None

    def test_decode_none_returns_none(self):
        """Decoding None returns None."""
        from app.api.integrations import _decode_credentials

        assert _decode_credentials(None) is None

    def test_decode_empty_string_returns_none(self):
        """Decoding an empty string returns None."""
        from app.api.integrations import _decode_credentials

        assert _decode_credentials("") is None

    def test_decode_invalid_json_returns_none(self):
        """Decoding a non-JSON plaintext string returns None."""
        from app.api.integrations import _decode_credentials

        # A non-JSON plaintext string (no enc: prefix) that decrypt_value returns as-is
        assert _decode_credentials("not-valid-json") is None


@pytest.mark.unit
class TestImapPasswordEncryption:
    """Unit tests verifying that IMAP passwords are encrypted at rest."""

    def test_create_encrypts_password(self, int_engine):
        """Creating an IMAP account stores the password encrypted."""
        from app.api.imap_accounts import _get_owner_id
        from app.main import app
        from app.models import SubscriptionPlan, UserImapAccount, UserProfile

        Session = sessionmaker(bind=int_engine)

        def override_db():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        def override_owner():
            return _OWNER

        # Seed a paid plan (max_mailboxes=0 means unlimited for paid) and profile
        setup_session = Session()
        plan = SubscriptionPlan(
            plan_id="paid",
            name="Paid",
            price_monthly=9.99,
            price_yearly=99.99,
            max_mailboxes=0,  # 0 = unlimited for paid plans
            is_active=True,
        )
        setup_session.add(plan)
        profile = UserProfile(user_id=_OWNER, subscription_tier="paid")
        setup_session.add(profile)
        setup_session.commit()
        setup_session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[_get_owner_id] = override_owner
        try:
            with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
                payload = {
                    "name": "Test",
                    "host": "imap.example.com",
                    "port": 993,
                    "username": "user@example.com",
                    "password": "plaintext_password",
                    "use_ssl": True,
                    "delete_after_process": False,
                    "is_active": True,
                }
                resp = client.post("/api/imap-accounts/", json=payload)
                assert resp.status_code == 201

                # Verify the stored password is encrypted
                verify_session = Session()
                acct = verify_session.query(UserImapAccount).first()
                assert acct is not None
                assert acct.password != "plaintext_password"
                assert acct.password.startswith("enc:")
                verify_session.close()
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Quota enforcement tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestQuotaEnforcementDestinations:
    """Tests for destination quota enforcement on POST /api/integrations/."""

    def test_create_destination_blocked_at_limit(self, int_engine, int_session):
        """Users at the destination quota limit receive a 403."""
        _make_profile(int_session, tier="starter")
        _make_plan(int_session, tier="starter", max_storage_destinations=1, max_mailboxes=1)

        from app.api.integrations import _get_owner_id
        from app.main import app

        def override_db():
            Session = sessionmaker(bind=int_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[_get_owner_id] = lambda: _OWNER

        try:
            with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
                # First destination should succeed
                resp1 = client.post("/api/integrations/", json=_S3_DESTINATION)
                assert resp1.status_code == 201

                # Second destination should be blocked
                second = dict(_S3_DESTINATION, name="Second Bucket")
                resp2 = client.post("/api/integrations/", json=second)
                assert resp2.status_code == 403
                assert "limit" in resp2.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_create_destination_allowed_under_limit(self, int_engine, int_session):
        """Users under the destination quota can create integrations."""
        _make_profile(int_session, tier="professional")
        _make_plan(int_session, tier="professional", max_storage_destinations=5, max_mailboxes=3)

        from app.api.integrations import _get_owner_id
        from app.main import app

        def override_db():
            Session = sessionmaker(bind=int_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[_get_owner_id] = lambda: _OWNER

        try:
            with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
                resp = client.post("/api/integrations/", json=_S3_DESTINATION)
                assert resp.status_code == 201
        finally:
            app.dependency_overrides.clear()

    def test_free_tier_allows_one_destination(self, int_engine, int_session):
        """Free tier allows exactly 1 destination."""
        _make_profile(int_session, tier="free")
        _make_plan(int_session, tier="free", max_storage_destinations=1, max_mailboxes=0)

        from app.api.integrations import _get_owner_id
        from app.main import app

        def override_db():
            Session = sessionmaker(bind=int_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[_get_owner_id] = lambda: _OWNER

        try:
            with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
                resp1 = client.post("/api/integrations/", json=_S3_DESTINATION)
                assert resp1.status_code == 201

                second = dict(_S3_DESTINATION, name="Second")
                resp2 = client.post("/api/integrations/", json=second)
                assert resp2.status_code == 403
        finally:
            app.dependency_overrides.clear()


@pytest.mark.integration
class TestQuotaEnforcementSources:
    """Tests for IMAP source quota enforcement on POST /api/integrations/."""

    def test_create_imap_source_blocked_on_free_tier(self, int_engine, int_session):
        """Free-tier users cannot add IMAP source integrations."""
        _make_profile(int_session, tier="free")
        _make_plan(int_session, tier="free", max_storage_destinations=1, max_mailboxes=0)

        from app.api.integrations import _get_owner_id
        from app.main import app

        def override_db():
            Session = sessionmaker(bind=int_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[_get_owner_id] = lambda: _OWNER

        try:
            with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
                resp = client.post("/api/integrations/", json=_IMAP_SOURCE)
                assert resp.status_code == 403
                assert "plan" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_create_imap_source_blocked_at_limit(self, int_engine, int_session):
        """Starter-tier users with 1 IMAP source cannot add a second."""
        _make_profile(int_session, tier="starter")
        _make_plan(int_session, tier="starter", max_storage_destinations=2, max_mailboxes=1)

        from app.api.integrations import _get_owner_id
        from app.main import app

        def override_db():
            Session = sessionmaker(bind=int_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[_get_owner_id] = lambda: _OWNER

        try:
            with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
                resp1 = client.post("/api/integrations/", json=_IMAP_SOURCE)
                assert resp1.status_code == 201

                second = dict(_IMAP_SOURCE, name="Second Mailbox")
                resp2 = client.post("/api/integrations/", json=second)
                assert resp2.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_create_imap_source_unlimited_on_power_tier(self, int_engine, int_session):
        """Power-tier users can add multiple IMAP sources (unlimited)."""
        _make_profile(int_session, tier="business")
        _make_plan(int_session, tier="business", max_storage_destinations=10, max_mailboxes=0)

        from app.api.integrations import _get_owner_id
        from app.main import app

        def override_db():
            Session = sessionmaker(bind=int_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[_get_owner_id] = lambda: _OWNER

        try:
            with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
                resp1 = client.post("/api/integrations/", json=_IMAP_SOURCE)
                resp2 = client.post("/api/integrations/", json=dict(_IMAP_SOURCE, name="Second"))
                resp3 = client.post("/api/integrations/", json=dict(_IMAP_SOURCE, name="Third"))
            assert resp1.status_code == 201
            assert resp2.status_code == 201
            assert resp3.status_code == 201
        finally:
            app.dependency_overrides.clear()

    def test_watch_folder_source_not_quota_limited(self, int_engine, int_session):
        """WATCH_FOLDER sources are not subject to mailbox quota limits."""
        _make_profile(int_session, tier="free")
        _make_plan(int_session, tier="free", max_storage_destinations=1, max_mailboxes=0)

        from app.api.integrations import _get_owner_id
        from app.main import app

        def override_db():
            Session = sessionmaker(bind=int_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[_get_owner_id] = lambda: _OWNER

        try:
            with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
                payload = {
                    "direction": "SOURCE",
                    "integration_type": "WATCH_FOLDER",
                    "name": "My Folder",
                    "config": {"path": "/tmp/watch"},
                    "is_active": True,
                }
                resp = client.post("/api/integrations/", json=payload)
                assert resp.status_code == 201
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Quota helpers unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestQuotaHelpers:
    """Unit tests for the quota helper functions."""

    def test_get_max_destinations_free_tier(self):
        from app.api.integrations import _get_max_destinations

        assert _get_max_destinations({"id": "free", "max_storage_destinations": 1}) == 1

    def test_get_max_destinations_paid_explicit(self):
        from app.api.integrations import _get_max_destinations

        assert _get_max_destinations({"id": "starter", "max_storage_destinations": 2}) == 2

    def test_get_max_destinations_paid_unlimited(self):
        from app.api.integrations import _get_max_destinations

        assert _get_max_destinations({"id": "business", "max_storage_destinations": 0}) is None

    def test_get_max_sources_free_tier(self):
        from app.api.integrations import _get_max_sources

        assert _get_max_sources({"id": "free", "max_mailboxes": 0}) == 0

    def test_get_max_sources_paid_explicit(self):
        from app.api.integrations import _get_max_sources

        assert _get_max_sources({"id": "starter", "max_mailboxes": 1}) == 1

    def test_get_max_sources_paid_unlimited(self):
        from app.api.integrations import _get_max_sources

        assert _get_max_sources({"id": "business", "max_mailboxes": 0}) is None


# ---------------------------------------------------------------------------
# Connection test endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestConnectionTestEndpoint:
    """Tests for POST /api/integrations/test."""

    def test_test_unsupported_type(self, int_client):
        """Unsupported integration types return a helpful non-error message."""
        payload = {
            "integration_type": "DROPBOX",
            "config": {},
            "credentials": {"token": "abc"},
        }
        resp = int_client.post("/api/integrations/test", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not yet supported" in data["message"]

    def test_test_invalid_type_returns_400(self, int_client):
        """Invalid integration_type returns 400."""
        payload = {
            "integration_type": "INVALID",
            "config": {},
        }
        resp = int_client.post("/api/integrations/test", json=payload)
        assert resp.status_code == 400

    def test_test_imap_missing_fields(self, int_client):
        """IMAP test with missing fields returns failure."""
        payload = {
            "integration_type": "IMAP",
            "config": {"host": ""},
            "credentials": {},
        }
        resp = int_client.post("/api/integrations/test", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "Missing" in data["message"]

    def test_test_s3_missing_bucket(self, int_client):
        """S3 test with missing bucket returns failure."""
        payload = {
            "integration_type": "S3",
            "config": {},
            "credentials": {"access_key_id": "AKIA", "secret_access_key": "secret"},
        }
        resp = int_client.post("/api/integrations/test", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "bucket" in data["message"].lower()

    def test_test_webdav_missing_url(self, int_client):
        """WebDAV test with missing URL returns failure."""
        payload = {
            "integration_type": "WEBDAV",
            "config": {},
            "credentials": {"username": "u", "password": "p"},
        }
        resp = int_client.post("/api/integrations/test", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "url" in data["message"].lower()

    def test_test_webdav_blocks_private_ip(self, int_client):
        """WebDAV test blocks requests to private/internal IPs (SSRF protection)."""
        payload = {
            "integration_type": "WEBDAV",
            "config": {"url": "http://127.0.0.1/webdav"},
            "credentials": {"username": "u", "password": "p"},
        }
        resp = int_client.post("/api/integrations/test", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "internal" in data["message"].lower() or "private" in data["message"].lower()

    def test_test_webdav_blocks_localhost(self, int_client):
        """WebDAV test blocks requests to localhost."""
        payload = {
            "integration_type": "WEBDAV",
            "config": {"url": "http://localhost/webdav"},
            "credentials": {},
        }
        resp = int_client.post("/api/integrations/test", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "internal" in data["message"].lower() or "private" in data["message"].lower()

    def test_test_webdav_blocks_file_scheme(self, int_client):
        """WebDAV test blocks file:// scheme."""
        payload = {
            "integration_type": "WEBDAV",
            "config": {"url": "file:///etc/passwd"},
            "credentials": {},
        }
        resp = int_client.post("/api/integrations/test", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "scheme" in data["message"].lower()


# ---------------------------------------------------------------------------
# Quota endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestQuotaEndpoint:
    """Tests for GET /api/integrations/quota/."""

    def test_quota_returns_tier_info(self, int_client):
        """Quota endpoint returns tier information and counts."""
        resp = int_client.get("/api/integrations/quota/")
        assert resp.status_code == 200
        data = resp.json()
        assert "tier_id" in data
        assert "tier_name" in data
        assert "destinations" in data
        assert "sources" in data
        assert "current_count" in data["destinations"]
        assert "max_allowed" in data["destinations"]
        assert "can_add" in data["destinations"]

    def test_quota_reflects_created_integrations(self, int_client):
        """Quota counts update after creating integrations."""
        int_client.post("/api/integrations/", json=_S3_DESTINATION)
        resp = int_client.get("/api/integrations/quota/")
        data = resp.json()
        assert data["destinations"]["current_count"] == 1

    def test_quota_free_tier(self, int_engine, int_session):
        """Free tier shows correct quota limits."""
        _make_profile(int_session, tier="free")
        _make_plan(int_session, tier="free", max_storage_destinations=1, max_mailboxes=0)

        from app.api.integrations import _get_owner_id
        from app.main import app

        def override_db():
            Session = sessionmaker(bind=int_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[_get_owner_id] = lambda: _OWNER

        try:
            with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
                resp = client.get("/api/integrations/quota/")
                data = resp.json()
                assert data["tier_id"] == "free"
                assert data["destinations"]["max_allowed"] == 1
                assert data["destinations"]["can_add"] is True
                assert data["sources"]["max_allowed"] == 0
                assert data["sources"]["can_add"] is False
        finally:
            app.dependency_overrides.clear()
