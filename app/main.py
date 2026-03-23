#!/usr/bin/env python3
import json as _json_mod
import logging
import os
import pathlib
from contextlib import asynccontextmanager
from datetime import datetime as _dt
from datetime import timezone as _tz

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi.errors import RateLimitExceeded
from starlette.config import Config
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api import router as api_router
from app.api.graphql_api import graphql_router
from app.api.local_auth import router as local_auth_router
from app.auth import router as auth_router
from app.config import settings
from app.database import init_db
from app.middleware.audit_log import AuditLogMiddleware
from app.middleware.csrf import CSRFMiddleware
from app.middleware.rate_limit import create_limiter, get_rate_limit_exceeded_handler
from app.middleware.request_size_limit import RequestSizeLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.utils.config_validator import check_all_configs
from app.utils.notification import init_apprise, notify_shutdown, notify_startup
from app.utils.sentry import init_sentry

# Import the routers - now using views directly instead of frontend
from app.views import router as frontend_router

# Explicitly include the files router
from app.views.files import router as files_router

# ---------------------------------------------------------------------------
# Configure Python root logging level early so that *all* loggers (including
# those already created via ``logging.getLogger(__name__)`` in other modules)
# respect the configured level.
#
# Standard behaviour (matches Django, Flask, 12-factor conventions):
#   • ``LOG_LEVEL`` env var takes precedence when explicitly set.
#   • When ``DEBUG=True`` and ``LOG_LEVEL`` is **not** set, the effective
#     level is automatically lowered to ``DEBUG``.
#   • Default (neither flag set): ``INFO``.
#
# ``LOG_FORMAT=json`` enables structured JSON lines on stdout, suitable for
# Promtail, Fluentd, Filebeat, Datadog, Splunk UF, or any log collector.
#
# ``LOG_SYSLOG_ENABLED=true`` adds a Python SysLogHandler so that every log
# message is also forwarded to the configured syslog receiver — useful for
# traditional (non-container) deployments and centralised SIEM ingestion.
#
# Noisy third-party loggers (httpx, httpcore, authlib, etc.) are pinned to
# WARNING when the app-level is DEBUG to keep output useful.
# ---------------------------------------------------------------------------
_explicit_log_level = os.environ.get("LOG_LEVEL")
if settings.debug and _explicit_log_level is None:
    _effective_level = "DEBUG"
else:
    _effective_level = settings.log_level.upper()

_effective_level_int = getattr(logging, _effective_level, logging.INFO)


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line for machine consumption.

    Fields emitted: ``timestamp``, ``level``, ``logger``, ``message``,
    ``module``, ``funcName``, ``lineno``, and — when present — ``exc_info``.
    Compatible with Grafana Loki, Splunk, ELK, Datadog, and most SIEM tools.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": _dt.fromtimestamp(record.created, tz=_tz.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno,
        }
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exc_info"] = self.formatException(record.exc_info)
        return _json_mod.dumps(log_entry, default=str)


# Choose formatter based on LOG_FORMAT setting
if settings.log_format.lower() == "json":
    _handler = logging.StreamHandler()
    _handler.setFormatter(_JsonFormatter())
    logging.root.handlers = [_handler]
    logging.root.setLevel(_effective_level_int)
else:
    logging.basicConfig(
        level=_effective_level_int,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )

# Optional: forward application logs to a syslog receiver
if settings.log_syslog_enabled:
    import logging.handlers as _lh
    import socket as _socket

    _proto = settings.log_syslog_protocol.lower()
    _socktype = _socket.SOCK_STREAM if _proto == "tcp" else _socket.SOCK_DGRAM
    _syslog_handler = _lh.SysLogHandler(
        address=(settings.log_syslog_host, settings.log_syslog_port),
        socktype=_socktype,
    )
    _syslog_handler.setLevel(_effective_level_int)
    # Use the same formatter as stdout (text or JSON)
    if settings.log_format.lower() == "json":
        _syslog_handler.setFormatter(_JsonFormatter())
    else:
        _syslog_handler.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))
    logging.root.addHandler(_syslog_handler)

# Keep noisy third-party loggers quiet at DEBUG level
if _effective_level_int <= logging.DEBUG:
    for _noisy in (
        "httpx",
        "httpcore",
        "authlib",
        "urllib3",
        "hpack",
        "multipart",
        "watchfiles",
    ):
        logging.getLogger(_noisy).setLevel(logging.WARNING)

_startup_logger = logging.getLogger(__name__)
_startup_logger.info(
    "Root logging level set to %s (debug=%s, format=%s, syslog=%s)",
    _effective_level,
    settings.debug,
    settings.log_format,
    settings.log_syslog_enabled,
)

# Load configuration from .env for the session key
config = Config(".env")
# Use settings.session_secret which has proper validation
# Fallback to raising an error if not set when auth is enabled
if settings.auth_enabled and not settings.session_secret:
    raise ValueError(
        "SESSION_SECRET must be set when AUTH_ENABLED=True. "
        "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
    )
SESSION_SECRET = (
    settings.session_secret or "INSECURE_DEFAULT_FOR_DEVELOPMENT_ONLY_DO_NOT_USE_IN_PRODUCTION_MINIMUM_32_CHARS"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifespan events (startup and shutdown).
    This replaces the deprecated @app.on_event decorators.
    """
    # Startup: Initialize database
    init_db()  # Create tables if they don't exist

    # Factory reset on startup — wipe all user data before anything else
    if settings.factory_reset_on_startup:
        from app.utils.system_reset import perform_startup_reset

        perform_startup_reset()

    # Load settings from database after DB initialization
    from app.database import SessionLocal
    from app.utils.config_loader import load_settings_from_db

    db = SessionLocal()
    try:
        load_settings_from_db(settings, db)
        logging.info("Database settings loaded successfully")
    except Exception as e:
        logging.error(f"Failed to load database settings: {e}")
    finally:
        db.close()

    # Re-register OAuth / social-login providers now that DB settings are
    # loaded.  auth.py runs its initial registration at import time (before
    # the lifespan runs), so providers that are only configured in the
    # database would not be registered yet.  Calling refresh here ensures
    # they are active immediately on startup without any manual restart.
    try:
        from app.auth import refresh_social_providers

        refresh_social_providers()
    except Exception as e:
        logging.warning(f"Could not refresh social login providers on startup: {e}")

    # Initialize Sentry after DB settings are loaded so that values configured
    # via the database UI (e.g. SENTRY_DSN) are respected in addition to env vars.
    init_sentry()

    # Ensure OCR language data is available (background download, non-blocking)
    from app.utils.ocr_language_manager import ensure_ocr_languages_async

    ensure_ocr_languages_async()

    # Force settings dump to log for troubleshooting
    from app.utils.config_validator import dump_all_settings

    dump_all_settings()

    # Validate configuration
    config_issues = check_all_configs()

    # Log overall status
    has_issues = any(config_issues["email"]) or any(
        len(issues) > 0 for provider, issues in config_issues["storage"].items()
    )
    if has_issues:
        logging.warning("Application started with configuration issues - some features may be unavailable")
    else:
        logging.info("Application started with valid configuration")

    logging.info("Router organization: Using refactored API routers from app/api/ directory")

    # Initialize notification system
    init_apprise()

    # Send startup notification
    notify_startup()

    # Seed default subscription plans if none exist
    try:
        from app.database import SessionLocal as _SessionLocal
        from app.utils.subscription import seed_default_plans as _seed_plans

        _db_seed = _SessionLocal()
        try:
            _seed_plans(_db_seed)
        finally:
            _db_seed.close()
    except Exception:
        logging.debug("Subscription plan seeding skipped — DB may not be ready yet")  # noqa: S110

    # Seed the default system pipeline (mirrors the current hardcoded processing
    # workflow) so it is immediately visible in the Pipelines management UI.
    try:
        from app.api.pipelines import seed_default_pipeline as _seed_pipeline
        from app.database import SessionLocal as _SessionLocal  # noqa: F811 (re-import for clarity)

        _db_pipeline = _SessionLocal()
        try:
            _seed_pipeline(_db_pipeline)
        finally:
            _db_pipeline.close()
    except Exception:
        logging.debug("Default pipeline seeding skipped — DB may not be ready yet")  # noqa: S110

    # Seed the default scheduled batch processing jobs so they appear in the
    # admin UI (/admin/scheduled-jobs) on first startup.
    try:
        from app.api.scheduled_jobs import seed_default_scheduled_jobs as _seed_jobs
        from app.database import SessionLocal as _SessionLocal  # noqa: F811

        _db_jobs = _SessionLocal()
        try:
            _seed_jobs(_db_jobs)
        finally:
            _db_jobs.close()
    except Exception:
        logging.debug("Scheduled jobs seeding skipped — DB may not be ready yet")  # noqa: S110

    # Seed the built-in compliance templates (GDPR, HIPAA, SOC2) so they
    # are available in the admin compliance dashboard on first startup.
    try:
        from app.database import SessionLocal as _SessionLocal  # noqa: F811
        from app.utils.compliance_service import seed_compliance_templates as _seed_compliance

        _db_compliance = _SessionLocal()
        try:
            _seed_compliance(_db_compliance)
        finally:
            _db_compliance.close()
    except Exception:
        logging.debug("Compliance template seeding skipped — DB may not be ready yet")  # noqa: S110

    # Application is now running
    yield

    # Shutdown: Cleanup tasks
    logging.info("Application shutting down")

    # Send shutdown notification
    notify_shutdown()


app = FastAPI(
    title="DocuElevate",
    lifespan=lifespan,
    docs_url="/admin/api-docs",
    redoc_url="/admin/api-redoc",
)

# Initialize rate limiter and attach to app state
limiter = create_limiter(redis_url=settings.redis_url, enabled=settings.rate_limiting_enabled)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, get_rate_limit_exceeded_handler())

# Middleware stack (order matters - applied in reverse order)
# Last added middleware is executed first

# 1) Security Headers Middleware (outermost - adds headers to final response)
#    Configure via SECURITY_HEADERS_ENABLED environment variable
#    Set to False if reverse proxy (Traefik, Nginx) handles security headers
app.add_middleware(SecurityHeadersMiddleware, config=settings)

# 2) Request Size Limit Middleware - enforces body size limits before reading
#    MAX_REQUEST_BODY_SIZE: limit for non-file requests (default 1 MB)
#    MAX_UPLOAD_SIZE: limit for multipart/form-data uploads (default 1 GB)
#    See SECURITY_AUDIT.md – Code Security section
app.add_middleware(RequestSizeLimitMiddleware, config=settings)

# 3) CSRF Protection Middleware - validates CSRF tokens for state-changing operations
#    Only active when AUTH_ENABLED=True. Exempts OAuth callback endpoints.
#    Tokens are stored in the session and validated via X-CSRF-Token header or form field.
app.add_middleware(CSRFMiddleware, config=settings)

# 2) Audit Logging Middleware - logs all requests with sensitive data masking
#    Configure via AUDIT_LOGGING_ENABLED environment variable
#    See SECURITY_AUDIT.md – Infrastructure Security section
app.add_middleware(AuditLogMiddleware, config=settings)


# 3) Session Middleware (for request.session to work)
def _get_session_max_age() -> int:
    """Compute session max-age at startup time."""
    try:
        from app.utils.session_manager import get_session_max_age_seconds

        return get_session_max_age_seconds()
    except Exception:
        return 30 * 86400  # 30 days default fallback


app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=_get_session_max_age())

# 3a) CORS Middleware - handles cross-origin requests and preflight (OPTIONS) responses.
#     Disabled by default: set CORS_ENABLED=True only when NOT using a reverse proxy
#     (Traefik, Nginx) that already injects CORS headers. When enabled, this middleware
#     runs after the session layer so preflight requests bypass CSRF/auth checks.
#     Allowed origins, methods, headers, and credentials are all configurable via env vars.
#     See SECURITY_AUDIT.md – Infrastructure Security section and docs/DeploymentGuide.md.
if settings.cors_enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allowed_methods,
        allow_headers=settings.cors_allowed_headers,
    )

# 4) Respect the X-Forwarded-* headers from reverse proxy (Traefik, Nginx)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# 5) Restrict valid hosts to prevent Host header attacks
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[settings.external_hostname, "localhost", "127.0.0.1"],
)

# Mount the static files directory
static_dir = pathlib.Path(__file__).parents[1] / "frontend" / "static"
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
else:
    print(f"WARNING: Static directory not found at {static_dir}. Static files will not be served.")

# Mount the built MkDocs developer documentation at /developer-docs/
# These docs target administrators and developers, not end-users.
# The user-facing Help Center is served by the /help view instead.
# The docs are pre-built into docs_build/ during the Docker image build.
# When running locally, run `mkdocs build` from the repo root first.
docs_build_dir = pathlib.Path(__file__).parents[1] / "docs_build"
if os.path.exists(docs_build_dir):
    app.mount("/developer-docs", StaticFiles(directory=str(docs_build_dir), html=True), name="developer_docs")
else:
    print(f"INFO: Developer docs not found at {docs_build_dir}. Run 'mkdocs build' to generate them.")


# Custom exception handlers that return JSON for API routes and HTML for frontend routes
# These use their own separate templates instance so that patches in tests on individual
# view modules do not affect the error handler rendering.
_error_templates_dir = pathlib.Path(__file__).parents[1] / "frontend" / "templates"
_error_templates = Jinja2Templates(directory=str(_error_templates_dir))
# Register the i18n translate helper as a global so error templates can use {{ _("key") }}.
# Error pages use the default language (English); request-specific locale is not needed here.
from app.utils.i18n import SUPPORTED_LANGUAGES as _SUPPORTED_LANGUAGES  # noqa: E402
from app.utils.i18n import get_suggested_languages as _get_suggested_languages  # noqa: E402
from app.utils.i18n import translate as _translate_fn  # noqa: E402

_error_templates.env.globals["_"] = lambda key, **kwargs: _translate_fn(key, "en", **kwargs)
_error_templates.env.globals["min"] = min
_error_templates.env.globals["max"] = max
_error_templates.env.globals["supported_languages"] = _SUPPORTED_LANGUAGES
_error_templates.env.globals["suggested_languages"] = _get_suggested_languages("en", "")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Handle all HTTPException instances.
    Returns JSON for API routes, HTML templates for frontend routes.
    """
    # For API routes, always return JSON
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    # For frontend routes, return appropriate HTML templates
    # Handle 404 errors with a custom template
    if exc.status_code == 404:
        return _error_templates.TemplateResponse(request, "404.html", status_code=status.HTTP_404_NOT_FOUND)

    # For other HTTP errors, we could create specific templates or use a generic one
    # For now, return a simple error page
    return _error_templates.TemplateResponse(
        request,
        "404.html",  # Reuse 404 template for other errors, or create a generic error template
        status_code=exc.status_code,
    )


@app.exception_handler(500)
async def custom_500_handler(request: Request, exc: Exception):
    """
    Handle internal server errors (500).
    Returns JSON for API routes, HTML templates for frontend routes.
    """
    # For API routes, return JSON instead of HTML
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    # Serve the 500 template for non-API routes
    return _error_templates.TemplateResponse(
        request,
        "500.html",
        context={"exc": exc},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@app.get("/test-500")
def test_500():
    raise RuntimeError("Testing forced 500 error!")


# Include the routers
app.include_router(frontend_router)
app.include_router(files_router)  # Explicitly include the files router
app.include_router(auth_router)
app.include_router(local_auth_router)
app.include_router(api_router, prefix="/api")
app.include_router(graphql_router, prefix="/graphql")
