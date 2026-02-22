#!/usr/bin/env python3

"""
Audit Logging Middleware for DocuElevate.

This middleware logs all HTTP requests and security-relevant events. Sensitive
data (passwords, tokens, secrets, API keys) is masked before logging so that
credentials are never recorded in application logs.

Security-relevant events that receive elevated ``[SECURITY]`` log entries:
- Authentication failures (401 Unauthorized)
- Authorisation denials (403 Forbidden)
- Login / logout endpoint access
- Server errors (5xx responses)

Logged per request:
- HTTP method
- Request path (query-param values for known sensitive keys are replaced with ``[REDACTED]``)
- Response status code
- Response time in milliseconds
- Client IP address (configurable)
- Authenticated username when available

See SECURITY_AUDIT.md – Infrastructure Security section for background.
"""

import logging
import re
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Query-parameter / form-field names whose *values* must never appear in logs.
# Matching is case-insensitive.
_SENSITIVE_PARAM_PATTERN = re.compile(
    r"^(password|passwd|pwd|secret|token|access_token|refresh_token|"
    r"api_key|apikey|key|credential|credentials|auth|authorization|"
    r"client_secret|private_key|session)$",
    re.IGNORECASE,
)

# HTTP headers whose values must never appear in logs.
_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
    }
)

# Endpoints considered security-sensitive for elevated logging.
_AUTH_PATHS = frozenset({"/auth", "/login", "/logout", "/oauth-login", "/oauth-callback"})


def mask_query_string(query_string: str) -> str:
    """
    Replace values of sensitive query parameters with ``[REDACTED]``.

    Args:
        query_string: Raw URL query string (e.g. ``"user=alice&password=secret"``).

    Returns:
        Query string with sensitive values replaced.
    """
    if not query_string:
        return query_string

    parts = []
    for pair in query_string.split("&"):
        if "=" in pair:
            name, _, value = pair.partition("=")
            if _SENSITIVE_PARAM_PATTERN.match(name):
                parts.append(f"{name}=[REDACTED]")
            else:
                parts.append(pair)
        else:
            parts.append(pair)
    return "&".join(parts)


def get_client_ip(request: Request) -> str:
    """
    Extract the real client IP, honouring X-Forwarded-For when present.

    Args:
        request: Incoming HTTP request.

    Returns:
        Client IP address string.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Take only the first (leftmost) address – that is the original client.
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def get_username(request: Request) -> str:
    """
    Extract the authenticated username from the session, if available.

    Args:
        request: Incoming HTTP request.

    Returns:
        Username string, or ``"anonymous"`` when not authenticated.
    """
    try:
        user = request.session.get("user") if hasattr(request, "session") else None
    except Exception:
        user = None

    if not user:
        return "anonymous"

    if isinstance(user, dict):
        return (
            user.get("preferred_username")
            or user.get("username")
            or user.get("email")
            or user.get("id")
            or "authenticated"
        )
    return str(user)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log HTTP requests and security-relevant events.

    Each request produces a single ``INFO``-level audit log line.
    Requests that result in 401/403 responses, or that target
    authentication endpoints, additionally produce a ``WARNING``-level
    security event line.  Server errors (5xx) produce an ``ERROR``-level
    security event line.

    Configuration is read from the application settings object passed at
    construction time via the ``config`` keyword argument.
    """

    def __init__(self, app, config) -> None:
        """
        Initialise the audit-log middleware.

        Args:
            app: FastAPI / ASGI application instance.
            config: Application settings object (must expose
                ``audit_logging_enabled`` and
                ``audit_log_include_client_ip`` boolean attributes).
        """
        super().__init__(app)
        self.enabled = config.audit_logging_enabled
        self.include_ip = config.audit_log_include_client_ip

        if self.enabled:
            logger.info(f"Audit logging middleware enabled (include_client_ip={self.include_ip})")
        else:
            logger.info("Audit logging middleware disabled")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request, call the next handler, then emit audit log entries.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route handler in the chain.

        Returns:
            HTTP response (unmodified).
        """
        if not self.enabled:
            return await call_next(request)

        start_time = time.monotonic()
        response = await call_next(request)
        duration_ms = int((time.monotonic() - start_time) * 1000)

        self._log_request(request, response.status_code, duration_ms)
        return response

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_path_with_masked_query(self, request: Request) -> str:
        """Return the request path with sensitive query-param values masked."""
        path = request.url.path
        raw_query = request.url.query
        if raw_query:
            masked = mask_query_string(raw_query)
            return f"{path}?{masked}"
        return path

    def _log_request(self, request: Request, status_code: int, duration_ms: int) -> None:
        """
        Emit audit log entries for a completed request.

        Args:
            request: The HTTP request object.
            status_code: HTTP response status code.
            duration_ms: Total request processing time in milliseconds.
        """
        method = request.method
        path = self._build_path_with_masked_query(request)
        username = get_username(request)
        ip_part = f" - {get_client_ip(request)}" if self.include_ip else ""

        # Core request log line (always INFO).
        logger.info(f"[AUDIT] {method} {path} {status_code} {duration_ms}ms{ip_part} - {username}")

        # Security-event log lines for noteworthy conditions.
        self._log_security_event(method, path, status_code, username, ip_part)

    def _log_security_event(
        self,
        method: str,
        path: str,
        status_code: int,
        username: str,
        ip_part: str,
    ) -> None:
        """
        Emit an additional security-event log line when warranted.

        Args:
            method: HTTP method (GET, POST, …).
            path: Sanitised request path (with masked query params).
            status_code: HTTP response status code.
            username: Authenticated username or ``"anonymous"``.
            ip_part: Pre-formatted IP string (may be empty string).
        """
        base_path = path.split("?", maxsplit=1)[0]

        if status_code == 401:
            logger.warning(f"[SECURITY] AUTH_FAILURE {method} {path} 401{ip_part} - {username}")
        elif status_code == 403:
            logger.warning(f"[SECURITY] ACCESS_DENIED {method} {path} 403{ip_part} - {username}")
        elif base_path in _AUTH_PATHS and method == "POST":
            # Login attempts (successful or not) are always noted.
            logger.info(f"[SECURITY] AUTH_ATTEMPT {method} {path} {status_code}{ip_part} - {username}")
        elif status_code >= 500:
            logger.error(f"[SECURITY] SERVER_ERROR {method} {path} {status_code}{ip_part} - {username}")
