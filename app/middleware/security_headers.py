#!/usr/bin/env python3

"""
Security Headers Middleware for DocuElevate.

This middleware adds security headers to HTTP responses to improve browser-side security.
Headers can be configured via environment variables to support different deployment scenarios:
- Direct deployment: Enable all security headers
- Reverse proxy deployment (Traefik, Nginx, etc.): Disable headers if proxy adds them

See docs/DeploymentGuide.md for configuration guidance.
"""

import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to HTTP responses.

    This middleware adds the following security headers when enabled:
    - Strict-Transport-Security (HSTS): Forces HTTPS connections
    - Content-Security-Policy (CSP): Controls resource loading
    - X-Frame-Options: Prevents clickjacking attacks
    - X-Content-Type-Options: Prevents MIME-sniffing attacks

    Headers are configurable via environment variables to support different deployment scenarios.
    """

    def __init__(self, app, config):
        """
        Initialize the security headers middleware.

        Args:
            app: FastAPI application instance
            config: Configuration object with security header settings
        """
        super().__init__(app)
        self.config = config
        self.enabled = config.security_headers_enabled

        if self.enabled:
            logger.info("Security headers middleware enabled")
            logger.debug(
                f"HSTS: {config.security_header_hsts_enabled}, "
                f"CSP: {config.security_header_csp_enabled}, "
                f"X-Frame-Options: {config.security_header_x_frame_options_enabled}, "
                f"X-Content-Type-Options: {config.security_header_x_content_type_options_enabled}"
            )
        else:
            logger.info("Security headers middleware disabled (likely handled by reverse proxy)")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request and add security headers to the response.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler

        Returns:
            HTTP response with security headers added (if enabled)
        """
        # Process the request
        response = await call_next(request)

        # Add security headers if enabled
        if self.enabled:
            self._add_security_headers(response)

        return response

    def _add_security_headers(self, response: Response) -> None:
        """
        Add configured security headers to the response.

        Args:
            response: HTTP response to add headers to
        """
        # Strict-Transport-Security (HSTS)
        # Forces browsers to use HTTPS for all future requests to this domain
        # max-age: Time in seconds browsers should remember to only use HTTPS
        # includeSubDomains: Apply to all subdomains
        # preload: Allow inclusion in browser HSTS preload lists
        if self.config.security_header_hsts_enabled:
            hsts_value = self.config.security_header_hsts_value
            response.headers["Strict-Transport-Security"] = hsts_value
            logger.debug(f"Added HSTS header: {hsts_value}")

        # Content-Security-Policy (CSP)
        # Controls which resources browsers are allowed to load for this page
        # This helps prevent XSS attacks and other code injection attacks
        if self.config.security_header_csp_enabled:
            csp_value = self.config.security_header_csp_value
            response.headers["Content-Security-Policy"] = csp_value
            logger.debug(f"Added CSP header: {csp_value[:50]}...")

        # X-Frame-Options
        # Prevents the page from being loaded in a frame/iframe
        # This helps prevent clickjacking attacks
        if self.config.security_header_x_frame_options_enabled:
            x_frame_value = self.config.security_header_x_frame_options_value
            response.headers["X-Frame-Options"] = x_frame_value
            logger.debug(f"Added X-Frame-Options header: {x_frame_value}")

        # X-Content-Type-Options
        # Prevents browsers from MIME-sniffing responses away from declared content-type
        # This helps prevent XSS attacks based on content-type confusion
        if self.config.security_header_x_content_type_options_enabled:
            response.headers["X-Content-Type-Options"] = "nosniff"
            logger.debug("Added X-Content-Type-Options header: nosniff")
