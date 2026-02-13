"""Comprehensive unit tests for app/auth.py module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request, status
from starlette.responses import RedirectResponse

from app.auth import get_current_user, get_gravatar_url, require_login


@pytest.mark.unit
class TestGetCurrentUser:
    """Tests for get_current_user function."""

    def test_returns_user_from_session(self):
        """Test returns user data from request session."""
        mock_request = MagicMock(spec=Request)
        mock_request.session = {"user": {"id": "123", "name": "John Doe", "email": "john@example.com"}}

        result = get_current_user(mock_request)

        assert result == {"id": "123", "name": "John Doe", "email": "john@example.com"}

    def test_returns_none_when_no_user_in_session(self):
        """Test returns None when no user in session."""
        mock_request = MagicMock(spec=Request)
        mock_request.session = {}

        result = get_current_user(mock_request)

        assert result is None


@pytest.mark.unit
class TestGetGravatarUrl:
    """Tests for get_gravatar_url function."""

    def test_generates_gravatar_url(self):
        """Test generates correct Gravatar URL."""
        email = "test@example.com"
        result = get_gravatar_url(email)

        assert result.startswith("https://www.gravatar.com/avatar/")
        assert "?d=identicon" in result

    def test_handles_uppercase_email(self):
        """Test handles uppercase email correctly."""
        email1 = "Test@Example.COM"
        email2 = "test@example.com"

        result1 = get_gravatar_url(email1)
        result2 = get_gravatar_url(email2)

        # Should produce the same hash for case-insensitive emails
        assert result1 == result2

    def test_strips_whitespace(self):
        """Test strips whitespace from email."""
        email1 = "  test@example.com  "
        email2 = "test@example.com"

        result1 = get_gravatar_url(email1)
        result2 = get_gravatar_url(email2)

        assert result1 == result2

    def test_hash_is_md5(self):
        """Test that the hash is MD5 (32 hexadecimal characters)."""
        email = "test@example.com"
        result = get_gravatar_url(email)

        # Extract hash from URL
        hash_part = result.split("/avatar/")[1].split("?")[0]
        assert len(hash_part) == 32
        assert all(c in "0123456789abcdef" for c in hash_part)


@pytest.mark.unit
class TestRequireLogin:
    """Tests for require_login decorator."""

    @pytest.mark.asyncio
    async def test_allows_access_when_auth_disabled(self):
        """Test allows access when AUTH_ENABLED is False."""
        with patch("app.auth.AUTH_ENABLED", False):

            @require_login
            async def test_endpoint(request: Request):
                return {"message": "success"}

            mock_request = MagicMock(spec=Request)
            mock_request.session = {}

            result = await test_endpoint(mock_request)

            assert result == {"message": "success"}

    @pytest.mark.asyncio
    async def test_allows_access_when_user_logged_in(self):
        """Test allows access when user is logged in."""
        with patch("app.auth.AUTH_ENABLED", True):

            @require_login
            async def test_endpoint(request: Request):
                return {"message": "success"}

            mock_request = MagicMock(spec=Request)
            mock_request.session = {"user": {"id": "123", "name": "John"}}
            mock_request.url = "http://localhost/test"

            result = await test_endpoint(mock_request)

            assert result == {"message": "success"}

    @pytest.mark.asyncio
    async def test_redirects_to_login_when_not_authenticated(self):
        """Test redirects to login when user is not authenticated."""
        with patch("app.auth.AUTH_ENABLED", True):

            @require_login
            async def test_endpoint(request: Request):
                return {"message": "success"}

            mock_request = MagicMock(spec=Request)
            mock_request.session = {}
            mock_request.url = "http://localhost/protected"

            result = await test_endpoint(mock_request)

            assert isinstance(result, RedirectResponse)
            assert result.status_code == status.HTTP_302_FOUND
            assert "/login" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_saves_redirect_url_in_session(self):
        """Test saves redirect URL in session before redirecting to login."""
        with patch("app.auth.AUTH_ENABLED", True):

            @require_login
            async def test_endpoint(request: Request):
                return {"message": "success"}

            mock_request = MagicMock(spec=Request)
            mock_request.session = {}
            mock_request.url = "http://localhost/protected/page"

            result = await test_endpoint(mock_request)

            assert "redirect_after_login" in mock_request.session
            assert mock_request.session["redirect_after_login"] == "http://localhost/protected/page"

    @pytest.mark.asyncio
    async def test_works_with_sync_functions(self):
        """Test decorator works with synchronous functions."""
        with patch("app.auth.AUTH_ENABLED", True):

            @require_login
            def test_sync_endpoint(request: Request):
                return {"message": "success"}

            mock_request = MagicMock(spec=Request)
            mock_request.session = {"user": {"id": "123"}}
            mock_request.url = "http://localhost/test"

            result = await test_sync_endpoint(mock_request)

            assert result == {"message": "success"}

    @pytest.mark.asyncio
    async def test_redirects_sync_function_when_not_authenticated(self):
        """Test redirects synchronous functions when not authenticated."""
        with patch("app.auth.AUTH_ENABLED", True):

            @require_login
            def test_sync_endpoint(request: Request):
                return {"message": "success"}

            mock_request = MagicMock(spec=Request)
            mock_request.session = {}
            mock_request.url = "http://localhost/protected"

            result = await test_sync_endpoint(mock_request)

            assert isinstance(result, RedirectResponse)
            assert result.status_code == status.HTTP_302_FOUND


@pytest.mark.unit
class TestOAuthConfiguration:
    """Tests for OAuth configuration."""

    def test_oauth_not_configured_without_credentials(self):
        """Test OAuth is not configured when credentials are missing."""
        import importlib

        import app.auth

        try:
            with patch("app.config.settings") as mock_settings:
                mock_settings.auth_enabled = True
                mock_settings.authentik_client_id = None
                mock_settings.authentik_client_secret = None

                importlib.reload(app.auth)

                assert app.auth.OAUTH_CONFIGURED is False
        finally:
            importlib.reload(app.auth)

    def test_oauth_configured_with_credentials(self):
        """Test OAuth is configured when credentials are provided."""
        import importlib

        import app.auth

        try:
            with patch("app.config.settings") as mock_settings:
                mock_settings.auth_enabled = True
                mock_settings.authentik_client_id = "test_client_id"
                mock_settings.authentik_client_secret = "test_secret"
                mock_settings.authentik_config_url = "https://auth.example.com/.well-known/openid-configuration"
                mock_settings.oauth_provider_name = "Test SSO"

                importlib.reload(app.auth)

                assert app.auth.OAUTH_CONFIGURED is True
                assert app.auth.OAUTH_PROVIDER_NAME == "Test SSO"
        finally:
            importlib.reload(app.auth)


@pytest.mark.unit
class TestLoginEndpoint:
    """Tests for login endpoint (when AUTH_ENABLED)."""

    @pytest.mark.asyncio
    async def test_login_page_shows_oauth_when_configured(self):
        """Test login page shows OAuth option when configured."""
        with patch("app.auth.AUTH_ENABLED", True):
            with patch("app.auth.OAUTH_CONFIGURED", True):
                with patch("app.auth.OAUTH_PROVIDER_NAME", "Test SSO"):
                    with patch("app.auth.templates") as mock_templates:
                        with patch("app.auth.settings") as mock_settings:
                            mock_settings.version = "1.0.0"

                            from app.auth import login

                            mock_request = MagicMock()
                            mock_request.query_params.get.return_value = None

                            await login(mock_request)

                            # Verify template was rendered with OAuth enabled
                            mock_templates.TemplateResponse.assert_called_once()
                            call_args = mock_templates.TemplateResponse.call_args
                            context = call_args[0][1]
                            assert context["show_oauth"] is True
                            assert context["oauth_provider_name"] == "Test SSO"


@pytest.mark.unit
class TestAuthEndpoint:
    """Tests for local authentication endpoint."""

    @pytest.mark.asyncio
    async def test_successful_authentication(self):
        """Test successful local authentication."""
        with patch("app.auth.AUTH_ENABLED", True):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.admin_username = "admin"
                mock_settings.admin_password = "secret123"

                from app.auth import auth

                mock_request = MagicMock()
                mock_form_data = {"username": "admin", "password": "secret123"}
                mock_request.form = AsyncMock(return_value=mock_form_data)
                mock_request.session = {}

                result = await auth(mock_request)

                # Verify redirect to upload page
                assert isinstance(result, RedirectResponse)
                assert result.status_code == 302

                # Verify user was added to session
                assert "user" in mock_request.session
                assert mock_request.session["user"]["id"] == "admin"
                assert mock_request.session["user"]["is_admin"] is True

    @pytest.mark.asyncio
    async def test_failed_authentication(self):
        """Test failed authentication with wrong credentials."""
        with patch("app.auth.AUTH_ENABLED", True):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.admin_username = "admin"
                mock_settings.admin_password = "secret123"

                from app.auth import auth

                mock_request = MagicMock()
                mock_form_data = {"username": "admin", "password": "wrong_password"}
                mock_request.form = AsyncMock(return_value=mock_form_data)
                mock_request.session = {}

                result = await auth(mock_request)

                # Verify redirect to login with error
                assert isinstance(result, RedirectResponse)
                assert "error=Invalid" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_authentication_with_redirect_after_login(self):
        """Test authentication redirects to saved URL after login."""
        with patch("app.auth.AUTH_ENABLED", True):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.admin_username = "admin"
                mock_settings.admin_password = "secret123"

                from app.auth import auth

                mock_request = MagicMock()
                mock_form_data = {"username": "admin", "password": "secret123"}
                mock_request.form = AsyncMock(return_value=mock_form_data)
                mock_request.session = {"redirect_after_login": "/protected/page"}

                result = await auth(mock_request)

                # Verify redirect to saved URL
                assert isinstance(result, RedirectResponse)
                assert "/protected/page" in result.headers["location"]

                # Verify redirect_after_login was removed from session
                assert "redirect_after_login" not in mock_request.session


@pytest.mark.unit
class TestOAuthCallback:
    """Tests for OAuth callback endpoint."""

    @pytest.mark.asyncio
    async def test_oauth_callback_not_available_when_not_configured(self):
        """Test OAuth callback returns error when OAuth not configured."""
        with patch("app.auth.AUTH_ENABLED", True):
            with patch("app.auth.OAUTH_CONFIGURED", False):
                from app.auth import oauth_login

                mock_request = MagicMock()

                result = await oauth_login(mock_request)

                # Should redirect to login with error
                assert isinstance(result, RedirectResponse)
                assert "error=OAuth+not+configured" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_oauth_callback_successful_authentication(self):
        """Test OAuth callback with successful authentication."""
        with patch("app.auth.AUTH_ENABLED", True):
            with patch("app.auth.OAUTH_CONFIGURED", True):
                with patch("app.auth.oauth") as mock_oauth:
                    with patch("app.auth.settings") as mock_settings:
                        mock_settings.admin_group_name = "admin"

                        # Mock OAuth token response
                        mock_token = {
                            "userinfo": {
                                "sub": "user123",
                                "name": "John Doe",
                                "email": "john@example.com",
                                "preferred_username": "johndoe",
                                "groups": ["admin", "users"],
                            }
                        }
                        mock_oauth.authentik.authorize_access_token = AsyncMock(return_value=mock_token)

                        from app.auth import oauth_callback

                        mock_request = MagicMock()
                        mock_request.session = {}

                        result = await oauth_callback(mock_request)

                        # Verify user was added to session
                        assert "user" in mock_request.session
                        assert mock_request.session["user"]["email"] == "john@example.com"
                        assert mock_request.session["user"]["is_admin"] is True

                        # Verify redirect
                        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_oauth_callback_non_admin_user(self):
        """Test OAuth callback for non-admin user."""
        with patch("app.auth.AUTH_ENABLED", True):
            with patch("app.auth.OAUTH_CONFIGURED", True):
                with patch("app.auth.oauth") as mock_oauth:
                    with patch("app.auth.settings") as mock_settings:
                        mock_settings.admin_group_name = "admin"

                        # Mock OAuth token response without admin group
                        mock_token = {
                            "userinfo": {
                                "sub": "user456",
                                "name": "Jane Doe",
                                "email": "jane@example.com",
                                "preferred_username": "janedoe",
                                "groups": ["users"],  # Not admin
                            }
                        }
                        mock_oauth.authentik.authorize_access_token = AsyncMock(return_value=mock_token)

                        from app.auth import oauth_callback

                        mock_request = MagicMock()
                        mock_request.session = {}

                        result = await oauth_callback(mock_request)

                        # Verify user is not admin
                        assert mock_request.session["user"]["is_admin"] is False

    @pytest.mark.asyncio
    async def test_oauth_callback_adds_gravatar_when_no_picture(self):
        """Test OAuth callback adds Gravatar when no picture provided."""
        with patch("app.auth.AUTH_ENABLED", True):
            with patch("app.auth.OAUTH_CONFIGURED", True):
                with patch("app.auth.oauth") as mock_oauth:
                    with patch("app.auth.settings") as mock_settings:
                        mock_settings.admin_group_name = "admin"

                        # Mock OAuth token response without picture
                        mock_token = {
                            "userinfo": {
                                "sub": "user789",
                                "name": "Bob Smith",
                                "email": "bob@example.com",
                                "preferred_username": "bobsmith",
                                # No picture field
                            }
                        }
                        mock_oauth.authentik.authorize_access_token = AsyncMock(return_value=mock_token)

                        from app.auth import oauth_callback

                        mock_request = MagicMock()
                        mock_request.session = {}

                        result = await oauth_callback(mock_request)

                        # Verify Gravatar was added
                        assert "picture" in mock_request.session["user"]
                        assert "gravatar.com/avatar/" in mock_request.session["user"]["picture"]


@pytest.mark.unit
class TestLogoutEndpoint:
    """Tests for logout endpoint."""

    @pytest.mark.asyncio
    async def test_logout_clears_session(self):
        """Test logout clears user from session."""
        with patch("app.auth.AUTH_ENABLED", True):
            from app.auth import logout

            mock_request = MagicMock()
            mock_request.session = {"user": {"id": "123", "name": "John"}}

            result = await logout(mock_request)

            # Verify user was removed from session
            assert "user" not in mock_request.session

            # Verify redirect to login with message
            assert isinstance(result, RedirectResponse)
            assert "message=You+have+been+logged+out" in result.headers["location"]


@pytest.mark.unit
class TestWhoAmIEndpoint:
    """Tests for whoami API endpoint."""

    @pytest.mark.asyncio
    async def test_whoami_returns_user_when_authenticated(self):
        """Test whoami returns user data when authenticated."""
        from app.auth import whoami

        mock_request = MagicMock()
        user_data = {"id": "123", "name": "John Doe", "email": "john@example.com"}
        mock_request.session = {"user": user_data}

        # Since require_login is applied, we need to bypass it for this test
        with patch("app.auth.AUTH_ENABLED", False):
            result = await whoami(mock_request)

            assert result == user_data

    @pytest.mark.asyncio
    async def test_whoami_returns_error_when_not_authenticated(self):
        """Test whoami returns error when not authenticated."""
        from app.auth import whoami

        mock_request = MagicMock()
        mock_request.session = {}

        with patch("app.auth.AUTH_ENABLED", False):
            result = await whoami(mock_request)

            assert result == {"error": "Not authenticated"}
