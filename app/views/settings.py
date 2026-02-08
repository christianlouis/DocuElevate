"""
Settings management views for the application.
"""

import os
import logging
import inspect
from functools import wraps
from fastapi import Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.views.base import APIRouter, templates, require_login, settings, get_db
from app.utils.settings_service import get_settings_by_category, get_setting_metadata, SETTING_METADATA
from app.utils.config_validator.masking import mask_sensitive_value

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
            logger.warning(f"Non-admin user attempted to access admin-only route")
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
        from app.utils.settings_service import get_all_settings_from_db
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
                
                settings_data[category].append({
                    "key": key,
                    "display_value": display_value if display_value is not None else "",
                    "metadata": metadata,
                    "source": source,
                    "source_label": source_label,
                    "source_color": source_color
                })
        
        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "settings_data": settings_data,
                "app_version": settings.version
            }
        )
    except Exception as e:
        logger.error(f"Error loading settings page: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load settings page"
        )
