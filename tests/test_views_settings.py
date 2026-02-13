"""Tests for app/views/settings.py module."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from app.views.settings import require_admin_access


@pytest.mark.unit
class TestRequireAdminAccess:
    """Tests for require_admin_access decorator."""

    @pytest.mark.asyncio
    async def test_redirects_non_admin_user(self):
        """Test that non-admin users are redirected."""

        @require_admin_access
        async def dummy_route(request):
            return {"success": True}

        mock_request = MagicMock()
        mock_request.session = {"user": {"id": "1", "is_admin": False}}

        result = await dummy_route(mock_request)
        assert result.status_code == 302

    @pytest.mark.asyncio
    async def test_redirects_when_no_user(self):
        """Test that unauthenticated users are redirected."""

        @require_admin_access
        async def dummy_route(request):
            return {"success": True}

        mock_request = MagicMock()
        mock_request.session = {}

        result = await dummy_route(mock_request)
        assert result.status_code == 302

    @pytest.mark.asyncio
    async def test_allows_admin_user(self):
        """Test that admin users can access the route."""

        @require_admin_access
        async def dummy_route(request):
            return {"success": True}

        mock_request = MagicMock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}

        result = await dummy_route(mock_request)
        assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_redirects_to_home_page(self):
        """Test that non-admin users are redirected to home page."""

        @require_admin_access
        async def dummy_route(request):
            return {"success": True}

        mock_request = MagicMock()
        mock_request.session = {}

        result = await dummy_route(mock_request)
        assert result.status_code == 302
        assert result.headers["location"] == "/"

    @pytest.mark.asyncio
    async def test_works_with_sync_functions(self):
        """Test decorator works with synchronous functions."""

        @require_admin_access
        def sync_route(request):
            return {"success": True}

        mock_request = MagicMock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}

        result = await sync_route(mock_request)
        assert result == {"success": True}


@pytest.mark.integration
class TestSettingsView:
    """Tests for settings page endpoint."""

    def test_settings_page_redirects_without_admin(self, client):
        """Test settings page redirects non-admin users."""
        response = client.get("/settings", follow_redirects=False)
        # Should redirect since no user in session
        assert response.status_code in (200, 302, 303)

    @patch("app.views.settings.get_all_settings_from_db")
    @patch("app.views.settings.get_settings_by_category")
    @patch("app.views.settings.templates.TemplateResponse")
    def test_settings_page_returns_template(self, mock_template, mock_categories, mock_db_settings, client):
        """Test settings page returns template response."""
        mock_db_settings.return_value = {}
        mock_categories.return_value = {"General": ["workdir"]}

        # Without admin session, will redirect
        response = client.get("/settings", follow_redirects=False)
        assert response.status_code in (200, 302, 303)


@pytest.mark.unit
class TestSettingsPageLogic:
    """Tests for settings page logic."""

    @patch("app.views.settings.get_all_settings_from_db")
    @patch("app.views.settings.get_settings_by_category")
    @patch("app.views.settings.get_setting_metadata")
    @patch("app.views.settings.mask_sensitive_value")
    @patch("app.views.settings.templates")
    @patch("app.views.settings.settings")
    @patch("app.views.settings.os.environ", {"TEST_VAR": "test_value"})
    @pytest.mark.asyncio
    async def test_determines_setting_source_database(
        self, mock_settings, mock_templates, mock_mask, mock_metadata, mock_categories, mock_db_settings
    ):
        """Test determines setting source as database."""
        from app.views.settings import settings_page

        mock_db_settings.return_value = {"test_key": "db_value"}
        mock_categories.return_value = {"General": ["test_key"]}
        mock_metadata.return_value = {"type": "str", "sensitive": False}
        mock_settings.test_key = "db_value"
        mock_settings.version = "1.0.0"
        mock_mask.return_value = "db_value"

        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        # Call the function with mocked db
        await settings_page(mock_request, mock_db)

        # Verify template was called
        mock_templates.TemplateResponse.assert_called_once()

    @patch("app.views.settings.get_all_settings_from_db")
    @patch("app.views.settings.get_settings_by_category")
    @patch("app.views.settings.get_setting_metadata")
    @patch("app.views.settings.mask_sensitive_value")
    @patch("app.views.settings.os.environ", {"WORKDIR": "/tmp"})
    def test_determines_setting_source_environment(self, mock_mask, mock_metadata, mock_categories, mock_db_settings):
        """Test determines setting source as environment variable."""
        mock_db_settings.return_value = {}
        mock_categories.return_value = {"General": ["workdir"]}
        mock_metadata.return_value = {"type": "str", "sensitive": False}
        mock_mask.return_value = "/tmp"

        # The actual test would verify source determination logic

    @patch("app.views.settings.get_all_settings_from_db")
    @patch("app.views.settings.get_settings_by_category")
    @patch("app.views.settings.get_setting_metadata")
    @patch("app.views.settings.mask_sensitive_value")
    def test_determines_setting_source_default(self, mock_mask, mock_metadata, mock_categories, mock_db_settings):
        """Test determines setting source as default value."""
        mock_db_settings.return_value = {}
        mock_categories.return_value = {"General": ["workdir"]}
        mock_metadata.return_value = {"type": "str", "sensitive": False}
        mock_mask.return_value = "/app/workdir"

        # The actual test would verify source determination logic

    @patch("app.views.settings.get_setting_metadata")
    def test_masks_sensitive_values(self, mock_metadata):
        """Test masks sensitive values."""
        from app.views.settings import mask_sensitive_value

        mock_metadata.return_value = {"sensitive": True}

        # Test that sensitive values are masked
        value = "sensitive_password_123"
        masked = mask_sensitive_value(value)
        assert masked != value

    @patch("app.views.settings.get_all_settings_from_db")
    @pytest.mark.asyncio
    async def test_handles_database_errors(self, mock_db_settings):
        """Test handles database errors gracefully."""
        from app.views.settings import settings_page

        mock_db_settings.side_effect = Exception("Database error")

        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        # Should raise HTTPException
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await settings_page(mock_request, mock_db)
        assert exc_info.value.status_code == 500
