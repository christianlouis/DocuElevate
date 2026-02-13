"""Tests for app/utils/notification.py module."""

from unittest.mock import patch

import pytest

from app.utils.notification import (
    _mask_sensitive_url,
    notify_celery_failure,
    notify_credential_failure,
    notify_file_processed,
    notify_shutdown,
    notify_startup,
    send_notification,
)


@pytest.mark.unit
class TestMaskSensitiveUrl:
    """Tests for _mask_sensitive_url function."""

    def test_masks_basic_auth_credentials(self):
        """Test masking of basic auth credentials in URL."""
        url = "smtp://user:mypassword@smtp.example.com:587"
        result = _mask_sensitive_url(url)
        assert "mypassword" not in result
        assert "user" in result
        assert "****" in result

    def test_masks_discord_webhook(self):
        """Test masking of Discord webhook URL."""
        url = "discord://webhook_id/webhook_token"
        result = _mask_sensitive_url(url)
        assert "webhook_token" not in result

    def test_masks_telegram_bot_token(self):
        """Test masking of Telegram bot token."""
        url = "tgram://bot_token/chat_id"
        result = _mask_sensitive_url(url)
        assert "chat_id" not in result

    def test_masks_query_param_tokens(self):
        """Test masking of token query parameters."""
        url = "https://example.com/api?token=secret123&key=apikey456"
        result = _mask_sensitive_url(url)
        assert "secret123" not in result
        assert "apikey456" not in result


@pytest.mark.unit
class TestSendNotification:
    """Tests for send_notification function."""

    @patch("app.utils.notification.settings")
    def test_returns_false_when_no_urls_configured(self, mock_settings):
        """Test that send_notification returns False when no URLs are configured."""
        mock_settings.notification_urls = []
        result = send_notification(title="Test", message="Test message")
        assert result is False

    @patch("app.utils.notification.settings")
    def test_returns_false_when_urls_is_none(self, mock_settings):
        """Test that send_notification returns False when URLs is None."""
        mock_settings.notification_urls = None
        result = send_notification(title="Test", message="Test message")
        assert result is False


@pytest.mark.unit
class TestNotifyCeleryFailure:
    """Tests for notify_celery_failure function."""

    @patch("app.utils.notification.settings")
    def test_returns_false_when_disabled(self, mock_settings):
        """Test returns False when task failure notifications are disabled."""
        mock_settings.notify_on_task_failure = False
        result = notify_celery_failure("test_task", "task-123", Exception("test"), [], {})
        assert result is False


@pytest.mark.unit
class TestNotifyCredentialFailure:
    """Tests for notify_credential_failure function."""

    @patch("app.utils.notification.settings")
    def test_returns_false_when_disabled(self, mock_settings):
        """Test returns False when credential failure notifications are disabled."""
        mock_settings.notify_on_credential_failure = False
        result = notify_credential_failure("OpenAI", "Invalid key")
        assert result is False


@pytest.mark.unit
class TestNotifyStartup:
    """Tests for notify_startup function."""

    @patch("app.utils.notification.settings")
    def test_returns_false_when_disabled(self, mock_settings):
        """Test returns False when startup notifications are disabled."""
        mock_settings.notify_on_startup = False
        result = notify_startup()
        assert result is False


@pytest.mark.unit
class TestNotifyShutdown:
    """Tests for notify_shutdown function."""

    @patch("app.utils.notification.settings")
    def test_returns_false_when_disabled(self, mock_settings):
        """Test returns False when shutdown notifications are disabled."""
        mock_settings.notify_on_shutdown = False
        result = notify_shutdown()
        assert result is False


@pytest.mark.unit
class TestNotifyFileProcessed:
    """Tests for notify_file_processed function."""

    @patch("app.utils.notification.settings")
    def test_returns_false_when_disabled(self, mock_settings):
        """Test returns False when file processed notifications are disabled."""
        mock_settings.notify_on_file_processed = False
        result = notify_file_processed("test.pdf", 1024, {"document_type": "invoice"}, ["Dropbox"])
        assert result is False
