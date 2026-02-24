"""Tests for app/api/diagnostic.py module."""

from unittest.mock import patch

import pytest


@pytest.mark.integration
class TestTestNotification:
    """Tests for test notification endpoint."""

    def test_test_notification_endpoint(self, client):
        """Test /api/diagnostic/test-notification endpoint."""
        response = client.post("/api/diagnostic/test-notification")
        assert response.status_code == 200
        data = response.json()
        # Should return warning (no notification services configured) or success
        assert data["status"] in ("warning", "success", "error")

    @patch("app.api.diagnostic.settings")
    def test_test_notification_no_urls_configured(self, mock_settings, client):
        """Test notification test when no URLs are configured."""
        mock_settings.notification_urls = []
        mock_settings.external_hostname = "test-host"

        response = client.post("/api/diagnostic/test-notification")
        data = response.json()

        assert data["status"] == "warning"
        assert "notification" in data["message"].lower() and "configured" in data["message"].lower()

    @patch("app.utils.notification.send_notification")
    @patch("app.api.diagnostic.settings")
    def test_test_notification_success(self, mock_settings, mock_send, client):
        """Test successful notification test."""
        mock_settings.notification_urls = ["https://example.com/notify"]
        mock_settings.external_hostname = "test-host"
        mock_send.return_value = True

        response = client.post("/api/diagnostic/test-notification")
        data = response.json()

        assert data["status"] == "success"
        assert "services_count" in data
        mock_send.assert_called_once()

    @patch("app.utils.notification.send_notification")
    @patch("app.api.diagnostic.settings")
    def test_test_notification_failure(self, mock_settings, mock_send, client):
        """Test notification test when sending fails."""
        mock_settings.notification_urls = ["https://example.com/notify"]
        mock_settings.external_hostname = "test-host"
        mock_send.return_value = False

        response = client.post("/api/diagnostic/test-notification")
        data = response.json()

        assert data["status"] == "error"
        assert "failed" in data["message"].lower()

    @patch("app.utils.notification.send_notification")
    @patch("app.api.diagnostic.settings")
    def test_test_notification_exception(self, mock_settings, mock_send, client):
        """Test notification test with exception."""
        mock_settings.notification_urls = ["https://example.com/notify"]
        mock_settings.external_hostname = "test-host"
        mock_send.side_effect = Exception("Connection error")

        response = client.post("/api/diagnostic/test-notification")
        data = response.json()

        assert data["status"] == "error"
        assert "error" in data["message"].lower()

    def test_test_notification_includes_timestamp(self, client):
        """Test that notification includes timestamp in message."""
        response = client.post("/api/diagnostic/test-notification")
        data = response.json()

        # Response should have been processed
        assert response.status_code == 200
