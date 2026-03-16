"""Tests for the per-user notification system (app/api/notifications.py)."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import InAppNotification, UserNotificationPreference, UserNotificationTarget

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_OWNER = "notifuser@example.com"
_OTHER_OWNER = "other@example.com"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def notif_engine():
    """In-memory SQLite engine for notification tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def notif_session(notif_engine):
    """DB session scoped to one test."""
    Session = sessionmaker(bind=notif_engine)
    session = Session()
    yield session
    session.close()


def _make_client(notif_engine, owner_id: str = _OWNER) -> TestClient:
    """Return a TestClient with *owner_id* injected as the authenticated user."""
    from app.api.notifications import _get_owner_id
    from app.main import app

    Session = sessionmaker(bind=notif_engine)

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

    return TestClient(app, base_url="http://localhost", raise_server_exceptions=False)


def _cleanup(app):
    """Remove dependency overrides after test."""
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests – Auth / 401 guard
# ---------------------------------------------------------------------------


class TestAuthGuard:
    """Verify that unauthenticated requests are rejected."""

    @pytest.mark.unit
    def test_inbox_requires_auth(self):
        """GET /api/user-notifications/inbox should return 401 when not authenticated."""
        from app.main import app

        client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
        resp = client.get("/api/user-notifications/inbox")
        assert resp.status_code == 401

    @pytest.mark.unit
    def test_unread_count_requires_auth(self):
        """GET /api/user-notifications/inbox/unread-count should return 401 when not authenticated."""
        from app.main import app

        client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
        resp = client.get("/api/user-notifications/inbox/unread-count")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests – Inbox
# ---------------------------------------------------------------------------


class TestInbox:
    """Tests for the in-app notification inbox."""

    @pytest.mark.unit
    def test_unread_count_empty(self, notif_engine):
        """Unread count should be 0 when no notifications exist."""
        from app.main import app

        client = _make_client(notif_engine)
        try:
            resp = client.get("/api/user-notifications/inbox/unread-count")
            assert resp.status_code == 200
            assert resp.json() == {"count": 0}
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_inbox_empty(self, notif_engine):
        """Listing inbox when empty should return an empty list."""
        from app.main import app

        client = _make_client(notif_engine)
        try:
            resp = client.get("/api/user-notifications/inbox")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_inbox_shows_notifications(self, notif_engine, notif_session):
        """Inbox should return notifications for the authenticated user."""
        from app.main import app

        notif_session.add(
            InAppNotification(
                owner_id=_OWNER,
                event_type="document.processed",
                title="Test",
                message="Done",
            )
        )
        notif_session.commit()

        client = _make_client(notif_engine)
        try:
            resp = client.get("/api/user-notifications/inbox")
            assert resp.status_code == 200
            items = resp.json()
            assert len(items) == 1
            assert items[0]["title"] == "Test"
            assert items[0]["is_read"] is False
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_inbox_isolation(self, notif_engine, notif_session):
        """Users should only see their own notifications."""
        from app.main import app

        notif_session.add(
            InAppNotification(
                owner_id=_OTHER_OWNER,
                event_type="document.processed",
                title="Other user notif",
                message="Not yours",
            )
        )
        notif_session.commit()

        client = _make_client(notif_engine, _OWNER)
        try:
            resp = client.get("/api/user-notifications/inbox")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_unread_count_reflects_notifications(self, notif_engine, notif_session):
        """Unread count should reflect actual unread notifications."""
        from app.main import app

        for i in range(3):
            notif_session.add(
                InAppNotification(
                    owner_id=_OWNER,
                    event_type="document.processed",
                    title=f"Notif {i}",
                    message="",
                    is_read=False,
                )
            )
        notif_session.commit()

        client = _make_client(notif_engine)
        try:
            resp = client.get("/api/user-notifications/inbox/unread-count")
            assert resp.status_code == 200
            assert resp.json()["count"] == 3
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_mark_read(self, notif_engine, notif_session):
        """Marking a notification as read should update is_read."""
        from app.main import app

        notif = InAppNotification(
            owner_id=_OWNER,
            event_type="document.processed",
            title="Unread",
            message="",
        )
        notif_session.add(notif)
        notif_session.commit()
        notif_session.refresh(notif)
        notif_id = notif.id

        client = _make_client(notif_engine)
        try:
            resp = client.post(f"/api/user-notifications/inbox/{notif_id}/read")
            assert resp.status_code == 200

            # Verify in DB
            notif_session.refresh(notif)
            assert notif.is_read is True
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_mark_read_wrong_user(self, notif_engine, notif_session):
        """Marking another user's notification should return 404."""
        from app.main import app

        notif = InAppNotification(
            owner_id=_OTHER_OWNER,
            event_type="document.processed",
            title="Other",
            message="",
        )
        notif_session.add(notif)
        notif_session.commit()
        notif_session.refresh(notif)
        notif_id = notif.id

        client = _make_client(notif_engine, _OWNER)
        try:
            resp = client.post(f"/api/user-notifications/inbox/{notif_id}/read")
            assert resp.status_code == 404
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_mark_all_read(self, notif_engine, notif_session):
        """Mark all read should set all user's notifications to read."""
        from app.main import app

        for i in range(4):
            notif_session.add(
                InAppNotification(
                    owner_id=_OWNER,
                    event_type="document.processed",
                    title=f"N{i}",
                    message="",
                    is_read=False,
                )
            )
        notif_session.commit()

        client = _make_client(notif_engine)
        try:
            resp = client.post("/api/user-notifications/inbox/read-all")
            assert resp.status_code == 200

            count_resp = client.get("/api/user-notifications/inbox/unread-count")
            assert count_resp.json()["count"] == 0
        finally:
            _cleanup(app)


# ---------------------------------------------------------------------------
# Tests – Notification Targets
# ---------------------------------------------------------------------------


class TestTargets:
    """Tests for notification target CRUD."""

    @pytest.mark.unit
    def test_list_targets_empty(self, notif_engine):
        """Listing targets when none exist should return empty list."""
        from app.main import app

        client = _make_client(notif_engine)
        try:
            resp = client.get("/api/user-notifications/targets")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_create_email_target(self, notif_engine):
        """Creating an email target should persist and mask the password in response."""
        from app.main import app

        client = _make_client(notif_engine)
        try:
            resp = client.post(
                "/api/user-notifications/targets",
                json={
                    "channel_type": "email",
                    "name": "My Gmail",
                    "config": {
                        "smtp_host": "smtp.gmail.com",
                        "smtp_port": 587,
                        "smtp_username": "me@gmail.com",
                        "smtp_password": "s3cr3t",
                        "recipient_email": "me@gmail.com",
                        "smtp_use_tls": True,
                    },
                    "is_active": True,
                },
            )
            assert resp.status_code == 201, resp.text
            data = resp.json()
            assert data["channel_type"] == "email"
            assert data["name"] == "My Gmail"
            assert data["is_active"] is True
            # Password must be masked
            assert data["config"]["smtp_password"] == "****"
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_create_webhook_target(self, notif_engine):
        """Creating a webhook target should persist correctly."""
        from app.main import app

        client = _make_client(notif_engine)
        try:
            resp = client.post(
                "/api/user-notifications/targets",
                json={
                    "channel_type": "webhook",
                    "name": "Slack Webhook",
                    "config": {"url": "https://hooks.slack.com/abc", "secret": ""},
                    "is_active": True,
                },
            )
            assert resp.status_code == 201, resp.text
            data = resp.json()
            assert data["channel_type"] == "webhook"
            assert data["name"] == "Slack Webhook"
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_create_target_invalid_channel_type(self, notif_engine):
        """Creating a target with an invalid channel_type should return 422."""
        from app.main import app

        client = _make_client(notif_engine)
        try:
            resp = client.post(
                "/api/user-notifications/targets",
                json={"channel_type": "sms", "name": "Bad", "config": {}},
            )
            assert resp.status_code == 422
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_list_targets_returns_created(self, notif_engine):
        """Listing targets should include newly created ones."""
        from app.main import app

        client = _make_client(notif_engine)
        try:
            client.post(
                "/api/user-notifications/targets",
                json={"channel_type": "webhook", "name": "W1", "config": {"url": "https://example.com"}},
            )
            client.post(
                "/api/user-notifications/targets",
                json={"channel_type": "email", "name": "E1", "config": {"smtp_host": "smtp.example.com"}},
            )
            resp = client.get("/api/user-notifications/targets")
            assert resp.status_code == 200
            assert len(resp.json()) == 2
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_targets_isolation(self, notif_engine):
        """Users should only see their own targets."""
        from app.main import app

        client_a = _make_client(notif_engine, _OWNER)
        try:
            client_a.post(
                "/api/user-notifications/targets",
                json={"channel_type": "webhook", "name": "Owner A target", "config": {"url": "https://a.example.com"}},
            )
        finally:
            _cleanup(app)

        client_b = _make_client(notif_engine, _OTHER_OWNER)
        try:
            resp = client_b.get("/api/user-notifications/targets")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_update_target(self, notif_engine):
        """Updating a target should change its name and active status."""
        from app.main import app

        client = _make_client(notif_engine)
        try:
            create_resp = client.post(
                "/api/user-notifications/targets",
                json={"channel_type": "webhook", "name": "Old Name", "config": {"url": "https://x.com"}},
            )
            target_id = create_resp.json()["id"]

            resp = client.put(
                f"/api/user-notifications/targets/{target_id}",
                json={"name": "New Name", "is_active": False},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "New Name"
            assert data["is_active"] is False
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_update_target_wrong_user(self, notif_engine, notif_session):
        """Updating another user's target should return 404."""
        from app.main import app

        target = UserNotificationTarget(
            owner_id=_OTHER_OWNER,
            channel_type="webhook",
            name="Other target",
            config=json.dumps({"url": "https://other.com"}),
        )
        notif_session.add(target)
        notif_session.commit()
        notif_session.refresh(target)

        client = _make_client(notif_engine, _OWNER)
        try:
            resp = client.put(
                f"/api/user-notifications/targets/{target.id}",
                json={"name": "Hacked"},
            )
            assert resp.status_code == 404
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_delete_target(self, notif_engine):
        """Deleting a target should remove it from the list."""
        from app.main import app

        client = _make_client(notif_engine)
        try:
            create_resp = client.post(
                "/api/user-notifications/targets",
                json={"channel_type": "webhook", "name": "To Delete", "config": {"url": "https://x.com"}},
            )
            target_id = create_resp.json()["id"]

            del_resp = client.delete(f"/api/user-notifications/targets/{target_id}")
            assert del_resp.status_code == 200

            list_resp = client.get("/api/user-notifications/targets")
            assert list_resp.json() == []
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_delete_target_wrong_user(self, notif_engine, notif_session):
        """Deleting another user's target should return 404."""
        from app.main import app

        target = UserNotificationTarget(
            owner_id=_OTHER_OWNER,
            channel_type="webhook",
            name="Not yours",
            config=json.dumps({"url": "https://other.com"}),
        )
        notif_session.add(target)
        notif_session.commit()
        notif_session.refresh(target)

        client = _make_client(notif_engine, _OWNER)
        try:
            resp = client.delete(f"/api/user-notifications/targets/{target.id}")
            assert resp.status_code == 404
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_delete_target_also_removes_preferences(self, notif_engine, notif_session):
        """Deleting a target should also remove associated preferences."""
        from app.main import app

        target = UserNotificationTarget(
            owner_id=_OWNER,
            channel_type="webhook",
            name="With prefs",
            config=json.dumps({"url": "https://x.com"}),
        )
        notif_session.add(target)
        notif_session.commit()
        notif_session.refresh(target)

        pref = UserNotificationPreference(
            owner_id=_OWNER,
            event_type="document.processed",
            channel_type="webhook",
            target_id=target.id,
            is_enabled=True,
        )
        notif_session.add(pref)
        notif_session.commit()

        client = _make_client(notif_engine, _OWNER)
        try:
            resp = client.delete(f"/api/user-notifications/targets/{target.id}")
            assert resp.status_code == 200

            remaining = (
                notif_session.query(UserNotificationPreference)
                .filter(UserNotificationPreference.owner_id == _OWNER)
                .all()
            )
            assert remaining == []
        finally:
            _cleanup(app)


# ---------------------------------------------------------------------------
# Tests – Preferences
# ---------------------------------------------------------------------------


class TestPreferences:
    """Tests for notification preferences CRUD."""

    @pytest.mark.unit
    def test_get_preferences_empty(self, notif_engine):
        """Getting preferences returns event_types and event_labels even with no prefs set."""
        from app.main import app

        client = _make_client(notif_engine)
        try:
            resp = client.get("/api/user-notifications/preferences")
            assert resp.status_code == 200
            data = resp.json()
            assert "event_types" in data
            assert "event_labels" in data
            assert "preferences" in data
            assert "document.processed" in data["event_types"]
            assert "document.failed" in data["event_types"]
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_update_preferences(self, notif_engine, notif_session):
        """Updating preferences should persist the changes."""
        from app.main import app

        target = UserNotificationTarget(
            owner_id=_OWNER,
            channel_type="webhook",
            name="My Webhook",
            config=json.dumps({"url": "https://x.com"}),
        )
        notif_session.add(target)
        notif_session.commit()
        notif_session.refresh(target)

        client = _make_client(notif_engine, _OWNER)
        try:
            resp = client.put(
                "/api/user-notifications/preferences",
                json={
                    "preferences": [
                        {
                            "event_type": "document.processed",
                            "channel_type": "webhook",
                            "is_enabled": True,
                            "target_id": target.id,
                        }
                    ]
                },
            )
            assert resp.status_code == 200

            # Verify stored
            pref = (
                notif_session.query(UserNotificationPreference)
                .filter(
                    UserNotificationPreference.owner_id == _OWNER,
                    UserNotificationPreference.event_type == "document.processed",
                    UserNotificationPreference.channel_type == "webhook",
                )
                .first()
            )
            assert pref is not None
            assert pref.is_enabled is True
            assert pref.target_id == target.id
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_update_preferences_upsert(self, notif_engine, notif_session):
        """Updating preferences twice should upsert (not duplicate)."""
        from app.main import app

        target = UserNotificationTarget(
            owner_id=_OWNER,
            channel_type="webhook",
            name="W",
            config=json.dumps({"url": "https://x.com"}),
        )
        notif_session.add(target)
        notif_session.commit()
        notif_session.refresh(target)

        client = _make_client(notif_engine, _OWNER)
        try:
            pref_item = {
                "event_type": "document.processed",
                "channel_type": "webhook",
                "is_enabled": True,
                "target_id": target.id,
            }
            client.put("/api/user-notifications/preferences", json={"preferences": [pref_item]})
            # Disable it
            pref_item["is_enabled"] = False
            resp = client.put("/api/user-notifications/preferences", json={"preferences": [pref_item]})
            assert resp.status_code == 200

            prefs = (
                notif_session.query(UserNotificationPreference)
                .filter(UserNotificationPreference.owner_id == _OWNER)
                .all()
            )
            assert len(prefs) == 1
            assert prefs[0].is_enabled is False
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_update_preferences_rejects_foreign_target(self, notif_engine, notif_session):
        """Preferences referencing another user's target_id should be rejected."""
        from app.main import app

        other_target = UserNotificationTarget(
            owner_id=_OTHER_OWNER,
            channel_type="webhook",
            name="Other webhook",
            config=json.dumps({"url": "https://other.com"}),
        )
        notif_session.add(other_target)
        notif_session.commit()
        notif_session.refresh(other_target)

        client = _make_client(notif_engine, _OWNER)
        try:
            resp = client.put(
                "/api/user-notifications/preferences",
                json={
                    "preferences": [
                        {
                            "event_type": "document.processed",
                            "channel_type": "webhook",
                            "is_enabled": True,
                            "target_id": other_target.id,
                        }
                    ]
                },
            )
            assert resp.status_code == 400
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_get_preferences_reflects_saved(self, notif_engine, notif_session):
        """GET preferences should reflect previously saved preferences."""
        from app.main import app

        target = UserNotificationTarget(
            owner_id=_OWNER,
            channel_type="email",
            name="Email target",
            config=json.dumps({"smtp_host": "smtp.example.com", "recipient_email": "me@example.com"}),
        )
        notif_session.add(target)
        notif_session.commit()
        notif_session.refresh(target)

        notif_session.add(
            UserNotificationPreference(
                owner_id=_OWNER,
                event_type="document.failed",
                channel_type="email",
                target_id=target.id,
                is_enabled=True,
            )
        )
        notif_session.commit()

        client = _make_client(notif_engine, _OWNER)
        try:
            resp = client.get("/api/user-notifications/preferences")
            assert resp.status_code == 200
            data = resp.json()
            assert "document.failed" in data["preferences"]
            assert "email" in data["preferences"]["document.failed"]
            assert data["preferences"]["document.failed"]["email"]["is_enabled"] is True
        finally:
            _cleanup(app)


# ---------------------------------------------------------------------------
# Tests – user_notification service
# ---------------------------------------------------------------------------


class TestUserNotificationService:
    """Unit tests for the user notification dispatch service."""

    @pytest.mark.unit
    def test_create_in_app_notification(self, notif_engine, notif_session):
        """create_in_app_notification should persist a record."""
        from unittest.mock import patch

        from app.utils.user_notification import create_in_app_notification

        Session = sessionmaker(bind=notif_engine)

        with patch("app.utils.user_notification.SessionLocal", Session):
            result = create_in_app_notification(
                owner_id=_OWNER,
                event_type="document.processed",
                title="Test",
                message="Done",
                file_id=42,
            )

        assert result is not None
        assert result.owner_id == _OWNER
        assert result.title == "Test"
        assert result.file_id == 42

    @pytest.mark.unit
    def test_notify_user_document_processed(self, notif_engine):
        """notify_user_document_processed should create an in-app notification."""
        from unittest.mock import patch

        from app.utils.user_notification import notify_user_document_processed

        Session = sessionmaker(bind=notif_engine)

        with patch("app.utils.user_notification.SessionLocal", Session):
            notify_user_document_processed(owner_id=_OWNER, filename="test.pdf", file_id=1)

        s = Session()
        notifs = s.query(InAppNotification).filter(InAppNotification.owner_id == _OWNER).all()
        s.close()
        assert len(notifs) == 1
        assert "test.pdf" in notifs[0].title

    @pytest.mark.unit
    def test_notify_user_document_failed(self, notif_engine):
        """notify_user_document_failed should create an in-app notification."""
        from unittest.mock import patch

        from app.utils.user_notification import notify_user_document_failed

        Session = sessionmaker(bind=notif_engine)

        with patch("app.utils.user_notification.SessionLocal", Session):
            notify_user_document_failed(owner_id=_OWNER, filename="doc.pdf", error="OCR timeout")

        s = Session()
        notifs = s.query(InAppNotification).filter(InAppNotification.owner_id == _OWNER).all()
        s.close()
        assert len(notifs) == 1
        assert notifs[0].event_type == "document.failed"
        assert "OCR timeout" in notifs[0].message

    @pytest.mark.unit
    def test_send_webhook_notification_missing_url(self):
        """_send_webhook_notification should return False when url is missing."""
        from app.utils.user_notification import _send_webhook_notification

        result = _send_webhook_notification({}, "document.processed", "Title", "Body")
        assert result is False

    @pytest.mark.unit
    def test_send_email_notification_missing_host(self):
        """_send_email_notification should return False when smtp_host is missing."""
        from app.utils.user_notification import _send_email_notification

        result = _send_email_notification({"recipient_email": "me@example.com"}, "Title", "Body")
        assert result is False

    @pytest.mark.unit
    def test_send_email_notification_missing_recipient(self):
        """_send_email_notification should return False when recipient_email is missing."""
        from app.utils.user_notification import _send_email_notification

        result = _send_email_notification({"smtp_host": "smtp.example.com"}, "Title", "Body")
        assert result is False

class TestBenchmark:
    @pytest.mark.unit
    def test_update_preferences_benchmark(self, notif_engine, notif_session):
        import time
        import statistics
        from app.main import app

        target = UserNotificationTarget(
            owner_id=_OWNER,
            channel_type="webhook",
            name="My Webhook",
            config=json.dumps({"url": "https://x.com"}),
        )
        notif_session.add(target)
        notif_session.commit()
        notif_session.refresh(target)

        client = _make_client(notif_engine, _OWNER)
        try:
            items_count = 100
            preferences = []
            for i in range(items_count):
                preferences.append({
                    "event_type": f"event.type.{i}",
                    "channel_type": "webhook",
                    "is_enabled": True,
                    "target_id": target.id,
                })

            payload = {"preferences": preferences}

            # Warm up
            client.put("/api/user-notifications/preferences", json=payload)

            times = []
            for _ in range(5):
                # Alter the values a bit so it's a real update
                for p in payload["preferences"]:
                    p["is_enabled"] = not p["is_enabled"]

                start = time.time()
                resp = client.put("/api/user-notifications/preferences", json=payload)
                end = time.time()

                assert resp.status_code == 200
                times.append(end - start)

            print(f"\nAverage time: {statistics.mean(times):.4f}s")
        finally:
            _cleanup(app)
