"""
Status and configuration views for the application.
"""

import logging
import os
from datetime import datetime

from fastapi import Request

from app.views.base import APIRouter, require_login, settings, templates

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_git_sha() -> str:
    """Extract shortened git SHA from settings, or 'Unknown'."""
    try:
        git_sha = settings.git_sha
        return git_sha[:7] if git_sha and git_sha != "unknown" else "Unknown"
    except Exception:
        return "Unknown"


def _get_container_info() -> dict:
    """Detect Docker environment and collect container metadata."""
    container_info: dict = {"is_docker": False, "git_sha": _get_git_sha()}
    try:
        if not os.path.exists("/.dockerenv"):
            return container_info

        container_info["is_docker"] = True
        # Try to get container ID from cgroup
        try:
            with open("/proc/self/cgroup", "r") as f:
                for line in f:
                    if "docker" in line:
                        container_info["id"] = line.split("/")[-1].strip()[:12]
                        break
        except Exception:
            container_info["id"] = "Unknown"

        # Try to get runtime information
        try:
            container_info["runtime_info"] = settings.runtime_info
        except Exception:
            pass

    except Exception:
        container_info = {"is_docker": False, "id": "Unknown", "git_sha": "Unknown"}

    return container_info


@router.get("/status")
@require_login
async def status_dashboard(request: Request):
    """
    Status dashboard showing all configured integration targets
    """
    from app.utils.config_validator import get_provider_status

    providers = get_provider_status()
    build_date = getattr(settings, "build_date", "Unknown")
    container_info = _get_container_info()
    notification_urls = getattr(settings, "notification_urls", [])

    return templates.TemplateResponse(
        "status_dashboard.html",
        {
            "request": request,
            "providers": providers,
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
    from app.utils.config_validator import get_settings_for_display

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
