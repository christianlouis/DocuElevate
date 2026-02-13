"""Comprehensive tests for app/middleware/security_headers.py to improve coverage."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.responses import Response


@pytest.mark.unit
class TestSecurityHeadersMiddlewareInit:
    """Tests for SecurityHeadersMiddleware initialization."""

    def test_init_enabled(self):
        """Test middleware initializes with enabled=True."""
        from app.middleware.security_headers import SecurityHeadersMiddleware

        mock_config = MagicMock()
        mock_config.security_headers_enabled = True
        mock_config.security_header_hsts_enabled = True
        mock_config.security_header_csp_enabled = True
        mock_config.security_header_x_frame_options_enabled = True
        mock_config.security_header_x_content_type_options_enabled = True

        middleware = SecurityHeadersMiddleware(app=MagicMock(), config=mock_config)
        assert middleware.enabled is True
        assert middleware.config == mock_config

    def test_init_disabled(self):
        """Test middleware initializes with enabled=False."""
        from app.middleware.security_headers import SecurityHeadersMiddleware

        mock_config = MagicMock()
        mock_config.security_headers_enabled = False

        middleware = SecurityHeadersMiddleware(app=MagicMock(), config=mock_config)
        assert middleware.enabled is False


@pytest.mark.unit
class TestSecurityHeadersDispatch:
    """Tests for SecurityHeadersMiddleware dispatch method."""

    @pytest.mark.asyncio
    async def test_dispatch_adds_headers_when_enabled(self):
        """Test dispatch adds security headers when enabled."""
        from app.middleware.security_headers import SecurityHeadersMiddleware

        mock_config = MagicMock()
        mock_config.security_headers_enabled = True
        mock_config.security_header_hsts_enabled = True
        mock_config.security_header_hsts_value = "max-age=31536000; includeSubDomains"
        mock_config.security_header_csp_enabled = True
        mock_config.security_header_csp_value = "default-src 'self'"
        mock_config.security_header_x_frame_options_enabled = True
        mock_config.security_header_x_frame_options_value = "DENY"
        mock_config.security_header_x_content_type_options_enabled = True

        middleware = SecurityHeadersMiddleware(app=MagicMock(), config=mock_config)

        response = Response(content="test")
        mock_call_next = AsyncMock(return_value=response)
        mock_request = MagicMock()

        result = await middleware.dispatch(mock_request, mock_call_next)
        assert result.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
        assert result.headers["Content-Security-Policy"] == "default-src 'self'"
        assert result.headers["X-Frame-Options"] == "DENY"
        assert result.headers["X-Content-Type-Options"] == "nosniff"

    @pytest.mark.asyncio
    async def test_dispatch_skips_headers_when_disabled(self):
        """Test dispatch does not add headers when disabled."""
        from app.middleware.security_headers import SecurityHeadersMiddleware

        mock_config = MagicMock()
        mock_config.security_headers_enabled = False

        middleware = SecurityHeadersMiddleware(app=MagicMock(), config=mock_config)

        response = Response(content="test")
        mock_call_next = AsyncMock(return_value=response)
        mock_request = MagicMock()

        result = await middleware.dispatch(mock_request, mock_call_next)
        assert "Strict-Transport-Security" not in result.headers
        assert "Content-Security-Policy" not in result.headers
        assert "X-Frame-Options" not in result.headers
        assert "X-Content-Type-Options" not in result.headers

    @pytest.mark.asyncio
    async def test_dispatch_selective_headers(self):
        """Test dispatch only adds individually enabled headers."""
        from app.middleware.security_headers import SecurityHeadersMiddleware

        mock_config = MagicMock()
        mock_config.security_headers_enabled = True
        mock_config.security_header_hsts_enabled = True
        mock_config.security_header_hsts_value = "max-age=86400"
        mock_config.security_header_csp_enabled = False
        mock_config.security_header_x_frame_options_enabled = False
        mock_config.security_header_x_content_type_options_enabled = True

        middleware = SecurityHeadersMiddleware(app=MagicMock(), config=mock_config)

        response = Response(content="test")
        mock_call_next = AsyncMock(return_value=response)
        mock_request = MagicMock()

        result = await middleware.dispatch(mock_request, mock_call_next)
        assert "Strict-Transport-Security" in result.headers
        assert "Content-Security-Policy" not in result.headers
        assert "X-Frame-Options" not in result.headers
        assert "X-Content-Type-Options" in result.headers


@pytest.mark.unit
class TestAddSecurityHeaders:
    """Tests for _add_security_headers method."""

    def test_adds_hsts_header(self):
        """Test adds HSTS header when enabled."""
        from app.middleware.security_headers import SecurityHeadersMiddleware

        mock_config = MagicMock()
        mock_config.security_headers_enabled = True
        mock_config.security_header_hsts_enabled = True
        mock_config.security_header_hsts_value = "max-age=63072000; includeSubDomains; preload"
        mock_config.security_header_csp_enabled = False
        mock_config.security_header_x_frame_options_enabled = False
        mock_config.security_header_x_content_type_options_enabled = False

        middleware = SecurityHeadersMiddleware(app=MagicMock(), config=mock_config)

        response = Response(content="test")
        middleware._add_security_headers(response)

        assert response.headers["Strict-Transport-Security"] == "max-age=63072000; includeSubDomains; preload"

    def test_adds_csp_header(self):
        """Test adds CSP header when enabled."""
        from app.middleware.security_headers import SecurityHeadersMiddleware

        mock_config = MagicMock()
        mock_config.security_headers_enabled = True
        mock_config.security_header_hsts_enabled = False
        mock_config.security_header_csp_enabled = True
        mock_config.security_header_csp_value = "default-src 'self'; script-src 'unsafe-inline'"
        mock_config.security_header_x_frame_options_enabled = False
        mock_config.security_header_x_content_type_options_enabled = False

        middleware = SecurityHeadersMiddleware(app=MagicMock(), config=mock_config)

        response = Response(content="test")
        middleware._add_security_headers(response)

        assert response.headers["Content-Security-Policy"] == "default-src 'self'; script-src 'unsafe-inline'"

    def test_adds_x_frame_options_header(self):
        """Test adds X-Frame-Options header when enabled."""
        from app.middleware.security_headers import SecurityHeadersMiddleware

        mock_config = MagicMock()
        mock_config.security_headers_enabled = True
        mock_config.security_header_hsts_enabled = False
        mock_config.security_header_csp_enabled = False
        mock_config.security_header_x_frame_options_enabled = True
        mock_config.security_header_x_frame_options_value = "SAMEORIGIN"
        mock_config.security_header_x_content_type_options_enabled = False

        middleware = SecurityHeadersMiddleware(app=MagicMock(), config=mock_config)

        response = Response(content="test")
        middleware._add_security_headers(response)

        assert response.headers["X-Frame-Options"] == "SAMEORIGIN"

    def test_adds_x_content_type_options_header(self):
        """Test adds X-Content-Type-Options header when enabled."""
        from app.middleware.security_headers import SecurityHeadersMiddleware

        mock_config = MagicMock()
        mock_config.security_headers_enabled = True
        mock_config.security_header_hsts_enabled = False
        mock_config.security_header_csp_enabled = False
        mock_config.security_header_x_frame_options_enabled = False
        mock_config.security_header_x_content_type_options_enabled = True

        middleware = SecurityHeadersMiddleware(app=MagicMock(), config=mock_config)

        response = Response(content="test")
        middleware._add_security_headers(response)

        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_no_headers_when_all_disabled(self):
        """Test no headers added when all individual headers are disabled."""
        from app.middleware.security_headers import SecurityHeadersMiddleware

        mock_config = MagicMock()
        mock_config.security_headers_enabled = True
        mock_config.security_header_hsts_enabled = False
        mock_config.security_header_csp_enabled = False
        mock_config.security_header_x_frame_options_enabled = False
        mock_config.security_header_x_content_type_options_enabled = False

        middleware = SecurityHeadersMiddleware(app=MagicMock(), config=mock_config)

        response = Response(content="test")
        middleware._add_security_headers(response)

        assert "Strict-Transport-Security" not in response.headers
        assert "Content-Security-Policy" not in response.headers
        assert "X-Frame-Options" not in response.headers
        assert "X-Content-Type-Options" not in response.headers

    def test_all_headers_added_together(self):
        """Test all headers added when all enabled."""
        from app.middleware.security_headers import SecurityHeadersMiddleware

        mock_config = MagicMock()
        mock_config.security_headers_enabled = True
        mock_config.security_header_hsts_enabled = True
        mock_config.security_header_hsts_value = "max-age=31536000"
        mock_config.security_header_csp_enabled = True
        mock_config.security_header_csp_value = "default-src 'self'"
        mock_config.security_header_x_frame_options_enabled = True
        mock_config.security_header_x_frame_options_value = "DENY"
        mock_config.security_header_x_content_type_options_enabled = True

        middleware = SecurityHeadersMiddleware(app=MagicMock(), config=mock_config)

        response = Response(content="test")
        middleware._add_security_headers(response)

        assert "Strict-Transport-Security" in response.headers
        assert "Content-Security-Policy" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "X-Content-Type-Options" in response.headers
