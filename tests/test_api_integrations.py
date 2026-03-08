"""Tests for the per-user integrations API (app/api/integrations.py)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import UserIntegration

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


def _make_client(int_engine, owner_id: str = _OWNER):
    """Return a TestClient with *owner_id* injected as the authenticated user."""
    from app.api.integrations import _get_owner_id
    from app.main import app

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
class TestGetIntegrationCredentials:
    """Tests for GET /api/integrations/{id}/credentials."""

    def test_returns_decrypted_credentials(self, int_client):
        """Credentials endpoint returns the decrypted dict."""
        created = int_client.post("/api/integrations/", json=_IMAP_SOURCE).json()
        resp = int_client.get(f"/api/integrations/{created['id']}/credentials")
        assert resp.status_code == 200
        creds = resp.json()["credentials"]
        assert creds["password"] == "s3cr3t"  # noqa: S105

    def test_returns_empty_dict_when_no_credentials(self, int_client):
        """No credentials stored returns empty dict."""
        payload = dict(_IMAP_SOURCE, credentials=None)
        created = int_client.post("/api/integrations/", json=payload).json()
        resp = int_client.get(f"/api/integrations/{created['id']}/credentials")
        assert resp.status_code == 200
        assert resp.json()["credentials"] == {}

    def test_not_found(self, int_client):
        """Non-existent integration returns 404."""
        resp = int_client.get("/api/integrations/9999/credentials")
        assert resp.status_code == 404

    def test_other_users_credentials_returns_404(self, int_client, int_session):
        """Cannot retrieve another user's credentials."""
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
        resp = int_client.get(f"/api/integrations/{other_integration.id}/credentials")
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
