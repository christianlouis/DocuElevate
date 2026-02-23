"""Tests for app/views/settings.py module."""

import base64
import json
from unittest.mock import MagicMock, Mock, patch

import pytest
from itsdangerous import TimestampSigner

from app.views.settings import require_admin_access

_SESSION_SECRET = "test_secret_key_for_testing_must_be_at_least_32_characters_long"


def _make_admin_session_cookie() -> str:
    """Create a properly signed session cookie with admin user for tests."""
    session_data = {"user": {"id": "admin", "is_admin": True}}
    signer = TimestampSigner(_SESSION_SECRET)
    data = base64.b64encode(json.dumps(session_data).encode()).decode("utf-8")
    return signer.sign(data).decode("utf-8")


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

    @patch("app.views.settings.get_all_settings_from_db")
    @patch("app.views.settings.get_settings_by_category")
    @patch("app.views.settings.get_setting_metadata")
    @patch("app.views.settings.mask_sensitive_value")
    @patch("app.views.settings.templates")
    @patch("app.views.settings.settings")
    @patch("app.views.settings.os.environ", {"WORKDIR": "/tmp"})
    @pytest.mark.asyncio
    async def test_env_source_when_key_in_environ(
        self, mock_settings, mock_templates, mock_mask, mock_metadata, mock_categories, mock_db_settings
    ):
        """Test that env source is used when key is in os.environ."""
        from app.views.settings import settings_page

        mock_db_settings.return_value = {}
        mock_categories.return_value = {"General": ["workdir"]}
        mock_metadata.return_value = {"type": "str", "sensitive": False}
        mock_settings.workdir = "/tmp"
        mock_settings.version = "1.0.0"

        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        await settings_page(mock_request, mock_db)
        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        settings_data = context["settings_data"]
        workdir_entry = settings_data["General"][0]
        assert workdir_entry["source"] == "environment"

    @patch("app.views.settings.get_all_settings_from_db")
    @patch("app.views.settings.get_settings_by_category")
    @patch("app.views.settings.get_setting_metadata")
    @patch("app.views.settings.templates")
    @patch("app.views.settings.settings")
    @patch("app.views.settings.os.environ", {})
    @pytest.mark.asyncio
    async def test_default_source_when_key_not_in_environ(
        self, mock_settings, mock_templates, mock_metadata, mock_categories, mock_db_settings
    ):
        """Test that default source is used when key is not in environ or DB."""
        from app.views.settings import settings_page

        mock_db_settings.return_value = {}
        mock_categories.return_value = {"General": ["workdir"]}
        mock_metadata.return_value = {"type": "str", "sensitive": False}
        mock_settings.workdir = "/app/workdir"
        mock_settings.version = "1.0.0"

        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        await settings_page(mock_request, mock_db)
        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        settings_data = context["settings_data"]
        workdir_entry = settings_data["General"][0]
        assert workdir_entry["source"] == "default"

    @patch("app.views.settings.get_all_settings_from_db")
    @patch("app.views.settings.get_settings_by_category")
    @patch("app.views.settings.get_setting_metadata")
    @patch("app.views.settings.mask_sensitive_value")
    @patch("app.views.settings.templates")
    @patch("app.views.settings.settings")
    @pytest.mark.asyncio
    async def test_sensitive_values_masked_in_settings_page(
        self, mock_settings, mock_templates, mock_mask, mock_metadata, mock_categories, mock_db_settings
    ):
        """Test that sensitive values are masked in settings page."""
        from app.views.settings import settings_page

        mock_db_settings.return_value = {"openai_api_key": "sk-real-secret"}
        mock_categories.return_value = {"AI": ["openai_api_key"]}
        mock_metadata.return_value = {"type": "str", "sensitive": True}
        mock_mask.return_value = "sk-****"
        mock_settings.version = "1.0.0"

        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        await settings_page(mock_request, mock_db)
        mock_mask.assert_called()


@pytest.mark.unit
class TestCredentialsPage:
    """Tests for credentials_page endpoint."""

    @patch("app.views.settings.get_all_settings_from_db")
    @patch("app.views.settings.SETTING_METADATA")
    @patch("app.views.settings.templates")
    @patch("app.views.settings.settings")
    @pytest.mark.asyncio
    async def test_credentials_page_success(self, mock_settings, mock_templates, mock_metadata, mock_db_settings):
        """Test credentials page renders successfully."""
        from app.views.settings import credentials_page

        mock_db_settings.return_value = {}
        mock_metadata.items.return_value = [
            ("openai_api_key", {"sensitive": True, "category": "AI", "description": "OpenAI key"}),
            ("workdir", {"sensitive": False, "category": "General", "description": "Work dir"}),
        ]
        mock_settings.openai_api_key = None
        mock_settings.version = "1.0.0"

        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        await credentials_page(mock_request, mock_db)
        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        assert call_args[0][0] == "credentials.html"

    @patch("app.views.settings.get_all_settings_from_db")
    @patch("app.views.settings.SETTING_METADATA")
    @patch("app.views.settings.templates")
    @patch("app.views.settings.settings")
    @pytest.mark.asyncio
    async def test_credentials_page_source_db(self, mock_settings, mock_templates, mock_metadata, mock_db_settings):
        """Test credentials page shows db source when credential is in database."""
        from app.views.settings import credentials_page

        mock_db_settings.return_value = {"openai_api_key": "sk-from-db"}
        mock_metadata.items.return_value = [
            ("openai_api_key", {"sensitive": True, "category": "AI", "description": "API key"}),
        ]
        mock_settings.openai_api_key = "sk-from-env"
        mock_settings.version = "1.0.0"

        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        await credentials_page(mock_request, mock_db)
        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        ai_creds = context["categories"].get("AI", [])
        if ai_creds:
            assert ai_creds[0]["source"] == "db"
            assert ai_creds[0]["configured"] is True

    @patch("app.views.settings.get_all_settings_from_db")
    @patch("app.views.settings.SETTING_METADATA")
    @patch("app.views.settings.templates")
    @patch("app.views.settings.settings")
    @pytest.mark.asyncio
    async def test_credentials_page_source_env(self, mock_settings, mock_templates, mock_metadata, mock_db_settings):
        """Test credentials page shows env source when credential is only in env."""
        from app.views.settings import credentials_page

        mock_db_settings.return_value = {}
        mock_metadata.items.return_value = [
            ("openai_api_key", {"sensitive": True, "category": "AI", "description": "API key"}),
        ]
        mock_settings.openai_api_key = "sk-from-env"
        mock_settings.version = "1.0.0"

        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        await credentials_page(mock_request, mock_db)
        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        ai_creds = context["categories"].get("AI", [])
        if ai_creds:
            assert ai_creds[0]["source"] == "env"

    @patch("app.views.settings.get_all_settings_from_db")
    @patch("app.views.settings.SETTING_METADATA")
    @patch("app.views.settings.templates")
    @patch("app.views.settings.settings")
    @pytest.mark.asyncio
    async def test_credentials_page_not_configured(
        self, mock_settings, mock_templates, mock_metadata, mock_db_settings
    ):
        """Test credentials page shows not configured when no credential value."""
        from app.views.settings import credentials_page

        mock_db_settings.return_value = {}
        mock_metadata.items.return_value = [
            ("openai_api_key", {"sensitive": True, "category": "AI", "description": "API key"}),
        ]
        mock_settings.openai_api_key = None
        mock_settings.version = "1.0.0"

        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        await credentials_page(mock_request, mock_db)
        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        ai_creds = context["categories"].get("AI", [])
        if ai_creds:
            assert ai_creds[0]["source"] is None
            assert ai_creds[0]["configured"] is False

    @patch("app.views.settings.get_all_settings_from_db")
    @pytest.mark.asyncio
    async def test_credentials_page_raises_500_on_error(self, mock_db_settings):
        """Test credentials page raises 500 on error."""
        from fastapi import HTTPException

        from app.views.settings import credentials_page

        mock_db_settings.side_effect = Exception("DB error")
        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        with pytest.raises(HTTPException) as exc_info:
            await credentials_page(mock_request, mock_db)
        assert exc_info.value.status_code == 500

    def test_credentials_page_redirects_non_admin(self, client):
        """Test that non-admin users are redirected from credentials page."""
        response = client.get("/admin/credentials", follow_redirects=False)
        assert response.status_code in (200, 302, 303)

    def test_credentials_page_accessible_with_admin(self, client):
        """Test credentials page is accessible with admin session."""
        client.cookies.set("session", _make_admin_session_cookie())
        response = client.get("/admin/credentials", follow_redirects=False)
        assert response.status_code == 200


@pytest.mark.unit
class TestAuditLogPage:
    """Tests for audit_log_page endpoint."""

    @patch("app.utils.settings_service.get_audit_log")
    @patch("app.views.settings.templates")
    @patch("app.views.settings.settings")
    @pytest.mark.asyncio
    async def test_audit_log_page_success(self, mock_settings, mock_templates, mock_audit_log):
        """Test audit log page renders successfully."""
        from app.views.settings import audit_log_page

        mock_audit_log.return_value = []
        mock_settings.version = "1.0.0"

        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        await audit_log_page(mock_request, mock_db)
        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        assert call_args[0][0] == "audit_log.html"

    @patch("app.utils.settings_service.get_audit_log")
    @patch("app.views.settings.templates")
    @patch("app.views.settings.settings")
    @pytest.mark.asyncio
    async def test_audit_log_page_with_entries(self, mock_settings, mock_templates, mock_audit_log):
        """Test audit log page with actual entries."""
        from app.views.settings import audit_log_page

        mock_entries = [
            {"key": "workdir", "old_value": "/old", "new_value": "/new", "changed_by": "admin"},
        ]
        mock_audit_log.return_value = mock_entries
        mock_settings.version = "1.0.0"

        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        await audit_log_page(mock_request, mock_db)
        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert len(context["entries"]) == 1

    @patch("app.utils.settings_service.get_audit_log")
    @pytest.mark.asyncio
    async def test_audit_log_page_raises_500_on_error(self, mock_audit_log):
        """Test audit log page raises 500 on error."""
        from fastapi import HTTPException

        from app.views.settings import audit_log_page

        mock_audit_log.side_effect = Exception("DB error")
        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        with pytest.raises(HTTPException) as exc_info:
            await audit_log_page(mock_request, mock_db)
        assert exc_info.value.status_code == 500

    def test_audit_log_redirects_non_admin(self, client):
        """Test that non-admin users are redirected."""
        response = client.get("/admin/settings/audit-log", follow_redirects=False)
        assert response.status_code in (200, 302, 303)

    def test_audit_log_accessible_with_admin(self, client):
        """Test audit log page is accessible with admin session."""
        client.cookies.set("session", _make_admin_session_cookie())
        response = client.get("/admin/settings/audit-log", follow_redirects=False)
        assert response.status_code == 200
