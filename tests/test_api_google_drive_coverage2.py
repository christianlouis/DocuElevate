"""
Coverage-targeted tests for app/api/google_drive.py

Focuses on uncovered lines: 125-127, 214-255, 339-341.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestUpdateSettingsExceptionHandler:
    """Cover lines 125-127: update_google_drive_settings outer exception."""

    def test_update_settings_outer_exception(self, client: TestClient):
        """Trigger the outer exception handler in update_google_drive_settings."""
        with patch("app.api.google_drive.save_setting_to_db", side_effect=Exception("DB crash")):
            response = client.post(
                "/api/google-drive/update-settings",
                data={
                    "refresh_token": "test_token",
                },
            )
        assert response.status_code == 500
        assert "Failed to update Google Drive settings" in response.json()["detail"]


@pytest.mark.unit
class TestTestTokenServiceAccount:
    """Cover lines 214-255: service account test-token paths."""

    @patch("app.tasks.upload_to_google_drive.get_google_drive_service")
    def test_test_token_service_account_success_no_delegation(self, mock_get_service, client: TestClient):
        """Test successful service account connection without delegation."""
        from app.config import settings

        mock_service = MagicMock()
        mock_service.about().get().execute.return_value = {
            "user": {"emailAddress": "sa@project.iam.gserviceaccount.com"}
        }
        mock_get_service.return_value = mock_service

        with (
            patch.object(settings, "google_drive_use_oauth", False),
            patch.object(settings, "google_drive_credentials_json", '{"type": "service_account"}'),
            patch.object(settings, "google_drive_delegate_to", None),
        ):
            response = client.get("/api/google-drive/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["auth_type"] == "service_account"
        assert "sa@project.iam.gserviceaccount.com" in data["message"]

    @patch("app.tasks.upload_to_google_drive.get_google_drive_service")
    def test_test_token_service_account_with_delegation(self, mock_get_service, client: TestClient):
        """Test service account with delegation shows delegated user info."""
        from app.config import settings

        mock_service = MagicMock()
        mock_service.about().get().execute.return_value = {
            "user": {"emailAddress": "sa@project.iam.gserviceaccount.com"}
        }
        mock_get_service.return_value = mock_service

        with (
            patch.object(settings, "google_drive_use_oauth", False),
            patch.object(settings, "google_drive_credentials_json", '{"type": "service_account"}'),
            patch.object(settings, "google_drive_delegate_to", "user@domain.com"),
        ):
            response = client.get("/api/google-drive/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "delegating as user@domain.com" in data["message"]

    def test_test_token_service_account_not_configured(self, client: TestClient):
        """Test service account not configured returns error."""
        from app.config import settings

        with (
            patch.object(settings, "google_drive_use_oauth", False),
            patch.object(settings, "google_drive_credentials_json", ""),
        ):
            response = client.get("/api/google-drive/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not configured" in data["message"]

    @patch("app.tasks.upload_to_google_drive.get_google_drive_service")
    def test_test_token_service_account_connection_error(self, mock_get_service, client: TestClient):
        """Test service account connection error (lines 245-251)."""
        from app.config import settings

        mock_get_service.side_effect = Exception("Service account credentials invalid")

        with (
            patch.object(settings, "google_drive_use_oauth", False),
            patch.object(settings, "google_drive_credentials_json", '{"type": "service_account"}'),
        ):
            response = client.get("/api/google-drive/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "Service account validation failed" in data["message"]


@pytest.mark.unit
class TestGetTokenInfoOuterException:
    """Cover lines 339-341: get_google_drive_token_info outer exception."""

    def test_get_token_info_outer_exception(self, client: TestClient):
        """Trigger the outer exception handler in get_google_drive_token_info."""
        with patch("app.api.google_drive.getattr", side_effect=Exception("boom")):
            response = client.get("/api/google-drive/get-token-info")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "Unexpected error" in data["message"]


@pytest.mark.unit
class TestTestTokenOuterException:
    """Cover lines 253-255: test_google_drive_token outer exception handler."""

    def test_test_token_outer_exception(self, client: TestClient):
        """Trigger the outermost exception handler in test_google_drive_token."""

        # Patch getattr on settings to raise on the first call within the try block
        with patch("app.api.google_drive.getattr", side_effect=Exception("unexpected error")):
            response = client.get("/api/google-drive/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "Unexpected error" in data["message"]
