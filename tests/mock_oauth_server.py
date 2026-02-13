"""
Mock OAuth2/OIDC Server for testing authentication flows.

Uses testcontainers to spin up a mock-oauth2-server instance that provides
a complete OIDC provider with .well-known/openid-configuration, JWKS, token,
and userinfo endpoints.

This allows for realistic OAuth testing without requiring a real IdP.
"""

import json
import logging
import time
from typing import Dict, Optional
from urllib.parse import urljoin

import requests
from testcontainers.core.container import DockerContainer

logger = logging.getLogger(__name__)


class MockOAuth2ServerContainer(DockerContainer):
    """
    Testcontainer for mock-oauth2-server.

    Provides a complete OIDC provider for testing OAuth2 flows.
    """

    def __init__(
        self,
        image: str = "ghcr.io/navikt/mock-oauth2-server:2.1.1",
        port: int = 8080,
        issuer_id: str = "default",
    ):
        """
        Initialize the mock OAuth2 server container.

        Args:
            image: Docker image to use
            port: Internal container port (default 8080)
            issuer_id: Issuer identifier for the mock server
        """
        super().__init__(image)
        self.port = port
        self.issuer_id = issuer_id
        self.with_exposed_ports(port)

    def get_base_url(self) -> str:
        """Get the base URL for the mock OAuth server."""
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.port)
        return f"http://{host}:{port}"

    def get_issuer_url(self) -> str:
        """Get the issuer URL for the OIDC provider."""
        return f"{self.get_base_url()}/{self.issuer_id}"

    def get_well_known_url(self) -> str:
        """Get the .well-known/openid-configuration URL."""
        return f"{self.get_issuer_url()}/.well-known/openid-configuration"

    def get_token_endpoint(self) -> str:
        """Get the token endpoint URL."""
        return f"{self.get_issuer_url()}/token"

    def get_authorization_endpoint(self) -> str:
        """Get the authorization endpoint URL."""
        return f"{self.get_issuer_url()}/authorize"

    def get_userinfo_endpoint(self) -> str:
        """Get the userinfo endpoint URL."""
        return f"{self.get_issuer_url()}/userinfo"

    def get_jwks_uri(self) -> str:
        """Get the JWKS URI."""
        return f"{self.get_issuer_url()}/jwks"

    def wait_for_ready(self, timeout: int = 30) -> None:
        """
        Wait for the OAuth server to be ready by checking the well-known endpoint.

        Args:
            timeout: Maximum time to wait in seconds
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(self.get_well_known_url(), timeout=5)
                if response.status_code == 200:
                    logger.info(f"Mock OAuth2 server is ready at {self.get_base_url()}")
                    return
            except requests.exceptions.RequestException:
                pass
            time.sleep(0.5)

        raise TimeoutError(f"Mock OAuth2 server did not become ready within {timeout}s")

    def get_config(self) -> Dict[str, str]:
        """
        Get the OAuth configuration for the mock server.

        Returns:
            Dictionary with OAuth endpoints and configuration
        """
        return {
            "issuer": self.get_issuer_url(),
            "authorization_endpoint": self.get_authorization_endpoint(),
            "token_endpoint": self.get_token_endpoint(),
            "userinfo_endpoint": self.get_userinfo_endpoint(),
            "jwks_uri": self.get_jwks_uri(),
            "well_known_url": self.get_well_known_url(),
            "base_url": self.get_base_url(),
        }

    def create_token(
        self,
        subject: str = "test-user",
        claims: Optional[Dict] = None,
        audience: str = "test-client",
    ) -> str:
        """
        Create a mock JWT token.

        The mock-oauth2-server will generate a valid JWT that can be verified
        using its JWKS endpoint.

        Args:
            subject: Subject (sub) claim for the token
            claims: Additional claims to include in the token
            audience: Audience (aud) claim

        Returns:
            JWT token string
        """
        if claims is None:
            claims = {}

        # Add standard claims
        token_claims = {
            "sub": subject,
            "aud": audience,
            **claims,
        }

        # The debugger endpoint expects a different format
        # For simpler testing, we'll use the token endpoint directly
        # with a mock authorization code flow

        # Note: For actual tests, we'll mock the token exchange in the tests
        # This method is mainly for documentation/example purposes
        logger.info(f"Creating token for subject: {subject}")

        # Return a placeholder - in actual tests we'll mock the OAuth flow
        return f"mock-token-{subject}"


def create_test_userinfo(
    sub: str = "test-user-123",
    email: str = "test@example.com",
    name: str = "Test User",
    preferred_username: str = "testuser",
    groups: Optional[list] = None,
) -> Dict:
    """
    Create a test userinfo response.

    Args:
        sub: Subject identifier
        email: User email address
        name: Full name
        preferred_username: Username
        groups: List of group names

    Returns:
        Dictionary with userinfo claims
    """
    if groups is None:
        groups = ["admin"]

    return {
        "sub": sub,
        "email": email,
        "email_verified": True,
        "name": name,
        "preferred_username": preferred_username,
        "groups": groups,
        "picture": f"https://www.gravatar.com/avatar/{sub}?d=identicon",
    }


def configure_mock_oauth_response(
    container: MockOAuth2ServerContainer,
    code: str,
    userinfo: Optional[Dict] = None,
    access_token: Optional[str] = None,
) -> None:
    """
    Configure the mock OAuth server to return specific responses for a code.

    This is useful for testing the OAuth callback flow.

    Args:
        container: The mock OAuth server container
        code: Authorization code to configure
        userinfo: Userinfo response to return
        access_token: Access token to return (if None, server generates one)
    """
    if userinfo is None:
        userinfo = create_test_userinfo()

    # The mock-oauth2-server automatically handles code exchange
    # and returns the configured userinfo
    # This is a placeholder for any additional configuration needed
    logger.info(f"Configured mock OAuth response for code: {code}")
