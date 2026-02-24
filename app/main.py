#!/usr/bin/env python3
import logging
import os
import pathlib
from contextlib import asynccontextmanager

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

# Import the routers - now using views directly instead of frontend
from app.views import router as frontend_router

# Explicitly include the files router
from app.views.files import router as files_router

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

    # Application is now running
    yield

    # Shutdown: Cleanup tasks
    logging.info("Application shutting down")

    # Send shutdown notification
    notify_shutdown()


app = FastAPI(title="DocuElevate", lifespan=lifespan)

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
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

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


# Custom exception handlers that return JSON for API routes and HTML for frontend routes
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
    templates = Jinja2Templates(directory=str(static_dir.parent / "templates"))

    # Handle 404 errors with a custom template
    if exc.status_code == 404:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=status.HTTP_404_NOT_FOUND)

    # For other HTTP errors, we could create specific templates or use a generic one
    # For now, return a simple error page
    return templates.TemplateResponse(
        "404.html",  # Reuse 404 template for other errors, or create a generic error template
        {"request": request},
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
    templates = Jinja2Templates(directory=str(static_dir.parent / "templates"))
    return templates.TemplateResponse(
        "500.html",
        {"request": request, "exc": exc},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@app.get("/test-500")
def test_500():
    raise RuntimeError("Testing forced 500 error!")


# Include the routers
app.include_router(frontend_router)
app.include_router(files_router)  # Explicitly include the files router
app.include_router(auth_router)
app.include_router(api_router, prefix="/api")
