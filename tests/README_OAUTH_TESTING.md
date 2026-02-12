# OAuth Testing with Mock OAuth2 Server

This directory contains infrastructure for testing OAuth/OIDC authentication flows using a mock OAuth2 server.

## Overview

The test setup supports two modes:

1. **Mock Mode (Default)**: Uses `mock-oauth2-server` via testcontainers for fast, deterministic tests
2. **Real Mode**: Uses actual OAuth credentials from GitHub Actions secrets for integration testing

## Quick Start

### Running Tests with Mock OAuth

```bash
# Run all OAuth integration tests (uses mock by default)
pytest tests/test_oauth_integration_flows.py -v

# Run with coverage
pytest tests/test_oauth_integration_flows.py --cov=app.auth --cov-report=term-missing
```

### Running Tests with Real OAuth (CI/GitHub Actions)

When running in GitHub Actions with secrets configured:

```bash
# Tests automatically detect real credentials and use them
pytest tests/test_oauth_integration_flows.py -v -m requires_external

# Force mock mode even with real credentials available
USE_MOCK_OAUTH=true pytest tests/test_oauth_integration_flows.py -v

# Force real mode (will skip if credentials not available)
USE_REAL_OAUTH=true pytest tests/test_oauth_integration_flows.py -v
```

## Architecture

### Components

1. **mock_oauth_server.py**: Testcontainers wrapper for mock-oauth2-server
   - Provides complete OIDC endpoints (.well-known, token, userinfo, JWKS)
   - Generates valid JWTs for testing
   - Fast startup (<1s), no persistence needed

2. **conftest_oauth.py**: Pytest fixtures for OAuth testing
   - `mock_oauth_server`: Session-scoped mock server fixture
   - `oauth_config`: OAuth configuration (mock or real)
   - `oauth_enabled_app`: Test client with OAuth enabled
   - `oauth_test_token`: Generate test JWT tokens
   - `test_user_info`: Test user claims

3. **test_oauth_integration_flows.py**: Integration tests
   - OAuth login flow
   - Token exchange and callback
   - Session management
   - Error handling
   - Real OAuth provider tests (when credentials available)

### Mock OAuth Server

The mock server (https://github.com/navikt/mock-oauth2-server) provides:

- **Authorization endpoint**: `/default/authorize`
- **Token endpoint**: `/default/token`
- **Userinfo endpoint**: `/default/userinfo`
- **JWKS endpoint**: `/default/jwks`
- **Discovery**: `/default/.well-known/openid-configuration`
- **Debug token creation**: `/debugger/token`

## Usage Examples

### Basic OAuth Test

```python
import pytest

@pytest.mark.integration
def test_oauth_login(oauth_enabled_app):
    """Test OAuth login redirects to provider."""
    response = oauth_enabled_app.get("/oauth-login", follow_redirects=False)
    assert response.status_code == 302
    assert "authorize" in response.headers["location"]
```

### Testing with Mock User

```python
from unittest.mock import patch

@pytest.mark.integration
@patch("app.auth.oauth.authentik.authorize_access_token")
async def test_oauth_callback(mock_authorize, oauth_enabled_app, test_user_info):
    """Test OAuth callback with test user."""
    mock_authorize.return_value = {
        "access_token": "test-token",
        "userinfo": test_user_info,
    }
    
    response = oauth_enabled_app.get("/oauth-callback?code=test-code")
    assert response.status_code == 302  # Redirects after login
```

### Testing with Generated Token

```python
@pytest.mark.integration
def test_with_jwt_token(oauth_test_token, test_user_info):
    """Test with a valid JWT from mock server."""
    # oauth_test_token is a valid JWT signed by the mock server
    # It can be verified using the mock server's JWKS endpoint
    assert oauth_test_token is not None
    print(f"Token for user: {test_user_info['email']}")
```

## Configuration

### Environment Variables

- `USE_MOCK_OAUTH=true`: Force mock mode
- `USE_REAL_OAUTH=true`: Force real mode (fails if credentials not available)
- `AUTHENTIK_CLIENT_ID`: OAuth client ID (for real mode)
- `AUTHENTIK_CLIENT_SECRET`: OAuth client secret (for real mode)
- `AUTHENTIK_CONFIG_URL`: OIDC discovery URL (for real mode)

### GitHub Actions Secrets

When these secrets are set in GitHub Actions, tests automatically use real OAuth:

```yaml
# .github/workflows/test.yml
env:
  AUTHENTIK_CLIENT_ID: ${{ secrets.AUTHENTIK_CLIENT_ID }}
  AUTHENTIK_CLIENT_SECRET: ${{ secrets.AUTHENTIK_CLIENT_SECRET }}
  AUTHENTIK_CONFIG_URL: ${{ secrets.AUTHENTIK_CONFIG_URL }}
```

## Troubleshooting

### Mock Server Won't Start

```bash
# Check Docker is running
docker ps

# Pull the image manually
docker pull ghcr.io/navikt/mock-oauth2-server:2.1.1

# Check logs
pytest tests/test_oauth_integration_flows.py -v -s
```

### Tests Hang on Container Startup

The mock server fixture waits up to 30 seconds for the server to be ready. If tests hang:

1. Check Docker resources (CPU, memory)
2. Check if port 8080 is available
3. Try running with `-s` flag to see container logs

### Token Validation Fails

The mock server generates valid JWTs that can be verified using its JWKS endpoint. If validation fails:

1. Ensure the token was created from the correct mock server instance
2. Check the `aud` (audience) claim matches your client ID
3. Verify the `iss` (issuer) claim matches the mock server URL

## Benefits of This Approach

1. **Fast**: Mock server starts in <1s, tests run quickly
2. **Deterministic**: No external dependencies, same results every time
3. **Realistic**: Tests actual OAuth flows with real OIDC endpoints
4. **Flexible**: Can switch to real OAuth for integration tests
5. **CI-Friendly**: Works in ephemeral CI environments
6. **Complete**: All OIDC endpoints available for testing

## Further Reading

- [Mock OAuth2 Server Documentation](https://github.com/navikt/mock-oauth2-server)
- [Testcontainers Python](https://testcontainers-python.readthedocs.io/)
- [OAuth 2.0 RFC 6749](https://tools.ietf.org/html/rfc6749)
- [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html)
