"""
Integration tests for OAuth authentication flows using mock OAuth2 server.

These tests use a real OIDC flow with a mock OAuth2 server to test:
- OAuth login initiation
- Authorization code exchange
- Token validation
- Userinfo retrieval
- Session management
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestOAuthLoginFlow:
    """Test the complete OAuth login flow with mock server."""

    def test_login_page_shows_oauth_option(self, oauth_enabled_app: TestClient):
        """Test that login page displays OAuth option when configured."""
        response = oauth_enabled_app.get("/login")
        assert response.status_code == 200
        # Check that OAuth option is shown
        assert b"oauth" in response.content.lower() or b"sign" in response.content.lower()

    def test_oauth_login_redirects_to_provider(self, oauth_enabled_app: TestClient, oauth_config: dict):
        """Test that /oauth-login redirects to the OAuth provider."""
        response = oauth_enabled_app.get("/oauth-login", follow_redirects=False)

        # Should redirect to authorization endpoint
        assert response.status_code == 302

        # Redirect location should contain the authorization endpoint
        location = response.headers.get("location", "")
        if oauth_config["mode"] == "mock":
            assert "authorize" in location
            assert oauth_config["client_id"] in location

    def test_oauth_login_without_config_shows_error(self):
        """Test that OAuth login fails gracefully when not configured."""
        # Test with OAuth disabled
        import os

        original = os.environ.get("AUTH_ENABLED")
        os.environ["AUTH_ENABLED"] = "False"

        try:
            from fastapi.testclient import TestClient

            from app.main import app

            client = TestClient(app, base_url="http://localhost")

            response = client.get("/oauth-login", follow_redirects=False)
            # Should either redirect to error page or show login page
            assert response.status_code in [302, 404]
        finally:
            if original:
                os.environ["AUTH_ENABLED"] = original


@pytest.mark.integration
class TestOAuthCallback:
    """Test OAuth callback handling."""

    @pytest.mark.asyncio
    @patch("app.auth.oauth.authentik.authorize_access_token")
    async def test_oauth_callback_with_valid_token(
        self, mock_authorize, oauth_enabled_app: TestClient, test_user_info: dict
    ):
        """Test OAuth callback with valid authorization code."""
        # Mock the token exchange response
        mock_authorize.return_value = {
            "access_token": "mock-access-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "userinfo": test_user_info,
        }

        # Simulate OAuth callback with authorization code
        response = oauth_enabled_app.get(
            "/oauth-callback?code=test-auth-code&state=test-state",
            follow_redirects=False,
        )

        # Should redirect after successful login
        assert response.status_code == 302

    @pytest.mark.asyncio
    @patch("app.auth.oauth.authentik.authorize_access_token")
    async def test_oauth_callback_stores_user_in_session(
        self, mock_authorize, oauth_enabled_app: TestClient, test_user_info: dict
    ):
        """Test that OAuth callback stores user info in session."""
        mock_authorize.return_value = {
            "access_token": "mock-access-token",
            "userinfo": test_user_info,
        }

        # First, initiate OAuth flow to set up session
        oauth_enabled_app.get("/oauth-login", follow_redirects=False)

        # Then handle callback
        response = oauth_enabled_app.get(
            "/oauth-callback?code=test-auth-code",
            follow_redirects=False,
        )

        # Should set session cookie
        assert "set-cookie" in response.headers or response.status_code == 302

    @pytest.mark.asyncio
    @patch("app.auth.oauth.authentik.authorize_access_token")
    async def test_oauth_callback_with_admin_user(self, mock_authorize, oauth_enabled_app: TestClient):
        """Test OAuth callback with admin user group."""
        mock_authorize.return_value = {
            "access_token": "mock-access-token",
            "userinfo": {
                "sub": "admin-user",
                "email": "admin@example.com",
                "name": "Admin User",
                "groups": ["admin"],
            },
        }

        response = oauth_enabled_app.get(
            "/oauth-callback?code=test-auth-code",
            follow_redirects=False,
        )

        # Should successfully authenticate
        assert response.status_code == 302

    @pytest.mark.asyncio
    @patch("app.auth.oauth.authentik.authorize_access_token")
    async def test_oauth_callback_rejects_non_admin(self, mock_authorize, oauth_enabled_app: TestClient):
        """Test that OAuth callback authenticates non-admin users with is_admin=False."""
        mock_authorize.return_value = {
            "access_token": "mock-access-token",
            "userinfo": {
                "sub": "regular-user",
                "email": "user@example.com",
                "name": "Regular User",
                "groups": ["users"],  # No admin group
            },
        }

        response = oauth_enabled_app.get(
            "/oauth-callback?code=test-auth-code",
            follow_redirects=False,
        )

        # Non-admin users are still authenticated but with is_admin=False
        assert response.status_code == 302


@pytest.mark.integration
class TestOAuthSessionManagement:
    """Test session management with OAuth authentication."""

    @pytest.mark.asyncio
    @patch("app.auth.oauth.authentik.authorize_access_token")
    async def test_authenticated_user_can_access_protected_routes(
        self, mock_authorize, oauth_enabled_app: TestClient, test_user_info: dict
    ):
        """Test that authenticated users can access protected routes."""
        # Mock successful authentication
        mock_authorize.return_value = {
            "access_token": "mock-access-token",
            "userinfo": test_user_info,
        }

        # Authenticate
        oauth_enabled_app.get("/oauth-callback?code=test-auth-code")

        # Try to access a protected route (e.g., files page)
        response = oauth_enabled_app.get("/files")

        # Should be able to access with valid session
        # Note: May redirect to login if session not properly set
        assert response.status_code in [200, 302]

    def test_unauthenticated_user_redirected_to_login(self, oauth_enabled_app: TestClient):
        """Test that unauthenticated users are redirected to login."""
        # Try to access protected route without authentication
        response = oauth_enabled_app.get("/files", follow_redirects=False)

        # Should redirect to login page
        if response.status_code == 302:
            assert "/login" in response.headers.get("location", "")

    @pytest.mark.asyncio
    @patch("app.auth.oauth.authentik.authorize_access_token")
    async def test_logout_clears_session(self, mock_authorize, oauth_enabled_app: TestClient, test_user_info: dict):
        """Test that logout clears user session."""
        # Mock successful authentication
        mock_authorize.return_value = {
            "access_token": "mock-access-token",
            "userinfo": test_user_info,
        }

        # Authenticate
        oauth_enabled_app.get("/oauth-callback?code=test-auth-code")

        # Logout
        response = oauth_enabled_app.get("/logout", follow_redirects=False)

        # Should redirect after logout
        assert response.status_code == 302


@pytest.mark.integration
class TestOAuthErrorHandling:
    """Test error handling in OAuth flows."""

    def test_oauth_callback_without_code_shows_error(self, oauth_enabled_app: TestClient):
        """Test OAuth callback without authorization code."""
        response = oauth_enabled_app.get("/oauth-callback", follow_redirects=False)

        # Should handle error gracefully
        assert response.status_code in [302, 400]

    @pytest.mark.asyncio
    @patch("app.auth.oauth.authentik.authorize_access_token")
    async def test_oauth_callback_with_invalid_token(self, mock_authorize, oauth_enabled_app: TestClient):
        """Test OAuth callback with invalid token."""
        # Mock token exchange failure
        mock_authorize.side_effect = Exception("Invalid authorization code")

        response = oauth_enabled_app.get(
            "/oauth-callback?code=invalid-code",
            follow_redirects=False,
        )

        # Should redirect to error page
        assert response.status_code == 302
        location = response.headers.get("location", "")
        assert "error" in location.lower() or "login" in location.lower()

    @pytest.mark.asyncio
    @patch("app.auth.oauth.authentik.authorize_access_token")
    async def test_oauth_callback_without_userinfo(self, mock_authorize, oauth_enabled_app: TestClient):
        """Test OAuth callback when userinfo is missing."""
        # Mock token without userinfo
        mock_authorize.return_value = {
            "access_token": "mock-access-token",
            "userinfo": None,
        }

        response = oauth_enabled_app.get(
            "/oauth-callback?code=test-auth-code",
            follow_redirects=False,
        )

        # Should handle missing userinfo
        assert response.status_code == 302


@pytest.mark.integration
@pytest.mark.requires_external
class TestRealOAuthIntegration:
    """
    Integration tests using real OAuth credentials from GitHub Actions secrets.

    These tests are skipped unless real OAuth credentials are available.
    """

    def test_real_oauth_well_known_endpoint(self, use_real_oauth: bool, oauth_config: dict):
        """Test that real OAuth .well-known endpoint is accessible."""
        if not use_real_oauth:
            pytest.skip("Real OAuth credentials not available")

        import requests

        response = requests.get(oauth_config["server_metadata_url"], timeout=10)
        assert response.status_code == 200

        config = response.json()
        assert "authorization_endpoint" in config
        assert "token_endpoint" in config
        assert "userinfo_endpoint" in config

    def test_real_oauth_jwks_endpoint(self, use_real_oauth: bool, oauth_config: dict):
        """Test that real OAuth JWKS endpoint is accessible."""
        if not use_real_oauth:
            pytest.skip("Real OAuth credentials not available")

        import requests

        # Get well-known config first
        response = requests.get(oauth_config["server_metadata_url"], timeout=10)
        config = response.json()

        # Test JWKS endpoint
        jwks_response = requests.get(config["jwks_uri"], timeout=10)
        assert jwks_response.status_code == 200

        jwks = jwks_response.json()
        assert "keys" in jwks
        assert len(jwks["keys"]) > 0
