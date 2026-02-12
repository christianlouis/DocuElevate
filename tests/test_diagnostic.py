"""Tests for app/api/diagnostic.py module."""

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
