"""Validation helpers for S3-compatible destination configuration."""

from urllib.parse import urlparse


def is_valid_s3_endpoint(endpoint: str | None) -> bool:
    """Return whether an S3 endpoint is a safe, absolute HTTPS URL."""
    if not isinstance(endpoint, str) or endpoint != endpoint.strip():
        return False
    try:
        parsed = urlparse(endpoint)
        port = parsed.port  # Validate an explicitly supplied port.
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and (port is None or port > 0)
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )
