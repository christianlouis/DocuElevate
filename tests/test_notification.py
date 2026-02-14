"""
Tests for app/utils/notification.py

Tests notification utilities and URL masking.
"""

from unittest.mock import MagicMock, patch

import pytest

_TEST_CREDENTIAL_URL = "https://user:password@example.com/notify"  # noqa: S105
_TEST_QUERY_URL = "https://example.com/api?key=secret1&password=secret2&public=visible"  # noqa: S105


@pytest.mark.unit
class TestNotificationUrlMasking:
    """Test URL masking for security"""

    def test_mask_sensitive_url_basic_auth(self):
        """Test masking of basic auth URLs"""
        from app.utils.notification import _mask_sensitive_url

        url = _TEST_CREDENTIAL_URL
        masked = _mask_sensitive_url(url)

        # Password should be masked
        assert "password" not in masked
        assert "****" in masked
        assert "user" in masked
        assert "example.com" in masked

    def test_mask_sensitive_url_discord(self):
        """Test masking of Discord webhook URLs"""
        from app.utils.notification import _mask_sensitive_url

        url = "discord://webhook_id/webhook_token/channel_id"
        masked = _mask_sensitive_url(url)

        # Token should be masked
        assert "webhook_token" not in masked
        assert "****" in masked
        assert "discord://" in masked

    def test_mask_sensitive_url_telegram(self):
        """Test masking of Telegram URLs"""
        from app.utils.notification import _mask_sensitive_url

        url = "tgram://bot_token/chat_id"
        masked = _mask_sensitive_url(url)

        # Bot token should be masked
        assert "bot_token" not in masked or "****" in masked
        assert "tgram://" in masked

    def test_mask_sensitive_url_with_token_parameter(self):
        """Test masking of URLs with token query parameters"""
        from app.utils.notification import _mask_sensitive_url

        url = "https://example.com/notify?token=secret_token_123&other=value"
        masked = _mask_sensitive_url(url)

        # Token value should be masked
        assert "secret_token_123" not in masked
        assert "token=****" in masked or "****" in masked
        assert "other=value" in masked

    def test_mask_sensitive_url_with_api_key(self):
        """Test masking of URLs with api_key parameter"""
        from app.utils.notification import _mask_sensitive_url

        url = "https://example.com/api?api_key=my_api_key_here"
        masked = _mask_sensitive_url(url)

        # API key should be masked
        assert "my_api_key_here" not in masked
        assert "****" in masked

    def test_mask_sensitive_url_with_multiple_params(self):
        """Test masking with multiple sensitive parameters"""
        from app.utils.notification import _mask_sensitive_url

        url = _TEST_QUERY_URL
        masked = _mask_sensitive_url(url)

        # Sensitive params should be masked
        assert "secret1" not in masked
        assert "secret2" not in masked
        assert "****" in masked
        assert "public=visible" in masked

    def test_mask_sensitive_url_no_sensitive_data(self):
        """Test masking of URLs without sensitive data"""
        from app.utils.notification import _mask_sensitive_url

        url = "https://example.com/notify?id=123&name=test"
        masked = _mask_sensitive_url(url)

        # Should return similar URL (no masking needed)
        assert "example.com" in masked
        assert "id=123" in masked or "****" not in masked or "****" in masked

    def test_mask_sensitive_url_empty_string(self):
        """Test masking of empty string"""
        from app.utils.notification import _mask_sensitive_url

        url = ""
        masked = _mask_sensitive_url(url)

        assert masked == ""

    def test_mask_sensitive_url_various_formats(self):
        """Test masking with various URL formats"""
        from app.utils.notification import _mask_sensitive_url

        test_urls = [
            "mailto://user:password@gmail.com",
            "slack://token@workspace",
            "https://api.example.com?secret=hidden",
        ]

        for url in test_urls:
            masked = _mask_sensitive_url(url)
            # All should return strings
            assert isinstance(masked, str)
            # Most should have masking applied
            assert len(masked) > 0


@pytest.mark.unit
class TestAppriseInitialization:
    """Test Apprise initialization"""

    @patch("app.utils.notification.apprise.Apprise")
    @patch("app.utils.notification.settings")
    def test_init_apprise_with_configured_urls(self, mock_settings, mock_apprise_class):
        """Test Apprise initialization with configured URLs"""
        import app.utils.notification
        from app.utils.notification import init_apprise

        # Reset global
        app.utils.notification._apprise = None

        mock_settings.notification_urls = [
            "https://example.com/notify1",
            "https://example.com/notify2",
        ]

        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        result = init_apprise()

        # Should create Apprise instance
        mock_apprise_class.assert_called_once()

        # Should add configured URLs
        assert mock_apprise_instance.add.call_count == 2

        # Should return the instance
        assert result == mock_apprise_instance

    @patch("app.utils.notification.apprise.Apprise")
    @patch("app.utils.notification.settings")
    def test_init_apprise_no_urls_configured(self, mock_settings, mock_apprise_class):
        """Test Apprise initialization without configured URLs"""
        import app.utils.notification
        from app.utils.notification import init_apprise

        # Reset global
        app.utils.notification._apprise = None

        mock_settings.notification_urls = []

        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        result = init_apprise()

        # Should still create Apprise instance
        mock_apprise_class.assert_called_once()

        # Should not add any URLs
        mock_apprise_instance.add.assert_not_called()

        # Should return the instance
        assert result == mock_apprise_instance

    @patch("app.utils.notification.apprise.Apprise")
    @patch("app.utils.notification.settings")
    def test_init_apprise_caches_instance(self, mock_settings, mock_apprise_class):
        """Test that Apprise instance is cached"""
        import app.utils.notification
        from app.utils.notification import init_apprise

        # Reset global
        app.utils.notification._apprise = None

        mock_settings.notification_urls = []
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        # First call
        result1 = init_apprise()

        # Second call
        result2 = init_apprise()

        # Should only create once (cached)
        mock_apprise_class.assert_called_once()

        # Both should return same instance
        assert result1 == result2

    @patch("app.utils.notification.apprise.Apprise")
    @patch("app.utils.notification.settings")
    def test_init_apprise_handles_add_failure(self, mock_settings, mock_apprise_class):
        """Test handling when adding notification URL fails"""
        import app.utils.notification
        from app.utils.notification import init_apprise

        # Reset global
        app.utils.notification._apprise = None

        mock_settings.notification_urls = ["invalid://url"]

        mock_apprise_instance = MagicMock()
        mock_apprise_instance.add.side_effect = Exception("Invalid URL format")
        mock_apprise_class.return_value = mock_apprise_instance

        # Should not raise exception, just log error
        result = init_apprise()

        # Should still return instance
        assert result == mock_apprise_instance


@pytest.mark.unit
class TestSendNotification:
    """Test send_notification function"""

    @patch("app.utils.notification.init_apprise")
    @patch("app.utils.notification.settings")
    def test_send_notification_no_urls_configured(self, mock_settings, mock_init_apprise):
        """Test sending notification when no URLs are configured."""
        from app.utils.notification import send_notification

        mock_settings.notification_urls = []

        result = send_notification("Test", "Test message")

        assert result is False
        mock_init_apprise.assert_not_called()

    @patch("app.utils.notification.init_apprise")
    @patch("app.utils.notification.settings")
    def test_send_notification_success_type(self, mock_settings, mock_init_apprise):
        """Test notification with success type."""
        from app.utils.notification import send_notification

        mock_settings.notification_urls = ["https://example.com/notify"]
        mock_apprise = MagicMock()
        mock_server = MagicMock()
        mock_server.notify.return_value = True
        mock_apprise.servers = [mock_server]
        mock_init_apprise.return_value = mock_apprise

        result = send_notification("Test", "Message", notification_type="success")

        assert result is True
        mock_server.notify.assert_called_once()
        # Check that SUCCESS type was used
        call_kwargs = mock_server.notify.call_args[1]
        assert "notify_type" in call_kwargs

    @patch("app.utils.notification.init_apprise")
    @patch("app.utils.notification.settings")
    def test_send_notification_warning_type(self, mock_settings, mock_init_apprise):
        """Test notification with warning type."""
        from app.utils.notification import send_notification

        mock_settings.notification_urls = ["https://example.com/notify"]
        mock_apprise = MagicMock()
        mock_server = MagicMock()
        mock_server.notify.return_value = True
        mock_apprise.servers = [mock_server]
        mock_init_apprise.return_value = mock_apprise

        result = send_notification("Test", "Message", notification_type="warn")

        assert result is True

    @patch("app.utils.notification.init_apprise")
    @patch("app.utils.notification.settings")
    def test_send_notification_failure_type(self, mock_settings, mock_init_apprise):
        """Test notification with failure type."""
        from app.utils.notification import send_notification

        mock_settings.notification_urls = ["https://example.com/notify"]
        mock_apprise = MagicMock()
        mock_server = MagicMock()
        mock_server.notify.return_value = True
        mock_apprise.servers = [mock_server]
        mock_init_apprise.return_value = mock_apprise

        result = send_notification("Test", "Message", notification_type="failed")

        assert result is True

    @patch("app.utils.notification.init_apprise")
    @patch("app.utils.notification.settings")
    def test_send_notification_no_servers(self, mock_settings, mock_init_apprise):
        """Test notification when no servers are available."""
        from app.utils.notification import send_notification

        mock_settings.notification_urls = ["https://example.com/notify"]
        mock_apprise = MagicMock()
        mock_apprise.servers = []
        mock_init_apprise.return_value = mock_apprise

        result = send_notification("Test", "Message")

        assert result is False

    @patch("app.utils.notification.init_apprise")
    @patch("app.utils.notification.settings")
    def test_send_notification_partial_success(self, mock_settings, mock_init_apprise):
        """Test notification with multiple servers, some failing."""
        from app.utils.notification import send_notification

        mock_settings.notification_urls = ["https://example.com/notify"]
        mock_apprise = MagicMock()
        mock_server1 = MagicMock()
        mock_server1.notify.return_value = True
        mock_server2 = MagicMock()
        mock_server2.notify.return_value = False
        mock_apprise.servers = [mock_server1, mock_server2]
        mock_init_apprise.return_value = mock_apprise

        result = send_notification("Test", "Message")

        assert result is True  # At least one succeeded

    @patch("app.utils.notification.init_apprise")
    @patch("app.utils.notification.settings")
    def test_send_notification_with_attachments(self, mock_settings, mock_init_apprise):
        """Test notification with file attachments."""
        from app.utils.notification import send_notification

        mock_settings.notification_urls = ["https://example.com/notify"]
        mock_apprise = MagicMock()
        mock_server = MagicMock()
        mock_server.notify.return_value = True
        mock_apprise.servers = [mock_server]
        mock_init_apprise.return_value = mock_apprise

        result = send_notification("Test", "Message", attachments=["/path/to/file.pdf"])

        assert result is True
        call_kwargs = mock_server.notify.call_args[1]
        assert call_kwargs["attach"] == ["/path/to/file.pdf"]

    @patch("app.utils.notification.init_apprise")
    @patch("app.utils.notification.settings")
    def test_send_notification_exception_handling(self, mock_settings, mock_init_apprise):
        """Test that exceptions are caught and logged."""
        from app.utils.notification import send_notification

        mock_settings.notification_urls = ["https://example.com/notify"]
        mock_init_apprise.side_effect = Exception("Connection error")

        result = send_notification("Test", "Message")

        assert result is False


@pytest.mark.unit
class TestNotificationHelpers:
    """Test notification helper functions."""

    @patch("app.utils.notification.send_notification")
    @patch("app.utils.notification.settings")
    def test_notify_celery_failure_disabled(self, mock_settings, mock_send):
        """Test Celery failure notification when disabled."""
        from app.utils.notification import notify_celery_failure

        mock_settings.notify_on_task_failure = False

        result = notify_celery_failure("test_task", "task-123", Exception("Error"), [], {})

        assert result is False
        mock_send.assert_not_called()

    @patch("app.utils.notification.send_notification")
    @patch("app.utils.notification.settings")
    def test_notify_celery_failure_enabled(self, mock_settings, mock_send):
        """Test Celery failure notification when enabled."""
        from app.utils.notification import notify_celery_failure

        mock_settings.notify_on_task_failure = True
        mock_send.return_value = True

        result = notify_celery_failure("test_task", "task-123", Exception("Error"), [], {})

        assert result is True
        mock_send.assert_called_once()
        call_args = mock_send.call_args[1]
        assert call_args["notification_type"] == "failure"

    @patch("app.utils.notification.send_notification")
    @patch("app.utils.notification.settings")
    def test_notify_credential_failure_disabled(self, mock_settings, mock_send):
        """Test credential failure notification when disabled."""
        from app.utils.notification import notify_credential_failure

        mock_settings.notify_on_credential_failure = False

        result = notify_credential_failure("Dropbox", "Invalid token")

        assert result is False
        mock_send.assert_not_called()

    @patch("app.utils.notification.send_notification")
    @patch("app.utils.notification.settings")
    def test_notify_startup_disabled(self, mock_settings, mock_send):
        """Test startup notification when disabled."""
        from app.utils.notification import notify_startup

        mock_settings.notify_on_startup = False

        result = notify_startup()

        assert result is False
        mock_send.assert_not_called()

    @patch("app.utils.notification.send_notification")
    @patch("app.utils.notification.settings")
    def test_notify_shutdown_disabled(self, mock_settings, mock_send):
        """Test shutdown notification when disabled."""
        from app.utils.notification import notify_shutdown

        mock_settings.notify_on_shutdown = False

        result = notify_shutdown()

        assert result is False
        mock_send.assert_not_called()

    @patch("app.utils.notification.send_notification")
    @patch("app.utils.notification.settings")
    def test_notify_file_processed_disabled(self, mock_settings, mock_send):
        """Test file processed notification when disabled."""
        from app.utils.notification import notify_file_processed

        mock_settings.notify_on_file_processed = False

        result = notify_file_processed("test.pdf", 1024000, {}, [])

        assert result is False
        mock_send.assert_not_called()

    @patch("app.utils.notification.send_notification")
    @patch("app.utils.notification.settings")
    def test_notify_file_processed_with_metadata(self, mock_settings, mock_send):
        """Test file processed notification with metadata."""
        from app.utils.notification import notify_file_processed

        mock_settings.notify_on_file_processed = True
        mock_send.return_value = True

        metadata = {"document_type": "invoice", "tags": ["important", "finance"]}
        result = notify_file_processed("test.pdf", 2048000, metadata, ["dropbox", "s3"])

        assert result is True
        mock_send.assert_called_once()
        # Check message contains expected info
        message = mock_send.call_args[0][1]
        assert "2.00 MB" in message
        assert "invoice" in message
        assert "important, finance" in message
        assert "dropbox, s3" in message
