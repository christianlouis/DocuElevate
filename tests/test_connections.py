"""Tests for the Connections admin page and new authentication providers."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import status


@pytest.mark.unit
class TestDropboxComplianceFix:
    """Tests for the Dropbox userinfo compliance fix."""

    def test_dropbox_compliance_fix_adds_sub(self):
        """Test that compliance fix adds 'sub' from account_id."""
        from app.auth import _dropbox_userinfo_compliance_fix

        data = {"account_id": "dbid:abc123", "email": "test@example.com"}
        result = _dropbox_userinfo_compliance_fix(None, None, None, data)
        assert result["sub"] == "dbid:abc123"

    def test_dropbox_compliance_fix_does_not_overwrite_sub(self):
        """Test that compliance fix preserves existing 'sub'."""
        from app.auth import _dropbox_userinfo_compliance_fix

        data = {"account_id": "dbid:abc123", "sub": "existing-sub"}
        result = _dropbox_userinfo_compliance_fix(None, None, None, data)
        assert result["sub"] == "existing-sub"

    def test_dropbox_compliance_fix_normalizes_name(self):
        """Test that compliance fix normalizes nested name object."""
        from app.auth import _dropbox_userinfo_compliance_fix

        data = {"name": {"display_name": "John Doe", "given_name": "John"}}
        result = _dropbox_userinfo_compliance_fix(None, None, None, data)
        assert result["name"] == "John Doe"

    def test_dropbox_compliance_fix_handles_no_name(self):
        """Test compliance fix works when no name is present."""
        from app.auth import _dropbox_userinfo_compliance_fix

        data = {"email": "test@example.com"}
        result = _dropbox_userinfo_compliance_fix(None, None, None, data)
        assert "email" in result


@pytest.mark.unit
class TestGitHubNormalization:
    """Tests for GitHub userinfo normalization."""

    def test_github_normalize_standard(self):
        """Test GitHub userinfo normalization with standard response."""
        from app.auth import _normalize_social_userinfo

        raw = {
            "id": 12345,
            "login": "octocat",
            "name": "The Octocat",
            "email": "octocat@github.com",
            "avatar_url": "https://avatars.githubusercontent.com/u/12345",
        }
        result = _normalize_social_userinfo("github", {}, raw)
        assert result["sub"] == "12345"
        assert result["email"] == "octocat@github.com"
        assert result["name"] == "The Octocat"
        assert result["preferred_username"] == "octocat"
        assert result["picture"] == "https://avatars.githubusercontent.com/u/12345"

    def test_github_normalize_no_name_uses_login(self):
        """Test GitHub normalization falls back to login when name is empty."""
        from app.auth import _normalize_social_userinfo

        raw = {"id": 12345, "login": "octocat", "name": "", "email": "octocat@github.com"}
        result = _normalize_social_userinfo("github", {}, raw)
        assert result["name"] == "octocat"

    def test_github_normalize_missing_fields(self):
        """Test GitHub normalization handles missing fields gracefully."""
        from app.auth import _normalize_social_userinfo

        result = _normalize_social_userinfo("github", {}, {})
        assert result["sub"] == ""
        assert result["email"] == ""
        assert result["name"] == ""
        assert result["preferred_username"] == ""


@pytest.mark.unit
class TestSSOAutoLogin:
    """Tests for SSO Auto Login configuration."""

    def test_sso_auto_login_default_false(self):
        """Test that SSO auto login defaults to False."""
        from app.config import Settings

        s = Settings(
            _env_file=None,
            auth_enabled=True,
        )
        assert s.sso_auto_login is False

    def test_sso_auto_login_can_be_enabled(self):
        """Test that SSO auto login can be set to True."""
        from app.config import Settings

        s = Settings(
            _env_file=None,
            auth_enabled=True,
            sso_auto_login=True,
        )
        assert s.sso_auto_login is True


@pytest.mark.unit
class TestNewConfigFields:
    """Tests for new configuration fields."""

    def test_github_config_defaults(self):
        """Test GitHub social auth config defaults."""
        from app.config import Settings

        s = Settings(_env_file=None, auth_enabled=True)
        assert s.social_auth_github_enabled is False
        assert s.social_auth_github_client_id is None
        assert s.social_auth_github_client_secret is None

    def test_keycloak_config_defaults(self):
        """Test Keycloak social auth config defaults."""
        from app.config import Settings

        s = Settings(_env_file=None, auth_enabled=True)
        assert s.social_auth_keycloak_enabled is False
        assert s.social_auth_keycloak_client_id is None
        assert s.social_auth_keycloak_server_url is None
        assert s.social_auth_keycloak_realm is None

    def test_generic_oauth2_config_defaults(self):
        """Test Generic OAuth2 config defaults."""
        from app.config import Settings

        s = Settings(_env_file=None, auth_enabled=True)
        assert s.social_auth_generic_oauth2_enabled is False
        assert s.social_auth_generic_oauth2_scope == "openid profile email"
        assert s.social_auth_generic_oauth2_name == "OAuth2"

    def test_saml2_config_defaults(self):
        """Test SAML2 config defaults."""
        from app.config import Settings

        s = Settings(_env_file=None, auth_enabled=True)
        assert s.social_auth_saml2_enabled is False
        assert s.social_auth_saml2_name == "SAML2"

    def test_telegram_config_defaults(self):
        """Test Telegram config defaults."""
        from app.config import Settings

        s = Settings(_env_file=None, auth_enabled=True)
        assert s.telegram_enabled is False
        assert s.telegram_bot_token is None
        assert s.telegram_chat_id is None


@pytest.mark.unit
class TestSettingsMetadata:
    """Tests that new settings have metadata entries."""

    def test_github_settings_have_metadata(self):
        """Test GitHub settings are in SETTING_METADATA."""
        from app.utils.settings_service import SETTING_METADATA

        assert "social_auth_github_enabled" in SETTING_METADATA
        assert "social_auth_github_client_id" in SETTING_METADATA
        assert "social_auth_github_client_secret" in SETTING_METADATA

    def test_keycloak_settings_have_metadata(self):
        """Test Keycloak settings are in SETTING_METADATA."""
        from app.utils.settings_service import SETTING_METADATA

        assert "social_auth_keycloak_enabled" in SETTING_METADATA
        assert "social_auth_keycloak_client_id" in SETTING_METADATA
        assert "social_auth_keycloak_server_url" in SETTING_METADATA
        assert "social_auth_keycloak_realm" in SETTING_METADATA

    def test_generic_oauth2_settings_have_metadata(self):
        """Test Generic OAuth2 settings are in SETTING_METADATA."""
        from app.utils.settings_service import SETTING_METADATA

        assert "social_auth_generic_oauth2_enabled" in SETTING_METADATA
        assert "social_auth_generic_oauth2_authorize_url" in SETTING_METADATA
        assert "social_auth_generic_oauth2_token_url" in SETTING_METADATA

    def test_saml2_settings_have_metadata(self):
        """Test SAML2 settings are in SETTING_METADATA."""
        from app.utils.settings_service import SETTING_METADATA

        assert "social_auth_saml2_enabled" in SETTING_METADATA
        assert "social_auth_saml2_sso_url" in SETTING_METADATA
        assert "social_auth_saml2_entity_id" in SETTING_METADATA

    def test_telegram_settings_have_metadata(self):
        """Test Telegram settings are in SETTING_METADATA."""
        from app.utils.settings_service import SETTING_METADATA

        assert "telegram_enabled" in SETTING_METADATA
        assert "telegram_bot_token" in SETTING_METADATA
        assert "telegram_chat_id" in SETTING_METADATA

    def test_sso_auto_login_has_metadata(self):
        """Test SSO auto login has metadata."""
        from app.utils.settings_service import SETTING_METADATA

        assert "sso_auto_login" in SETTING_METADATA
        meta = SETTING_METADATA["sso_auto_login"]
        assert meta["category"] == "Authentication"
        assert meta["type"] == "boolean"

    def test_github_category_is_social_login(self):
        """Test GitHub settings are in Social Login category."""
        from app.utils.settings_service import SETTING_METADATA

        assert SETTING_METADATA["social_auth_github_enabled"]["category"] == "Social Login"

    def test_github_secret_is_sensitive(self):
        """Test GitHub client secret is marked sensitive."""
        from app.utils.settings_service import SETTING_METADATA

        assert SETTING_METADATA["social_auth_github_client_secret"]["sensitive"] is True

    def test_github_has_help_link(self):
        """Test GitHub has a help link to developer settings."""
        from app.utils.settings_service import SETTING_METADATA

        assert "help_link" in SETTING_METADATA["social_auth_github_enabled"]


@pytest.mark.unit
class TestConnectionsPageRoute:
    """Tests for the /admin/connections route."""

    @pytest.mark.asyncio
    async def test_connections_page_non_admin_redirected(self):
        """Test that non-admin users are redirected from connections page."""

        mock_request = MagicMock()
        mock_request.session = {"user": {"is_admin": False}}
        mock_db = MagicMock()

        # The require_admin_access decorator should handle this, so we test the decorator
        from app.views.settings import require_admin_access

        @require_admin_access
        async def dummy_view(request):
            return "success"

        result = await dummy_view(mock_request)
        assert result.status_code == status.HTTP_302_FOUND

    @pytest.mark.asyncio
    async def test_connections_page_returns_services(self):
        """Test that connections page includes expected services in context."""
        from app.views.settings import connections_page

        mock_request = MagicMock()
        mock_request.session = {"user": {"is_admin": True}}
        mock_db = MagicMock()

        with (
            patch("app.views.settings.get_all_settings_from_db", return_value={}),
            patch("app.views.settings.templates") as mock_templates,
            patch("app.views.settings.SETTING_METADATA", {}),
            patch("app.auth.OAUTH_CONFIGURED", False),
            patch("app.auth.SOCIAL_PROVIDERS", {}),
            patch("app.views.settings.get_setting_metadata", return_value={}),
        ):
            mock_templates.TemplateResponse.return_value = "response"
            result = await connections_page(mock_request, db=mock_db)

            # Check TemplateResponse was called
            mock_templates.TemplateResponse.assert_called_once()
            call_args = mock_templates.TemplateResponse.call_args
            template_name = call_args[0][0]
            context = call_args[0][1]

            assert template_name == "admin_connections.html"
            assert "services" in context
            assert "service_settings" in context
            assert "sso_auto_login" in context

            # Verify expected service keys
            service_keys = [s["key"] for s in context["services"]]
            assert "google" in service_keys
            assert "github" in service_keys
            assert "keycloak" in service_keys
            assert "generic_oauth2" in service_keys
            assert "saml2" in service_keys
            assert "smtp" in service_keys
            assert "telegram" in service_keys


@pytest.mark.unit
class TestTranslationKeys:
    """Tests for new translation keys."""

    def test_connections_translation_keys_exist(self):
        """Test that connections translation keys are in en.json."""
        import json
        from pathlib import Path

        en_path = Path("/home/runner/work/DocuElevate/DocuElevate/frontend/translations/en.json")
        translations = json.loads(en_path.read_text())

        expected_keys = [
            "connections.title",
            "connections.description",
            "connections.configure",
            "connections.linked",
            "connections.unlinked",
            "connections.sso_auto_login",
            "connections.sso_auto_login_title",
            "connections.sso_auto_login_description",
            "connections.mobile_upload_title",
            "connections.qr_code_enabled",
            "connections.unlinked_services",
            "nav.connections",
        ]
        for key in expected_keys:
            assert key in translations, f"Missing translation key: {key}"
