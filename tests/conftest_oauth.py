"""
Pytest fixtures for OAuth/OIDC testing.

Provides fixtures for:
- Mock OAuth2 server (using testcontainers)
- Real OAuth credentials (from environment/GitHub Actions secrets)
- OAuth test helpers
"""

import logging
import os
from typing import Dict, Generator, Optional

import pytest

from tests.mock_oauth_server import MockOAuth2ServerContainer, create_test_userinfo

# Check if we should use real OAuth credentials from environment
_REAL_OAUTH_AVAILABLE = all(
    [
        os.environ.get("AUTHENTIK_CLIENT_ID") not in {"", "NOT_SET", "test-key", None},
        os.environ.get("AUTHENTIK_CLIENT_SECRET") not in {"", "NOT_SET", "test-key", None},
        os.environ.get("AUTHENTIK_CONFIG_URL") not in {"", "NOT_SET", "test-key", None},
    ]
)

# Static fallback OAuth endpoint constants used when Docker is unavailable
_STATIC_OAUTH_AUTHORIZE_URL = "http://mock-oauth.test/default/authorize"
_STATIC_OAUTH_TOKEN_URL = "http://mock-oauth.test/default/token"
_STATIC_OAUTH_USERINFO_URL = "http://mock-oauth.test/default/userinfo"
_STATIC_OAUTH_JWKS_URL = "http://mock-oauth.test/default/jwks"
_STATIC_OAUTH_ISSUER = "http://mock-oauth.test/default"


@pytest.fixture(scope="session")
def use_real_oauth() -> bool:
    """
    Determine if tests should use real OAuth credentials.

    Returns True if valid OAuth credentials are available in the environment
    (typically from GitHub Actions secrets).

    Returns:
        bool: True if real OAuth should be used, False for mock
    """
    # Can be overridden with environment variable
    if os.environ.get("USE_REAL_OAUTH", "").lower() in ("true", "1", "yes"):
        return True
    if os.environ.get("USE_MOCK_OAUTH", "").lower() in ("true", "1", "yes"):
        return False

    return _REAL_OAUTH_AVAILABLE


@pytest.fixture(scope="session")
def mock_oauth_server() -> Generator[Optional[MockOAuth2ServerContainer], None, None]:
    """
    Provide a mock OAuth2/OIDC server for testing.

    This fixture starts a mock-oauth2-server container that provides
    a complete OIDC provider with all necessary endpoints.

    Yields:
        MockOAuth2ServerContainer: Running mock OAuth server, or None if Docker is unavailable
    """
    # Only start if we're not using real OAuth
    if not _REAL_OAUTH_AVAILABLE or os.environ.get("USE_MOCK_OAUTH", "").lower() in ("true", "1", "yes"):
        container = None
        try:
            container = MockOAuth2ServerContainer()
            container.start()
            # Wait for the server to be ready
            container.wait_for_ready()
        except Exception as exc:
            # Docker not accessible or image pull failed – fall back to static mock config.
            # Attempt cleanup in case the container was partially started.
            if container is not None:
                try:
                    container.stop()
                except Exception:  # noqa: BLE001
                    pass
            logging.getLogger(__name__).warning(
                "Mock OAuth2 server unavailable (Docker inaccessible): %s – using static fallback config", exc
            )
            yield None
            return

        try:
            yield container
        finally:
            container.stop()
    else:
        pytest.skip("Using real OAuth credentials, mock server not needed")


@pytest.fixture(scope="session")
def oauth_config(mock_oauth_server: Optional[MockOAuth2ServerContainer], use_real_oauth: bool) -> Dict[str, str]:
    """
    Provide OAuth configuration for tests.

    Returns either mock OAuth config or real OAuth config based on availability.

    Args:
        mock_oauth_server: Mock OAuth server fixture (None if Docker unavailable)
        use_real_oauth: Whether to use real OAuth credentials

    Returns:
        Dictionary with OAuth configuration
    """
    if use_real_oauth and _REAL_OAUTH_AVAILABLE:
        # Use real OAuth credentials from environment
        return {
            "client_id": os.environ["AUTHENTIK_CLIENT_ID"],
            "client_secret": os.environ["AUTHENTIK_CLIENT_SECRET"],
            "server_metadata_url": os.environ["AUTHENTIK_CONFIG_URL"],
            "issuer": os.environ["AUTHENTIK_CONFIG_URL"].replace("/.well-known/openid-configuration", ""),
            "mode": "real",
        }
    elif mock_oauth_server is None:
        # Docker unavailable – use a static in-process mock configuration so
        # tests that mock the OAuth token exchange still work without a container.
        return {
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "server_metadata_url": f"{_STATIC_OAUTH_ISSUER}/.well-known/openid-configuration",
            "authorization_endpoint": _STATIC_OAUTH_AUTHORIZE_URL,
            "token_endpoint": _STATIC_OAUTH_TOKEN_URL,
            "userinfo_endpoint": _STATIC_OAUTH_USERINFO_URL,
            "jwks_uri": _STATIC_OAUTH_JWKS_URL,
            "issuer": _STATIC_OAUTH_ISSUER,
            "mode": "static",
        }
    else:
        # Use mock OAuth server
        config = mock_oauth_server.get_config()
        return {
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "server_metadata_url": config["well_known_url"],
            "issuer": config["issuer"],
            "token_endpoint": config["token_endpoint"],
            "authorization_endpoint": config["authorization_endpoint"],
            "userinfo_endpoint": config["userinfo_endpoint"],
            "jwks_uri": config["jwks_uri"],
            "mode": "mock",
        }


@pytest.fixture
def test_user_info() -> Dict:
    """
    Provide test user information for OAuth flows.

    Returns:
        Dictionary with test user claims
    """
    return create_test_userinfo(
        sub="test-user-123",
        email="testuser@example.com",
        name="Test User",
        preferred_username="testuser",
        groups=["admin"],
    )


@pytest.fixture
def oauth_test_token(
    mock_oauth_server: Optional[MockOAuth2ServerContainer],
    test_user_info: Dict,
    use_real_oauth: bool,
) -> Optional[str]:
    """
    Generate a test OAuth token.

    For mock mode: Creates a valid JWT from the mock server.
    For real mode: Skips (would need real authentication flow).

    Args:
        mock_oauth_server: Mock OAuth server
        test_user_info: User information to include in token
        use_real_oauth: Whether using real OAuth

    Returns:
        JWT token string or None if using real OAuth
    """
    if use_real_oauth:
        # Can't generate tokens for real OAuth - would need actual auth flow
        return None

    if mock_oauth_server is None:
        pytest.fail("Mock OAuth server not available")

    # Create a token with the test user info
    return mock_oauth_server.create_token(
        subject=test_user_info["sub"],
        claims={
            "email": test_user_info["email"],
            "name": test_user_info["name"],
            "preferred_username": test_user_info["preferred_username"],
            "groups": test_user_info["groups"],
        },
        audience="test-client-id",
    )


@pytest.fixture
def oauth_enabled_app(oauth_config: Dict[str, str]):
    """
    Configure the FastAPI app with OAuth enabled for testing.

    This fixture temporarily enables OAuth and configures it with the
    test OAuth provider (mock or real).

    Args:
        oauth_config: OAuth configuration

    Yields:
        Configured test client
    """

    import app.auth as auth_module
    from app.auth import auth, login, logout, oauth_callback, oauth_login
    from app.main import app

    # Save original state
    original_auth_enabled = auth_module.AUTH_ENABLED
    original_oauth_configured = auth_module.OAUTH_CONFIGURED
    original_oauth_provider = auth_module.OAUTH_PROVIDER_NAME
    original_route_count = len(app.router.routes)

    try:
        # Enable auth and configure OAuth flags
        auth_module.AUTH_ENABLED = True
        auth_module.OAUTH_CONFIGURED = True
        auth_module.OAUTH_PROVIDER_NAME = oauth_config.get("provider_name", "Test SSO")

        # Clear any previously cached client so the new params take effect.
        # authlib caches created clients in _clients; we must evict before re-registering.
        auth_module.oauth._clients.pop("authentik", None)
        auth_module.oauth._registry.pop("authentik", None)

        # Register OAuth client using direct endpoint URLs to avoid HTTP metadata
        # discovery – this allows tests to work without a running OAuth server.
        auth_module.oauth.register(
            name="authentik",
            client_id=oauth_config["client_id"],
            client_secret=oauth_config["client_secret"],
            authorize_url=oauth_config.get("authorization_endpoint", _STATIC_OAUTH_AUTHORIZE_URL),
            access_token_url=oauth_config.get("token_endpoint", _STATIC_OAUTH_TOKEN_URL),
            client_kwargs={"scope": "openid profile email"},
        )

        # Add auth routes directly to the app (since include_router was called at startup
        # with AUTH_ENABLED=False, routes weren't registered)
        app.add_api_route("/login", login, methods=["GET"])
        app.add_api_route("/oauth-login", oauth_login, methods=["GET"])
        app.add_api_route("/oauth-callback", oauth_callback, methods=["GET"], name="oauth_callback")
        app.add_api_route("/auth", auth, methods=["POST"])
        app.add_api_route("/logout", logout, methods=["GET"])

        from fastapi.testclient import TestClient

        # Create test client with base_url to satisfy TrustedHostMiddleware
        client = TestClient(app, base_url="http://localhost")

        yield client

    finally:
        # Restore original auth state
        auth_module.AUTH_ENABLED = original_auth_enabled
        auth_module.OAUTH_CONFIGURED = original_oauth_configured
        auth_module.OAUTH_PROVIDER_NAME = original_oauth_provider

        # Remove added routes
        app.router.routes = app.router.routes[:original_route_count]

        # Clean up OAuth registration to avoid cross-test contamination
        auth_module.oauth._clients.pop("authentik", None)
        auth_module.oauth._registry.pop("authentik", None)
