#!/usr/bin/env python3
import os
import logging
import pathlib

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.config import Config
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from pathlib import Path

from app.database import init_db
from app.config import settings
from app.utils.config_validator import check_all_configs
from app.utils.notification import init_apprise, send_notification, notify_startup, notify_shutdown

# Import the routers - now using views directly instead of frontend
from app.views import router as frontend_router
from app.api import router as api_router
from app.auth import router as auth_router

# Explicitly include the files router
from app.views.files import router as files_router

# Load configuration from .env for the session key
config = Config(".env")
# Use settings.session_secret which has proper validation
# Fallback to raising an error if not set when auth is enabled
if settings.auth_enabled and not settings.session_secret:
    raise ValueError("SESSION_SECRET must be set when AUTH_ENABLED=True. Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'")
SESSION_SECRET = settings.session_secret or "INSECURE_DEFAULT_FOR_DEVELOPMENT_ONLY_DO_NOT_USE_IN_PRODUCTION_MINIMUM_32_CHARS"

app = FastAPI(title="DocuElevate")

# 1) Session Middleware (for request.session to work)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# 2) Respect the X-Forwarded-* headers from Traefik
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# 3) (Optional but recommended) Restrict valid hosts:
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[
    settings.external_hostname,
    "localhost",
    "127.0.0.1"
])

# Mount the static files directory
static_dir = pathlib.Path(__file__).parents[1] / "frontend" / "static"
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
else:
    print(f"WARNING: Static directory not found at {static_dir}. Static files will not be served.")

@app.on_event("startup")
def on_startup():
    init_db()  # Create tables if they don't exist

@app.on_event("startup")
async def startup_event():
    """Run startup tasks for the application"""
    # Force settings dump to log for troubleshooting
    from app.utils.config_validator import dump_all_settings
    dump_all_settings()
    
    # Validate configuration
    config_issues = check_all_configs()
    
    # Log overall status
    has_issues = any(config_issues['email']) or any(len(issues) > 0 for provider, issues in config_issues['storage'].items())
    if has_issues:
        logging.warning("Application started with configuration issues - some features may be unavailable")
    else:
        logging.info("Application started with valid configuration")
    
    logging.info("Router organization: Using refactored API routers from app/api/ directory")
    
    # Initialize notification system
    init_apprise()
    
    # Send startup notification
    notify_startup()

@app.on_event("shutdown")
async def shutdown_event():
    """Run shutdown tasks for the application"""
    logging.info("Application shutting down")
    
    # Send shutdown notification
    notify_shutdown()

# Custom exception handlers that return JSON for API routes and HTML for frontend routes
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Handle all HTTPException instances.
    Returns JSON for API routes, HTML templates for frontend routes.
    """
    # For API routes, always return JSON
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    
    # For frontend routes, return appropriate HTML templates
    templates = Jinja2Templates(directory=str(static_dir.parent / "templates"))
    
    # Handle 404 errors with a custom template
    if exc.status_code == 404:
        return templates.TemplateResponse(
            "404.html",
            {"request": request},
            status_code=status.HTTP_404_NOT_FOUND
        )
    
    # For other HTTP errors, we could create specific templates or use a generic one
    # For now, return a simple error page
    return templates.TemplateResponse(
        "404.html",  # Reuse 404 template for other errors, or create a generic error template
        {"request": request},
        status_code=exc.status_code
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
            content={"detail": "Internal server error"}
        )
    
    # Serve the 500 template for non-API routes
    templates = Jinja2Templates(directory=str(static_dir.parent / "templates"))
    return templates.TemplateResponse(
        "500.html",
        {"request": request, "exc": exc},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )

@app.get("/test-500")
def test_500():
    raise RuntimeError("Testing forced 500 error!")

# Include the routers
app.include_router(frontend_router)
app.include_router(files_router)  # Explicitly include the files router
app.include_router(auth_router)
app.include_router(api_router, prefix="/api")



