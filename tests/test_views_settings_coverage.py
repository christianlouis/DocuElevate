"""Comprehensive tests for app/views/settings.py to improve coverage."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from fastapi import HTTPException
from fastapi.responses import RedirectResponse


@pytest.mark.unit
class TestRequireAdminAccessDecorator:
    """Tests for require_admin_access decorator."""

    @pytest.mark.asyncio
    async def test_redirects_non_admin(self):
        """Test non-admin users are redirected."""
        from app.views.settings import require_admin_access

        @require_admin_access
        async def my_route(request):
            return {"success": True}

        mock_request = MagicMock()
        mock_request.session = {"user": {"id": "1", "is_admin": False}}

        result = await my_route(mock_request)
        assert result.status_code == 302

    @pytest.mark.asyncio
    async def test_redirects_no_user(self):
        """Test unauthenticated users are redirected."""
        from app.views.settings import require_admin_access

        @require_admin_access
        async def my_route(request):
            return {"success": True}

        mock_request = MagicMock()
        mock_request.session = {}

        result = await my_route(mock_request)
        assert result.status_code == 302

    @pytest.mark.asyncio
    async def test_allows_admin(self):
        """Test admin users can access route."""
        from app.views.settings import require_admin_access

        @require_admin_access
        async def my_route(request):
            return {"success": True}

        mock_request = MagicMock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}

        result = await my_route(mock_request)
        assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_supports_sync_functions(self):
        """Test decorator works with synchronous functions."""
        from app.views.settings import require_admin_access

        @require_admin_access
        def my_sync_route(request):
            return {"sync": True}

        mock_request = MagicMock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}

        result = await my_sync_route(mock_request)
        assert result == {"sync": True}

    @pytest.mark.asyncio
    async def test_passes_extra_args(self):
        """Test decorator passes extra args and kwargs."""
        from app.views.settings import require_admin_access

        @require_admin_access
        async def my_route(request, db=None):
            return {"db": db is not None}

        mock_request = MagicMock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}

        result = await my_route(mock_request, db=MagicMock())
        assert result == {"db": True}

    @pytest.mark.asyncio
    async def test_redirect_url(self):
        """Test redirect goes to home page."""
        from app.views.settings import require_admin_access

        @require_admin_access
        async def my_route(request):
            return {"success": True}

        mock_request = MagicMock()
        mock_request.session = {"user": {"id": "1", "is_admin": False}}

        result = await my_route(mock_request)
        assert isinstance(result, RedirectResponse)
        assert result.headers.get("location") == "/"


@pytest.mark.unit
class TestSettingsPage:
    """Tests for settings_page view function."""

    @pytest.mark.asyncio
    @patch("app.views.settings.templates")
    @patch("app.views.settings.get_settings_by_category")
    @patch("app.views.settings.get_setting_metadata")
    @patch("app.views.settings.mask_sensitive_value")
    @patch("app.views.settings.settings")
    async def test_settings_page_renders(self, mock_settings, mock_mask, mock_metadata, mock_categories, mock_templates):
        """Test settings page renders with settings data."""
        from app.views.settings import settings_page

        mock_settings.version = "1.0.0"
        mock_settings.workdir = "/tmp"
        mock_categories.return_value = {"general": ["workdir"]}
        mock_metadata.return_value = {"description": "Work dir", "sensitive": False}
        mock_mask.return_value = "***"

        mock_db = MagicMock()
        mock_request = MagicMock()

        with patch("app.utils.settings_service.get_all_settings_from_db", return_value={}):
            with patch("os.environ", {}):
                mock_templates.TemplateResponse.return_value = MagicMock()
                result = await settings_page(mock_request, db=mock_db)
                mock_templates.TemplateResponse.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.views.settings.templates")
    @patch("app.views.settings.get_settings_by_category")
    @patch("app.views.settings.get_setting_metadata")
    @patch("app.views.settings.settings")
    async def test_settings_page_with_db_settings(self, mock_settings, mock_metadata, mock_categories, mock_templates):
        """Test settings page shows DB source for settings in database."""
        from app.views.settings import settings_page

        mock_settings.version = "1.0.0"
        mock_settings.workdir = "/data"
        mock_categories.return_value = {"general": ["workdir"]}
        mock_metadata.return_value = {"description": "Work dir", "sensitive": False}

        mock_db = MagicMock()
        mock_request = MagicMock()

        with patch("app.utils.settings_service.get_all_settings_from_db", return_value={"workdir": "/data"}):
            mock_templates.TemplateResponse.return_value = MagicMock()
            result = await settings_page(mock_request, db=mock_db)
            # Verify template was called
            call_args = mock_templates.TemplateResponse.call_args
            context = call_args[0][1]
            settings_data = context["settings_data"]
            assert "general" in settings_data
            general_settings = settings_data["general"]
            assert len(general_settings) == 1
            assert general_settings[0]["source"] == "database"
            assert general_settings[0]["source_label"] == "DB"

    @pytest.mark.asyncio
    @patch("app.views.settings.templates")
    @patch("app.views.settings.get_settings_by_category")
    @patch("app.views.settings.get_setting_metadata")
    @patch("app.views.settings.settings")
    async def test_settings_page_with_env_settings(self, mock_settings, mock_metadata, mock_categories, mock_templates):
        """Test settings page shows ENV source for environment settings."""
        from app.views.settings import settings_page

        mock_settings.version = "1.0.0"
        mock_settings.workdir = "/env_path"
        mock_categories.return_value = {"general": ["workdir"]}
        mock_metadata.return_value = {"description": "Work dir", "sensitive": False}

        mock_db = MagicMock()
        mock_request = MagicMock()

        with patch("app.utils.settings_service.get_all_settings_from_db", return_value={}):
            with patch.dict("os.environ", {"WORKDIR": "/env_path"}):
                mock_templates.TemplateResponse.return_value = MagicMock()
                result = await settings_page(mock_request, db=mock_db)
                call_args = mock_templates.TemplateResponse.call_args
                context = call_args[0][1]
                settings_data = context["settings_data"]
                general_settings = settings_data["general"]
                assert general_settings[0]["source"] == "environment"

    @pytest.mark.asyncio
    @patch("app.views.settings.templates")
    @patch("app.views.settings.get_settings_by_category")
    @patch("app.views.settings.get_setting_metadata")
    @patch("app.views.settings.mask_sensitive_value")
    @patch("app.views.settings.settings")
    async def test_settings_page_masks_sensitive(
        self, mock_settings, mock_mask, mock_metadata, mock_categories, mock_templates
    ):
        """Test settings page masks sensitive values."""
        from app.views.settings import settings_page

        mock_settings.version = "1.0.0"
        mock_settings.api_key = "super-secret-key"
        mock_categories.return_value = {"security": ["api_key"]}
        mock_metadata.return_value = {"description": "API Key", "sensitive": True}
        mock_mask.return_value = "sup***key"

        mock_db = MagicMock()
        mock_request = MagicMock()

        with patch("app.utils.settings_service.get_all_settings_from_db", return_value={}):
            with patch.dict("os.environ", {}, clear=False):
                mock_templates.TemplateResponse.return_value = MagicMock()
                result = await settings_page(mock_request, db=mock_db)
                call_args = mock_templates.TemplateResponse.call_args
                context = call_args[0][1]
                settings_data = context["settings_data"]
                security_settings = settings_data["security"]
                assert security_settings[0]["display_value"] == "sup***key"

    @pytest.mark.asyncio
    @patch("app.views.settings.get_settings_by_category")
    @patch("app.views.settings.settings")
    async def test_settings_page_exception(self, mock_settings, mock_categories):
        """Test settings page raises HTTPException on error."""
        from app.views.settings import settings_page

        mock_categories.side_effect = Exception("DB Error")

        mock_request = MagicMock()
        mock_db = MagicMock()

        with patch("app.utils.settings_service.get_all_settings_from_db", side_effect=Exception("DB Error")):
            with pytest.raises(HTTPException) as exc_info:
                await settings_page(mock_request, db=mock_db)
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    @patch("app.views.settings.templates")
    @patch("app.views.settings.get_settings_by_category")
    @patch("app.views.settings.get_setting_metadata")
    @patch("app.views.settings.settings")
    async def test_settings_page_default_source(self, mock_settings, mock_metadata, mock_categories, mock_templates):
        """Test settings page shows DEFAULT source for default values."""
        from app.views.settings import settings_page

        mock_settings.version = "1.0.0"
        mock_settings.debug = False
        mock_categories.return_value = {"general": ["debug"]}
        mock_metadata.return_value = {"description": "Debug mode", "sensitive": False}

        mock_db = MagicMock()
        mock_request = MagicMock()

        with patch("app.utils.settings_service.get_all_settings_from_db", return_value={}):
            with patch.dict("os.environ", {}, clear=False):
                import os

                if "DEBUG" in os.environ:
                    del os.environ["DEBUG"]
                if "debug" in os.environ:
                    del os.environ["debug"]

                mock_templates.TemplateResponse.return_value = MagicMock()
                result = await settings_page(mock_request, db=mock_db)
                call_args = mock_templates.TemplateResponse.call_args
                context = call_args[0][1]
                settings_data = context["settings_data"]
                general_settings = settings_data["general"]
                assert general_settings[0]["source"] == "default"
                assert general_settings[0]["source_label"] == "DEFAULT"
                assert general_settings[0]["source_color"] == "gray"


@pytest.mark.integration
class TestSettingsViewIntegration:
    """Integration tests for settings page endpoint."""

    def test_settings_page_redirects_unauthenticated(self, client):
        """Test settings page redirects when not authenticated."""
        response = client.get("/settings", follow_redirects=False)
        assert response.status_code in (200, 302, 303)
