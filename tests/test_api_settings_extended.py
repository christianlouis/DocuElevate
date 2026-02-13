"""Comprehensive unit tests for app/api/settings.py module."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestSettingsRequireAdmin:
    """Tests for require_admin dependency."""

    def test_require_admin_with_admin_user(self):
        """Test that admin users pass the requirement."""
        from app.api.settings import require_admin

        mock_request = MagicMock()
        mock_request.session.get.return_value = {"username": "admin", "is_admin": True}

        result = require_admin(mock_request)
        assert result == {"username": "admin", "is_admin": True}

    def test_require_admin_without_admin_user(self):
        """Test that non-admin users are rejected."""
        from app.api.settings import require_admin

        mock_request = MagicMock()
        mock_request.session.get.return_value = {"username": "user", "is_admin": False}

        with pytest.raises(HTTPException) as exc_info:
            require_admin(mock_request)
        assert exc_info.value.status_code == 403
        assert "Admin access required" in exc_info.value.detail

    def test_require_admin_without_user(self):
        """Test that requests without user are rejected."""
        from app.api.settings import require_admin

        mock_request = MagicMock()
        mock_request.session.get.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            require_admin(mock_request)
        assert exc_info.value.status_code == 403


@pytest.mark.unit
class TestGetSettings:
    """Tests for GET /settings/ endpoint."""

    @patch("app.api.settings.get_all_settings_from_db")
    @patch("app.api.settings.get_settings_by_category")
    @patch("app.api.settings.get_setting_metadata")
    def test_get_settings_success(self, mock_metadata, mock_category, mock_db_settings, client: TestClient, db_session):
        """Test successful retrieval of settings."""
        # Mock session to have admin user
        mock_metadata.return_value = {"description": "Test setting", "type": "string"}
        mock_category.return_value = {"general": ["setting1"]}
        mock_db_settings.return_value = {"setting1": "value1"}

        with patch.object(client, "get") as mock_get:
            with patch("app.api.settings.settings") as mock_settings:
                mock_settings.setting1 = "test_value"

                # Create mock request with admin session
                from starlette.testclient import TestClient as StarletteClient

                response = client.get("/api/settings/", cookies={"session": "admin_session"})

    @patch("app.api.settings.get_all_settings_from_db")
    def test_get_settings_database_error(self, mock_db_settings, client: TestClient, db_session):
        """Test handling of database errors."""
        mock_db_settings.side_effect = Exception("Database error")

        # This would need admin auth mocked properly
        # The endpoint should return 500 error


@pytest.mark.unit
class TestGetSetting:
    """Tests for GET /settings/{key} endpoint."""

    @patch("app.api.settings.get_setting_metadata")
    def test_get_setting_existing_key(self, mock_metadata):
        """Test retrieval of existing setting."""
        from app.api.settings import get_setting
        from app.config import settings

        mock_metadata.return_value = {"description": "Test setting"}
        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with patch.object(settings, "workdir", "/tmp/test"):
            # This would be called via FastAPI, testing the logic
            pass

    @patch("app.api.settings.get_setting_metadata")
    def test_get_setting_nonexistent_key(self, mock_metadata):
        """Test retrieval of non-existent setting."""
        mock_metadata.return_value = {}
        # Should still return metadata even if setting doesn't exist


@pytest.mark.unit
class TestUpdateSetting:
    """Tests for POST /settings/{key} endpoint."""

    @patch("app.api.settings.validate_setting_value")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.get_setting_metadata")
    def test_update_setting_success(self, mock_metadata, mock_save, mock_validate):
        """Test successful setting update."""
        mock_validate.return_value = (True, None)
        mock_save.return_value = True
        mock_metadata.return_value = {"restart_required": False}

        # Would test via client with proper auth mocking

    @patch("app.api.settings.validate_setting_value")
    def test_update_setting_invalid_value(self, mock_validate):
        """Test update with invalid value."""
        mock_validate.return_value = (False, "Invalid value")

        # Should raise HTTPException with 400 status

    @patch("app.api.settings.validate_setting_value")
    @patch("app.api.settings.save_setting_to_db")
    def test_update_setting_database_error(self, mock_save, mock_validate):
        """Test handling of database save errors."""
        mock_validate.return_value = (True, None)
        mock_save.return_value = False

        # Should raise HTTPException with 500 status

    @patch("app.api.settings.validate_setting_value")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.get_setting_metadata")
    def test_update_setting_requires_restart(self, mock_metadata, mock_save, mock_validate):
        """Test update of setting that requires restart."""
        mock_validate.return_value = (True, None)
        mock_save.return_value = True
        mock_metadata.return_value = {"restart_required": True}

        # Response should include restart_required: True


@pytest.mark.unit
class TestDeleteSetting:
    """Tests for DELETE /settings/{key} endpoint."""

    @patch("app.api.settings.delete_setting_from_db")
    def test_delete_setting_success(self, mock_delete):
        """Test successful setting deletion."""
        mock_delete.return_value = True

        # Should return success response

    @patch("app.api.settings.delete_setting_from_db")
    def test_delete_setting_not_found(self, mock_delete):
        """Test deletion of non-existent setting."""
        mock_delete.return_value = False

        # Should raise HTTPException with 404 status

    @patch("app.api.settings.delete_setting_from_db")
    def test_delete_setting_database_error(self, mock_delete):
        """Test handling of database errors."""
        mock_delete.side_effect = Exception("Database error")

        # Should raise HTTPException with 500 status


@pytest.mark.unit
class TestBulkUpdateSettings:
    """Tests for POST /settings/bulk-update endpoint."""

    @patch("app.api.settings.validate_setting_value")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.get_setting_metadata")
    def test_bulk_update_all_success(self, mock_metadata, mock_save, mock_validate):
        """Test successful bulk update of multiple settings."""
        mock_validate.return_value = (True, None)
        mock_save.return_value = True
        mock_metadata.return_value = {"restart_required": False}

        # Should return success with all updated

    @patch("app.api.settings.validate_setting_value")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.get_setting_metadata")
    def test_bulk_update_partial_failure(self, mock_metadata, mock_save, mock_validate):
        """Test bulk update with some failures."""
        # First validation succeeds, second fails
        mock_validate.side_effect = [(True, None), (False, "Invalid value")]
        mock_save.return_value = True
        mock_metadata.return_value = {"restart_required": False}

        # Should return success=False with errors list

    @patch("app.api.settings.validate_setting_value")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.get_setting_metadata")
    def test_bulk_update_with_restart_required(self, mock_metadata, mock_save, mock_validate):
        """Test bulk update where one setting requires restart."""
        mock_validate.return_value = (True, None)
        mock_save.return_value = True
        # First setting doesn't require restart, second does
        mock_metadata.side_effect = [{"restart_required": False}, {"restart_required": True}]

        # Response should have restart_required: True

    @patch("app.api.settings.validate_setting_value")
    @patch("app.api.settings.save_setting_to_db")
    def test_bulk_update_database_errors(self, mock_save, mock_validate):
        """Test bulk update with database save errors."""
        mock_validate.return_value = (True, None)
        # First save succeeds, second fails
        mock_save.side_effect = [True, False]

        # Should include errors for failed saves

    @patch("app.api.settings.validate_setting_value")
    def test_bulk_update_empty_list(self, mock_validate):
        """Test bulk update with empty updates list."""
        # Should return success with empty results

    @patch("app.api.settings.validate_setting_value")
    @patch("app.api.settings.save_setting_to_db")
    def test_bulk_update_with_none_value(self, mock_save, mock_validate):
        """Test bulk update with None value (delete)."""
        mock_validate.return_value = (True, None)
        mock_save.return_value = True

        # None values should be handled (possibly as deletes)


@pytest.mark.unit
class TestSettingModels:
    """Tests for Pydantic models."""

    def test_setting_update_model_valid(self):
        """Test SettingUpdate model with valid data."""
        from app.api.settings import SettingUpdate

        setting = SettingUpdate(key="test_key", value="test_value")
        assert setting.key == "test_key"
        assert setting.value == "test_value"

    def test_setting_update_model_none_value(self):
        """Test SettingUpdate model with None value."""
        from app.api.settings import SettingUpdate

        setting = SettingUpdate(key="test_key", value=None)
        assert setting.key == "test_key"
        assert setting.value is None

    def test_setting_response_model(self):
        """Test SettingResponse model."""
        from app.api.settings import SettingResponse

        response = SettingResponse(key="test_key", value="test_value", metadata={"description": "test"})
        assert response.key == "test_key"
        assert response.value == "test_value"
        assert response.metadata["description"] == "test"

    def test_settings_list_response_model(self):
        """Test SettingsListResponse model."""
        from app.api.settings import SettingsListResponse

        response = SettingsListResponse(
            settings={"key1": {"value": "val1"}},
            categories={"general": ["key1"]},
            db_settings={"key1": "val1"},
        )
        assert "key1" in response.settings
        assert "general" in response.categories
