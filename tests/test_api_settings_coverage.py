"""Comprehensive tests for app/api/settings.py to improve coverage."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


@pytest.mark.unit
class TestRequireAdminDependency:
    """Tests for require_admin dependency function."""

    def test_returns_user_for_valid_admin(self):
        """Test returns user dict when user is admin."""
        from app.api.settings import require_admin

        mock_request = MagicMock()
        user = {"id": "admin1", "is_admin": True, "name": "Admin"}
        mock_request.session.get.return_value = user

        result = require_admin(mock_request)
        assert result == user

    def test_raises_403_for_non_admin(self):
        """Test raises 403 for non-admin user."""
        from app.api.settings import require_admin

        mock_request = MagicMock()
        mock_request.session.get.return_value = {"id": "user1", "is_admin": False}

        with pytest.raises(HTTPException) as exc_info:
            require_admin(mock_request)
        assert exc_info.value.status_code == 403

    def test_raises_403_for_no_user(self):
        """Test raises 403 when no user in session."""
        from app.api.settings import require_admin

        mock_request = MagicMock()
        mock_request.session.get.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            require_admin(mock_request)
        assert exc_info.value.status_code == 403

    def test_raises_403_for_empty_session(self):
        """Test raises 403 when session is empty dict."""
        from app.api.settings import require_admin

        mock_request = MagicMock()
        mock_request.session = {}

        with pytest.raises(HTTPException) as exc_info:
            require_admin(mock_request)
        assert exc_info.value.status_code == 403


@pytest.mark.unit
class TestGetSettingsEndpoint:
    """Tests for GET /settings/ endpoint."""

    @pytest.mark.asyncio
    @patch("app.api.settings.get_all_settings_from_db")
    @patch("app.api.settings.get_settings_by_category")
    @patch("app.api.settings.get_setting_metadata")
    @patch("app.api.settings.SETTING_METADATA", {"workdir": {}, "debug": {}})
    @patch("app.api.settings.settings")
    async def test_get_settings_success(self, mock_settings, mock_metadata, mock_categories, mock_db):
        """Test successful settings retrieval."""
        from app.api.settings import get_settings

        mock_settings.workdir = "/tmp"
        mock_settings.debug = True
        mock_metadata.return_value = {"description": "Test", "type": "string"}
        mock_categories.return_value = {"general": ["workdir", "debug"]}
        mock_db.return_value = {"workdir": "/data"}

        mock_request = MagicMock()
        mock_db_session = MagicMock()
        mock_admin = {"id": "admin", "is_admin": True}

        result = await get_settings(mock_request, mock_db_session, mock_admin)
        assert "general" in result.categories
        assert result.db_settings == {"workdir": "/data"}

    @pytest.mark.asyncio
    @patch("app.api.settings.get_all_settings_from_db")
    @patch("app.api.settings.SETTING_METADATA", {"workdir": {}})
    @patch("app.api.settings.settings")
    async def test_get_settings_exception(self, mock_settings, mock_db):
        """Test get_settings raises HTTPException on error."""
        from app.api.settings import get_settings

        mock_db.side_effect = Exception("DB Error")
        mock_request = MagicMock()
        mock_db_session = MagicMock()
        mock_admin = {"id": "admin", "is_admin": True}

        with pytest.raises(HTTPException) as exc_info:
            await get_settings(mock_request, mock_db_session, mock_admin)
        assert exc_info.value.status_code == 500


@pytest.mark.unit
class TestGetSettingEndpoint:
    """Tests for GET /settings/{key} endpoint."""

    @pytest.mark.asyncio
    @patch("app.api.settings.get_setting_metadata")
    @patch("app.api.settings.settings")
    async def test_get_existing_setting(self, mock_settings, mock_metadata):
        """Test retrieving an existing setting."""
        from app.api.settings import get_setting

        mock_settings.workdir = "/tmp/test"
        mock_metadata.return_value = {"description": "Work directory", "type": "string"}

        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"id": "admin", "is_admin": True}

        result = await get_setting("workdir", mock_request, mock_db, mock_admin)
        assert result.key == "workdir"
        assert result.value == "/tmp/test"

    @pytest.mark.asyncio
    @patch("app.api.settings.get_setting_metadata")
    @patch("app.api.settings.settings")
    async def test_get_nonexistent_setting(self, mock_settings, mock_metadata):
        """Test retrieving a setting that doesn't exist returns None value."""
        from app.api.settings import get_setting

        # settings doesn't have this attribute
        mock_metadata.return_value = {"description": "Unknown setting"}
        del mock_settings.nonexistent_key  # Ensure getattr returns None

        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"id": "admin", "is_admin": True}

        result = await get_setting("nonexistent_key", mock_request, mock_db, mock_admin)
        assert result.key == "nonexistent_key"
        assert result.value is None

    @pytest.mark.asyncio
    @patch("app.api.settings.get_setting_metadata")
    async def test_get_setting_exception(self, mock_metadata):
        """Test get_setting raises HTTPException on error."""
        from app.api.settings import get_setting

        mock_metadata.side_effect = Exception("Error")

        with pytest.raises(HTTPException) as exc_info:
            await get_setting("key", MagicMock(), MagicMock(), MagicMock())
        assert exc_info.value.status_code == 500


@pytest.mark.unit
class TestUpdateSettingEndpoint:
    """Tests for POST /settings/{key} endpoint."""

    @pytest.mark.asyncio
    @patch("app.api.settings.get_setting_metadata")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.validate_setting_value")
    async def test_update_setting_success(self, mock_validate, mock_save, mock_metadata):
        """Test successful setting update."""
        from app.api.settings import SettingUpdate, update_setting

        mock_validate.return_value = (True, None)
        mock_save.return_value = True
        mock_metadata.return_value = {"restart_required": False}

        setting = SettingUpdate(key="workdir", value="/new/path")
        result = await update_setting("workdir", setting, MagicMock(), MagicMock(), MagicMock())
        assert result["success"] is True
        assert result["restart_required"] is False

    @pytest.mark.asyncio
    @patch("app.api.settings.validate_setting_value")
    async def test_update_setting_invalid_value(self, mock_validate):
        """Test update with invalid value raises 400."""
        from app.api.settings import SettingUpdate, update_setting

        mock_validate.return_value = (False, "Value must be a positive integer")

        setting = SettingUpdate(key="some_key", value="-1")
        with pytest.raises(HTTPException) as exc_info:
            await update_setting("some_key", setting, MagicMock(), MagicMock(), MagicMock())
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.validate_setting_value")
    async def test_update_setting_save_failure(self, mock_validate, mock_save):
        """Test update when save fails raises 500."""
        from app.api.settings import SettingUpdate, update_setting

        mock_validate.return_value = (True, None)
        mock_save.return_value = False

        setting = SettingUpdate(key="key", value="value")
        with pytest.raises(HTTPException) as exc_info:
            await update_setting("key", setting, MagicMock(), MagicMock(), MagicMock())
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    @patch("app.api.settings.get_setting_metadata")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.validate_setting_value")
    async def test_update_setting_requires_restart(self, mock_validate, mock_save, mock_metadata):
        """Test update of setting that requires restart."""
        from app.api.settings import SettingUpdate, update_setting

        mock_validate.return_value = (True, None)
        mock_save.return_value = True
        mock_metadata.return_value = {"restart_required": True}

        setting = SettingUpdate(key="key", value="value")
        result = await update_setting("key", setting, MagicMock(), MagicMock(), MagicMock())
        assert result["restart_required"] is True

    @pytest.mark.asyncio
    @patch("app.api.settings.get_setting_metadata")
    @patch("app.api.settings.save_setting_to_db")
    async def test_update_setting_with_none_value(self, mock_save, mock_metadata):
        """Test update with None value (skip validation)."""
        from app.api.settings import SettingUpdate, update_setting

        mock_save.return_value = True
        mock_metadata.return_value = {"restart_required": False}

        setting = SettingUpdate(key="key", value=None)
        result = await update_setting("key", setting, MagicMock(), MagicMock(), MagicMock())
        assert result["success"] is True

    @pytest.mark.asyncio
    @patch("app.api.settings.validate_setting_value")
    async def test_update_setting_unexpected_exception(self, mock_validate):
        """Test update with unexpected exception raises 500."""
        from app.api.settings import SettingUpdate, update_setting

        mock_validate.side_effect = RuntimeError("Unexpected")

        setting = SettingUpdate(key="key", value="value")
        with pytest.raises(HTTPException) as exc_info:
            await update_setting("key", setting, MagicMock(), MagicMock(), MagicMock())
        assert exc_info.value.status_code == 500


@pytest.mark.unit
class TestDeleteSettingEndpoint:
    """Tests for DELETE /settings/{key} endpoint."""

    @pytest.mark.asyncio
    @patch("app.api.settings.delete_setting_from_db")
    async def test_delete_setting_success(self, mock_delete):
        """Test successful setting deletion."""
        from app.api.settings import delete_setting

        mock_delete.return_value = True
        result = await delete_setting("key", MagicMock(), MagicMock(), MagicMock())
        assert result["success"] is True

    @pytest.mark.asyncio
    @patch("app.api.settings.delete_setting_from_db")
    async def test_delete_setting_not_found(self, mock_delete):
        """Test deletion of non-existent setting raises 404."""
        from app.api.settings import delete_setting

        mock_delete.return_value = False
        with pytest.raises(HTTPException) as exc_info:
            await delete_setting("nonexistent", MagicMock(), MagicMock(), MagicMock())
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.api.settings.delete_setting_from_db")
    async def test_delete_setting_exception(self, mock_delete):
        """Test deletion with exception raises 500."""
        from app.api.settings import delete_setting

        mock_delete.side_effect = Exception("DB Error")
        with pytest.raises(HTTPException) as exc_info:
            await delete_setting("key", MagicMock(), MagicMock(), MagicMock())
        assert exc_info.value.status_code == 500


@pytest.mark.unit
class TestBulkUpdateSettingsEndpoint:
    """Tests for POST /settings/bulk-update endpoint."""

    @pytest.mark.asyncio
    @patch("app.api.settings.get_setting_metadata")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.validate_setting_value")
    async def test_bulk_update_all_success(self, mock_validate, mock_save, mock_metadata):
        """Test successful bulk update."""
        from app.api.settings import SettingUpdate, bulk_update_settings

        mock_validate.return_value = (True, None)
        mock_save.return_value = True
        mock_metadata.return_value = {"restart_required": False}

        updates = [
            SettingUpdate(key="key1", value="val1"),
            SettingUpdate(key="key2", value="val2"),
        ]
        result = await bulk_update_settings(updates, MagicMock(), MagicMock(), MagicMock())
        assert result["success"] is True
        assert len(result["updated"]) == 2
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    @patch("app.api.settings.get_setting_metadata")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.validate_setting_value")
    async def test_bulk_update_partial_failure(self, mock_validate, mock_save, mock_metadata):
        """Test bulk update with validation failure."""
        from app.api.settings import SettingUpdate, bulk_update_settings

        mock_validate.side_effect = [(True, None), (False, "Invalid value")]
        mock_save.return_value = True
        mock_metadata.return_value = {"restart_required": False}

        updates = [
            SettingUpdate(key="key1", value="val1"),
            SettingUpdate(key="key2", value="bad"),
        ]
        result = await bulk_update_settings(updates, MagicMock(), MagicMock(), MagicMock())
        assert result["success"] is False
        assert len(result["updated"]) == 1
        assert len(result["errors"]) == 1

    @pytest.mark.asyncio
    @patch("app.api.settings.get_setting_metadata")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.validate_setting_value")
    async def test_bulk_update_save_failure(self, mock_validate, mock_save, mock_metadata):
        """Test bulk update with save failure."""
        from app.api.settings import SettingUpdate, bulk_update_settings

        mock_validate.return_value = (True, None)
        mock_save.side_effect = [True, False]
        mock_metadata.return_value = {"restart_required": False}

        updates = [
            SettingUpdate(key="key1", value="val1"),
            SettingUpdate(key="key2", value="val2"),
        ]
        result = await bulk_update_settings(updates, MagicMock(), MagicMock(), MagicMock())
        assert len(result["errors"]) == 1

    @pytest.mark.asyncio
    @patch("app.api.settings.get_setting_metadata")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.validate_setting_value")
    async def test_bulk_update_with_restart_required(self, mock_validate, mock_save, mock_metadata):
        """Test bulk update where setting requires restart."""
        from app.api.settings import SettingUpdate, bulk_update_settings

        mock_validate.return_value = (True, None)
        mock_save.return_value = True
        mock_metadata.return_value = {"restart_required": True}

        updates = [SettingUpdate(key="key1", value="val1")]
        result = await bulk_update_settings(updates, MagicMock(), MagicMock(), MagicMock())
        assert result["restart_required"] is True

    @pytest.mark.asyncio
    @patch("app.api.settings.get_setting_metadata")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.validate_setting_value")
    async def test_bulk_update_empty_list(self, mock_validate, mock_save, mock_metadata):
        """Test bulk update with empty list."""
        from app.api.settings import bulk_update_settings

        result = await bulk_update_settings([], MagicMock(), MagicMock(), MagicMock())
        assert result["success"] is True
        assert len(result["updated"]) == 0
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    @patch("app.api.settings.get_setting_metadata")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.validate_setting_value")
    async def test_bulk_update_with_none_value(self, mock_validate, mock_save, mock_metadata):
        """Test bulk update with None value skips validation."""
        from app.api.settings import SettingUpdate, bulk_update_settings

        mock_save.return_value = True
        mock_metadata.return_value = {"restart_required": False}

        updates = [SettingUpdate(key="key1", value=None)]
        result = await bulk_update_settings(updates, MagicMock(), MagicMock(), MagicMock())
        assert result["success"] is True
        mock_validate.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.api.settings.get_setting_metadata")
    @patch("app.api.settings.save_setting_to_db")
    @patch("app.api.settings.validate_setting_value")
    async def test_bulk_update_exception_in_loop(self, mock_validate, mock_save, mock_metadata):
        """Test bulk update handles exception in individual update."""
        from app.api.settings import SettingUpdate, bulk_update_settings

        mock_validate.return_value = (True, None)
        mock_save.side_effect = [True, Exception("DB Error")]
        mock_metadata.return_value = {"restart_required": False}

        updates = [
            SettingUpdate(key="key1", value="val1"),
            SettingUpdate(key="key2", value="val2"),
        ]
        result = await bulk_update_settings(updates, MagicMock(), MagicMock(), MagicMock())
        assert len(result["updated"]) == 1
        assert len(result["errors"]) == 1
