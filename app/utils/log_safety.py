"""Logging safeguards for providers that may include user content in DEBUG output."""

import logging

SENSITIVE_PROVIDER_LOGGERS = ("openai", "openai._base_client")


def restrict_sensitive_provider_logging(*_args: object, **_kwargs: object) -> None:
    """Prevent third-party SDKs from logging prompts, documents, or credentials."""
    for logger_name in SENSITIVE_PROVIDER_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
