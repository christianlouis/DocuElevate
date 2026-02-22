#!/usr/bin/env python3

"""
CSRF Protection Middleware for DocuElevate.

This middleware implements Cross-Site Request Forgery (CSRF) protection for all
state-changing HTTP operations (POST, PUT, DELETE, PATCH).

How it works:
- A cryptographically secure token is generated per session and stored in the session.
- The token is attached to ``request.state.csrf_token`` so Jinja2 templates can render it.
- For every state-changing request the middleware validates the submitted token by
  checking (in order):
    1. The ``X-CSRF-Token`` HTTP request header  (used by AJAX / fetch calls).
    2. The ``csrf_token`` field in ``application/x-www-form-urlencoded`` bodies
       (used by traditional HTML forms such as the login form).
  Multipart file-upload requests must always supply the token via the header.
- Validation is only enforced when ``AUTH_ENABLED=True``.  When authentication is
  disabled (development / single-user mode) the middleware is a no-op.

Exempt paths (CSRF is not checked even for state-changing methods):
- ``/oauth-callback`` – OAuth 2.0 callback; protected by the ``state`` parameter.
"""

import logging
import secrets
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse

logger = logging.getLogger(__name__)

# HTTP methods that change server state and therefore require a valid CSRF token.
CSRF_PROTECTED_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

# Paths that must never be CSRF-checked (e.g. OAuth flow endpoints that carry
# their own replay-protection mechanism).
CSRF_EXEMPT_PATHS = {
    "/oauth-callback",
}


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Middleware that generates and validates CSRF tokens for state-changing requests.

    Token lifecycle
    ---------------
    1. On the first request for a session a 64-character hex token is created with
       ``secrets.token_hex(32)`` and stored in ``request.session["csrf_token"]``.
    2. On every subsequent request the existing token is read from the session.
    3. The token is always attached to ``request.state.csrf_token`` so that
       Jinja2 templates (and response processors) can embed it.

    Validation
    ----------
    For ``POST``, ``PUT``, ``DELETE``, and ``PATCH`` requests the middleware
    checks whether the submitted token matches the session token using a
    constant-time comparison (``secrets.compare_digest``) to prevent timing
    attacks.

    Failure response
    ----------------
    - API routes (``/api/*``):  HTTP 403 JSON response.
    - All other routes:         HTTP 302 redirect to ``/login?error=…``.
    """

    def __init__(self, app, config):
        """
        Initialise the middleware.

        Args:
            app:    The ASGI application.
            config: Application settings object (``app.config.Settings``).
                    ``config.auth_enabled`` controls whether CSRF enforcement is active.
        """
        super().__init__(app)
        self.config = config
        self.enabled = config.auth_enabled
        if self.enabled:
            logger.info("CSRF protection middleware enabled")
        else:
            logger.info("CSRF protection middleware disabled (AUTH_ENABLED=False)")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request: generate/attach the token and validate it when required.

        Args:
            request:   Incoming HTTP request.
            call_next: Next middleware or route handler in the ASGI chain.

        Returns:
            HTTP response, or an error response when CSRF validation fails.
        """
        if not self.enabled:
            return await call_next(request)

        # Generate or retrieve the per-session CSRF token.
        csrf_token = request.session.get("csrf_token")
        if not csrf_token:
            csrf_token = secrets.token_hex(32)
            request.session["csrf_token"] = csrf_token

        # Attach token to request state so templates and route handlers can access it.
        request.state.csrf_token = csrf_token

        # Validate for state-changing methods on non-exempt paths.
        if request.method in CSRF_PROTECTED_METHODS and request.url.path not in CSRF_EXEMPT_PATHS:
            submitted_token = await self._get_submitted_token(request)
            if not submitted_token or not secrets.compare_digest(csrf_token, submitted_token):
                logger.warning(
                    f"[SECURITY] CSRF_VALIDATION_FAILED method={request.method} path={request.url.path}"
                )
                if request.url.path.startswith("/api/"):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "CSRF token missing or invalid"},
                    )
                return RedirectResponse(url="/login?error=Invalid+request", status_code=302)

        return await call_next(request)

    @staticmethod
    async def _get_submitted_token(request: Request) -> str | None:
        """
        Extract the CSRF token submitted by the client.

        Checks (in priority order):
        1. ``X-CSRF-Token`` request header – preferred for AJAX / fetch requests.
        2. ``csrf_token`` form field in ``application/x-www-form-urlencoded`` bodies –
           used by plain HTML forms (e.g. the login form).

        Multipart bodies (file uploads) are intentionally not parsed here to avoid
        buffering large uploads in middleware; those endpoints must send the token
        via the header instead.

        Args:
            request: The incoming HTTP request.

        Returns:
            The submitted CSRF token string, or ``None`` if not found.
        """
        # 1. Check the request header (AJAX / fetch).
        token = request.headers.get("X-CSRF-Token")
        if token:
            return token

        # 2. For URL-encoded form bodies only (plain HTML form submissions).
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type:
            try:
                form = await request.form()
                token = form.get("csrf_token")
                if token:
                    return str(token)
            except Exception as exc:
                logger.debug(f"CSRF: could not parse form body: {exc}")

        return None
