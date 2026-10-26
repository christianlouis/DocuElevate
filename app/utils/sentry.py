"""
Sentry integration utilities for DocuElevate.

Call ``init_sentry()`` early in your application entry point (before any
request handling) to enable error tracking and performance monitoring.  The
function is a no-op when ``SENTRY_DSN`` is not configured, so it is safe to
call unconditionally in all environments.

Example (FastAPI)::

    from app.utils.sentry import init_sentry
    init_sentry()

Example (Celery worker)::

    from app.utils.sentry import init_sentry
    init_sentry(integrations_extra=["celery"])
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)

_SENSITIVE_EVENT_KEYS = frozenset(
    {
        "args",
        "body",
        "content",
        "data",
        "document",
        "document_content",
        "document_text",
        "extracted_text",
        "kwargs",
        "local_vars",
        "task_args",
        "task_kwargs",
    }
)


def _redact_sensitive_event(event: dict, hint: dict) -> dict:
    """Remove request and task payloads while preserving error diagnostics."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "headers", "query_string"):
            request.pop(key, None)

    def scrub(container: object) -> None:
        if isinstance(container, dict):
            for key in list(container):
                if str(key).lower() in _SENSITIVE_EVENT_KEYS:
                    container.pop(key, None)
                else:
                    scrub(container[key])
        elif isinstance(container, list):
            for item in container:
                scrub(item)

    scrub(event.get("extra"))
    scrub(event.get("contexts"))
    return event


def init_sentry(*, integrations_extra: list[str] | None = None) -> bool:
    """
    Initialise the Sentry SDK if ``SENTRY_DSN`` is configured.

    Args:
        integrations_extra: Optional list of additional integration names to
            activate.  Currently recognised values: ``"celery"``.  The
            ``FastApiIntegration``, ``SqlalchemyIntegration``, and
            ``LoggingIntegration`` are always included when the SDK is
            initialised.

    Returns:
        ``True`` when Sentry was successfully initialised, ``False`` otherwise
        (e.g. DSN not configured or SDK not installed).
    """
    dsn = settings.sentry_dsn
    if not dsn:
        logger.debug("Sentry DSN not configured – error monitoring disabled")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        logger.warning(
            "sentry-sdk is not installed.  Install it with: pip install 'sentry-sdk[fastapi,celery,sqlalchemy]'"
        )
        return False

    integrations = [
        StarletteIntegration(transaction_style="url"),
        FastApiIntegration(transaction_style="url"),
        SqlalchemyIntegration(),
        LoggingIntegration(
            level=logging.INFO,  # Breadcrumbs from INFO+
            event_level=logging.ERROR,  # Send Sentry events for ERROR+
        ),
    ]

    if integrations_extra and "celery" in integrations_extra:
        try:
            from sentry_sdk.integrations.celery import CeleryIntegration

            integrations.append(CeleryIntegration(monitor_beat_tasks=True))
        except ImportError:
            logger.warning("CeleryIntegration not available – skipping")

    # Clamp sample rates to [0.0, 1.0]
    traces_rate = max(0.0, min(1.0, settings.sentry_traces_sample_rate))
    profiles_rate = max(0.0, min(1.0, settings.sentry_profiles_sample_rate))

    version = _get_app_version()

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.sentry_environment,
        release=version,
        integrations=integrations,
        traces_sample_rate=traces_rate,
        profiles_sample_rate=profiles_rate,
        send_default_pii=settings.sentry_send_default_pii,
        # Request bodies, local variables, and task payloads are not telemetry.
        max_request_body_size="never",
        include_local_variables=False,
        before_send=_redact_sensitive_event,
        attach_stacktrace=True,
    )

    logger.info(
        "Sentry initialised (environment=%s, traces_sample_rate=%s)",
        settings.sentry_environment,
        traces_rate,
    )
    return True


def _get_app_version() -> str | None:
    """Return the application version string for Sentry release tracking."""
    try:
        return settings.version or None
    except AttributeError:  # pragma: no cover
        return None
