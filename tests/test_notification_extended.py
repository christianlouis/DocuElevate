"""
Additional tests for notification utility
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


@pytest.mark.unit
class TestNotificationHelpers:
    """Tests for notification helper functions."""

    def test_mask_sensitive_url_basic_auth(self):
        """Test masking URL with basic auth credentials."""
        from app.utils.notification import _mask_sensitive_url

        url = "http://user:password123@example.com/path"
        masked = _mask_sensitive_url(url)
        assert "password123" not in masked
        assert "****" in masked
        assert "user" in masked

    def test_mask_sensitive_url_discord(self):
        """Test masking Discord webhook URL."""
        from app.utils.notification import _mask_sensitive_url

        url = "discord://webhook_id/webhook_token"
        masked = _mask_sensitive_url(url)
        assert "webhook_token" not in masked
        assert "****" in masked

    def test_mask_sensitive_url_telegram(self):
        """Test masking Telegram bot URL."""
        from app.utils.notification import _mask_sensitive_url

        url = "tgram://bot_token/chat_id"
        masked = _mask_sensitive_url(url)
        assert "bot_token" not in masked
        assert "****" in masked

    def test_mask_sensitive_url_with_params(self):
        """Test masking URL with sensitive query parameters."""
        from app.utils.notification import _mask_sensitive_url

        url = "http://example.com?token=secret123&key=apikey456&other=value"
        masked = _mask_sensitive_url(url)
        assert "secret123" not in masked
        assert "apikey456" not in masked
        assert "****" in masked
        assert "other=value" in masked

    def test_mask_sensitive_url_no_sensitive_data(self):
        """Test masking URL with no sensitive data."""
        from app.utils.notification import _mask_sensitive_url

        url = "http://example.com/path"
        masked = _mask_sensitive_url(url)
        assert masked == url


@pytest.mark.unit
class TestInitApprise:
    """Tests for Apprise initialization."""

    @patch("app.utils.notification.settings")
    @patch("app.utils.notification.apprise.Apprise")
    def test_init_apprise_with_urls(self, mock_apprise_class, mock_settings):
        """Test initializing Apprise with notification URLs."""
        from app.utils.notification import init_apprise, _apprise
        import app.utils.notification as notif_module

        # Reset global
        notif_module._apprise = None

        mock_settings.notification_urls = ["mailto://user@example.com"]
        mock_instance = MagicMock()
        mock_apprise_class.return_value = mock_instance

        result = init_apprise()

        assert result == mock_instance
        mock_instance.add.assert_called_once()

    @patch("app.utils.notification.settings")
    @patch("app.utils.notification.apprise.Apprise")
    def test_init_apprise_no_urls(self, mock_apprise_class, mock_settings):
        """Test initializing Apprise without notification URLs."""
        from app.utils.notification import init_apprise
        import app.utils.notification as notif_module

        notif_module._apprise = None

        mock_settings.notification_urls = []
        mock_instance = MagicMock()
        mock_apprise_class.return_value = mock_instance

        result = init_apprise()

        assert result == mock_instance
        mock_instance.add.assert_not_called()

    @patch("app.utils.notification.settings")
    @patch("app.utils.notification.apprise.Apprise")
    def test_init_apprise_singleton(self, mock_apprise_class, mock_settings):
        """Test that init_apprise returns same instance."""
        from app.utils.notification import init_apprise
        import app.utils.notification as notif_module

        notif_module._apprise = None

        mock_settings.notification_urls = []
        mock_instance = MagicMock()
        mock_apprise_class.return_value = mock_instance

        result1 = init_apprise()
        result2 = init_apprise()

        assert result1 == result2
        assert mock_apprise_class.call_count == 1


@pytest.mark.unit
class TestSendNotification:
    """Tests for send_notification function."""

    @patch("app.utils.notification.init_apprise")
    @patch("app.utils.notification.settings")
    def test_send_notification_no_urls(self, mock_settings, mock_init):
        """Test sending notification with no URLs configured."""
        from app.utils.notification import send_notification

        mock_settings.notification_urls = []

        result = send_notification("Test", "Message")

        assert result is False
        mock_init.assert_not_called()

    @patch("app.utils.notification.init_apprise")
    @patch("app.utils.notification.settings")
    def test_send_notification_success(self, mock_settings, mock_init):
        """Test sending notification successfully."""
        from app.utils.notification import send_notification

        mock_settings.notification_urls = ["mailto://test@example.com"]

        mock_apprise = MagicMock()
        mock_server = MagicMock()
        mock_server.notify.return_value = True
        mock_apprise.servers = [mock_server]
        mock_init.return_value = mock_apprise

        result = send_notification("Test Title", "Test Message", "success")

        assert result is True
        mock_server.notify.assert_called_once()

    @patch("app.utils.notification.init_apprise")
    @patch("app.utils.notification.settings")
    def test_send_notification_all_fail(self, mock_settings, mock_init):
        """Test sending notification when all services fail."""
        from app.utils.notification import send_notification

        mock_settings.notification_urls = ["mailto://test@example.com"]

        mock_apprise = MagicMock()
        mock_server = MagicMock()
        mock_server.notify.return_value = False
        mock_apprise.servers = [mock_server]
        mock_init.return_value = mock_apprise

        result = send_notification("Test", "Message")

        assert result is False

    @patch("app.utils.notification.init_apprise")
    @patch("app.utils.notification.settings")
    def test_send_notification_no_servers(self, mock_settings, mock_init):
        """Test sending notification with no servers available."""
        from app.utils.notification import send_notification

        mock_settings.notification_urls = ["mailto://test@example.com"]

        mock_apprise = MagicMock()
        mock_apprise.servers = []
        mock_init.return_value = mock_apprise

        result = send_notification("Test", "Message")

        assert result is False


@pytest.mark.unit
class TestNotificationWrappers:
    """Tests for notification wrapper functions."""

    @patch("app.utils.notification.send_notification")
    @patch("app.utils.notification.settings")
    def test_notify_celery_failure_enabled(self, mock_settings, mock_send):
        """Test notifying about Celery task failure."""
        from app.utils.notification import notify_celery_failure

        mock_settings.notify_on_task_failure = True
        mock_send.return_value = True

        result = notify_celery_failure("test_task", "task-123", Exception("Error"), [], {})

        assert result is True
        mock_send.assert_called_once()

    @patch("app.utils.notification.settings")
    def test_notify_celery_failure_disabled(self, mock_settings):
        """Test that Celery failure notification respects settings."""
        from app.utils.notification import notify_celery_failure

        mock_settings.notify_on_task_failure = False

        result = notify_celery_failure("test_task", "task-123", Exception("Error"), [], {})

        assert result is False

    @patch("app.utils.notification.send_notification")
    @patch("app.utils.notification.settings")
    def test_notify_credential_failure(self, mock_settings, mock_send):
        """Test notifying about credential failure."""
        from app.utils.notification import notify_credential_failure

        mock_settings.notify_on_credential_failure = True
        mock_send.return_value = True

        result = notify_credential_failure("Dropbox", "Invalid token")

        assert result is True
        mock_send.assert_called_once()

    @patch("app.utils.notification.send_notification")
    @patch("app.utils.notification.settings")
    def test_notify_startup(self, mock_settings, mock_send):
        """Test startup notification."""
        from app.utils.notification import notify_startup

        mock_settings.notify_on_startup = True
        mock_settings.external_hostname = "test.example.com"
        mock_send.return_value = True

        result = notify_startup()

        assert result is True
        mock_send.assert_called_once()

    @patch("app.utils.notification.send_notification")
    @patch("app.utils.notification.settings")
    def test_notify_shutdown(self, mock_settings, mock_send):
        """Test shutdown notification."""
        from app.utils.notification import notify_shutdown

        mock_settings.notify_on_shutdown = True
        mock_settings.external_hostname = "test.example.com"
        mock_send.return_value = True

        result = notify_shutdown()

        assert result is True
        mock_send.assert_called_once()

    @patch("app.utils.notification.send_notification")
    @patch("app.utils.notification.settings")
    def test_notify_file_processed(self, mock_settings, mock_send):
        """Test file processed notification."""
        from app.utils.notification import notify_file_processed

        mock_settings.notify_on_file_processed = True
        mock_send.return_value = True

        metadata = {"document_type": "Invoice", "tags": ["test", "invoice"]}
        result = notify_file_processed("test.pdf", 1024000, metadata, ["dropbox", "email"])

        assert result is True
        mock_send.assert_called_once()
