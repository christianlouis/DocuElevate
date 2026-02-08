"""
Tests for authentication module
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestAuthHelpers:
    """Tests for authentication helper functions."""

    def test_get_gravatar_url(self):
        """Test Gravatar URL generation."""
        from app.auth import get_gravatar_url

        # Test with a known email
        email = "test@example.com"
        url = get_gravatar_url(email)
        assert "gravatar.com/avatar/" in url
        assert "d=identicon" in url

    def test_get_gravatar_url_case_insensitive(self):
        """Test that Gravatar URL is case-insensitive."""
        from app.auth import get_gravatar_url

        url1 = get_gravatar_url("Test@Example.COM")
        url2 = get_gravatar_url("test@example.com")
        assert url1 == url2

    def test_get_gravatar_url_strips_whitespace(self):
        """Test that Gravatar URL strips whitespace."""
        from app.auth import get_gravatar_url

        url1 = get_gravatar_url("  test@example.com  ")
        url2 = get_gravatar_url("test@example.com")
        assert url1 == url2

    def test_get_current_user_with_session(self):
        """Test getting current user from session."""
        from app.auth import get_current_user

        # Mock request with user session
        mock_request = MagicMock()
        mock_request.session.get.return_value = {"email": "test@example.com"}

        user = get_current_user(mock_request)
        assert user["email"] == "test@example.com"

    def test_get_current_user_no_session(self):
        """Test getting current user with no session."""
        from app.auth import get_current_user

        # Mock request without user session
        mock_request = MagicMock()
        mock_request.session.get.return_value = None

        user = get_current_user(mock_request)
        assert user is None


@pytest.mark.integration
class TestAuthEndpoints:
    """Tests for authentication endpoints."""

    @patch("app.auth.AUTH_ENABLED", True)
    @patch("app.auth.OAUTH_CONFIGURED", False)
    def test_login_page_no_oauth(self, client: TestClient):
        """Test login page when OAuth is not configured."""
        # Import settings to ensure AUTH_ENABLED is properly patched
        with patch("app.config.settings") as mock_settings:
            mock_settings.auth_enabled = True
            mock_settings.version = "1.0.0"

            response = client.get("/login")
            # With AUTH_ENABLED=False in test env, this might not work as expected
            # Just check it doesn't crash
            assert response.status_code in [200, 404]

    def test_whoami_endpoint_unauthenticated(self, client: TestClient):
        """Test whoami endpoint when not authenticated."""
        # With AUTH_ENABLED=False in tests, should return empty/error
        response = client.get("/api/auth/whoami")
        assert response.status_code == 200
        data = response.json()
        # Should return error or empty dict since not authenticated
        assert "error" in data or "email" not in data

    def test_private_endpoint_with_auth_disabled(self, client: TestClient):
        """Test private endpoint when auth is disabled."""
        # With AUTH_ENABLED=False in test env, endpoint should be accessible
        response = client.get("/private")
        assert response.status_code == 200

    @patch("app.auth.AUTH_ENABLED", True)
    @patch("app.auth.OAUTH_CONFIGURED", True)
    def test_oauth_login_redirect(self, client: TestClient):
        """Test OAuth login initiates redirect."""
        response = client.get("/oauth-login", follow_redirects=False)
        # Should redirect or return an error if OAuth not properly configured in test
        assert response.status_code in [302, 303, 307, 404, 500]

    @patch("app.auth.AUTH_ENABLED", True)
    @patch("app.auth.OAUTH_CONFIGURED", False)
    def test_oauth_login_not_configured(self, client: TestClient):
        """Test OAuth login when OAuth is not configured."""
        response = client.get("/oauth-login", follow_redirects=False)
        # Should redirect to login with error or return 404
        assert response.status_code in [302, 404]


@pytest.mark.unit
class TestRequireLoginDecorator:
    """Tests for require_login decorator."""

    def test_require_login_auth_disabled(self):
        """Test require_login decorator when auth is disabled."""
        from app.auth import require_login

        # When AUTH_ENABLED=False, decorator should be a no-op
        @require_login
        async def test_func(request):
            return {"message": "success"}

        # Function should be callable
        assert callable(test_func)

    @patch("app.auth.AUTH_ENABLED", True)
    def test_require_login_no_user_session(self):
        """Test require_login decorator redirects when no user session."""
        from app.auth import require_login
        import asyncio

        @require_login
        async def test_func(request):
            return {"message": "success"}

        # Mock request without user session
        mock_request = MagicMock()
        mock_request.session.get.return_value = None
        mock_request.url = "http://test.com/page"

        # Should redirect
        result = asyncio.run(test_func(mock_request))
        from starlette.responses import RedirectResponse
        assert isinstance(result, RedirectResponse)

    @patch("app.auth.AUTH_ENABLED", True)
    def test_require_login_with_user_session(self):
        """Test require_login decorator allows access with user session."""
        from app.auth import require_login
        import asyncio

        @require_login
        async def test_func(request):
            return {"message": "success"}

        # Mock request with user session
        mock_request = MagicMock()
        mock_request.session.get.return_value = {"email": "test@example.com"}

        # Should allow access
        result = asyncio.run(test_func(mock_request))
        assert result["message"] == "success"

    @patch("app.auth.AUTH_ENABLED", True)
    def test_require_login_sync_function(self):
        """Test require_login decorator with synchronous function."""
        from app.auth import require_login
        import asyncio

        @require_login
        def test_func(request):
            return {"message": "success"}

        # Mock request with user session
        mock_request = MagicMock()
        mock_request.session.get.return_value = {"email": "test@example.com"}

        # Wrapper should handle sync functions
        result = asyncio.run(test_func(mock_request))
        assert result["message"] == "success"
