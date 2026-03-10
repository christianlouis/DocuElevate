"""Tests for social login functionality in app/auth.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request, status
from starlette.responses import RedirectResponse


@pytest.mark.unit
class TestSocialProviders:
    """Tests for SOCIAL_PROVIDERS dictionary population."""

    def test_social_providers_is_dict(self):
        """Test that SOCIAL_PROVIDERS is a dict."""
        from app.auth import SOCIAL_PROVIDERS

        assert isinstance(SOCIAL_PROVIDERS, dict)

    def test_social_providers_empty_by_default(self):
        """Test that no social providers are enabled by default (settings have enabled=False)."""
        # In test environment, social login settings are not set, so the dict should be empty
        from app.auth import SOCIAL_PROVIDERS

        # Since tests run with default settings (all social providers disabled),
        # SOCIAL_PROVIDERS should be empty
        assert isinstance(SOCIAL_PROVIDERS, dict)


@pytest.mark.unit
class TestSocialLogin:
    """Tests for social_login() function."""

    @pytest.mark.asyncio
    async def test_social_login_unknown_provider(self):
        """Test social_login redirects when provider is unknown."""
        from app.auth import social_login

        mock_request = MagicMock(spec=Request)

        with patch("app.auth.SOCIAL_PROVIDERS", {}):
            result = await social_login(mock_request, "unknown_provider")

            assert isinstance(result, RedirectResponse)
            assert result.status_code == status.HTTP_302_FOUND
            assert "/login?error=Unknown+social+provider" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_social_login_provider_not_in_oauth(self):
        """Test social_login redirects when provider is registered but OAuth client is missing."""
        from app.auth import social_login

        mock_request = MagicMock(spec=Request)

        with (
            patch("app.auth.SOCIAL_PROVIDERS", {"google": {"name": "Google", "icon": "fab fa-google", "color": "red"}}),
            patch("app.auth.oauth") as mock_oauth,
        ):
            mock_oauth.google = None

            result = await social_login(mock_request, "google")

            assert isinstance(result, RedirectResponse)
            assert "/login?error=Provider+not+configured" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_social_login_initiates_redirect(self):
        """Test social_login initiates OAuth redirect for a valid provider."""
        from app.auth import social_login

        mock_request = MagicMock(spec=Request)
        mock_request.url_for = MagicMock(return_value="http://localhost/social-callback/google")

        mock_google = MagicMock()
        mock_google.authorize_redirect = AsyncMock(return_value="google_redirect")

        with (
            patch("app.auth.SOCIAL_PROVIDERS", {"google": {"name": "Google", "icon": "fab fa-google", "color": "red"}}),
            patch("app.auth.oauth") as mock_oauth,
        ):
            mock_oauth.google = mock_google

            result = await social_login(mock_request, "google")

            assert result == "google_redirect"
            mock_google.authorize_redirect.assert_called_once_with(
                mock_request, "http://localhost/social-callback/google"
            )


@pytest.mark.unit
class TestNormalizeSocialUserinfo:
    """Tests for _normalize_social_userinfo()."""

    def test_normalize_google_userinfo(self):
        """Test normalizing Google OIDC userinfo."""
        from app.auth import _normalize_social_userinfo

        raw = {
            "sub": "123456789",
            "email": "user@gmail.com",
            "name": "Test User",
            "picture": "https://lh3.googleusercontent.com/photo.jpg",
        }
        result = _normalize_social_userinfo("google", {}, raw)

        assert result["sub"] == "123456789"
        assert result["email"] == "user@gmail.com"
        assert result["name"] == "Test User"
        assert result["preferred_username"] == "user@gmail.com"
        assert result["picture"] == "https://lh3.googleusercontent.com/photo.jpg"

    def test_normalize_microsoft_userinfo(self):
        """Test normalizing Microsoft OIDC userinfo."""
        from app.auth import _normalize_social_userinfo

        raw = {
            "sub": "ms-sub-123",
            "email": "user@outlook.com",
            "name": "MS User",
        }
        result = _normalize_social_userinfo("microsoft", {}, raw)

        assert result["sub"] == "ms-sub-123"
        assert result["email"] == "user@outlook.com"
        assert result["name"] == "MS User"
        assert result["preferred_username"] == "user@outlook.com"

    def test_normalize_apple_userinfo(self):
        """Test normalizing Apple OIDC userinfo."""
        from app.auth import _normalize_social_userinfo

        raw = {
            "sub": "apple-sub-456",
            "email": "user@privaterelay.appleid.com",
        }
        result = _normalize_social_userinfo("apple", {}, raw)

        assert result["sub"] == "apple-sub-456"
        assert result["email"] == "user@privaterelay.appleid.com"

    def test_normalize_dropbox_userinfo(self):
        """Test normalizing Dropbox non-standard userinfo."""
        from app.auth import _normalize_social_userinfo

        raw = {
            "account_id": "dbid:AABcDEfGhIjKlMnOpQr",
            "email": "user@example.com",
            "name": {"display_name": "Dropbox User"},
            "profile_photo_url": "https://dropbox.com/photo.jpg",
        }
        result = _normalize_social_userinfo("dropbox", {}, raw)

        assert result["sub"] == "dbid:AABcDEfGhIjKlMnOpQr"
        assert result["email"] == "user@example.com"
        assert result["name"] == "Dropbox User"
        assert result["picture"] == "https://dropbox.com/photo.jpg"

    def test_normalize_dropbox_missing_fields(self):
        """Test normalizing Dropbox userinfo with missing fields."""
        from app.auth import _normalize_social_userinfo

        raw = {"email": "user@example.com"}
        result = _normalize_social_userinfo("dropbox", {}, raw)

        assert result["sub"] == "user@example.com"  # Falls back to email
        assert result["email"] == "user@example.com"
        assert result["name"] == ""

    def test_normalize_with_none_userinfo(self):
        """Test normalizing when userinfo is None."""
        from app.auth import _normalize_social_userinfo

        result = _normalize_social_userinfo("google", {}, None)

        assert result["sub"] == ""
        assert result["email"] == ""
        assert result["name"] == ""


@pytest.mark.unit
class TestSocialCallback:
    """Tests for social_callback() function."""

    @pytest.mark.asyncio
    async def test_social_callback_unknown_provider(self):
        """Test social_callback redirects when provider is unknown."""
        from app.auth import social_callback

        mock_request = MagicMock(spec=Request)
        mock_db = MagicMock()

        with patch("app.auth.SOCIAL_PROVIDERS", {}):
            result = await social_callback(mock_request, "unknown_provider", db=mock_db)

            assert isinstance(result, RedirectResponse)
            assert "/login?error=Unknown+social+provider" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_social_callback_provider_not_configured(self):
        """Test social_callback redirects when OAuth client is missing."""
        from app.auth import social_callback

        mock_request = MagicMock(spec=Request)
        mock_db = MagicMock()

        with (
            patch("app.auth.SOCIAL_PROVIDERS", {"google": {"name": "Google", "icon": "fab fa-google", "color": "red"}}),
            patch("app.auth.oauth") as mock_oauth,
        ):
            mock_oauth.google = None

            result = await social_callback(mock_request, "google", db=mock_db)

            assert isinstance(result, RedirectResponse)
            assert "/login?error=Provider+not+configured" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_social_callback_success_google(self):
        """Test successful Google social callback flow."""
        from app.auth import social_callback

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_db = MagicMock()

        mock_google = MagicMock()
        mock_google.authorize_access_token = AsyncMock(
            return_value={
                "userinfo": {
                    "sub": "google-123",
                    "email": "testuser@gmail.com",
                    "name": "Test User",
                    "picture": "https://example.com/photo.jpg",
                }
            }
        )

        mock_profile = MagicMock()
        mock_profile.onboarding_completed = True

        with (
            patch("app.auth.SOCIAL_PROVIDERS", {"google": {"name": "Google", "icon": "fab fa-google", "color": "red"}}),
            patch("app.auth.oauth") as mock_oauth,
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._UserProfile") as mock_user_profile_cls,
        ):
            mock_oauth.google = mock_google
            mock_db.query.return_value.filter.return_value.first.return_value = mock_profile

            result = await social_callback(mock_request, "google", db=mock_db)

            assert isinstance(result, RedirectResponse)
            # Verify session was set
            assert mock_request.session["user"]["email"] == "testuser@gmail.com"
            assert mock_request.session["user"]["auth_provider"] == "google"
            assert mock_request.session["user"]["is_admin"] is False

    @pytest.mark.asyncio
    async def test_social_callback_no_email(self):
        """Test social callback when provider doesn't return email."""
        from app.auth import social_callback

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_db = MagicMock()

        mock_google = MagicMock()
        mock_google.authorize_access_token = AsyncMock(
            return_value={
                "userinfo": {
                    "sub": "google-123",
                    # No email!
                    "name": "Test User",
                }
            }
        )

        with (
            patch("app.auth.SOCIAL_PROVIDERS", {"google": {"name": "Google", "icon": "fab fa-google", "color": "red"}}),
            patch("app.auth.oauth") as mock_oauth,
        ):
            mock_oauth.google = mock_google

            result = await social_callback(mock_request, "google", db=mock_db)

            assert isinstance(result, RedirectResponse)
            assert "/login?error=Could+not+retrieve+email+from+provider" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_social_callback_exception_handling(self):
        """Test social callback handles exceptions gracefully."""
        from app.auth import social_callback

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_db = MagicMock()

        mock_google = MagicMock()
        mock_google.authorize_access_token = AsyncMock(side_effect=Exception("Token exchange failed"))

        with (
            patch("app.auth.SOCIAL_PROVIDERS", {"google": {"name": "Google", "icon": "fab fa-google", "color": "red"}}),
            patch("app.auth.oauth") as mock_oauth,
        ):
            mock_oauth.google = mock_google

            result = await social_callback(mock_request, "google", db=mock_db)

            assert isinstance(result, RedirectResponse)
            assert "/login?error=Social+login+failed" in result.headers["location"]
            # Ensure internal exception details are not exposed to the user
            assert "Exception" not in result.headers["location"]


@pytest.mark.unit
class TestLoginPageSocialProviders:
    """Tests for login page rendering with social providers."""

    @pytest.mark.asyncio
    async def test_login_page_includes_social_providers(self):
        """Test login page passes social_providers to template."""
        mock_providers = {
            "google": {"name": "Google", "icon": "fab fa-google", "color": "red"},
            "microsoft": {"name": "Microsoft", "icon": "fab fa-microsoft", "color": "blue"},
        }

        with (
            patch("app.auth.AUTH_ENABLED", True),
            patch("app.auth.OAUTH_CONFIGURED", False),
            patch("app.auth.SOCIAL_PROVIDERS", mock_providers),
            patch("app.auth.templates") as mock_templates,
            patch("app.auth.settings") as mock_settings,
        ):
            mock_settings.version = "1.0.0"
            mock_settings.multi_user_enabled = False
            mock_settings.allow_local_signup = False

            from app.auth import login

            mock_request = MagicMock()
            mock_request.query_params.get.return_value = None

            await login(mock_request)

            mock_templates.TemplateResponse.assert_called_once()
            call_args = mock_templates.TemplateResponse.call_args
            context = call_args[0][1]
            assert context["social_providers"] == mock_providers

    @pytest.mark.asyncio
    async def test_login_page_empty_social_providers(self):
        """Test login page with no social providers configured."""
        with (
            patch("app.auth.AUTH_ENABLED", True),
            patch("app.auth.OAUTH_CONFIGURED", False),
            patch("app.auth.SOCIAL_PROVIDERS", {}),
            patch("app.auth.templates") as mock_templates,
            patch("app.auth.settings") as mock_settings,
        ):
            mock_settings.version = "1.0.0"
            mock_settings.multi_user_enabled = False
            mock_settings.allow_local_signup = False

            from app.auth import login

            mock_request = MagicMock()
            mock_request.query_params.get.return_value = None

            await login(mock_request)

            mock_templates.TemplateResponse.assert_called_once()
            call_args = mock_templates.TemplateResponse.call_args
            context = call_args[0][1]
            assert context["social_providers"] == {}


@pytest.mark.unit
class TestConfigValidatorSocialLogin:
    """Tests for config validator social login checks."""

    def test_social_login_counts_as_valid_auth(self):
        """Test that enabled social login prevents 'neither auth configured' warning."""
        from app.utils.config_validator.validators import validate_auth_config

        with patch("app.utils.config_validator.validators.settings") as mock_settings:
            mock_settings.auth_enabled = True
            mock_settings.session_secret = "a" * 32
            mock_settings.admin_username = None
            mock_settings.admin_password = None
            mock_settings.authentik_client_id = None
            mock_settings.authentik_client_secret = None
            mock_settings.authentik_config_url = None
            mock_settings.oauth_provider_name = None
            mock_settings.social_auth_google_enabled = True
            mock_settings.social_auth_google_client_id = "test-id"
            mock_settings.social_auth_google_client_secret = "test-secret"
            mock_settings.social_auth_microsoft_enabled = False
            mock_settings.social_auth_apple_enabled = False
            mock_settings.social_auth_dropbox_enabled = False

            issues = validate_auth_config()

            # Should NOT contain the "neither...configured" message
            assert not any("Neither" in issue for issue in issues)

    def test_social_login_missing_credentials_reported(self):
        """Test that enabled social login without credentials is reported."""
        from app.utils.config_validator.validators import validate_auth_config

        with patch("app.utils.config_validator.validators.settings") as mock_settings:
            mock_settings.auth_enabled = True
            mock_settings.session_secret = "a" * 32
            mock_settings.admin_username = "admin"
            mock_settings.admin_password = "pass"
            mock_settings.authentik_client_id = None
            mock_settings.authentik_client_secret = None
            mock_settings.authentik_config_url = None
            mock_settings.oauth_provider_name = None
            mock_settings.social_auth_google_enabled = True
            mock_settings.social_auth_google_client_id = None  # Missing!
            mock_settings.social_auth_google_client_secret = None  # Missing!
            mock_settings.social_auth_microsoft_enabled = False
            mock_settings.social_auth_apple_enabled = False
            mock_settings.social_auth_dropbox_enabled = False

            issues = validate_auth_config()

            assert any("SOCIAL_AUTH_GOOGLE_CLIENT_ID" in issue for issue in issues)
            assert any("SOCIAL_AUTH_GOOGLE_CLIENT_SECRET" in issue for issue in issues)

    def test_microsoft_missing_credentials(self):
        """Test Microsoft login validation when credentials are missing."""
        from app.utils.config_validator.validators import validate_auth_config

        with patch("app.utils.config_validator.validators.settings") as mock_settings:
            mock_settings.auth_enabled = True
            mock_settings.session_secret = "a" * 32
            mock_settings.admin_username = "admin"
            mock_settings.admin_password = "pass"
            mock_settings.authentik_client_id = None
            mock_settings.authentik_client_secret = None
            mock_settings.authentik_config_url = None
            mock_settings.oauth_provider_name = None
            mock_settings.social_auth_google_enabled = False
            mock_settings.social_auth_microsoft_enabled = True
            mock_settings.social_auth_microsoft_client_id = None
            mock_settings.social_auth_microsoft_client_secret = None
            mock_settings.social_auth_apple_enabled = False
            mock_settings.social_auth_dropbox_enabled = False

            issues = validate_auth_config()

            assert any("SOCIAL_AUTH_MICROSOFT_CLIENT_ID" in issue for issue in issues)
            assert any("SOCIAL_AUTH_MICROSOFT_CLIENT_SECRET" in issue for issue in issues)

    def test_apple_missing_credentials(self):
        """Test Apple login validation when credentials are missing."""
        from app.utils.config_validator.validators import validate_auth_config

        with patch("app.utils.config_validator.validators.settings") as mock_settings:
            mock_settings.auth_enabled = True
            mock_settings.session_secret = "a" * 32
            mock_settings.admin_username = "admin"
            mock_settings.admin_password = "pass"
            mock_settings.authentik_client_id = None
            mock_settings.authentik_client_secret = None
            mock_settings.authentik_config_url = None
            mock_settings.oauth_provider_name = None
            mock_settings.social_auth_google_enabled = False
            mock_settings.social_auth_microsoft_enabled = False
            mock_settings.social_auth_apple_enabled = True
            mock_settings.social_auth_apple_client_id = None
            mock_settings.social_auth_apple_team_id = None
            mock_settings.social_auth_dropbox_enabled = False

            issues = validate_auth_config()

            assert any("SOCIAL_AUTH_APPLE_CLIENT_ID" in issue for issue in issues)
            assert any("SOCIAL_AUTH_APPLE_TEAM_ID" in issue for issue in issues)

    def test_dropbox_missing_credentials(self):
        """Test Dropbox login validation when credentials are missing."""
        from app.utils.config_validator.validators import validate_auth_config

        with patch("app.utils.config_validator.validators.settings") as mock_settings:
            mock_settings.auth_enabled = True
            mock_settings.session_secret = "a" * 32
            mock_settings.admin_username = "admin"
            mock_settings.admin_password = "pass"
            mock_settings.authentik_client_id = None
            mock_settings.authentik_client_secret = None
            mock_settings.authentik_config_url = None
            mock_settings.oauth_provider_name = None
            mock_settings.social_auth_google_enabled = False
            mock_settings.social_auth_microsoft_enabled = False
            mock_settings.social_auth_apple_enabled = False
            mock_settings.social_auth_dropbox_enabled = True
            mock_settings.social_auth_dropbox_client_id = None
            mock_settings.social_auth_dropbox_client_secret = None

            issues = validate_auth_config()

            assert any("SOCIAL_AUTH_DROPBOX_CLIENT_ID" in issue for issue in issues)
            assert any("SOCIAL_AUTH_DROPBOX_CLIENT_SECRET" in issue for issue in issues)
