"""Tests for app/utils/user_notification.py.

Covers all previously-uncovered branches:
- create_in_app_notification: exception/rollback path
- _send_email_notification: full SMTP success path, TLS disabled, no credentials
- _send_webhook_notification: success path with/without secret header
- dispatch_user_notification: preference loop (email, webhook), no target_id,
  inactive target, invalid/empty JSON config, JSON decode error, outer exception
- dispatch_user_notification: push notification path (success and exception)
- notify_user_document_processed / notify_user_document_failed: happy-path smoke tests
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import InAppNotification, UserNotificationPreference, UserNotificationTarget

_OWNER = "dispatch-test-user@example.com"


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def mem_engine():
    """In-memory SQLite engine for user_notification tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def Session(mem_engine):  # noqa: N802
    """Session factory bound to mem_engine."""
    return sessionmaker(bind=mem_engine)


# ---------------------------------------------------------------------------
# create_in_app_notification
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateInAppNotification:
    """Tests for create_in_app_notification()."""

    def test_returns_none_on_db_exception(self, Session):
        """create_in_app_notification should return None and rollback on error."""
        from app.utils.user_notification import create_in_app_notification

        # Provide a session whose commit raises to exercise the except branch
        bad_session = MagicMock()
        bad_session.add = MagicMock()
        bad_session.commit = MagicMock(side_effect=RuntimeError("DB is down"))
        bad_session.rollback = MagicMock()
        bad_session.close = MagicMock()

        BadSession = MagicMock(return_value=bad_session)  # noqa: N806

        with patch("app.utils.user_notification.SessionLocal", BadSession):
            result = create_in_app_notification(
                owner_id=_OWNER,
                event_type="document.processed",
                title="Oops",
                message="Something went wrong",
            )

        assert result is None
        bad_session.rollback.assert_called_once()
        bad_session.close.assert_called_once()


# ---------------------------------------------------------------------------
# _send_email_notification
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSendEmailNotification:
    """Tests for _send_email_notification()."""

    def test_success_with_tls_and_credentials(self):
        """Email is sent with STARTTLS and login when fully configured."""
        from app.utils.user_notification import _send_email_notification

        config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_username": "user@example.com",
            "smtp_password": "secret",
            "smtp_use_tls": True,
            "recipient_email": "dest@example.com",
        }

        mock_server = MagicMock()
        mock_smtp_cls = MagicMock(return_value=mock_server)
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch("app.utils.user_notification.smtplib.SMTP", mock_smtp_cls):
            result = _send_email_notification(config, "Subject", "Body text")

        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@example.com", "secret")
        mock_server.send_message.assert_called_once()

    def test_success_without_tls_and_without_credentials(self):
        """Email sent without STARTTLS and login when tls=False and no creds."""
        from app.utils.user_notification import _send_email_notification

        config = {
            "smtp_host": "relay.internal",
            "smtp_port": 25,
            "smtp_use_tls": False,
            "recipient_email": "dest@example.com",
        }

        mock_server = MagicMock()
        mock_smtp_cls = MagicMock(return_value=mock_server)
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch("app.utils.user_notification.smtplib.SMTP", mock_smtp_cls):
            result = _send_email_notification(config, "Subject", "No TLS body")

        assert result is True
        mock_server.starttls.assert_not_called()
        mock_server.login.assert_not_called()
        mock_server.send_message.assert_called_once()

    def test_returns_false_on_smtp_exception(self):
        """_send_email_notification returns False when SMTP.connect raises."""
        from app.utils.user_notification import _send_email_notification

        config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "recipient_email": "dest@example.com",
        }

        with patch(
            "app.utils.user_notification.smtplib.SMTP",
            side_effect=ConnectionRefusedError("refused"),
        ):
            result = _send_email_notification(config, "Subject", "Body")

        assert result is False

    def test_sender_email_defaults_to_smtp_username(self):
        """When sender_email is absent the smtp_username is used as From."""
        from app.utils.user_notification import _send_email_notification

        captured_msgs = []

        config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "sender@example.com",
            "smtp_use_tls": False,
            "recipient_email": "dest@example.com",
        }

        mock_server = MagicMock()

        def capture_send(msg):
            captured_msgs.append(msg)

        mock_server.send_message = capture_send
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch("app.utils.user_notification.smtplib.SMTP", return_value=mock_server):
            result = _send_email_notification(config, "Hi", "Body")

        assert result is True
        assert captured_msgs[0]["From"] == "sender@example.com"

    def test_sender_email_defaults_to_noreply_when_no_username(self):
        """When no sender_email and no smtp_username, From falls back to noreply."""
        from app.utils.user_notification import _send_email_notification

        captured_msgs = []

        config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 25,
            "smtp_use_tls": False,
            "recipient_email": "dest@example.com",
        }

        mock_server = MagicMock()

        def capture_send(msg):
            captured_msgs.append(msg)

        mock_server.send_message = capture_send
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch("app.utils.user_notification.smtplib.SMTP", return_value=mock_server):
            result = _send_email_notification(config, "Hi", "Body")

        assert result is True
        assert captured_msgs[0]["From"] == "noreply@docuelevate.local"


# ---------------------------------------------------------------------------
# _send_webhook_notification
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSendWebhookNotification:
    """Tests for _send_webhook_notification()."""

    def test_success_with_secret_header(self):
        """Webhook sent and X-DocuElevate-Secret header set when secret provided."""
        from app.utils.user_notification import _send_webhook_notification

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("app.utils.user_notification.httpx.post", return_value=mock_response) as mock_post:
            result = _send_webhook_notification(
                {"url": "https://hook.example.com/test", "secret": "mysecret"},
                "document.processed",
                "Title",
                "Body",
            )

        assert result is True
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["X-DocuElevate-Secret"] == "mysecret"
        assert kwargs["json"]["event"] == "document.processed"

    def test_success_without_secret(self):
        """Webhook sent without X-DocuElevate-Secret header when no secret."""
        from app.utils.user_notification import _send_webhook_notification

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("app.utils.user_notification.httpx.post", return_value=mock_response) as mock_post:
            result = _send_webhook_notification(
                {"url": "https://hook.example.com/test"},
                "document.failed",
                "Failed",
                "Error details",
            )

        assert result is True
        _, kwargs = mock_post.call_args
        assert "X-DocuElevate-Secret" not in kwargs["headers"]

    def test_returns_false_on_http_error(self):
        """_send_webhook_notification returns False when httpx raises."""
        from app.utils.user_notification import _send_webhook_notification

        with patch(
            "app.utils.user_notification.httpx.post",
            side_effect=Exception("connection error"),
        ):
            result = _send_webhook_notification(
                {"url": "https://hook.example.com/test"},
                "document.processed",
                "T",
                "M",
            )

        assert result is False

    def test_returns_false_on_raise_for_status(self):
        """Returns False when response.raise_for_status() throws."""
        import httpx as _httpx

        from app.utils.user_notification import _send_webhook_notification

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=_httpx.HTTPStatusError(
                "400",
                request=MagicMock(),
                response=MagicMock(),
            )
        )

        with patch("app.utils.user_notification.httpx.post", return_value=mock_response):
            result = _send_webhook_notification(
                {"url": "https://hook.example.com/test"},
                "document.processed",
                "T",
                "M",
            )

        assert result is False


# ---------------------------------------------------------------------------
# dispatch_user_notification – preference loop
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDispatchUserNotification:
    """Tests for dispatch_user_notification() preference dispatch logic."""

    def _make_target(self, session, channel_type: str, config_dict: dict | None = None, is_active: bool = True):
        target = UserNotificationTarget(
            owner_id=_OWNER,
            channel_type=channel_type,
            name=f"{channel_type}-target",
            config=json.dumps(config_dict) if config_dict is not None else None,
            is_active=is_active,
        )
        session.add(target)
        session.commit()
        session.refresh(target)
        return target

    def _make_pref(self, session, channel_type: str, target_id: int | None, is_enabled: bool = True):
        pref = UserNotificationPreference(
            owner_id=_OWNER,
            event_type="document.processed",
            channel_type=channel_type,
            target_id=target_id,
            is_enabled=is_enabled,
        )
        session.add(pref)
        session.commit()
        return pref

    def test_dispatches_email_when_pref_enabled(self, Session):
        """Email notification is sent for an active email preference."""
        s = Session()
        target = self._make_target(
            s,
            "email",
            {
                "smtp_host": "smtp.example.com",
                "recipient_email": "u@example.com",
                "smtp_use_tls": False,
            },
        )
        self._make_pref(s, "email", target.id)
        s.close()

        with (
            patch("app.utils.user_notification.SessionLocal", Session),
            patch("app.utils.user_notification._send_email_notification", return_value=True) as mock_email,
            patch("app.utils.push_notification.send_push_to_owner"),
        ):
            from app.utils.user_notification import dispatch_user_notification

            dispatch_user_notification(_OWNER, "document.processed", "Title", "Body")

        mock_email.assert_called_once()

    def test_dispatches_webhook_when_pref_enabled(self, Session):
        """Webhook notification is sent for an active webhook preference."""
        s = Session()
        target = self._make_target(s, "webhook", {"url": "https://hook.example.com"})
        self._make_pref(s, "webhook", target.id)
        s.close()

        with (
            patch("app.utils.user_notification.SessionLocal", Session),
            patch("app.utils.user_notification._send_webhook_notification", return_value=True) as mock_hook,
            patch("app.utils.push_notification.send_push_to_owner"),
        ):
            from app.utils.user_notification import dispatch_user_notification

            dispatch_user_notification(_OWNER, "document.processed", "Title", "Body")

        mock_hook.assert_called_once()

    def test_skips_pref_with_no_target_id(self, Session):
        """Preferences without a target_id are skipped (in-app only)."""
        s = Session()
        self._make_pref(s, "email", target_id=None)
        s.close()

        with (
            patch("app.utils.user_notification.SessionLocal", Session),
            patch("app.utils.user_notification._send_email_notification") as mock_email,
            patch("app.utils.push_notification.send_push_to_owner"),
        ):
            from app.utils.user_notification import dispatch_user_notification

            dispatch_user_notification(_OWNER, "document.processed", "Title", "Body")

        mock_email.assert_not_called()

    def test_skips_inactive_target(self, Session):
        """Preferences pointing at an inactive target are skipped."""
        s = Session()
        target = self._make_target(s, "email", {"smtp_host": "x", "recipient_email": "y"}, is_active=False)
        self._make_pref(s, "email", target.id)
        s.close()

        with (
            patch("app.utils.user_notification.SessionLocal", Session),
            patch("app.utils.user_notification._send_email_notification") as mock_email,
            patch("app.utils.push_notification.send_push_to_owner"),
        ):
            from app.utils.user_notification import dispatch_user_notification

            dispatch_user_notification(_OWNER, "document.processed", "Title", "Body")

        mock_email.assert_not_called()

    def test_handles_invalid_json_config(self, Session):
        """Invalid JSON in target.config falls back to empty dict (no crash)."""
        target = UserNotificationTarget(
            owner_id=_OWNER,
            channel_type="email",
            name="bad-config-target",
            config="NOT_VALID_JSON",
            is_active=True,
        )
        s = Session()
        s.add(target)
        s.commit()
        s.refresh(target)
        self._make_pref(s, "email", target.id)
        s.close()

        with (
            patch("app.utils.user_notification.SessionLocal", Session),
            patch("app.utils.user_notification._send_email_notification", return_value=False) as mock_email,
            patch("app.utils.push_notification.send_push_to_owner"),
        ):
            from app.utils.user_notification import dispatch_user_notification

            # Should not raise even though config is bad JSON
            dispatch_user_notification(_OWNER, "document.processed", "Title", "Body")

        # Called with empty config dict, which is missing smtp_host → returns False
        mock_email.assert_called_once_with({}, "Title", "Body")

    def test_handles_null_config(self, Session):
        """NULL target.config is treated as empty dict (no crash)."""
        target = UserNotificationTarget(
            owner_id=_OWNER,
            channel_type="webhook",
            name="null-config-target",
            config=None,
            is_active=True,
        )
        s = Session()
        s.add(target)
        s.commit()
        s.refresh(target)
        self._make_pref(s, "webhook", target.id)
        s.close()

        with (
            patch("app.utils.user_notification.SessionLocal", Session),
            patch("app.utils.user_notification._send_webhook_notification", return_value=False) as mock_hook,
            patch("app.utils.push_notification.send_push_to_owner"),
        ):
            from app.utils.user_notification import dispatch_user_notification

            dispatch_user_notification(_OWNER, "document.processed", "Title", "Body")

        mock_hook.assert_called_once_with({}, "document.processed", "Title", "Body")

    def test_outer_exception_does_not_propagate(self):
        """An exception in the preference query must be caught and logged."""
        bad_session = MagicMock()
        bad_session.query = MagicMock(side_effect=RuntimeError("DB gone"))
        bad_session.add = MagicMock()
        bad_session.commit = MagicMock()
        bad_session.refresh = MagicMock(return_value=MagicMock())
        bad_session.close = MagicMock()

        BadSession = MagicMock(return_value=bad_session)  # noqa: N806

        with (
            patch("app.utils.user_notification.SessionLocal", BadSession),
            patch("app.utils.push_notification.send_push_to_owner"),
        ):
            from app.utils.user_notification import dispatch_user_notification

            # Must not raise
            dispatch_user_notification(_OWNER, "document.processed", "Title", "Body")

    def test_push_notification_sent(self, Session):
        """Push notification is sent via send_push_to_owner."""
        with (
            patch("app.utils.user_notification.SessionLocal", Session),
            patch("app.utils.push_notification.send_push_to_owner") as mock_push,
        ):
            from app.utils.user_notification import dispatch_user_notification

            dispatch_user_notification(_OWNER, "document.processed", "Push Title", "Push Body", file_id=99)

        mock_push.assert_called_once_with(
            owner_id=_OWNER,
            title="Push Title",
            body="Push Body",
            data={"event_type": "document.processed", "file_id": 99},
        )

    def test_push_exception_does_not_propagate(self, Session):
        """An exception in send_push_to_owner must be caught and logged."""
        with (
            patch("app.utils.user_notification.SessionLocal", Session),
            patch(
                "app.utils.push_notification.send_push_to_owner",
                side_effect=RuntimeError("push service down"),
            ),
        ):
            from app.utils.user_notification import dispatch_user_notification

            # Must not raise
            dispatch_user_notification(_OWNER, "document.processed", "T", "M")

    def test_unknown_channel_type_is_skipped(self, Session):
        """Preferences with an unrecognised channel_type are silently skipped.

        The live query filters to ("email", "webhook"), so this branch is only
        reachable via a mocked session that bypasses the filter.  The test
        exercises the dead else-branch in dispatch_user_notification so that
        branch coverage reaches 100%.
        """
        import json as _json

        target = UserNotificationTarget(
            owner_id=_OWNER,
            channel_type="sms",
            name="sms-target",
            config=_json.dumps({"phone": "+1555000000"}),
            is_active=True,
        )
        s = Session()
        s.add(target)
        s.commit()
        s.refresh(target)
        target_id = target.id

        unknown_pref = MagicMock()
        unknown_pref.target_id = target_id
        unknown_pref.channel_type = "sms"

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [unknown_pref]

        # Build a real session but intercept only the query for preferences
        real_session = Session()

        def fake_query(model):
            from app.models import UserNotificationPreference as _UNP

            if model is _UNP:
                return mock_query
            return real_session.query(model)

        real_session.query = fake_query  # type: ignore[method-assign]
        real_session_cls = MagicMock(return_value=real_session)

        with (
            patch("app.utils.user_notification.SessionLocal", real_session_cls),
            patch("app.utils.user_notification._send_email_notification") as mock_email,
            patch("app.utils.user_notification._send_webhook_notification") as mock_hook,
            patch("app.utils.push_notification.send_push_to_owner"),
        ):
            from app.utils.user_notification import dispatch_user_notification

            dispatch_user_notification(_OWNER, "document.processed", "T", "M")

        mock_email.assert_not_called()
        mock_hook.assert_not_called()
        real_session.close()


# ---------------------------------------------------------------------------
# notify_user_document_processed / notify_user_document_failed
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNotifyUserDocumentHelpers:
    """Smoke tests for the convenience wrappers."""

    def test_notify_processed_creates_in_app_record(self, Session):
        """notify_user_document_processed creates an InAppNotification."""
        with (
            patch("app.utils.user_notification.SessionLocal", Session),
            patch("app.utils.push_notification.send_push_to_owner"),
        ):
            from app.utils.user_notification import notify_user_document_processed

            notify_user_document_processed(owner_id=_OWNER, filename="report.pdf", file_id=5)

        s = Session()
        notifs = s.query(InAppNotification).filter_by(owner_id=_OWNER).all()
        s.close()
        assert len(notifs) == 1
        assert "report.pdf" in notifs[0].title
        assert notifs[0].event_type == "document.processed"

    def test_notify_failed_creates_in_app_record(self, Session):
        """notify_user_document_failed creates an InAppNotification."""
        with (
            patch("app.utils.user_notification.SessionLocal", Session),
            patch("app.utils.push_notification.send_push_to_owner"),
        ):
            from app.utils.user_notification import notify_user_document_failed

            notify_user_document_failed(owner_id=_OWNER, filename="broken.pdf", error="Timeout")

        s = Session()
        notifs = s.query(InAppNotification).filter_by(owner_id=_OWNER).all()
        s.close()
        assert len(notifs) == 1
        assert "broken.pdf" in notifs[0].title
        assert "Timeout" in notifs[0].message
        assert notifs[0].event_type == "document.failed"
