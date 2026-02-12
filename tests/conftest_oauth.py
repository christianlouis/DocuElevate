"""
Pytest fixtures for OAuth/OIDC testing.

Provides fixtures for:
- Mock OAuth2 server (using testcontainers)
- Real OAuth credentials (from environment/GitHub Actions secrets)
- OAuth test helpers
"""

import os
from typing import Dict, Generator, Optional

import pytest

from tests.mock_oauth_server import MockOAuth2ServerContainer, create_test_userinfo

# Check if we should use real OAuth credentials from environment
_REAL_OAUTH_AVAILABLE = all([
    os.environ.get("AUTHENTIK_CLIENT_ID") not in {"", "NOT_SET", "test-key", None},
    os.environ.get("AUTHENTIK_CLIENT_SECRET") not in {"", "NOT_SET", "test-key", None},
    os.environ.get("AUTHENTIK_CONFIG_URL") not in {"", "NOT_SET", "test-key", None},
])


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
def mock_oauth_server() -> Generator[MockOAuth2ServerContainer, None, None]:
    """
    Provide a mock OAuth2/OIDC server for testing.
    
    This fixture starts a mock-oauth2-server container that provides
    a complete OIDC provider with all necessary endpoints.
    
    Yields:
        MockOAuth2ServerContainer: Running mock OAuth server
    """
    # Only start if we're not using real OAuth
    if not _REAL_OAUTH_AVAILABLE or os.environ.get("USE_MOCK_OAUTH", "").lower() in ("true", "1", "yes"):
        container = MockOAuth2ServerContainer()
        container.start()
        
        try:
            # Wait for the server to be ready
            container.wait_for_ready()
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
        mock_oauth_server: Mock OAuth server fixture (may be None if using real)
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
    else:
        # Use mock OAuth server
        if mock_oauth_server is None:
            pytest.fail("Mock OAuth server not available and real credentials not configured")
        
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
    import os
    from unittest.mock import patch
    
    # Save original values
    original_auth_enabled = os.environ.get("AUTH_ENABLED")
    original_client_id = os.environ.get("AUTHENTIK_CLIENT_ID")
    original_client_secret = os.environ.get("AUTHENTIK_CLIENT_SECRET")
    original_config_url = os.environ.get("AUTHENTIK_CONFIG_URL")
    
    try:
        # Enable auth and configure OAuth
        os.environ["AUTH_ENABLED"] = "True"
        os.environ["AUTHENTIK_CLIENT_ID"] = oauth_config["client_id"]
        os.environ["AUTHENTIK_CLIENT_SECRET"] = oauth_config["client_secret"]
        os.environ["AUTHENTIK_CONFIG_URL"] = oauth_config["server_metadata_url"]
        
        # Need to reload the app module to pick up new config
        import importlib
        from app import auth
        importlib.reload(auth)
        
        from fastapi.testclient import TestClient
        from app.main import app
        
        # Create test client
        client = TestClient(app)
        
        yield client
        
    finally:
        # Restore original values
        if original_auth_enabled is not None:
            os.environ["AUTH_ENABLED"] = original_auth_enabled
        else:
            os.environ.pop("AUTH_ENABLED", None)
        
        if original_client_id is not None:
            os.environ["AUTHENTIK_CLIENT_ID"] = original_client_id
        else:
            os.environ.pop("AUTHENTIK_CLIENT_ID", None)
            
        if original_client_secret is not None:
            os.environ["AUTHENTIK_CLIENT_SECRET"] = original_client_secret
        else:
            os.environ.pop("AUTHENTIK_CLIENT_SECRET", None)
            
        if original_config_url is not None:
            os.environ["AUTHENTIK_CONFIG_URL"] = original_config_url
        else:
            os.environ.pop("AUTHENTIK_CONFIG_URL", None)
        
        # Reload auth module to restore original state
        import importlib
        from app import auth
        importlib.reload(auth)
