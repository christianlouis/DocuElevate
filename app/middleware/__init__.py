"""Middleware package for DocuElevate."""

from app.middleware.security_headers import SecurityHeadersMiddleware

__all__ = ["SecurityHeadersMiddleware"]
