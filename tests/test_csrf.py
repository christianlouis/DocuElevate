"""Tests for the CSRF protection middleware (app/middleware/csrf.py)."""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from starlette.responses import JSONResponse, RedirectResponse

from app.middleware.csrf import CSRF_EXEMPT_PATHS, CSRF_PROTECTED_METHODS, CSRFMiddleware

# ---------------------------------------------------------------------------
# Unit tests – CSRFMiddleware._get_submitted_token
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetSubmittedToken:
    """Unit tests for the CSRF token extraction helper."""

    @pytest.mark.asyncio
    async def test_returns_header_token(self):
        """Token is read from the X-CSRF-Token request header."""
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"X-CSRF-Token": "abc123"}
        mock_request.form = AsyncMock(return_value={})

        token = await CSRFMiddleware._get_submitted_token(mock_request)
        assert token == "abc123"

    @pytest.mark.asyncio
    async def test_returns_form_token_for_urlencoded(self):
        """Token is read from the form body for URL-encoded POST data."""
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"content-type": "application/x-www-form-urlencoded"}
        mock_request.body = AsyncMock(return_value=b"csrf_token=form_token_xyz")
        mock_request.form = AsyncMock(return_value={"csrf_token": "form_token_xyz"})

        token = await CSRFMiddleware._get_submitted_token(mock_request)
        assert token == "form_token_xyz"
        # body() must have been awaited so the body is cached for downstream re-reads.
        mock_request.body.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_header_takes_priority_over_form(self):
        """Header token takes priority over form body token."""
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {
            "X-CSRF-Token": "header_token",
            "content-type": "application/x-www-form-urlencoded",
        }
        mock_request.form = AsyncMock(return_value={"csrf_token": "form_token"})

        token = await CSRFMiddleware._get_submitted_token(mock_request)
        assert token == "header_token"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_token(self):
        """Returns None when no token is present in header or body."""
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"content-type": "application/json"}
        mock_request.form = AsyncMock(return_value={})

        token = await CSRFMiddleware._get_submitted_token(mock_request)
        assert token is None

    @pytest.mark.asyncio
    async def test_returns_none_for_multipart_without_header(self):
        """Multipart bodies without a header should return None (not parsed)."""
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"content-type": "multipart/form-data; boundary=----boundary"}
        mock_request.form = AsyncMock(return_value={"csrf_token": "should_not_be_read"})

        token = await CSRFMiddleware._get_submitted_token(mock_request)
        assert token is None

    @pytest.mark.asyncio
    async def test_body_is_cached_before_form_parse(self):
        """body() is called before form() so downstream handlers can re-read the body.

        This covers the Starlette BaseHTTPMiddleware body-replay bug: if form()
        is called without first calling body(), _stream_consumed is set to True
        but _body remains unset.  _CachedRequest.wrapped_receive then forwards
        an empty body to downstream apps (e.g. the /auth endpoint) causing
        form_keys=[] and login failures.  Calling body() first caches _body so
        wrapped_receive correctly replays the full body.
        """
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"content-type": "application/x-www-form-urlencoded"}
        call_order: list[str] = []

        async def _body():
            call_order.append("body")
            return b"csrf_token=tok&username=alice&password=test_password"

        async def _form():
            call_order.append("form")
            return {"csrf_token": "tok", "username": "alice", "password": "test_password"}

        mock_request.body = _body
        mock_request.form = _form

        token = await CSRFMiddleware._get_submitted_token(mock_request)

        assert token == "tok"
        # body() must be called BEFORE form() to ensure body caching.
        assert call_order == ["body", "form"]

    @pytest.mark.asyncio
    async def test_body_is_not_called_when_header_present(self):
        """When the CSRF token is in the X-CSRF-Token header, body() is not called.

        For header-based token submission (AJAX / fetch requests) we skip body
        parsing entirely, so the body stream remains unconsumed and downstream
        handlers can read it normally.
        """
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {
            "X-CSRF-Token": "header_tok",
            "content-type": "application/x-www-form-urlencoded",
        }
        mock_request.body = AsyncMock(return_value=b"username=alice")
        mock_request.form = AsyncMock(return_value={"csrf_token": "header_tok"})

        token = await CSRFMiddleware._get_submitted_token(mock_request)

        assert token == "header_tok"
        # body() must NOT be called – the header path returns early.
        mock_request.body.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handles_form_parse_exception_gracefully(self):
        """A broken form body does not crash the middleware."""
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"content-type": "application/x-www-form-urlencoded"}
        mock_request.body = AsyncMock(return_value=b"")
        mock_request.form = AsyncMock(side_effect=Exception("parse error"))

        token = await CSRFMiddleware._get_submitted_token(mock_request)
        assert token is None


# Unit tests – CSRFMiddleware.dispatch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCSRFMiddlewareDispatch:
    """Unit tests for the CSRFMiddleware.dispatch method."""

    def _make_middleware(self, auth_enabled: bool = True):
        mock_app = AsyncMock()
        mock_config = MagicMock()
        mock_config.auth_enabled = auth_enabled
        return CSRFMiddleware(mock_app, mock_config)

    def _make_request(self, method="GET", path="/", session=None, headers=None, state=None):
        mock_request = MagicMock(spec=Request)
        mock_request.method = method
        mock_request.url = MagicMock()
        mock_request.url.path = path
        mock_request.session = session if session is not None else {}
        mock_request.headers = headers or {}
        mock_request.state = MagicMock()
        mock_request.state.csrf_token = None
        return mock_request

    @pytest.mark.asyncio
    async def test_noop_when_auth_disabled(self):
        """Middleware is a no-op when AUTH_ENABLED is False."""
        middleware = self._make_middleware(auth_enabled=False)
        request = self._make_request(method="POST", path="/api/test")

        next_response = MagicMock()
        call_next = AsyncMock(return_value=next_response)

        result = await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)
        assert result is next_response

    @pytest.mark.asyncio
    async def test_generates_token_when_not_in_session(self):
        """A new CSRF token is generated and stored in the session when absent."""
        middleware = self._make_middleware()
        request = self._make_request(method="GET", session={})
        call_next = AsyncMock(return_value=MagicMock())

        await middleware.dispatch(request, call_next)

        assert "csrf_token" in request.session
        token = request.session["csrf_token"]
        assert len(token) == 64  # secrets.token_hex(32) -> 64 hex chars

    @pytest.mark.asyncio
    async def test_reuses_existing_token_from_session(self):
        """An existing session token is reused instead of regenerating."""
        existing_token = secrets.token_hex(32)
        middleware = self._make_middleware()
        request = self._make_request(method="GET", session={"csrf_token": existing_token})
        call_next = AsyncMock(return_value=MagicMock())

        await middleware.dispatch(request, call_next)

        assert request.session["csrf_token"] == existing_token
        assert request.state.csrf_token == existing_token

    @pytest.mark.asyncio
    async def test_attaches_token_to_request_state(self):
        """Token is always attached to request.state.csrf_token."""
        middleware = self._make_middleware()
        request = self._make_request(method="GET", session={})
        call_next = AsyncMock(return_value=MagicMock())

        await middleware.dispatch(request, call_next)

        assert request.state.csrf_token is not None
        assert len(request.state.csrf_token) == 64

    @pytest.mark.asyncio
    async def test_safe_methods_pass_without_token(self):
        """GET/HEAD/OPTIONS requests pass through without CSRF validation."""
        middleware = self._make_middleware()

        for method in ("GET", "HEAD", "OPTIONS"):
            request = self._make_request(method=method, session={})
            call_next = AsyncMock(return_value=MagicMock())
            result = await middleware.dispatch(request, call_next)
            call_next.assert_called_once_with(request)
            call_next.reset_mock()

    @pytest.mark.asyncio
    async def test_post_with_valid_header_token_passes(self):
        """POST with a matching X-CSRF-Token header passes validation."""
        token = secrets.token_hex(32)
        middleware = self._make_middleware()
        request = self._make_request(
            method="POST",
            path="/api/process/",
            session={"csrf_token": token},
            headers={"X-CSRF-Token": token},
        )
        call_next = AsyncMock(return_value=MagicMock())

        with patch.object(CSRFMiddleware, "_get_submitted_token", new=AsyncMock(return_value=token)):
            result = await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_post_with_invalid_token_returns_403_for_api(self):
        """POST with a wrong token on an API route returns HTTP 403."""
        token = secrets.token_hex(32)
        middleware = self._make_middleware()
        request = self._make_request(
            method="POST",
            path="/api/process/",
            session={"csrf_token": token},
        )
        call_next = AsyncMock(return_value=MagicMock())

        with patch.object(CSRFMiddleware, "_get_submitted_token", new=AsyncMock(return_value="wrong_token")):
            result = await middleware.dispatch(request, call_next)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 403
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_post_with_missing_token_returns_403_for_api(self):
        """POST with no CSRF token on an API route returns HTTP 403."""
        token = secrets.token_hex(32)
        middleware = self._make_middleware()
        request = self._make_request(
            method="POST",
            path="/api/settings/bulk-update",
            session={"csrf_token": token},
        )
        call_next = AsyncMock(return_value=MagicMock())

        with patch.object(CSRFMiddleware, "_get_submitted_token", new=AsyncMock(return_value=None)):
            result = await middleware.dispatch(request, call_next)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 403

    @pytest.mark.asyncio
    async def test_post_with_invalid_token_redirects_for_frontend(self):
        """POST with a wrong token on a frontend route redirects to /login."""
        token = secrets.token_hex(32)
        middleware = self._make_middleware()
        request = self._make_request(
            method="POST",
            path="/auth",
            session={"csrf_token": token},
        )
        call_next = AsyncMock(return_value=MagicMock())

        with patch.object(CSRFMiddleware, "_get_submitted_token", new=AsyncMock(return_value="bad_token")):
            result = await middleware.dispatch(request, call_next)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert "/login?error=Invalid+request" in result.headers["location"]
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_with_valid_token_passes(self):
        """DELETE with a matching token passes through."""
        token = secrets.token_hex(32)
        middleware = self._make_middleware()
        request = self._make_request(
            method="DELETE",
            path="/api/files/1",
            session={"csrf_token": token},
        )
        call_next = AsyncMock(return_value=MagicMock())

        with patch.object(CSRFMiddleware, "_get_submitted_token", new=AsyncMock(return_value=token)):
            result = await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_oauth_callback_is_exempt(self):
        """OAuth callback path is exempt from CSRF validation even on POST."""
        middleware = self._make_middleware()
        request = self._make_request(
            method="POST",
            path="/oauth-callback",
            session={"csrf_token": secrets.token_hex(32)},
        )
        call_next = AsyncMock(return_value=MagicMock())

        with patch.object(CSRFMiddleware, "_get_submitted_token", new=AsyncMock(return_value=None)):
            result = await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_qr_auth_claim_is_exempt(self):
        """QR auth claim path is exempt from CSRF validation.

        The mobile app calls this endpoint without a browser session and
        therefore without a CSRF token.  The cryptographically-random,
        single-use challenge token provides equivalent protection.
        """
        middleware = self._make_middleware()
        request = self._make_request(
            method="POST",
            path="/api/qr-auth/claim",
            session={},
        )
        call_next = AsyncMock(return_value=MagicMock())

        with patch.object(CSRFMiddleware, "_get_submitted_token", new=AsyncMock(return_value=None)):
            result = await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)


# ---------------------------------------------------------------------------
# Integration tests – via TestClient
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.security
class TestCSRFIntegration:
    """Integration tests for CSRF protection using the FastAPI TestClient.

    The shared ``client`` fixture runs with ``AUTH_ENABLED=False`` (see
    ``conftest.py``), so the CSRF middleware is disabled by design.  The tests
    below verify constants and confirm that the middleware is a no-op in that
    configuration.
    """

    def test_csrf_constants(self):
        """Verify the constant sets have the expected members."""
        assert "POST" in CSRF_PROTECTED_METHODS
        assert "PUT" in CSRF_PROTECTED_METHODS
        assert "DELETE" in CSRF_PROTECTED_METHODS
        assert "PATCH" in CSRF_PROTECTED_METHODS
        assert "GET" not in CSRF_PROTECTED_METHODS
        assert "/oauth-callback" in CSRF_EXEMPT_PATHS
        assert "/api/qr-auth/claim" in CSRF_EXEMPT_PATHS

    def test_csrf_middleware_noop_when_auth_disabled(self):
        """When AUTH_ENABLED=False the middleware dispatch is a no-op (no validation)."""
        # Build a middleware instance with auth disabled.
        mock_app = AsyncMock()
        mock_config = MagicMock()
        mock_config.auth_enabled = False
        middleware = CSRFMiddleware(mock_app, mock_config)

        import asyncio

        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.url = MagicMock()
        mock_request.url.path = "/api/process/"
        mock_request.session = {}

        call_next = AsyncMock(return_value=MagicMock())
        asyncio.run(middleware.dispatch(mock_request, call_next))

        # call_next must have been called (request was not blocked).
        call_next.assert_called_once_with(mock_request)
        # Session should remain untouched (no token generated).
        assert "csrf_token" not in mock_request.session
