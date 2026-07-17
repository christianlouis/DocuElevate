"""
Module for masking sensitive information in configuration values
"""

from sqlalchemy.engine import make_url


def mask_sensitive_value(value: str | None) -> str | None:
    """
    Masks sensitive values like API keys in logs and output
    """
    # Return masked value for sensitive data
    if value and isinstance(value, str) and len(value) > 8:
        return value[:4] + "*" * (len(value) - 4)
    return value


def redact_sensitive_value(value: str | None) -> str | None:
    """Mask a configured secret without ever returning it verbatim.

    ``mask_sensitive_value`` predates API/export redaction and intentionally
    leaves short display values alone. Public response surfaces need the
    stronger invariant implemented here.
    """
    if not value:
        return value
    masked = mask_sensitive_value(value)
    return "********" if masked == value else masked


def mask_database_url(value: str | None) -> str | None:
    """Preserve useful database location details while hiding credentials."""
    if not value or not isinstance(value, str):
        return value
    try:
        parsed = make_url(value)
        return parsed.render_as_string(hide_password=True)
    except Exception:
        # Malformed connection strings may still contain credentials. Never
        # echo them back merely because SQLAlchemy cannot parse the value.
        return mask_sensitive_value(value)
