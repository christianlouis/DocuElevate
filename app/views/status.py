"""
Status and configuration views for the application.
"""

import logging
import os
import time
from datetime import datetime

from fastapi import Request
from sqlalchemy import text

from app.database import SessionLocal, engine
from app.utils.config_validator import get_provider_status, get_settings_for_display
from app.views.base import APIRouter, require_login, settings, templates

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_database_status() -> dict:
    """Return a non-secret database health summary for the status dashboard."""
    backend = engine.url.get_backend_name()
    database_name = engine.url.database or "Unknown"
    started_at = time.perf_counter()

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - started_at) * 1000, 1)
        return {
            "configured": True,
            "status": "healthy",
            "label": "Healthy",
            "backend": backend,
            "database": database_name,
            "latency_ms": latency_ms,
            "error": None,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started_at) * 1000, 1)
        logger.warning("Database status check failed: %s", exc)
        return {
            "configured": True,
            "status": "unhealthy",
            "label": "Unhealthy",
            "backend": backend,
            "database": database_name,
            "latency_ms": latency_ms,
            "error": exc.__class__.__name__,
        }


@router.get("/status")
@require_login
async def status_dashboard(request: Request):
    """
    Status dashboard showing all configured integration targets
    """
    # Get provider status
    providers = get_provider_status()
    database_status = _get_database_status()

    # Get build date from settings
    build_date = getattr(settings, "build_date", "Unknown")

    # Try to get container information
    container_info = {}
    try:
        # Check for Docker environment
        if os.path.exists("/.dockerenv"):
            # We're inside a Docker container
            container_info["is_docker"] = True

            # Try to get container ID
            try:
                with open("/proc/self/cgroup", "r") as f:
                    for line in f:
                        if "docker" in line:
                            container_id = line.split("/")[-1].strip()
                            container_info["id"] = container_id[:12]  # Short ID format
                            break
            except Exception:
                container_info["id"] = "Unknown"

            # Get Git commit SHA from settings
            try:
                git_sha = settings.git_sha
                container_info["git_sha"] = git_sha[:7] if git_sha and git_sha != "unknown" else "Unknown"
            except Exception:
                container_info["git_sha"] = "Unknown"

            # Try to get runtime information
            try:
                container_info["runtime_info"] = settings.runtime_info
            except Exception:  # noqa: S110
                pass  # Ignore if runtime_info not available
        else:
            container_info["is_docker"] = False

            # If not in Docker, get Git info from settings
            try:
                git_sha = settings.git_sha
                container_info["git_sha"] = git_sha[:7] if git_sha and git_sha != "unknown" else "Unknown"
            except Exception:
                container_info["git_sha"] = "Unknown"
    except Exception:
        container_info = {"is_docker": False, "id": "Unknown", "git_sha": "Unknown"}

    # Get notification URLs for the notification box
    notification_urls = getattr(settings, "notification_urls", [])

    return templates.TemplateResponse(
        "status_dashboard.html",
        {
            "request": request,
            "providers": providers,
            "database_status": database_status,
            "app_version": settings.version,
            "build_date": build_date,
            "debug_enabled": getattr(settings, "debug", False),
            "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "container_info": container_info,
            "settings": {"notification_urls": notification_urls},
        },
    )


@router.get("/env")
@require_login
async def env_debug(request: Request):
    """
    Debug endpoint to view environment variables and settings
    Uses actual debug setting from config
    """
    # Use the actual debug setting from configuration
    debug_enabled = settings.debug

    # Get settings data
    settings_data = get_settings_for_display(show_values=debug_enabled)

    return templates.TemplateResponse(
        "env_debug.html",
        {
            "request": request,
            "settings": settings_data,
            "debug_enabled": debug_enabled,
            "app_version": settings.version,
        },
    )
