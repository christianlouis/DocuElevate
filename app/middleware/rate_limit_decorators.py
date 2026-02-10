#!/usr/bin/env python3

"""
Rate limiting decorators for DocuElevate API endpoints.

This module provides convenient decorators to apply rate limits to specific endpoints.
Import the limiter from main.py state and use these decorators to protect endpoints.
"""

from functools import wraps

from fastapi import Request

# Import will happen at runtime to avoid circular dependencies
_limiter = None


def get_limiter():
    """Get the limiter instance from the app state."""
    global _limiter
    if _limiter is None:
        from app.main import app

        _limiter = app.state.limiter
    return _limiter


def limit(rate_limit: str):
    """
    Apply a rate limit to an endpoint.
    
    Args:
        rate_limit: Rate limit string (e.g., "10/minute", "100/hour")
        
    Returns:
        Decorator function
        
    Example:
        @router.post("/login")
        @limit("10/minute")
        async def login(request: Request):
            ...
    """

    def decorator(func):
        limiter = get_limiter()
        # Apply the slowapi limit decorator
        return limiter.limit(rate_limit)(func)

    return decorator


def exempt():
    """
    Exempt an endpoint from rate limiting.
    
    Returns:
        Decorator function
        
    Example:
        @router.get("/health")
        @exempt()
        def health_check():
            ...
    """

    def decorator(func):
        limiter = get_limiter()
        # Apply the slowapi exempt decorator
        return limiter.exempt(func)

    return decorator
