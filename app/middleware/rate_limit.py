#!/usr/bin/env python3

"""
Rate Limiting Middleware for DocuElevate.

This middleware provides rate limiting capabilities to protect API endpoints from abuse
and DoS attacks. It uses SlowAPI with Redis backend for distributed rate limiting.

Key features:
- Per-IP rate limiting by default
- Per-user rate limiting for authenticated endpoints
- Configurable global and per-endpoint limits
- Redis-backed for distributed deployments
- Fallback to in-memory for development

See docs/ConfigurationGuide.md and docs/API.md for configuration and usage.
"""

import logging
from typing import Callable

from fastapi import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def get_identifier(request: Request) -> str:
    """
    Get unique identifier for rate limiting.

    Uses authenticated user ID if available, otherwise falls back to IP address.
    This provides better rate limiting for authenticated users and prevents
    IP-based bypassing for authenticated endpoints.

    Args:
        request: FastAPI request object

    Returns:
        Unique identifier string for rate limiting
    """
    # Check if user is authenticated (from session)
    if hasattr(request, "session") and request.session.get("user"):
        user = request.session.get("user")
        # Use username or user_id as identifier
        if isinstance(user, dict):
            identifier = user.get("username") or user.get("user_id") or user.get("id")
            if identifier:
                logger.debug(f"Rate limiting by user: {identifier}")
                return f"user:{identifier}"

    # Fall back to IP address for unauthenticated requests
    ip = get_remote_address(request)
    logger.debug(f"Rate limiting by IP: {ip}")
    return ip


def create_limiter(redis_url: str = None, enabled: bool = True) -> Limiter:
    """
    Create and configure the rate limiter.

    Args:
        redis_url: Redis connection URL for distributed rate limiting
        enabled: Whether rate limiting is enabled (default: True)

    Returns:
        Configured Limiter instance
    """
    if not enabled:
        logger.info("Rate limiting is disabled")
        # Return a limiter with very high limits when disabled
        return Limiter(
            key_func=get_identifier,
            default_limits=["10000/minute"],  # Effectively unlimited
            enabled=False,
        )

    # Use Redis if available, otherwise fall back to in-memory
    storage_uri = redis_url if redis_url else "memory://"

    if redis_url:
        logger.info(f"Rate limiting enabled with Redis backend: {redis_url}")
    else:
        logger.warning(
            "Rate limiting using in-memory storage (not suitable for production with multiple workers). "
            "Configure REDIS_URL for distributed rate limiting."
        )

    # Create limiter with default limits
    # Default: 100 requests per minute per IP/user
    limiter = Limiter(
        key_func=get_identifier,
        default_limits=["100/minute"],
        storage_uri=storage_uri,
        strategy="fixed-window",  # Can be: fixed-window, moving-window, or fixed-window-elastic-expiry
        enabled=True,
    )

    logger.info("Rate limiter initialized successfully")
    return limiter


def get_rate_limit_exceeded_handler() -> Callable:
    """
    Get the rate limit exceeded exception handler.

    Returns a handler that provides user-friendly 429 responses with
    Retry-After header when rate limit is exceeded.

    Returns:
        Exception handler function
    """
    return _rate_limit_exceeded_handler
