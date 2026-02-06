#!/usr/bin/env python3
"""
Authentication configuration validators
"""

import logging

from app.config import settings

logger = logging.getLogger(__name__)


def validate_auth_config():
    """Validates authentication configuration settings"""
    issues = []

    # If auth is enabled, check for required settings
    if getattr(settings, "auth_enabled", False):
        # Check for session secret
        if not getattr(settings, "session_secret", None):
            issues.append("SESSION_SECRET is not configured but AUTH_ENABLED is True")
        elif len(getattr(settings, "session_secret", "")) < 32:
            issues.append("SESSION_SECRET must be at least 32 characters long")

        # Check if using simple authentication or OIDC
        using_simple_auth = bool(
            getattr(settings, "admin_username", None) and getattr(settings, "admin_password", None)
        )

        using_oidc = bool(
            getattr(settings, "authentik_client_id", None)
            and getattr(settings, "authentik_client_secret", None)
            and getattr(settings, "authentik_config_url", None)
        )

        if not using_simple_auth and not using_oidc:
            issues.append("Neither simple authentication nor OIDC are properly configured")

        # If using OIDC, check for provider name
        if using_oidc and not getattr(settings, "oauth_provider_name", None):
            issues.append("OAUTH_PROVIDER_NAME is not configured but OIDC is enabled")

    return issues
