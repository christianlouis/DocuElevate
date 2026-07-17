"""
Module for masking sensitive information in configuration values
"""

from sqlalchemy.engine import make_url

CONFIGURED_VALUE = "<configured>"
NOT_CONFIGURED_VALUE = "<not configured>"

_SENSITIVE_NAME_PARTS = {
    "credential",
    "credentials",
    "cookie",
    "dsn",
    "key",
    "password",
    "passphrase",
    "secret",
    "token",
}
_SENSITIVE_NAME_FRAGMENTS = (
    "access_key",
    "api_key",
    "auth_token",
    "client_secret",
    "credentials_json",
    "private_key",
    "refresh_token",
    "session_secret",
    "virtual_key",
)
_SENSITIVE_URL_SETTINGS = {
    "audit_siem_http_custom_headers",
    "database_url",
    "notification_urls",
    "redis_url",
    "uptime_kuma_url",
}
_OPERATIONAL_TOKEN_FRAGMENTS = (
    "token_budget",
    "token_count",
    "token_limit",
    "token_reservation",
    "token_threshold",
)
_NON_SECRET_SETTING_NAMES = {
    "cors_allow_credentials",
    "dropbox_allow_global_credentials_for_integrations",
    "notify_on_credential_failure",
    "sftp_disable_host_key_verification",
    "social_auth_dropbox_use_global_credentials",
    "social_auth_generic_oauth2_token_url",
    "social_auth_google_use_global_credentials",
    "social_auth_microsoft_use_global_credentials",
}


def is_sensitive_setting(name: str) -> bool:
    """Return whether a setting may contain authentication material.

    Singular ``token`` parts are secret-bearing, while operational settings
    such as ``max_completion_tokens`` and token budgets intentionally remain
    visible.
    """
    normalized = name.lower()
    if normalized in _NON_SECRET_SETTING_NAMES:
        return False
    if normalized in _SENSITIVE_URL_SETTINGS:
        return True
    if any(fragment in normalized for fragment in _SENSITIVE_NAME_FRAGMENTS):
        return True
    if any(fragment in normalized for fragment in _OPERATIONAL_TOKEN_FRAGMENTS):
        return False
    return any(part in _SENSITIVE_NAME_PARTS for part in normalized.split("_"))


def configured_state(value: object) -> str:
    """Describe only whether a secret exists, never any part of its value."""
    if value is None:
        return NOT_CONFIGURED_VALUE
    if isinstance(value, (str, list, dict, set, tuple)) and not value:
        return NOT_CONFIGURED_VALUE
    return CONFIGURED_VALUE


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
