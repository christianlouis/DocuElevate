"""Tests for the mobile API endpoints (app/api/mobile.py)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import ApiToken, MobileDevice

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_OWNER = "mobile_user@example.com"
_OTHER_OWNER = "other@example.com"
_EXPO_TOKEN = "ExponentPushToken[test-token-abc123]"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mob_engine():
    """In-memory SQLite engine for mobile tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def mob_session(mob_engine):
    """DB session scoped to one test."""
    Session = sessionmaker(bind=mob_engine)
    session = Session()
    yield session
    session.close()


def _make_client(mob_engine, owner_id: str = _OWNER) -> TestClient:
    """Return a TestClient with *owner_id* injected as the authenticated user."""
    from app.api.mobile import _get_owner_id
    from app.main import app

    Session = sessionmaker(bind=mob_engine)

    def _override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def _override_owner():
        return owner_id

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_get_owner_id] = _override_owner

    client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
    return client


def _cleanup(app):
    """Remove dependency overrides after test."""
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests – /mobile/generate-token
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateMobileToken:
    """Tests for POST /api/mobile/generate-token."""

    def test_generate_token_success(self, mob_engine):
        """Generating a mobile token returns a token string and metadata."""
        from app.main import app

        client = _make_client(mob_engine)
        try:
            resp = client.post(
                "/api/mobile/generate-token",
                json={"device_name": "John's iPhone"},
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["token"].startswith("de_")
            assert data["token_id"] > 0
            assert "Mobile App" in data["name"]
            assert "John's iPhone" in data["name"]
            assert "created_at" in data
        finally:
            _cleanup(app)

    def test_generate_token_default_device_name(self, mob_engine):
        """A default device name is used if none is provided."""
        from app.main import app

        client = _make_client(mob_engine)
        try:
            resp = client.post("/api/mobile/generate-token", json={})
            assert resp.status_code == 201
            data = resp.json()
            assert "Mobile App" in data["name"]
        finally:
            _cleanup(app)

    def test_generate_token_persisted_in_db(self, mob_engine, mob_session):
        """The generated token is stored in the api_tokens table."""
        from app.main import app

        client = _make_client(mob_engine)
        try:
            resp = client.post(
                "/api/mobile/generate-token",
                json={"device_name": "Test Device"},
            )
            assert resp.status_code == 201
            token_id = resp.json()["token_id"]

            db_token = mob_session.get(ApiToken, token_id)
            assert db_token is not None
            assert db_token.owner_id == _OWNER
            assert "Mobile App" in db_token.name
        finally:
            _cleanup(app)

    def test_generate_token_unauthenticated(self, mob_engine):
        """Unauthenticated requests are rejected with 401."""
        from app.api.mobile import _get_owner_id
        from app.main import app

        Session = sessionmaker(bind=mob_engine)

        def _override_get_db():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        def _raise_401():
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[_get_owner_id] = _raise_401

        client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
        try:
            resp = client.post("/api/mobile/generate-token", json={"device_name": "Test"})
            assert resp.status_code == 401
        finally:
            _cleanup(app)


# ---------------------------------------------------------------------------
# Tests – /mobile/register-device
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRegisterDevice:
    """Tests for POST /api/mobile/register-device."""

    def test_register_new_device(self, mob_engine, mob_session):
        """Registering a new device persists it in mobile_devices."""
        from app.main import app

        client = _make_client(mob_engine)
        try:
            resp = client.post(
                "/api/mobile/register-device",
                json={
                    "push_token": _EXPO_TOKEN,
                    "device_name": "Test iPhone",
                    "platform": "ios",
                },
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["id"] > 0
            assert data["platform"] == "ios"
            assert data["is_active"] is True
            assert "ExponentPushToken" in data["push_token_preview"]

            device = mob_session.get(MobileDevice, data["id"])
            assert device is not None
            assert device.push_token == _EXPO_TOKEN
            assert device.owner_id == _OWNER
        finally:
            _cleanup(app)

    def test_register_same_token_is_idempotent(self, mob_engine, mob_session):
        """Re-registering the same token reactivates the existing record."""
        from app.main import app

        client = _make_client(mob_engine)
        try:
            resp1 = client.post(
                "/api/mobile/register-device",
                json={"push_token": _EXPO_TOKEN, "platform": "ios"},
            )
            assert resp1.status_code == 201
            id1 = resp1.json()["id"]

            resp2 = client.post(
                "/api/mobile/register-device",
                json={"push_token": _EXPO_TOKEN, "device_name": "Updated Name", "platform": "ios"},
            )
            assert resp2.status_code == 201
            id2 = resp2.json()["id"]

            assert id1 == id2  # Same record reused

            devices = mob_session.query(MobileDevice).filter(MobileDevice.owner_id == _OWNER).all()
            assert len(devices) == 1
        finally:
            _cleanup(app)

    def test_register_invalid_platform(self, mob_engine):
        """An invalid platform value is rejected with 422."""
        from app.main import app

        client = _make_client(mob_engine)
        try:
            resp = client.post(
                "/api/mobile/register-device",
                json={"push_token": _EXPO_TOKEN, "platform": "windows"},
            )
            assert resp.status_code == 422
        finally:
            _cleanup(app)

    def test_register_android_device(self, mob_engine):
        """Android devices can be registered."""
        from app.main import app

        client = _make_client(mob_engine)
        try:
            resp = client.post(
                "/api/mobile/register-device",
                json={
                    "push_token": "ExponentPushToken[android-token-xyz]",
                    "device_name": "Pixel 8",
                    "platform": "android",
                },
            )
            assert resp.status_code == 201
            assert resp.json()["platform"] == "android"
        finally:
            _cleanup(app)


# ---------------------------------------------------------------------------
# Tests – /mobile/devices
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListDevices:
    """Tests for GET /api/mobile/devices."""

    def test_list_devices_empty(self, mob_engine):
        """An empty list is returned when no devices are registered."""
        from app.main import app

        client = _make_client(mob_engine)
        try:
            resp = client.get("/api/mobile/devices")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _cleanup(app)

    def test_list_devices_returns_own_devices_only(self, mob_engine, mob_session):
        """Only the current user's devices are returned."""
        from app.main import app

        # Add devices for two different owners directly
        mob_session.add(
            MobileDevice(
                owner_id=_OWNER,
                push_token="ExponentPushToken[owner-token-12345]",
                platform="ios",
            )
        )
        mob_session.add(
            MobileDevice(
                owner_id=_OTHER_OWNER,
                push_token="ExponentPushToken[other-token-67890]",
                platform="android",
            )
        )
        mob_session.commit()

        client = _make_client(mob_engine)
        try:
            resp = client.get("/api/mobile/devices")
            assert resp.status_code == 200
            devices = resp.json()
            assert len(devices) == 1
            # The push_token_preview is the first 20 chars + "…"
            assert devices[0]["push_token_preview"].startswith("ExponentPushToken[ow")
        finally:
            _cleanup(app)


# ---------------------------------------------------------------------------
# Tests – DELETE /mobile/devices/{device_id}
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeactivateDevice:
    """Tests for DELETE /api/mobile/devices/{device_id}."""

    def test_deactivate_own_device(self, mob_engine, mob_session):
        """Deactivating a device sets is_active to False."""
        from app.main import app

        device = MobileDevice(
            owner_id=_OWNER,
            push_token=_EXPO_TOKEN,
            platform="ios",
            is_active=True,
        )
        mob_session.add(device)
        mob_session.commit()
        mob_session.refresh(device)
        device_id = device.id

        client = _make_client(mob_engine)
        try:
            resp = client.delete(f"/api/mobile/devices/{device_id}")
            assert resp.status_code == 204

            mob_session.expire_all()
            updated = mob_session.get(MobileDevice, device_id)
            assert updated is not None
            assert updated.is_active is False
        finally:
            _cleanup(app)

    def test_deactivate_other_users_device_returns_404(self, mob_engine, mob_session):
        """Attempting to deactivate another user's device returns 404."""
        from app.main import app

        device = MobileDevice(
            owner_id=_OTHER_OWNER,
            push_token="ExponentPushToken[other-token]",
            platform="ios",
            is_active=True,
        )
        mob_session.add(device)
        mob_session.commit()
        mob_session.refresh(device)
        device_id = device.id

        client = _make_client(mob_engine)
        try:
            resp = client.delete(f"/api/mobile/devices/{device_id}")
            assert resp.status_code == 404
        finally:
            _cleanup(app)

    def test_deactivate_nonexistent_device_returns_404(self, mob_engine):
        """Deactivating a device that does not exist returns 404."""
        from app.main import app

        client = _make_client(mob_engine)
        try:
            resp = client.delete("/api/mobile/devices/99999")
            assert resp.status_code == 404
        finally:
            _cleanup(app)


# ---------------------------------------------------------------------------
# Tests – /mobile/whoami
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWhoAmI:
    """Tests for GET /api/mobile/whoami."""

    def test_whoami_with_no_profile(self, mob_engine):
        """Returns owner_id and inferred email even when no UserProfile exists."""
        from app.main import app

        client = _make_client(mob_engine)
        try:
            resp = client.get("/api/mobile/whoami")
            assert resp.status_code == 200
            data = resp.json()
            assert data["owner_id"] == _OWNER
            assert data["display_name"] is None
            # _OWNER contains "@" so email is inferred from owner_id
            assert data["email"] == _OWNER
            assert data["avatar_url"] is not None  # Gravatar URL from email
            assert data["is_admin"] is False
        finally:
            _cleanup(app)

    def test_whoami_with_profile(self, mob_engine, mob_session):
        """Returns full profile data when a UserProfile record exists."""
        from app.main import app
        from app.models import UserProfile

        profile = UserProfile(
            user_id=_OWNER,
            display_name="Alice Test",
        )
        mob_session.add(profile)
        mob_session.commit()

        client = _make_client(mob_engine)
        try:
            resp = client.get("/api/mobile/whoami")
            assert resp.status_code == 200
            data = resp.json()
            assert data["owner_id"] == _OWNER
            assert data["display_name"] == "Alice Test"
            # owner_id contains "@" so email is inferred from it
            assert data["email"] == _OWNER
            assert data["avatar_url"] is not None  # Gravatar URL
            assert data["is_admin"] is False
        finally:
            _cleanup(app)


# ---------------------------------------------------------------------------
# Tests – push notification utility
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPushNotificationUtility:
    """Tests for app/utils/push_notification.py."""

    def test_send_expo_push_empty_tokens(self):
        """send_expo_push_notification with no tokens returns empty list."""
        from app.utils.push_notification import send_expo_push_notification

        result = send_expo_push_notification([], "Title", "Body")
        assert result == []

    def test_send_expo_push_calls_expo_api(self):
        """send_expo_push_notification POSTs to the Expo push API."""
        from app.utils.push_notification import send_expo_push_notification

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"status": "ok"}]}
        mock_response.raise_for_status = MagicMock()

        with patch("app.utils.push_notification.httpx.post", return_value=mock_response) as mock_post:
            result = send_expo_push_notification(
                tokens=["ExponentPushToken[abc]"],
                title="Test",
                body="Message",
            )

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "exp.host" in call_kwargs[0][0]
        payload = call_kwargs[1]["json"]
        assert len(payload) == 1
        assert payload[0]["to"] == "ExponentPushToken[abc]"
        assert payload[0]["title"] == "Test"

    def test_send_push_to_owner_no_devices(self, mob_engine):
        """send_push_to_owner silently does nothing when no devices are registered."""
        from app.utils.push_notification import send_push_to_owner

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_session.close = MagicMock()

        with patch("app.utils.push_notification.SessionLocal", return_value=mock_session):
            with patch("app.utils.push_notification.send_expo_push_notification") as mock_send:
                send_push_to_owner("user@example.com", "Title", "Body")
                mock_send.assert_not_called()
                mock_session.close.assert_called_once()

    def test_send_push_to_owner_with_devices(self):
        """send_push_to_owner calls send_expo_push_notification with device tokens."""
        from app.utils.push_notification import send_push_to_owner

        fake_device = MagicMock()
        fake_device.push_token = "ExponentPushToken[device1]"
        fake_device.is_active = True

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [fake_device]
        mock_session.close = MagicMock()

        with patch("app.utils.push_notification.SessionLocal", return_value=mock_session):
            with patch("app.utils.push_notification.send_expo_push_notification") as mock_send:
                mock_send.return_value = [{"status": "ok"}]
                send_push_to_owner("user@example.com", "Processed!", "Your doc is ready.")

                mock_send.assert_called_once()
                call_kwargs = mock_send.call_args[1]
                assert "ExponentPushToken[device1]" in call_kwargs["tokens"]
