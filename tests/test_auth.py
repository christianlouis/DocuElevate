"""Tests for app/auth.py module."""

import hashlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request, status
from starlette.responses import RedirectResponse

from app.auth import get_current_user, get_gravatar_url, require_login

_TEST_CREDENTIAL = "test"  # noqa: S105


@pytest.mark.unit
class TestGetCurrentUser:
    """Tests for get_current_user function."""

    def test_returns_user_from_session(self):
        """Test that get_current_user returns user data from session."""
        mock_request = MagicMock(spec=Request)
        mock_request.session = {"user": {"id": "test_user", "name": "Test"}}
        result = get_current_user(mock_request)
        assert result == {"id": "test_user", "name": "Test"}

    def test_returns_none_when_no_user(self):
        """Test that get_current_user returns None when no user in session."""
        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        result = get_current_user(mock_request)
        assert result is None

    def test_returns_none_when_user_is_none(self):
        """Test that get_current_user returns None when user is None."""
        mock_request = MagicMock(spec=Request)
        mock_request.session = {"user": None}
        result = get_current_user(mock_request)
        assert result is None


@pytest.mark.unit
class TestGetGravatarUrl:
    """Tests for get_gravatar_url function."""

    def test_generates_correct_url(self):
        """Test gravatar URL generation with known email."""
        email = "test@example.com"
        expected_hash = hashlib.md5(email.lower().strip().encode("utf-8"), usedforsecurity=False).hexdigest()
        result = get_gravatar_url(email)
        assert result == f"https://www.gravatar.com/avatar/{expected_hash}?d=identicon"

    def test_handles_uppercase_email(self):
        """Test that email is lowercased."""
        result_upper = get_gravatar_url("TEST@EXAMPLE.COM")
        result_lower = get_gravatar_url("test@example.com")
        assert result_upper == result_lower

    def test_handles_whitespace(self):
        """Test that whitespace is stripped."""
        result_spaces = get_gravatar_url("  test@example.com  ")
        result_clean = get_gravatar_url("test@example.com")
        assert result_spaces == result_clean


@pytest.mark.unit
class TestRequireLogin:
    """Tests for require_login decorator."""

    def test_noop_when_auth_disabled(self):
        """Test that require_login is a no-op when AUTH_ENABLED is False."""

        # AUTH_ENABLED is False in test environment
        def my_func():
            return "hello"

        decorated = require_login(my_func)
        # When AUTH_ENABLED is False, the decorator returns the function unchanged
        assert decorated is my_func

    @pytest.mark.asyncio
    async def test_redirects_to_login_when_no_user(self):
        """Test that require_login redirects to /login when no user in session and auth is enabled."""
        with patch("app.auth.AUTH_ENABLED", True):
            # Import fresh to get patched AUTH_ENABLED
            from app.auth import require_login

            @require_login
            async def protected_endpoint(request: Request):
                return {"message": "success"}

            mock_request = MagicMock(spec=Request)
            mock_request.session = {}
            mock_request.url = MagicMock()
            mock_request.url.__str__ = MagicMock(return_value="http://test.com/protected")

            result = await protected_endpoint(mock_request)

            assert isinstance(result, RedirectResponse)
            assert result.status_code == status.HTTP_302_FOUND
            assert "/login" in str(result.headers.get("location"))

    @pytest.mark.asyncio
    async def test_saves_redirect_url_when_not_authenticated(self):
        """Test that require_login saves the original URL in session."""
        with patch("app.auth.AUTH_ENABLED", True):
            from app.auth import require_login

            @require_login
            async def protected_endpoint(request: Request):
                return {"message": "success"}

            mock_request = MagicMock(spec=Request)
            mock_request.session = {}
            mock_request.url = MagicMock()
            original_url = "http://test.com/protected/page?param=value"
            mock_request.url.__str__ = MagicMock(return_value=original_url)

            await protected_endpoint(mock_request)

            assert mock_request.session.get("redirect_after_login") == original_url

    @pytest.mark.asyncio
    async def test_allows_access_when_user_in_session(self):
        """Test that require_login allows access when user is in session."""
        with patch("app.auth.AUTH_ENABLED", True):
            from app.auth import require_login

            @require_login
            async def protected_endpoint(request: Request):
                return {"message": "success", "user": request.session.get("user")}

            mock_request = MagicMock(spec=Request)
            mock_request.session = {"user": {"id": "test_user", "name": "Test"}}

            result = await protected_endpoint(mock_request)

            assert result["message"] == "success"
            assert result["user"]["id"] == "test_user"

    @pytest.mark.asyncio
    async def test_handles_async_functions(self):
        """Test that require_login correctly wraps async functions."""
        with patch("app.auth.AUTH_ENABLED", True):
            from app.auth import require_login

            @require_login
            async def async_endpoint(request: Request, param: str):
                return {"message": "async", "param": param}

            mock_request = MagicMock(spec=Request)
            mock_request.session = {"user": {"id": "test"}}

            result = await async_endpoint(mock_request, param="test_value")

            assert result["message"] == "async"
            assert result["param"] == "test_value"

    def test_handles_sync_functions(self):
        """Test that require_login correctly wraps sync functions."""
        with patch("app.auth.AUTH_ENABLED", True):
            from app.auth import require_login

            @require_login
            def sync_endpoint(request: Request, param: str):
                return {"message": "sync", "param": param}

            mock_request = MagicMock(spec=Request)
            mock_request.session = {"user": {"id": "test"}}

            # Call the decorated sync function
            import asyncio

            result = asyncio.run(sync_endpoint(request=mock_request, param="test_value"))

            assert result["message"] == "sync"
            assert result["param"] == "test_value"


@pytest.mark.integration
class TestWhoamiEndpoint:
    """Tests for the /api/auth/whoami endpoint."""

    def test_whoami_returns_user_or_error(self, client):
        """Test whoami endpoint without auth (auth disabled)."""
        response = client.get("/api/auth/whoami")
        assert response.status_code == 200
        data = response.json()
        # When auth is disabled and no user in session, returns error dict
        assert "error" in data or "id" in data

    def test_private_endpoint(self, client):
        """Test /private endpoint without auth (auth disabled)."""
        response = client.get("/private")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data


@pytest.mark.integration
class TestAuthEndpoints:
    """Integration tests for authentication endpoints."""

    def test_login_page_not_available_when_auth_disabled(self, client):
        """Test that login page returns 404 when auth is disabled (default in tests)."""
        # In the test environment, AUTH_ENABLED is False by default
        response = client.get("/login")
        # When auth is disabled, the auth routes are not registered
        assert response.status_code == 404

    def test_oauth_login_not_available_when_auth_disabled(self, client):
        """Test that /oauth-login returns 404 when auth is disabled."""
        response = client.get("/oauth-login")
        assert response.status_code == 404

    def test_logout_not_available_when_auth_disabled(self, client):
        """Test that /logout returns 404 when auth is disabled."""
        response = client.get("/logout")
        assert response.status_code == 404

    def test_auth_post_not_available_when_auth_disabled(self, client):
        """Test that POST /auth returns 404 when auth is disabled."""
        response = client.post("/auth", data={"username": "admin", "password": _TEST_CREDENTIAL})
        assert response.status_code == 404


@pytest.mark.unit
class TestSessionValidation:
    """Tests for session validation edge cases."""

    def test_empty_user_object(self):
        """Test get_current_user with empty user object."""
        mock_request = MagicMock(spec=Request)
        mock_request.session = {"user": {}}
        result = get_current_user(mock_request)
        assert result == {}

    def test_user_object_missing_id(self):
        """Test session with user missing id field."""
        mock_request = MagicMock(spec=Request)
        mock_request.session = {"user": {"name": "Test", "email": "test@example.com"}}
        result = get_current_user(mock_request)
        # Should still return the user object even if id is missing
        assert result["name"] == "Test"
        assert "id" not in result

    def test_user_object_with_extra_fields(self):
        """Test session with user having extra fields."""
        mock_request = MagicMock(spec=Request)
        user = {
            "id": "123",
            "name": "Test",
            "email": "test@example.com",
            "is_admin": True,
            "groups": ["admin"],
            "picture": "https://example.com/pic.jpg",
        }
        mock_request.session = {"user": user}
        result = get_current_user(mock_request)
        assert result == user

    @pytest.mark.asyncio
    async def test_require_login_with_user_missing_required_fields(self):
        """Test require_login with user object missing typical fields."""
        with patch("app.auth.AUTH_ENABLED", True):
            from app.auth import require_login

            @require_login
            async def protected_endpoint(request: Request):
                return {"message": "success"}

            # User object exists but is minimal
            mock_request = MagicMock(spec=Request)
            mock_request.session = {"user": {"id": "123"}}  # Missing name, email, etc.

            result = await protected_endpoint(mock_request)

            # Should still allow access as long as user key exists
            assert result["message"] == "success"
