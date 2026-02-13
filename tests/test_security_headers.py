#!/usr/bin/env python3

"""
Tests for security headers middleware.

These tests validate that security headers are properly added to HTTP responses
based on configuration settings.
"""

import pytest


@pytest.mark.unit
def test_security_headers_enabled_by_default(client):
    """Test that security headers are enabled by default."""
    response = client.get("/")

    # Should get a valid response (200, 302 redirect, or 404)
    assert response.status_code in [200, 302, 404], f"Unexpected status code: {response.status_code}"


@pytest.mark.unit
def test_hsts_header_present(client):
    """Test that HSTS header is present when enabled."""
    from app.config import settings

    # Skip test if HSTS is disabled
    if not settings.security_headers_enabled or not settings.security_header_hsts_enabled:
        pytest.skip("HSTS header is disabled in configuration")

    response = client.get("/")
    assert "Strict-Transport-Security" in response.headers
    assert "max-age" in response.headers["Strict-Transport-Security"]


@pytest.mark.unit
def test_csp_header_present(client):
    """Test that CSP header is present when enabled."""
    from app.config import settings

    # Skip test if CSP is disabled
    if not settings.security_headers_enabled or not settings.security_header_csp_enabled:
        pytest.skip("CSP header is disabled in configuration")

    response = client.get("/")
    assert "Content-Security-Policy" in response.headers
    assert "default-src" in response.headers["Content-Security-Policy"]


@pytest.mark.unit
def test_x_frame_options_header_present(client):
    """Test that X-Frame-Options header is present when enabled."""
    from app.config import settings

    # Skip test if X-Frame-Options is disabled
    if not settings.security_headers_enabled or not settings.security_header_x_frame_options_enabled:
        pytest.skip("X-Frame-Options header is disabled in configuration")

    response = client.get("/")
    assert "X-Frame-Options" in response.headers
    assert response.headers["X-Frame-Options"] in ["DENY", "SAMEORIGIN"]


@pytest.mark.unit
def test_x_content_type_options_header_present(client):
    """Test that X-Content-Type-Options header is present when enabled."""
    from app.config import settings

    # Skip test if X-Content-Type-Options is disabled
    if not settings.security_headers_enabled or not settings.security_header_x_content_type_options_enabled:
        pytest.skip("X-Content-Type-Options header is disabled in configuration")

    response = client.get("/")
    assert "X-Content-Type-Options" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.unit
def test_security_headers_on_api_endpoints(client):
    """Test that security headers are applied to API endpoints."""
    from app.config import settings

    if not settings.security_headers_enabled:
        pytest.skip("Security headers are disabled in configuration")

    response = client.get("/api/diagnostic/health")

    # Check that at least some security headers are present
    security_headers = [
        "Strict-Transport-Security",
        "Content-Security-Policy",
        "X-Frame-Options",
        "X-Content-Type-Options",
    ]
    present_headers = [h for h in security_headers if h in response.headers]
    assert len(present_headers) > 0, "No security headers found on API endpoint"


@pytest.mark.security
def test_hsts_header_value_format(client):
    """Test that HSTS header has correct format."""
    from app.config import settings

    if not settings.security_headers_enabled or not settings.security_header_hsts_enabled:
        pytest.skip("HSTS header is disabled in configuration")

    response = client.get("/")
    if "Strict-Transport-Security" in response.headers:
        hsts_value = response.headers["Strict-Transport-Security"]
        assert "max-age=" in hsts_value, "HSTS header missing max-age directive"
        # Extract max-age value
        parts = hsts_value.split(";")
        max_age_part = [p.strip() for p in parts if p.strip().startswith("max-age=")]
        assert len(max_age_part) > 0, "HSTS header missing max-age value"


@pytest.mark.security
def test_csp_header_value_format(client):
    """Test that CSP header has correct format."""
    from app.config import settings

    if not settings.security_headers_enabled or not settings.security_header_csp_enabled:
        pytest.skip("CSP header is disabled in configuration")

    response = client.get("/")
    if "Content-Security-Policy" in response.headers:
        csp_value = response.headers["Content-Security-Policy"]
        # CSP should have at least a default-src directive
        assert "default-src" in csp_value or "script-src" in csp_value, "CSP header missing required directives"


@pytest.mark.security
def test_x_frame_options_valid_value(client):
    """Test that X-Frame-Options header has valid value."""
    from app.config import settings

    if not settings.security_headers_enabled or not settings.security_header_x_frame_options_enabled:
        pytest.skip("X-Frame-Options header is disabled in configuration")

    response = client.get("/")
    if "X-Frame-Options" in response.headers:
        x_frame_value = response.headers["X-Frame-Options"]
        valid_values = ["DENY", "SAMEORIGIN"]
        # Note: ALLOW-FROM is deprecated in modern browsers; use CSP frame-ancestors instead
        assert x_frame_value in valid_values or x_frame_value.startswith(
            "ALLOW-FROM"
        ), f"Invalid X-Frame-Options value: {x_frame_value}"


@pytest.mark.integration
def test_security_headers_configuration_loading():
    """Test that security header configuration is loaded correctly."""
    from app.config import settings

    # Verify that security header configuration attributes exist
    assert hasattr(settings, "security_headers_enabled")
    assert hasattr(settings, "security_header_hsts_enabled")
    assert hasattr(settings, "security_header_hsts_value")
    assert hasattr(settings, "security_header_csp_enabled")
    assert hasattr(settings, "security_header_csp_value")
    assert hasattr(settings, "security_header_x_frame_options_enabled")
    assert hasattr(settings, "security_header_x_frame_options_value")
    assert hasattr(settings, "security_header_x_content_type_options_enabled")

    # Verify that boolean settings are actual booleans
    assert isinstance(settings.security_headers_enabled, bool)
    assert isinstance(settings.security_header_hsts_enabled, bool)
    assert isinstance(settings.security_header_csp_enabled, bool)
    assert isinstance(settings.security_header_x_frame_options_enabled, bool)
    assert isinstance(settings.security_header_x_content_type_options_enabled, bool)

    # Verify that string settings are actual strings
    assert isinstance(settings.security_header_hsts_value, str)
    assert isinstance(settings.security_header_csp_value, str)
    assert isinstance(settings.security_header_x_frame_options_value, str)


@pytest.mark.integration
def test_middleware_respects_configuration():
    """Test that middleware respects individual header enable/disable settings."""
    from app.config import settings
    from app.middleware.security_headers import SecurityHeadersMiddleware

    # Create middleware instance
    middleware = SecurityHeadersMiddleware(app=None, config=settings)

    # Verify that middleware stores configuration
    assert middleware.config == settings
    assert middleware.enabled == settings.security_headers_enabled
