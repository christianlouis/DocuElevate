"""Tests for user-event notifications and webhooks.

Covers:
- notify_user_signup / notify_plan_changed / notify_payment_issue helpers
- New webhook events: user.signup, user.plan_changed, user.payment_issue
- Plan-change notification fired from POST /api/onboarding/plan
- Plan-change notification fired from PUT /api/admin/users/{user_id}
- Payment-issue endpoint: POST /api/admin/users/{user_id}/payment-issue
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import UserProfile

# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

_ADMIN_USER = {
    "sub": "admin-001",
    "name": "Admin User",
    "email": "admin@example.com",
    "is_admin": True,
}

_REGULAR_USER_ID = "user-evt-001"


def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


# ---------------------------------------------------------------------------
# Tests: notification helper functions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNotifyUserSignup:
    """Tests for notify_user_signup()."""

    def test_sends_notification_when_enabled(self, mocker):
        """Notification is sent when notify_on_user_signup=True."""
        mock_send = mocker.patch("app.utils.notification.send_notification", return_value=True)
        mocker.patch("app.config.settings.notify_on_user_signup", True)

        from app.utils.notification import notify_user_signup

        result = notify_user_signup("alice", display_name="Alice", email="alice@example.com")
        assert result is True
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert "alice" in call_kwargs["title"].lower() or "Alice" in call_kwargs["title"]
        assert "alice@example.com" in call_kwargs["message"]

    def test_skips_notification_when_disabled(self, mocker):
        """Notification is NOT sent when notify_on_user_signup=False."""
        mock_send = mocker.patch("app.utils.notification.send_notification")
        mocker.patch("app.config.settings.notify_on_user_signup", False)

        from app.utils.notification import notify_user_signup

        result = notify_user_signup("alice")
        assert result is False
        mock_send.assert_not_called()

    def test_uses_user_id_as_fallback_name(self, mocker):
        """When display_name is None the user_id appears in the title."""
        mock_send = mocker.patch("app.utils.notification.send_notification", return_value=True)
        mocker.patch("app.config.settings.notify_on_user_signup", True)

        from app.utils.notification import notify_user_signup

        notify_user_signup("bob123")
        call_kwargs = mock_send.call_args[1]
        assert "bob123" in call_kwargs["title"]

    def test_returns_false_when_no_notification_urls(self):
        """Returns False gracefully when no notification URLs are configured."""
        from app.config import settings
        from app.utils.notification import notify_user_signup

        original = settings.notify_on_user_signup
        original_urls = settings.notification_urls
        try:
            settings.notify_on_user_signup = True
            settings.notification_urls = []
            result = notify_user_signup("charlie")
            assert result is False
        finally:
            settings.notify_on_user_signup = original
            settings.notification_urls = original_urls


@pytest.mark.unit
class TestNotifyPlanChanged:
    """Tests for notify_plan_changed()."""

    def test_sends_notification_when_enabled(self, mocker):
        mock_send = mocker.patch("app.utils.notification.send_notification", return_value=True)
        mocker.patch("app.config.settings.notify_on_plan_change", True)

        from app.utils.notification import notify_plan_changed

        result = notify_plan_changed("alice", old_tier="free", new_tier="starter", changed_by="user")
        assert result is True
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert "free" in call_kwargs["message"]
        assert "starter" in call_kwargs["message"]
        assert "user" in call_kwargs["message"]

    def test_skips_when_disabled(self, mocker):
        mock_send = mocker.patch("app.utils.notification.send_notification")
        mocker.patch("app.config.settings.notify_on_plan_change", False)

        from app.utils.notification import notify_plan_changed

        result = notify_plan_changed("alice", old_tier="free", new_tier="starter")
        assert result is False
        mock_send.assert_not_called()

    def test_changed_by_defaults_to_user(self, mocker):
        mock_send = mocker.patch("app.utils.notification.send_notification", return_value=True)
        mocker.patch("app.config.settings.notify_on_plan_change", True)

        from app.utils.notification import notify_plan_changed

        notify_plan_changed("alice", old_tier="free", new_tier="professional")
        call_kwargs = mock_send.call_args[1]
        assert "user" in call_kwargs["message"]


@pytest.mark.unit
class TestNotifyPaymentIssue:
    """Tests for notify_payment_issue()."""

    def test_sends_notification_when_enabled(self, mocker):
        mock_send = mocker.patch("app.utils.notification.send_notification", return_value=True)
        mocker.patch("app.config.settings.notify_on_payment_issue", True)

        from app.utils.notification import notify_payment_issue

        result = notify_payment_issue("alice", issue="Card declined")
        assert result is True
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert "Card declined" in call_kwargs["message"]
        assert call_kwargs["notification_type"] == "warning"

    def test_skips_when_disabled(self, mocker):
        mock_send = mocker.patch("app.utils.notification.send_notification")
        mocker.patch("app.config.settings.notify_on_payment_issue", False)

        from app.utils.notification import notify_payment_issue

        result = notify_payment_issue("alice", issue="Card declined")
        assert result is False
        mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: VALID_EVENTS contains new user events
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWebhookValidEvents:
    """Ensure new user-event types are registered in VALID_EVENTS."""

    def test_user_signup_is_valid(self):
        from app.utils.webhook import VALID_EVENTS

        assert "user.signup" in VALID_EVENTS

    def test_user_plan_changed_is_valid(self):
        from app.utils.webhook import VALID_EVENTS

        assert "user.plan_changed" in VALID_EVENTS

    def test_user_payment_issue_is_valid(self):
        from app.utils.webhook import VALID_EVENTS

        assert "user.payment_issue" in VALID_EVENTS

    def test_dispatch_user_signup_event(self, mocker):
        """dispatch_webhook_event accepts user.signup without warning."""
        mock_task = mocker.patch("app.tasks.webhook_tasks.deliver_webhook_task")
        mock_task.delay = MagicMock()
        mocker.patch(
            "app.utils.webhook.get_active_webhooks_for_event",
            return_value=[{"id": 1, "url": "https://hook.example.com", "secret": None}],
        )

        from app.utils.webhook import dispatch_webhook_event

        dispatch_webhook_event("user.signup", {"user_id": "alice"})
        mock_task.delay.assert_called_once()

    def test_dispatch_user_plan_changed_event(self, mocker):
        mock_task = mocker.patch("app.tasks.webhook_tasks.deliver_webhook_task")
        mock_task.delay = MagicMock()
        mocker.patch(
            "app.utils.webhook.get_active_webhooks_for_event",
            return_value=[{"id": 2, "url": "https://hook.example.com", "secret": "s"}],
        )

        from app.utils.webhook import dispatch_webhook_event

        dispatch_webhook_event("user.plan_changed", {"user_id": "alice", "old_tier": "free", "new_tier": "starter"})
        mock_task.delay.assert_called_once()

    def test_dispatch_user_payment_issue_event(self, mocker):
        mock_task = mocker.patch("app.tasks.webhook_tasks.deliver_webhook_task")
        mock_task.delay = MagicMock()
        mocker.patch(
            "app.utils.webhook.get_active_webhooks_for_event",
            return_value=[{"id": 3, "url": "https://hook.example.com", "secret": None}],
        )

        from app.utils.webhook import dispatch_webhook_event

        dispatch_webhook_event("user.payment_issue", {"user_id": "alice", "issue": "Card declined"})
        mock_task.delay.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: /api/onboarding/plan fires plan-change notification
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOnboardingPlanNotification:
    """Plan-change events are fired when the user changes tier via onboarding."""

    @pytest.fixture()
    def _engine(self):
        engine = _make_engine()
        yield engine
        Base.metadata.drop_all(bind=engine)

    @pytest.fixture()
    def _client(self, _engine):
        from app.api import onboarding as ob_module
        from app.main import app

        original_get_user = ob_module._get_current_user_id

        def override_db():
            Session = sessionmaker(bind=_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        def fake_user_id(_request):
            return _REGULAR_USER_ID

        ob_module._get_current_user_id = fake_user_id
        app.dependency_overrides[get_db] = override_db

        with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
            yield client

        ob_module._get_current_user_id = original_get_user
        app.dependency_overrides.clear()

    def test_plan_change_fires_notification_and_webhook(self, _client, _engine, mocker):
        """Changing from free → starter sends notification and webhook."""
        # Pre-create a profile with 'free' tier
        Session = sessionmaker(bind=_engine)
        session = Session()
        profile = UserProfile(user_id=_REGULAR_USER_ID, subscription_tier="free")
        session.add(profile)
        session.commit()
        session.close()

        mock_notify = mocker.patch("app.utils.notification.notify_plan_changed", return_value=True)
        mock_dispatch = mocker.patch("app.utils.webhook.dispatch_webhook_event")

        resp = _client.post("/api/onboarding/plan", json={"subscription_tier": "starter", "billing_cycle": "monthly"})
        assert resp.status_code == 200

        mock_notify.assert_called_once_with(_REGULAR_USER_ID, old_tier="free", new_tier="starter", changed_by="user")
        mock_dispatch.assert_called_once()
        call_args = mock_dispatch.call_args
        assert call_args[0][0] == "user.plan_changed"
        assert call_args[0][1]["old_tier"] == "free"
        assert call_args[0][1]["new_tier"] == "starter"

    def test_no_event_when_tier_unchanged(self, _client, _engine, mocker):
        """No notification or webhook when the tier stays the same."""
        Session = sessionmaker(bind=_engine)
        session = Session()
        profile = UserProfile(user_id=_REGULAR_USER_ID, subscription_tier="starter")
        session.add(profile)
        session.commit()
        session.close()

        mock_notify = mocker.patch("app.utils.notification.notify_plan_changed")
        mock_dispatch = mocker.patch("app.utils.webhook.dispatch_webhook_event")

        resp = _client.post("/api/onboarding/plan", json={"subscription_tier": "starter", "billing_cycle": "monthly"})
        assert resp.status_code == 200

        mock_notify.assert_not_called()
        mock_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: /api/admin/users/{user_id} fires plan-change notification
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAdminUsersPlanNotification:
    """Plan-change events are fired when an admin changes a user's tier."""

    @pytest.fixture()
    def _engine(self):
        engine = _make_engine()
        yield engine
        Base.metadata.drop_all(bind=engine)

    @pytest.fixture()
    def _admin_client(self, _engine):
        from app.api.admin_users import _require_admin
        from app.main import app

        def override_db():
            Session = sessionmaker(bind=_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[_require_admin] = lambda: _ADMIN_USER

        with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
            yield client

        app.dependency_overrides.clear()

    def _seed_profile(self, engine, user_id: str, tier: str = "free") -> None:
        Session = sessionmaker(bind=engine)
        session = Session()
        profile = UserProfile(user_id=user_id, subscription_tier=tier)
        session.add(profile)
        session.commit()
        session.close()

    def test_admin_plan_change_fires_notification(self, _admin_client, _engine, mocker):
        """Admin changing free → professional sends notification and webhook."""
        self._seed_profile(_engine, _REGULAR_USER_ID, tier="free")

        mock_notify = mocker.patch("app.utils.notification.notify_plan_changed", return_value=True)
        mock_dispatch = mocker.patch("app.utils.webhook.dispatch_webhook_event")

        resp = _admin_client.put(
            f"/api/admin/users/{_REGULAR_USER_ID}",
            json={"subscription_tier": "professional", "is_blocked": False},
        )
        assert resp.status_code == 200

        mock_notify.assert_called_once_with(
            _REGULAR_USER_ID, old_tier="free", new_tier="professional", changed_by="admin"
        )
        mock_dispatch.assert_called_once()
        call_args = mock_dispatch.call_args
        assert call_args[0][0] == "user.plan_changed"
        assert call_args[0][1]["changed_by"] == "admin"

    def test_admin_no_event_when_tier_unchanged(self, _admin_client, _engine, mocker):
        """No notification when admin saves a profile without changing the tier."""
        self._seed_profile(_engine, _REGULAR_USER_ID, tier="starter")

        mock_notify = mocker.patch("app.utils.notification.notify_plan_changed")
        mock_dispatch = mocker.patch("app.utils.webhook.dispatch_webhook_event")

        resp = _admin_client.put(
            f"/api/admin/users/{_REGULAR_USER_ID}",
            json={"subscription_tier": "starter", "is_blocked": False},
        )
        assert resp.status_code == 200
        mock_notify.assert_not_called()
        mock_dispatch.assert_not_called()

    def test_admin_no_event_for_brand_new_profile(self, _admin_client, _engine, mocker):
        """Creating a brand-new profile via PUT does NOT fire a plan-changed event."""
        mock_notify = mocker.patch("app.utils.notification.notify_plan_changed")
        mock_dispatch = mocker.patch("app.utils.webhook.dispatch_webhook_event")

        resp = _admin_client.put(
            "/api/admin/users/brand-new-user",
            json={"subscription_tier": "starter", "is_blocked": False},
        )
        assert resp.status_code == 200
        mock_notify.assert_not_called()
        mock_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: POST /api/admin/users/{user_id}/payment-issue
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPaymentIssueEndpoint:
    """Tests for POST /api/admin/users/{user_id}/payment-issue."""

    @pytest.fixture()
    def _engine(self):
        engine = _make_engine()
        yield engine
        Base.metadata.drop_all(bind=engine)

    @pytest.fixture()
    def _admin_client(self, _engine):
        from app.api.admin_users import _require_admin
        from app.main import app

        def override_db():
            Session = sessionmaker(bind=_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[_require_admin] = lambda: _ADMIN_USER

        with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
            yield client

        app.dependency_overrides.clear()

    def _seed_profile(self, engine, user_id: str) -> None:
        Session = sessionmaker(bind=engine)
        session = Session()
        session.add(UserProfile(user_id=user_id))
        session.commit()
        session.close()

    def test_payment_issue_returns_200(self, _admin_client, _engine, mocker):
        """POST /payment-issue returns 200 with acknowledged=True."""
        self._seed_profile(_engine, _REGULAR_USER_ID)
        mocker.patch("app.utils.notification.notify_payment_issue", return_value=True)
        mocker.patch("app.utils.webhook.dispatch_webhook_event")

        resp = _admin_client.post(
            f"/api/admin/users/{_REGULAR_USER_ID}/payment-issue",
            json={"issue": "Card declined"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["acknowledged"] is True
        assert data["user_id"] == _REGULAR_USER_ID

    def test_payment_issue_fires_notification_and_webhook(self, _admin_client, _engine, mocker):
        """Notification and webhook are dispatched for a payment issue."""
        self._seed_profile(_engine, _REGULAR_USER_ID)

        mock_notify = mocker.patch("app.utils.notification.notify_payment_issue", return_value=True)
        mock_dispatch = mocker.patch("app.utils.webhook.dispatch_webhook_event")

        _admin_client.post(
            f"/api/admin/users/{_REGULAR_USER_ID}/payment-issue",
            json={"issue": "Disputed charge"},
        )

        mock_notify.assert_called_once_with(_REGULAR_USER_ID, issue="Disputed charge")
        mock_dispatch.assert_called_once()
        call_args = mock_dispatch.call_args
        assert call_args[0][0] == "user.payment_issue"
        assert call_args[0][1]["issue"] == "Disputed charge"

    def test_payment_issue_404_for_unknown_user(self, _admin_client, _engine, mocker):
        """Returns 404 when the user profile does not exist."""
        mocker.patch("app.utils.notification.notify_payment_issue")
        resp = _admin_client.post(
            "/api/admin/users/ghost-user/payment-issue",
            json={"issue": "Unpaid invoice"},
        )
        assert resp.status_code == 404

    def test_payment_issue_requires_admin(self, _engine):
        """Returns 403 without admin session."""
        from app.api.admin_users import _require_admin
        from app.main import app

        def override_db():
            Session = sessionmaker(bind=_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        # Remove the admin override so the real guard runs
        app.dependency_overrides.pop(_require_admin, None)

        with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/admin/users/any-user/payment-issue",
                json={"issue": "Test"},
            )

        app.dependency_overrides.clear()
        assert resp.status_code == 403

    def test_payment_issue_rejects_empty_issue(self, _admin_client, _engine, mocker):
        """Empty issue string fails validation (422)."""
        self._seed_profile(_engine, _REGULAR_USER_ID)
        mocker.patch("app.utils.notification.notify_payment_issue")

        resp = _admin_client.post(
            f"/api/admin/users/{_REGULAR_USER_ID}/payment-issue",
            json={"issue": ""},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests: signup notification is fired on new profile creation via auth
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSignupNotificationFromAuth:
    """_ensure_user_profile fires signup notification for new users."""

    def test_fires_signup_notification_for_new_user(self, mocker):
        """Notification and webhook are triggered when a brand-new profile is created."""
        mock_notify = mocker.patch("app.utils.notification.notify_user_signup", return_value=True)
        mock_dispatch = mocker.patch("app.utils.webhook.dispatch_webhook_event")

        from app.auth import _ensure_user_profile

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None  # no existing profile

        user_data = {
            "sub": "new-user-sub",
            "name": "New User",
            "email": "newuser@example.com",
            "preferred_username": "newuser",
        }

        _ensure_user_profile(mock_db, user_data)

        mock_notify.assert_called_once_with(
            "new-user-sub",
            display_name="New User",
            email="newuser@example.com",
        )
        mock_dispatch.assert_called_once()
        call_args = mock_dispatch.call_args
        assert call_args[0][0] == "user.signup"
        assert call_args[0][1]["user_id"] == "new-user-sub"

    def test_no_signup_notification_for_existing_user(self, mocker):
        """No notification when the user profile already exists (returning user)."""
        mock_notify = mocker.patch("app.utils.notification.notify_user_signup")
        mock_dispatch = mocker.patch("app.utils.webhook.dispatch_webhook_event")

        from app.auth import _ensure_user_profile
        from app.models import UserProfile

        existing_profile = MagicMock(spec=UserProfile)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing_profile

        user_data = {
            "sub": "existing-user-sub",
            "name": "Existing User",
            "email": "existing@example.com",
        }

        _ensure_user_profile(mock_db, user_data)

        mock_notify.assert_not_called()
        mock_dispatch.assert_not_called()

    def test_no_signup_notification_when_no_user_id(self, mocker):
        """No notification when user_data has no stable identifier."""
        mock_notify = mocker.patch("app.utils.notification.notify_user_signup")

        from app.auth import _ensure_user_profile

        mock_db = MagicMock()
        _ensure_user_profile(mock_db, {})

        mock_notify.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: webhook events listed via the API include new user events
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestWebhookAPIEventsIncludeUserEvents:
    """GET /api/webhooks/events/ includes the new user event types."""

    def test_list_events_includes_user_signup(self, client):
        """user.signup appears in the events list."""
        from app.api.webhooks import _require_admin

        client.app.dependency_overrides[_require_admin] = lambda: _ADMIN_USER
        resp = client.get("/api/webhooks/events/")
        client.app.dependency_overrides.pop(_require_admin, None)
        assert resp.status_code == 200
        assert "user.signup" in resp.json()

    def test_list_events_includes_user_plan_changed(self, client):
        from app.api.webhooks import _require_admin

        client.app.dependency_overrides[_require_admin] = lambda: _ADMIN_USER
        resp = client.get("/api/webhooks/events/")
        client.app.dependency_overrides.pop(_require_admin, None)
        assert resp.status_code == 200
        assert "user.plan_changed" in resp.json()

    def test_list_events_includes_user_payment_issue(self, client):
        from app.api.webhooks import _require_admin

        client.app.dependency_overrides[_require_admin] = lambda: _ADMIN_USER
        resp = client.get("/api/webhooks/events/")
        client.app.dependency_overrides.pop(_require_admin, None)
        assert resp.status_code == 200
        assert "user.payment_issue" in resp.json()
