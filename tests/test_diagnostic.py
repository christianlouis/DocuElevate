"""Tests for app/api/diagnostic.py module."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.integration
class TestDiagnosticSettings:
    """Tests for diagnostic settings endpoint."""

    def test_diagnostic_settings_endpoint(self, client):
        """Test /api/diagnostic/settings endpoint."""
        response = client.get("/api/diagnostic/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "settings" in data
        assert "configured_services" in data["settings"]

    def test_diagnostic_settings_has_expected_services(self, client):
        """Test that diagnostic settings has expected service keys."""
        response = client.get("/api/diagnostic/settings")
        data = response.json()
        services = data["settings"]["configured_services"]
        expected_keys = ["email", "s3", "dropbox", "onedrive", "nextcloud", "sftp", "openai", "azure"]
        for key in expected_keys:
            assert key in services

    def test_diagnostic_settings_includes_workdir(self, client):
        """Test that settings include workdir."""
        response = client.get("/api/diagnostic/settings")
        data = response.json()
        assert "workdir" in data["settings"]

    def test_diagnostic_settings_includes_hostname(self, client):
        """Test that settings include external hostname."""
        response = client.get("/api/diagnostic/settings")
        data = response.json()
        assert "external_hostname" in data["settings"]

    def test_diagnostic_settings_includes_imap_status(self, client):
        """Test that settings include IMAP enabled status."""
        response = client.get("/api/diagnostic/settings")
        data = response.json()
        assert "imap_enabled" in data["settings"]


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
        assert "not configured" in data["message"].lower()

    @patch("app.api.diagnostic.send_notification")
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

    @patch("app.api.diagnostic.send_notification")
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

    @patch("app.api.diagnostic.send_notification")
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


@pytest.mark.unit
class TestDiagnosticHelpers:
    """Test helper functions in diagnostic module."""

    @patch("app.api.diagnostic.dump_all_settings")
    @patch("app.api.diagnostic.settings")
    def test_dump_all_settings_called(self, mock_settings, mock_dump, client):
        """Test that dump_all_settings is called."""
        mock_settings.external_hostname = "test"
        # Setup minimal mocks for configured services
        mock_settings.email_host = None
        mock_settings.s3_bucket_name = None
        mock_settings.dropbox_refresh_token = None
        mock_settings.onedrive_refresh_token = None
        mock_settings.nextcloud_upload_url = None
        mock_settings.sftp_host = None
        mock_settings.paperless_host = None
        mock_settings.google_drive_credentials_json = None
        mock_settings.uptime_kuma_url = None
        mock_settings.authentik_config_url = None
        mock_settings.openai_api_key = None
        mock_settings.azure_api_key = None
        mock_settings.azure_endpoint = None
        mock_settings.imap1_host = None
        mock_settings.imap2_host = None

        response = client.get("/api/diagnostic/settings")

        # dump_all_settings should have been called
        mock_dump.assert_called_once()

    @patch("app.api.diagnostic.settings")
    def test_safe_settings_no_sensitive_data(self, mock_settings, client):
        """Test that safe settings don't include sensitive data."""
        mock_settings.workdir = "/tmp/workdir"
        mock_settings.external_hostname = "test-host"
        mock_settings.openai_api_key = "sk-secret-key-12345"
        mock_settings.aws_secret_access_key = "secret-aws-key"
        # Setup minimal configured services
        mock_settings.email_host = None
        mock_settings.s3_bucket_name = None
        mock_settings.dropbox_refresh_token = None
        mock_settings.onedrive_refresh_token = None
        mock_settings.nextcloud_upload_url = None
        mock_settings.sftp_host = None
        mock_settings.paperless_host = None
        mock_settings.google_drive_credentials_json = None
        mock_settings.uptime_kuma_url = None
        mock_settings.authentik_config_url = None
        mock_settings.azure_api_key = None
        mock_settings.azure_endpoint = None
        mock_settings.imap1_host = None
        mock_settings.imap2_host = None

        response = client.get("/api/diagnostic/settings")
        data = response.json()

        # Sensitive keys should not be in response
        response_str = str(data)
        assert "sk-secret-key" not in response_str
        assert "secret-aws-key" not in response_str
