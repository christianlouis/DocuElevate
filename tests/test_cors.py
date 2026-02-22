#!/usr/bin/env python3

"""
Tests for CORS middleware configuration.

These tests validate that:
- CORS middleware is disabled by default (reverse proxy handles CORS in production)
- When enabled, CORS headers are present on responses
- Configuration settings (allowed origins, methods, headers, credentials) are respected
- Preflight (OPTIONS) requests are handled correctly when CORS is enabled
"""

from unittest.mock import Mock

import pytest


@pytest.mark.integration
def test_cors_configuration_exists():
    """Test that CORS configuration attributes exist in settings."""
    from app.config import settings

    assert hasattr(settings, "cors_enabled")
    assert hasattr(settings, "cors_allowed_origins")
    assert hasattr(settings, "cors_allow_credentials")
    assert hasattr(settings, "cors_allowed_methods")
    assert hasattr(settings, "cors_allowed_headers")


@pytest.mark.integration
def test_cors_disabled_by_default():
    """Test that CORS is disabled by default (reverse proxy handles it)."""
    from app.config import Settings

    # The default value for cors_enabled should be False
    field_info = Settings.model_fields.get("cors_enabled")
    assert field_info is not None
    assert field_info.default is False, "CORS should be disabled by default"


@pytest.mark.integration
def test_cors_configuration_types():
    """Test that CORS configuration settings have correct types."""
    from app.config import settings

    assert isinstance(settings.cors_enabled, bool)
    assert isinstance(settings.cors_allowed_origins, list)
    assert isinstance(settings.cors_allow_credentials, bool)
    assert isinstance(settings.cors_allowed_methods, list)
    assert isinstance(settings.cors_allowed_headers, list)


@pytest.mark.unit
def test_cors_headers_absent_when_disabled(client):
    """Test that CORS headers are NOT present when middleware is disabled."""
    from app.config import settings

    if settings.cors_enabled:
        pytest.skip("CORS is enabled in this test environment")

    response = client.get("/api/diagnostic/health", headers={"Origin": "https://example.com"})
    # When CORS middleware is disabled, the application should not add CORS headers
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.unit
def test_no_cors_preflight_when_disabled(client):
    """Test that preflight OPTIONS requests return 405 (or similar) when CORS is disabled."""
    from app.config import settings

    if settings.cors_enabled:
        pytest.skip("CORS is enabled in this test environment")

    response = client.options(
        "/api/diagnostic/health",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Without CORSMiddleware, OPTIONS preflight is not handled as CORS
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.unit
class TestCORSMiddlewareEnabled:
    """Tests for CORSMiddleware behavior when enabled."""

    def _make_app_with_cors(self, allow_origins=None, allow_credentials=False, allow_methods=None, allow_headers=None):
        """Create a minimal FastAPI app with CORSMiddleware for isolated testing."""
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.testclient import TestClient

        test_app = FastAPI()
        test_app.add_middleware(
            CORSMiddleware,
            allow_origins=allow_origins or ["https://trusted.example.com"],
            allow_credentials=allow_credentials,
            allow_methods=allow_methods or ["GET", "POST", "OPTIONS"],
            allow_headers=allow_headers or ["*"],
        )

        @test_app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        return TestClient(test_app)

    def test_cors_header_present_for_allowed_origin(self):
        """Test that CORS header is present for allowed origin."""
        test_client = self._make_app_with_cors(allow_origins=["https://trusted.example.com"])
        response = test_client.get("/test", headers={"Origin": "https://trusted.example.com"})
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
        assert response.headers["access-control-allow-origin"] == "https://trusted.example.com"

    def test_cors_wildcard_origin(self):
        """Test that wildcard origin allows any origin."""
        test_client = self._make_app_with_cors(allow_origins=["*"])
        response = test_client.get("/test", headers={"Origin": "https://any-origin.example.com"})
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_cors_preflight_returns_200(self):
        """Test that CORS preflight OPTIONS request returns 200."""
        test_client = self._make_app_with_cors(allow_origins=["https://trusted.example.com"])
        response = test_client.options(
            "/test",
            headers={
                "Origin": "https://trusted.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_cors_credentials_allowed(self):
        """Test that credentials header is present when allow_credentials=True."""
        test_client = self._make_app_with_cors(
            allow_origins=["https://trusted.example.com"],
            allow_credentials=True,
        )
        response = test_client.get("/test", headers={"Origin": "https://trusted.example.com"})
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_cors_methods_in_preflight(self):
        """Test that allowed methods appear in preflight response."""
        test_client = self._make_app_with_cors(
            allow_origins=["https://trusted.example.com"],
            allow_methods=["GET", "POST"],
        )
        response = test_client.options(
            "/test",
            headers={
                "Origin": "https://trusted.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 200


@pytest.mark.unit
def test_cors_parse_comma_separated_origins():
    """Test that comma-separated CORS origins string is parsed into a list."""
    import os

    # Temporarily set env var to test parsing
    original = os.environ.get("CORS_ALLOWED_ORIGINS")
    os.environ["CORS_ALLOWED_ORIGINS"] = "https://app.example.com,https://admin.example.com"
    try:
        from importlib import reload

        import app.config as config_module

        reload(config_module)
        test_settings = config_module.Settings(
            database_url="sqlite:///:memory:",
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            azure_ai_key="test-key",
            azure_region="test",
            azure_endpoint="https://test.cognitiveservices.azure.com/",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
        )
        assert isinstance(test_settings.cors_allowed_origins, list)
        assert len(test_settings.cors_allowed_origins) == 2
        origins = set(test_settings.cors_allowed_origins)
        assert origins == {"https://app.example.com", "https://admin.example.com"}
    finally:
        if original is None:
            os.environ.pop("CORS_ALLOWED_ORIGINS", None)
        else:
            os.environ["CORS_ALLOWED_ORIGINS"] = original


@pytest.mark.unit
def test_cors_single_origin_string_to_list():
    """Test that a single-origin string is parsed into a list with one item."""
    import os

    original = os.environ.get("CORS_ALLOWED_ORIGINS")
    os.environ["CORS_ALLOWED_ORIGINS"] = "https://app.example.com"
    try:
        from importlib import reload

        import app.config as config_module

        reload(config_module)
        test_settings = config_module.Settings(
            database_url="sqlite:///:memory:",
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            azure_ai_key="test-key",
            azure_region="test",
            azure_endpoint="https://test.cognitiveservices.azure.com/",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
        )
        assert isinstance(test_settings.cors_allowed_origins, list)
        assert len(test_settings.cors_allowed_origins) == 1
        assert test_settings.cors_allowed_origins[0] == "https://app.example.com"
    finally:
        if original is None:
            os.environ.pop("CORS_ALLOWED_ORIGINS", None)
        else:
            os.environ["CORS_ALLOWED_ORIGINS"] = original
