"""
Settings management views for the application.
"""

import inspect
import logging
import os
from functools import wraps

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.utils.config_validator.masking import mask_sensitive_value
from app.utils.settings_service import (
    SETTING_METADATA,
    get_all_settings_from_db,
    get_setting_metadata,
    get_settings_by_category,
)
from app.views.base import APIRouter, get_db, require_login, settings, templates

logger = logging.getLogger(__name__)
router = APIRouter()


def require_admin_access(func):
    """
    Decorator to require admin access for a route.

    This decorator checks if the user in the session has admin privileges.
    If not, redirects to the home page. Works with both sync and async functions,
    though FastAPI route handlers should always be async.
    """

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        user = request.session.get("user")
        if not user or not user.get("is_admin"):
            logger.warning("Non-admin user attempted to access admin-only route")
            return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

        # FastAPI route handlers are async, but we support sync for flexibility
        if inspect.iscoroutinefunction(func):
            return await func(request, *args, **kwargs)
        else:
            return func(request, *args, **kwargs)

    return wrapper


@router.get("/settings")
@require_login
@require_admin_access
async def settings_page(request: Request, db: Session = Depends(get_db)):
    """
    Settings management page - admin only.

    This page is a convenience feature to view and edit settings.
    Values are displayed in precedence order: Database > Environment > Defaults
    """

    try:
        # Get settings from database
        db_settings = get_all_settings_from_db(db)

        # Get settings organized by category
        categories = get_settings_by_category()

        # Build settings data for display
        settings_data = {}
        for category, keys in categories.items():
            settings_data[category] = []
            for key in keys:
                # Get current value from settings (already has precedence applied)
                value = getattr(settings, key, None)

                # Determine the source of this setting
                # Check if it's in the database
                if key in db_settings:
                    source = "database"
                    source_label = "DB"
                    source_color = "green"
                # Check if it's from environment variable
                elif key.upper() in os.environ or key in os.environ:
                    source = "environment"
                    source_label = "ENV"
                    source_color = "blue"
                else:
                    # It's using the default value
                    source = "default"
                    source_label = "DEFAULT"
                    source_color = "gray"

                # Get metadata
                metadata = get_setting_metadata(key)

                # Mask sensitive values
                display_value = value
                if metadata.get("sensitive") and value:
                    display_value = mask_sensitive_value(value)

                settings_data[category].append(
                    {
                        "key": key,
                        "display_value": display_value if display_value is not None else "",
                        "metadata": metadata,
                        "source": source,
                        "source_label": source_label,
                        "source_color": source_color,
                    }
                )

        return templates.TemplateResponse(
            "settings.html", {"request": request, "settings_data": settings_data, "app_version": settings.version}
        )
    except Exception as e:
        logger.error(f"Error loading settings page: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load settings page")


@router.get("/admin/credentials")
@require_login
@require_admin_access
async def credentials_page(request: Request, db: Session = Depends(get_db)):
    """
    Credential audit page - admin only.

    Displays all sensitive credential settings grouped by category, showing
    whether each is configured and whether it comes from the database or an
    environment variable. Supports the credential rotation workflow.
    """
    try:
        db_settings = get_all_settings_from_db(db)
        categories: dict[str, list[dict]] = {}

        for key, meta in SETTING_METADATA.items():
            if not meta.get("sensitive", False):
                continue

            env_value = getattr(settings, key, None)
            in_db = key in db_settings and db_settings[key]

            if in_db:
                source = "db"
                configured = True
            elif env_value:
                source = "env"
                configured = True
            else:
                source = None
                configured = False

            category = meta.get("category", "Other")
            if category not in categories:
                categories[category] = []

            categories[category].append(
                {
                    "key": key,
                    "description": meta.get("description", ""),
                    "configured": configured,
                    "source": source,
                    "restart_required": meta.get("restart_required", False),
                }
            )

        total = sum(len(v) for v in categories.values())
        configured_count = sum(1 for creds in categories.values() for c in creds if c["configured"])

        return templates.TemplateResponse(
            "credentials.html",
            {
                "request": request,
                "categories": categories,
                "total": total,
                "configured_count": configured_count,
                "unconfigured_count": total - configured_count,
                "app_version": settings.version,
            },
        )
    except Exception as e:
        logger.error(f"Error loading credentials page: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load credentials page")
