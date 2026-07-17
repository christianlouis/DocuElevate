"""Logging safeguards for providers that may include sensitive data in output."""

import logging

SENSITIVE_PROVIDER_LOGGERS = (
    "openai",
    "openai._base_client",
    # Apprise DEBUG messages can contain complete provider request payloads,
    # including API tokens and recipient identifiers.
    "apprise",
)


def restrict_sensitive_provider_logging(*_args: object, **_kwargs: object) -> None:
    """Prevent third-party SDKs from logging prompts, documents, or credentials."""
    for logger_name in SENSITIVE_PROVIDER_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
