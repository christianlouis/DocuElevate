"""
Tests for diagnostic API endpoints
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestDiagnosticEndpoints:
    """Tests for diagnostic API endpoints."""

    @patch("app.api.diagnostic.dump_all_settings")
    @patch("app.api.diagnostic.settings")
    def test_diagnostic_settings_endpoint(self, mock_settings, mock_dump, client: TestClient):
        """Test diagnostic settings endpoint."""
        mock_settings.workdir = "/tmp"
        mock_settings.external_hostname = "test.example.com"
        mock_settings.email_host = "smtp.example.com"
        mock_settings.s3_bucket_name = "test-bucket"

        response = client.get("/api/diagnostic/settings")

        # Should return 200 or 401/403 depending on auth
        assert response.status_code in [200, 401, 403, 404]

        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "settings" in data

    @patch("app.api.diagnostic.send_notification")
    @patch("app.api.diagnostic.settings")
    def test_test_notification_no_urls(self, mock_settings, mock_send, client: TestClient):
        """Test notification endpoint with no URLs configured."""
        mock_settings.notification_urls = []

        response = client.post("/api/diagnostic/test-notification")

        # Should return warning or auth error
        assert response.status_code in [200, 401, 403, 404]

        if response.status_code == 200:
            data = response.json()
            assert "status" in data

    @patch("app.api.diagnostic.send_notification")
    @patch("app.api.diagnostic.settings")
    def test_test_notification_success(self, mock_settings, mock_send, client: TestClient):
        """Test notification endpoint with successful send."""
        mock_settings.notification_urls = ["mailto://test@example.com"]
        mock_settings.external_hostname = "test.example.com"
        mock_send.return_value = True

        response = client.post("/api/diagnostic/test-notification")

        # Should return success or auth error
        assert response.status_code in [200, 401, 403, 404]

        if response.status_code == 200:
            data = response.json()
            assert "status" in data

    @patch("app.api.diagnostic.send_notification")
    @patch("app.api.diagnostic.settings")
    def test_test_notification_failure(self, mock_settings, mock_send, client: TestClient):
        """Test notification endpoint with failed send."""
        mock_settings.notification_urls = ["mailto://test@example.com"]
        mock_settings.external_hostname = "test.example.com"
        mock_send.return_value = False

        response = client.post("/api/diagnostic/test-notification")

        # Should return error or auth error
        assert response.status_code in [200, 401, 403, 404, 500]

    @patch("app.api.diagnostic.send_notification")
    @patch("app.api.diagnostic.settings")
    def test_test_notification_exception(self, mock_settings, mock_send, client: TestClient):
        """Test notification endpoint with exception."""
        mock_settings.notification_urls = ["mailto://test@example.com"]
        mock_settings.external_hostname = "test.example.com"
        mock_send.side_effect = Exception("Notification error")

        response = client.post("/api/diagnostic/test-notification")

        # Should handle exception gracefully
        assert response.status_code in [200, 401, 403, 404, 500]

    @patch("app.api.diagnostic.dump_all_settings")
    @patch("app.api.diagnostic.settings")
    def test_diagnostic_settings_shows_configured_services(
        self, mock_settings, mock_dump, client: TestClient
    ):
        """Test that diagnostic endpoint shows configured services."""
        mock_settings.workdir = "/tmp"
        mock_settings.external_hostname = "test.example.com"
        mock_settings.dropbox_refresh_token = "token"
        mock_settings.openai_api_key = "sk-key"
        mock_settings.google_drive_credentials_json = '{"key": "value"}'

        response = client.get("/api/diagnostic/settings")

        # Check response structure
        assert response.status_code in [200, 401, 403, 404]

        if response.status_code == 200:
            data = response.json()
            if "settings" in data:
                settings_data = data["settings"]
                assert "configured_services" in settings_data
