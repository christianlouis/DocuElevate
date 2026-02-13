"""
Tests for improving coverage on config_validator, settings API, license routes,
diagnostic API, and OpenAI API endpoints.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.api.settings import require_admin
from app.main import app as fastapi_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _override_admin():
    """Dependency override that simulates an admin user."""
    return {"is_admin": True, "name": "admin"}


# ---------------------------------------------------------------------------
# 1. app/utils/config_validator.py (backward-compatible re-export wrapper)
# ---------------------------------------------------------------------------

class TestConfigValidatorReExports:
    """Verify the backward-compatible wrapper re-exports all expected symbols."""

    @pytest.mark.unit
    def test_imports_from_wrapper(self):
        """All public names are importable from the wrapper module."""
        from app.utils import config_validator as cv

        assert callable(cv.mask_sensitive_value)
        assert callable(cv.get_provider_status)
        assert callable(cv.dump_all_settings)
        assert callable(cv.get_settings_for_display)
        assert callable(cv.validate_email_config)
        assert callable(cv.validate_storage_configs)
        assert callable(cv.validate_notification_config)
        assert callable(cv.validate_auth_config)
        assert callable(cv.check_all_configs)

    @pytest.mark.unit
    def test_all_list_matches_expected_exports(self):
        """__all__ contains exactly the expected names."""
        from app.utils import config_validator as cv

        expected = {
            "validate_email_config",
            "validate_storage_configs",
            "validate_notification_config",
            "validate_auth_config",
            "mask_sensitive_value",
            "get_provider_status",
            "get_settings_for_display",
            "dump_all_settings",
            "check_all_configs",
        }
        assert set(cv.__all__) == expected

    @pytest.mark.unit
    def test_mask_sensitive_value_callable(self):
        """mask_sensitive_value from wrapper returns a result."""
        from app.utils.config_validator import mask_sensitive_value

        result = mask_sensitive_value("secret-token-12345")
        assert isinstance(result, str)
        # Should mask part of the value
        assert result != "secret-token-12345"

    @pytest.mark.unit
    def test_get_provider_status_returns_dict(self):
        """get_provider_status returns a dictionary."""
        from app.utils.config_validator import get_provider_status

        result = get_provider_status()
        assert isinstance(result, dict)

    @pytest.mark.unit
    def test_check_all_configs_returns_dict(self):
        """check_all_configs returns a dictionary of validation results."""
        from app.utils.config_validator import check_all_configs

        result = check_all_configs()
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 2. app/api/settings.py  (admin-only settings CRUD)
# ---------------------------------------------------------------------------

class TestRequireAdminDependency:
    """Tests for the require_admin dependency itself."""

    @pytest.mark.unit
    def test_require_admin_raises_when_no_session_user(self):
        """require_admin raises 403 when there is no user in session."""
        from fastapi import HTTPException

        mock_request = MagicMock()
        mock_request.session.get.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            require_admin(mock_request)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_require_admin_raises_when_user_not_admin(self):
        """require_admin raises 403 when user is not admin."""
        from fastapi import HTTPException

        mock_request = MagicMock()
        mock_request.session.get.return_value = {"name": "user", "is_admin": False}
        with pytest.raises(HTTPException) as exc_info:
            require_admin(mock_request)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_require_admin_returns_user_when_admin(self):
        """require_admin returns user dict when user is admin."""
        mock_request = MagicMock()
        admin_user = {"name": "admin", "is_admin": True}
        mock_request.session.get.return_value = admin_user
        result = require_admin(mock_request)
        assert result == admin_user


class TestSettingsGetAll:
    """GET /api/settings/ - list all settings."""

    @pytest.mark.unit
    def test_get_settings_success(self, client):
        """Successfully retrieve all settings as admin."""
        fastapi_app.dependency_overrides[require_admin] = _override_admin
        try:
            response = client.get("/api/settings/")
            assert response.status_code == 200
            data = response.json()
            assert "settings" in data
            assert "categories" in data
            assert "db_settings" in data
        finally:
            fastapi_app.dependency_overrides.pop(require_admin, None)

    @pytest.mark.unit
    def test_get_settings_error_handling(self, client):
        """500 error when internal exception occurs."""
        fastapi_app.dependency_overrides[require_admin] = _override_admin
        try:
            with patch("app.api.settings.get_all_settings_from_db", side_effect=RuntimeError("db error")):
                response = client.get("/api/settings/")
                assert response.status_code == 500
                assert "Failed to retrieve settings" in response.json()["detail"]
        finally:
            fastapi_app.dependency_overrides.pop(require_admin, None)


class TestSettingsGetOne:
    """GET /api/settings/{key} - get a specific setting."""

    @pytest.mark.unit
    def test_get_setting_known_key(self, client):
        """Retrieve a known setting key."""
        fastapi_app.dependency_overrides[require_admin] = _override_admin
        try:
            response = client.get("/api/settings/workdir")
            assert response.status_code == 200
            data = response.json()
            assert data["key"] == "workdir"
            assert "metadata" in data
        finally:
            fastapi_app.dependency_overrides.pop(require_admin, None)

    @pytest.mark.unit
    def test_get_setting_unknown_key(self, client):
        """Retrieve an unknown setting key returns value=None."""
        fastapi_app.dependency_overrides[require_admin] = _override_admin
        try:
            response = client.get("/api/settings/nonexistent_key_xyz")
            assert response.status_code == 200
            data = response.json()
            assert data["key"] == "nonexistent_key_xyz"
            assert data["value"] is None
        finally:
            fastapi_app.dependency_overrides.pop(require_admin, None)

    @pytest.mark.unit
    def test_get_setting_internal_error(self, client):
        """500 error when get_setting_metadata raises."""
        fastapi_app.dependency_overrides[require_admin] = _override_admin
        try:
            with patch("app.api.settings.get_setting_metadata", side_effect=RuntimeError("boom")):
                response = client.get("/api/settings/workdir")
                assert response.status_code == 500
                assert "Failed to retrieve setting" in response.json()["detail"]
        finally:
            fastapi_app.dependency_overrides.pop(require_admin, None)


class TestSettingsUpdate:
    """POST /api/settings/{key} - update a setting."""

    @pytest.mark.unit
    def test_update_setting_success(self, client):
        """Successfully update a setting."""
        fastapi_app.dependency_overrides[require_admin] = _override_admin
        try:
            with patch("app.api.settings.save_setting_to_db", return_value=True), \
                 patch("app.api.settings.validate_setting_value", return_value=(True, None)):
                response = client.post(
                    "/api/settings/workdir",
                    json={"key": "workdir", "value": "/new/path"},
                )
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["key"] == "workdir"
                assert data["value"] == "/new/path"
        finally:
            fastapi_app.dependency_overrides.pop(require_admin, None)

    @pytest.mark.unit
    def test_update_setting_validation_failure(self, client):
        """400 error when validation fails."""
        fastapi_app.dependency_overrides[require_admin] = _override_admin
        try:
            with patch("app.api.settings.validate_setting_value", return_value=(False, "Invalid value")):
                response = client.post(
                    "/api/settings/workdir",
                    json={"key": "workdir", "value": "bad"},
                )
                assert response.status_code == 400
                assert "Invalid value" in response.json()["detail"]
        finally:
            fastapi_app.dependency_overrides.pop(require_admin, None)

    @pytest.mark.unit
    def test_update_setting_save_failure(self, client):
        """500 error when save_setting_to_db returns False."""
        fastapi_app.dependency_overrides[require_admin] = _override_admin
        try:
            with patch("app.api.settings.validate_setting_value", return_value=(True, None)), \
                 patch("app.api.settings.save_setting_to_db", return_value=False):
                response = client.post(
                    "/api/settings/workdir",
                    json={"key": "workdir", "value": "/tmp"},
                )
                assert response.status_code == 500
                assert "Failed to save setting" in response.json()["detail"]
        finally:
            fastapi_app.dependency_overrides.pop(require_admin, None)

    @pytest.mark.unit
    def test_update_setting_with_none_value(self, client):
        """Update a setting with None value (delete semantics)."""
        fastapi_app.dependency_overrides[require_admin] = _override_admin
        try:
            with patch("app.api.settings.save_setting_to_db", return_value=True):
                response = client.post(
                    "/api/settings/workdir",
                    json={"key": "workdir", "value": None},
                )
                assert response.status_code == 200
                assert response.json()["success"] is True
        finally:
            fastapi_app.dependency_overrides.pop(require_admin, None)

    @pytest.mark.unit
    def test_update_setting_unexpected_error(self, client):
        """500 error when an unexpected exception is raised."""
        fastapi_app.dependency_overrides[require_admin] = _override_admin
        try:
            with patch("app.api.settings.validate_setting_value", return_value=(True, None)), \
                 patch("app.api.settings.save_setting_to_db", side_effect=RuntimeError("unexpected")):
                response = client.post(
                    "/api/settings/workdir",
                    json={"key": "workdir", "value": "/tmp"},
                )
                assert response.status_code == 500
                assert "Failed to update setting" in response.json()["detail"]
        finally:
            fastapi_app.dependency_overrides.pop(require_admin, None)


class TestSettingsDelete:
    """DELETE /api/settings/{key} - delete a setting."""

    @pytest.mark.unit
    def test_delete_setting_success(self, client):
        """Successfully delete a setting."""
        fastapi_app.dependency_overrides[require_admin] = _override_admin
        try:
            with patch("app.api.settings.delete_setting_from_db", return_value=True):
                response = client.delete("/api/settings/workdir")
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert "deleted" in data["message"].lower()
        finally:
            fastapi_app.dependency_overrides.pop(require_admin, None)

    @pytest.mark.unit
    def test_delete_setting_not_found(self, client):
        """404 error when setting not found in DB."""
        fastapi_app.dependency_overrides[require_admin] = _override_admin
        try:
            with patch("app.api.settings.delete_setting_from_db", return_value=False):
                response = client.delete("/api/settings/nonexistent")
                assert response.status_code == 404
                assert "not found" in response.json()["detail"].lower()
        finally:
            fastapi_app.dependency_overrides.pop(require_admin, None)

    @pytest.mark.unit
    def test_delete_setting_unexpected_error(self, client):
        """500 error when an unexpected exception is raised."""
        fastapi_app.dependency_overrides[require_admin] = _override_admin
        try:
            with patch("app.api.settings.delete_setting_from_db", side_effect=RuntimeError("db crash")):
                response = client.delete("/api/settings/workdir")
                assert response.status_code == 500
                assert "Failed to delete setting" in response.json()["detail"]
        finally:
            fastapi_app.dependency_overrides.pop(require_admin, None)


class TestSettingsBulkUpdate:
    """Tests for bulk_update_settings handler.

    The /bulk-update route is defined after /{key} in the router, so FastAPI
    matches /{key} first. We test the async handler function directly.
    """

    def _make_mock_db(self):
        return MagicMock()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_bulk_update_all_success(self):
        """Successfully bulk update multiple settings."""
        from app.api.settings import SettingUpdate, bulk_update_settings

        mock_request = MagicMock()
        mock_db = self._make_mock_db()
        mock_admin = {"is_admin": True, "name": "admin"}
        updates = [
            SettingUpdate(key="workdir", value="/tmp/a"),
            SettingUpdate(key="external_hostname", value="example.com"),
        ]

        with patch("app.api.settings.validate_setting_value", return_value=(True, None)), \
             patch("app.api.settings.save_setting_to_db", return_value=True):
            result = await bulk_update_settings(updates, mock_request, mock_db, mock_admin)
            assert result["success"] is True
            assert len(result["updated"]) == 2
            assert len(result["errors"]) == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_bulk_update_with_validation_error(self):
        """Bulk update skips invalid settings and reports errors."""
        from app.api.settings import SettingUpdate, bulk_update_settings

        def mock_validate(key, value):
            if key == "bad_key":
                return (False, "Invalid value for bad_key")
            return (True, None)

        mock_request = MagicMock()
        mock_db = self._make_mock_db()
        updates = [
            SettingUpdate(key="workdir", value="/tmp"),
            SettingUpdate(key="bad_key", value="invalid"),
        ]

        with patch("app.api.settings.validate_setting_value", side_effect=mock_validate), \
             patch("app.api.settings.save_setting_to_db", return_value=True):
            result = await bulk_update_settings(updates, mock_request, mock_db, {"is_admin": True})
            assert result["success"] is False
            assert len(result["updated"]) == 1
            assert len(result["errors"]) == 1
            assert result["errors"][0]["key"] == "bad_key"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_bulk_update_save_failure(self):
        """Bulk update reports errors when save_setting_to_db returns False."""
        from app.api.settings import SettingUpdate, bulk_update_settings

        mock_request = MagicMock()
        mock_db = self._make_mock_db()
        updates = [SettingUpdate(key="workdir", value="/tmp")]

        with patch("app.api.settings.validate_setting_value", return_value=(True, None)), \
             patch("app.api.settings.save_setting_to_db", return_value=False):
            result = await bulk_update_settings(updates, mock_request, mock_db, {"is_admin": True})
            assert result["success"] is False
            assert len(result["errors"]) == 1
            assert "Failed to save" in result["errors"][0]["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_bulk_update_with_exception_during_save(self):
        """Bulk update catches per-item exceptions and reports them."""
        from app.api.settings import SettingUpdate, bulk_update_settings

        mock_request = MagicMock()
        mock_db = self._make_mock_db()
        updates = [SettingUpdate(key="workdir", value="/tmp")]

        with patch("app.api.settings.validate_setting_value", return_value=(True, None)), \
             patch("app.api.settings.save_setting_to_db", side_effect=RuntimeError("boom")):
            result = await bulk_update_settings(updates, mock_request, mock_db, {"is_admin": True})
            assert result["success"] is False
            assert len(result["errors"]) == 1
            assert "boom" in result["errors"][0]["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_bulk_update_with_none_value(self):
        """Bulk update with None value skips validation."""
        from app.api.settings import SettingUpdate, bulk_update_settings

        mock_request = MagicMock()
        mock_db = self._make_mock_db()
        updates = [SettingUpdate(key="workdir", value=None)]

        with patch("app.api.settings.save_setting_to_db", return_value=True):
            result = await bulk_update_settings(updates, mock_request, mock_db, {"is_admin": True})
            assert result["success"] is True
            assert len(result["updated"]) == 1


# ---------------------------------------------------------------------------
# 3. app/views/license_routes.py
# ---------------------------------------------------------------------------

class TestLicenseRoutes:
    """Tests for license and attribution view routes."""

    @pytest.mark.unit
    def test_get_lgpl_license_success(self, client):
        """GET /licenses/lgpl.txt returns the LGPL license text."""
        response = client.get("/licenses/lgpl.txt")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        # LGPL license files typically contain recognizable text
        assert len(response.text) > 0

    @pytest.mark.unit
    def test_get_lgpl_license_file_missing(self, client):
        """GET /licenses/lgpl.txt returns 404 when file doesn't exist."""
        with patch("app.views.license_routes.Path") as MockPath:
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = False
            MockPath.return_value = mock_path_instance
            response = client.get("/licenses/lgpl.txt")
            assert response.status_code == 404
            # HTTPException returns JSON even with PlainTextResponse response_class
            assert "not found" in response.text.lower()

    @pytest.mark.unit
    def test_serve_attribution_page(self, client):
        """GET /attribution returns the attribution HTML page."""
        response = client.get("/attribution")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# 4. app/api/diagnostic.py
# ---------------------------------------------------------------------------

class TestDiagnosticSettings:
    """GET /api/diagnostic/settings - dump settings."""

    @pytest.mark.unit
    def test_diagnostic_settings_success(self, client):
        """Returns safe subset of settings."""
        with patch("app.utils.config_validator.dump_all_settings"):
            response = client.get("/api/diagnostic/settings")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "settings" in data
            assert "configured_services" in data["settings"]


class TestDiagnosticTestNotification:
    """POST /api/diagnostic/test-notification - send test notification."""

    @pytest.mark.unit
    def test_notification_no_urls_configured(self, client):
        """Returns warning when no notification URLs are configured."""
        with patch("app.config.settings.notification_urls", new=[], create=True):
            response = client.post("/api/diagnostic/test-notification")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "warning"
            assert "No notification" in data["message"]

    @pytest.mark.unit
    def test_notification_send_success(self, client):
        """Returns success when notification is sent."""
        with patch("app.config.settings.notification_urls", new=["http://ntfy.example.com/test"], create=True), \
             patch("app.utils.notification.send_notification", return_value=True) as mock_send:
            response = client.post("/api/diagnostic/test-notification")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["services_count"] == 1
            mock_send.assert_called_once()

    @pytest.mark.unit
    def test_notification_send_failure(self, client):
        """Returns error when send_notification returns False."""
        with patch("app.config.settings.notification_urls", new=["http://ntfy.example.com/test"], create=True), \
             patch("app.utils.notification.send_notification", return_value=False):
            response = client.post("/api/diagnostic/test-notification")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            assert "Failed" in data["message"]

    @pytest.mark.unit
    def test_notification_send_exception(self, client):
        """Returns error when send_notification raises an exception."""
        with patch("app.config.settings.notification_urls", new=["http://ntfy.example.com/test"], create=True), \
             patch("app.utils.notification.send_notification", side_effect=RuntimeError("connection refused")):
            response = client.post("/api/diagnostic/test-notification")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            assert "connection refused" in data["message"]


# ---------------------------------------------------------------------------
# 5. app/api/openai.py
# ---------------------------------------------------------------------------

class TestOpenAITestEndpoint:
    """GET /api/openai/test - test OpenAI API key."""

    @pytest.mark.unit
    def test_openai_no_api_key(self, client):
        """Returns error when no API key is configured."""
        with patch("app.config.settings.openai_api_key", new=""):
            response = client.get("/api/openai/test")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            assert "No OpenAI API key" in data["message"]

    @pytest.mark.unit
    def test_openai_valid_key(self, client):
        """Returns success when API key is valid."""
        mock_models = MagicMock()
        mock_models.data = [MagicMock(), MagicMock(), MagicMock()]

        mock_client_instance = MagicMock()
        mock_client_instance.models.list.return_value = mock_models

        with patch("app.config.settings.openai_api_key", new="sk-valid-key"), \
             patch("openai.OpenAI", return_value=mock_client_instance):
            response = client.get("/api/openai/test")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["models_available"] == 3

    @pytest.mark.unit
    def test_openai_auth_error(self, client):
        """Returns error with auth flag when key is invalid."""
        mock_client_instance = MagicMock()
        mock_client_instance.models.list.side_effect = Exception("Incorrect API key provided")

        with patch("app.config.settings.openai_api_key", new="sk-bad-key"), \
             patch("openai.OpenAI", return_value=mock_client_instance):
            response = client.get("/api/openai/test")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            assert data["is_auth_error"] is True

    @pytest.mark.unit
    def test_openai_non_auth_error(self, client):
        """Returns error without auth flag for non-auth failures."""
        mock_client_instance = MagicMock()
        mock_client_instance.models.list.side_effect = Exception("Connection timeout")

        with patch("app.config.settings.openai_api_key", new="sk-valid-key"), \
             patch("openai.OpenAI", return_value=mock_client_instance):
            response = client.get("/api/openai/test")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            assert data["is_auth_error"] is False
            assert "Connection timeout" in data["message"]

    @pytest.mark.unit
    def test_openai_import_error(self, client):
        """Returns error when openai package is not installed."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "openai":
                raise ImportError("No module named 'openai'")
            return original_import(name, *args, **kwargs)

        with patch("app.config.settings.openai_api_key", new="sk-key"), \
             patch("builtins.__import__", side_effect=mock_import):
            response = client.get("/api/openai/test")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            assert "not installed" in data["message"]

    @pytest.mark.unit
    def test_openai_unexpected_error(self, client):
        """Returns error for unexpected exceptions outside the inner try."""
        with patch("app.config.settings.openai_api_key", new="sk-key"), \
             patch("openai.OpenAI", side_effect=RuntimeError("unexpected crash")):
            response = client.get("/api/openai/test")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            assert "Unexpected error" in data["message"]
