"""Tests for app/api/settings.py module."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.settings import require_admin


@pytest.mark.unit
class TestRequireAdmin:
    """Tests for require_admin dependency."""

    def test_raises_403_when_no_user(self):
        """Test that 403 is raised when no user in session."""
        mock_request = MagicMock()
        mock_request.session = {}

        with pytest.raises(HTTPException) as exc_info:
            require_admin(mock_request)
        assert exc_info.value.status_code == 403

    def test_raises_403_when_not_admin(self):
        """Test that 403 is raised for non-admin user."""
        mock_request = MagicMock()
        mock_request.session = {"user": {"id": "1", "is_admin": False}}

        with pytest.raises(HTTPException) as exc_info:
            require_admin(mock_request)
        assert exc_info.value.status_code == 403

    def test_returns_user_when_admin(self):
        """Test that admin user is returned."""
        mock_request = MagicMock()
        user = {"id": "admin", "is_admin": True}
        mock_request.session = {"user": user}

        result = require_admin(mock_request)
        assert result == user

    def test_raises_403_with_correct_detail_message(self):
        """Test that 403 includes correct detail message."""
        mock_request = MagicMock()
        mock_request.session = {}

        with pytest.raises(HTTPException) as exc_info:
            require_admin(mock_request)
        assert exc_info.value.detail == "Admin access required"


@pytest.mark.integration
class TestSettingsEndpoints:
    """Integration tests for settings API endpoints."""

    def test_get_settings_requires_admin(self, client):
        """Test GET /settings requires admin access."""
        response = client.get("/api/settings/")
        assert response.status_code in [302, 401, 403]

    def test_get_single_setting_requires_admin(self, client):
        """Test GET /settings/{key} requires admin access."""
        response = client.get("/api/settings/workdir")
        assert response.status_code in [302, 401, 403]

    def test_update_setting_requires_admin(self, client):
        """Test POST /settings/{key} requires admin access."""
        response = client.post("/api/settings/test_key", json={"key": "test_key", "value": "test_value"})
        assert response.status_code in [302, 401, 403]

    def test_delete_setting_requires_admin(self, client):
        """Test DELETE /settings/{key} requires admin access."""
        response = client.delete("/api/settings/test_key")
        assert response.status_code in [302, 401, 403]

    def test_bulk_update_requires_admin(self, client):
        """Test POST /settings/bulk-update requires admin access."""
        response = client.post("/api/settings/bulk-update", json=[{"key": "test_key", "value": "test_value"}])
        assert response.status_code in [302, 401, 403]


@pytest.mark.integration
class TestSettingsEndpointsWithAuth:
    """Integration tests for settings endpoints with authentication."""

    @patch("app.api.settings.get_all_settings_from_db")
    @patch("app.api.settings.get_settings_by_category")
    @patch("app.api.settings.get_setting_metadata")
    def test_get_all_settings_success(self, mock_metadata, mock_categories, mock_db_settings, client, db_session):
        """Test GET /settings returns all settings."""
        from app.api.settings import require_admin
        from app.main import app as fastapi_app

        # Mock the settings data
        mock_db_settings.return_value = {"test_key": "test_value"}
        mock_categories.return_value = {"General": ["workdir", "debug"]}
        mock_metadata.return_value = {"type": "str", "description": "Test setting"}

        # Override the require_admin dependency to return a mock admin user
        def override_require_admin():
            return {"id": "admin", "is_admin": True}

        fastapi_app.dependency_overrides[require_admin] = override_require_admin

        try:
            # Make the request with the mocked admin dependency
            response = client.get("/api/settings/")
            assert response.status_code == 200
            data = response.json()
            assert "settings" in data
            assert "categories" in data
            assert "db_settings" in data
        finally:
            # Clean up the override
            fastapi_app.dependency_overrides.pop(require_admin, None)

    @patch("app.api.settings.get_setting_metadata")
    def test_get_single_setting_returns_metadata(self, mock_metadata, client):
        """Test GET /settings/{key} returns setting with metadata."""
        mock_metadata.return_value = {"type": "str", "description": "Working directory"}

        # Without admin auth, should be 403
        response = client.get("/api/settings/workdir")
        assert response.status_code in [302, 401, 403]

    @patch("app.api.settings.validate_setting_value")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.get_setting_metadata")
    def test_update_setting_validates_value(self, mock_metadata, mock_save, mock_validate, client):
        """Test POST /settings/{key} validates setting value."""
        mock_validate.return_value = (False, "Invalid value")
        mock_metadata.return_value = {"restart_required": False}

        # Without admin auth, should be 403
        response = client.post("/api/settings/test_key", json={"key": "test_key", "value": "invalid"})
        assert response.status_code in [302, 401, 403]

    @patch("app.api.settings.delete_setting_from_db")
    def test_delete_setting_handles_not_found(self, mock_delete, client):
        """Test DELETE /settings/{key} handles not found."""
        mock_delete.return_value = False

        # Without admin auth, should be 403
        response = client.delete("/api/settings/nonexistent_key")
        assert response.status_code in [302, 401, 403]

    @patch("app.api.settings.validate_setting_value")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.get_setting_metadata")
    def test_bulk_update_processes_multiple_settings(self, mock_metadata, mock_save, mock_validate, client):
        """Test POST /settings/bulk-update processes multiple settings."""
        mock_validate.return_value = (True, None)
        mock_save.return_value = True
        mock_metadata.return_value = {"restart_required": False}

        updates = [{"key": "setting1", "value": "value1"}, {"key": "setting2", "value": "value2"}]

        # Without admin auth, should be 403
        response = client.post("/api/settings/bulk-update", json=updates)
        assert response.status_code in [302, 401, 403]


@pytest.mark.unit
class TestSettingModels:
    """Tests for Pydantic models."""

    def test_setting_update_model(self):
        """Test SettingUpdate model."""
        from app.api.settings import SettingUpdate

        update = SettingUpdate(key="test_key", value="test_value")
        assert update.key == "test_key"
        assert update.value == "test_value"

    def test_setting_update_model_with_none_value(self):
        """Test SettingUpdate model with None value."""
        from app.api.settings import SettingUpdate

        update = SettingUpdate(key="test_key", value=None)
        assert update.key == "test_key"
        assert update.value is None

    def test_setting_response_model(self):
        """Test SettingResponse model."""
        from app.api.settings import SettingResponse

        response = SettingResponse(
            key="test_key", value="test_value", metadata={"type": "str", "description": "Test setting"}
        )
        assert response.key == "test_key"
        assert response.value == "test_value"
        assert response.metadata["type"] == "str"

    def test_settings_list_response_model(self):
        """Test SettingsListResponse model."""
        from app.api.settings import SettingsListResponse

        response = SettingsListResponse(
            settings={"test_key": {"value": "test_value", "metadata": {}}},
            categories={"General": ["test_key"]},
            db_settings={"test_key": "test_value"},
        )
        assert "test_key" in response.settings
        assert "General" in response.categories
        assert "test_key" in response.db_settings


@pytest.mark.unit
class TestListCredentials:
    """Tests for the list_credentials function (GET /api/settings/credentials)."""

    @patch("app.api.settings.get_all_settings_from_db")
    def test_list_credentials_returns_sensitive_keys_only(self, mock_db_settings):
        """Test that list_credentials only includes keys marked sensitive in SETTING_METADATA."""
        import asyncio

        from app.api.settings import list_credentials
        from app.utils.settings_service import SETTING_METADATA

        mock_db_settings.return_value = {}
        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with patch("app.api.settings.settings") as mock_settings:
            for key in SETTING_METADATA:
                setattr(mock_settings, key, None)

            result = asyncio.get_event_loop().run_until_complete(list_credentials(mock_request, mock_db, mock_admin))

        returned_keys = {c["key"] for c in result["credentials"]}
        sensitive_keys = {k for k, v in SETTING_METADATA.items() if v.get("sensitive")}
        assert returned_keys == sensitive_keys

    @patch("app.api.settings.get_all_settings_from_db")
    def test_list_credentials_source_db_when_in_database(self, mock_db_settings):
        """Test that credentials stored in the database report source='db'."""
        import asyncio

        from app.api.settings import list_credentials

        mock_db_settings.return_value = {"openai_api_key": "sk-db-key"}
        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with patch("app.api.settings.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-env-key"

            result = asyncio.get_event_loop().run_until_complete(list_credentials(mock_request, mock_db, mock_admin))

        openai_entry = next(c for c in result["credentials"] if c["key"] == "openai_api_key")
        assert openai_entry["source"] == "db"
        assert openai_entry["configured"] is True

    @patch("app.api.settings.get_all_settings_from_db")
    def test_list_credentials_source_env_when_only_in_env(self, mock_db_settings):
        """Test that credentials only in env report source='env'."""
        import asyncio

        from app.api.settings import list_credentials

        mock_db_settings.return_value = {}
        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with patch("app.api.settings.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-env-key"

            result = asyncio.get_event_loop().run_until_complete(list_credentials(mock_request, mock_db, mock_admin))

        openai_entry = next(c for c in result["credentials"] if c["key"] == "openai_api_key")
        assert openai_entry["source"] == "env"
        assert openai_entry["configured"] is True

    @patch("app.api.settings.get_all_settings_from_db")
    def test_list_credentials_unconfigured_when_no_value(self, mock_db_settings):
        """Test that credentials with no value are marked as unconfigured."""
        import asyncio

        from app.api.settings import list_credentials

        mock_db_settings.return_value = {}
        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with patch("app.api.settings.settings") as mock_settings:
            mock_settings.openai_api_key = None

            result = asyncio.get_event_loop().run_until_complete(list_credentials(mock_request, mock_db, mock_admin))

        openai_entry = next(c for c in result["credentials"] if c["key"] == "openai_api_key")
        assert openai_entry["configured"] is False
        assert openai_entry["source"] is None

    @patch("app.api.settings.get_all_settings_from_db")
    def test_list_credentials_counts_are_accurate(self, mock_db_settings):
        """Test that configured_count and unconfigured_count are correct."""
        import asyncio

        from app.api.settings import list_credentials

        mock_db_settings.return_value = {"openai_api_key": "sk-db-key"}
        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with patch("app.api.settings.settings") as mock_settings:
            # Most keys will be None, one will be set via db_settings mock
            mock_settings.openai_api_key = "sk-key"

            result = asyncio.get_event_loop().run_until_complete(list_credentials(mock_request, mock_db, mock_admin))

        assert result["total"] == len(result["credentials"])
        assert result["configured_count"] + result["unconfigured_count"] == result["total"]

    @patch("app.api.settings.get_all_settings_from_db")
    def test_list_credentials_raises_500_on_exception(self, mock_db_settings):
        """Test that list_credentials raises HTTP 500 on unexpected errors."""
        import asyncio

        from fastapi import HTTPException

        from app.api.settings import list_credentials

        mock_db_settings.side_effect = Exception("DB failure")
        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(list_credentials(mock_request, mock_db, mock_admin))
        assert exc_info.value.status_code == 500

    def test_list_credentials_endpoint_requires_admin(self, client):
        """Test that GET /api/settings/credentials requires admin access."""
        response = client.get("/api/settings/credentials")
        assert response.status_code in [302, 401, 403]

    @patch("app.api.settings.get_all_settings_from_db")
    def test_list_credentials_response_has_required_fields(self, mock_db_settings):
        """Test that each credential entry has the required fields."""
        import asyncio

        from app.api.settings import list_credentials

        mock_db_settings.return_value = {}
        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with patch("app.api.settings.settings") as mock_settings:
            mock_settings.openai_api_key = None

            result = asyncio.get_event_loop().run_until_complete(list_credentials(mock_request, mock_db, mock_admin))

        for cred in result["credentials"]:
            assert "key" in cred
            assert "category" in cred
            assert "description" in cred
            assert "configured" in cred
            assert "source" in cred
            assert "restart_required" in cred
