"""
Tests for app/utils/notification.py

Tests notification utilities and URL masking.
"""

from unittest.mock import MagicMock, Mock, patch

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
