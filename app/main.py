#!/usr/bin/env python3
import os
import logging
import pathlib

from fastapi import FastAPI, HTTPException, Request, status
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
SESSION_SECRET = config(
    "SESSION_SECRET",
    default="YOUR_DEFAULT_SESSION_SECRET_MUST_BE_32_CHARS_OR_MORE"
)

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

# Custom 404 - we can still return the Jinja2 template, or the old static file:
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: HTTPException):
    # Serve the 404 template directly
    templates = Jinja2Templates(directory=str(static_dir.parent / "templates"))
    return templates.TemplateResponse(
        "404.html",
        {"request": request},
        status_code=status.HTTP_404_NOT_FOUND
    )

@app.exception_handler(500)
async def custom_500_handler(request: Request, exc: Exception):
    templates = Jinja2Templates(directory=str(static_dir.parent / "templates"))
    # Option 1: Keep it simple, just show a funny 500 message:
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



