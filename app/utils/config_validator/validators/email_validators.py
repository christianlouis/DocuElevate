#!/usr/bin/env python3
"""
Email configuration validators
"""

import logging
import socket

from app.config import settings

logger = logging.getLogger(__name__)


def validate_email_config():
    """Validates email configuration settings"""
    issues = []

    # Check for required email settings
    if not getattr(settings, "email_host", None):
        issues.append("EMAIL_HOST is not configured")
    if not getattr(settings, "email_port", None):
        issues.append("EMAIL_PORT is not configured")

    # Test SMTP server connectivity if host is configured
    if getattr(settings, "email_host", None) and getattr(settings, "email_port", None):
        try:
            # Attempt to resolve the hostname
            socket.gethostbyname(settings.email_host)
        except socket.gaierror:
            issues.append(f"Cannot resolve email host: {settings.email_host}")

    # Check for authentication settings
    if not getattr(settings, "email_username", None):
        issues.append("EMAIL_USERNAME is not configured")
    if not getattr(settings, "email_password", None):
        issues.append("EMAIL_PASSWORD is not configured")

    return issues
