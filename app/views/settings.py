"""
Settings management views for the application.
"""

import logging
from fastapi import Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.views.base import APIRouter, templates, require_login, settings, get_db
from app.utils.settings_service import get_settings_by_category, get_setting_metadata, SETTING_METADATA
from app.utils.config_validator.masking import mask_sensitive_value

logger = logging.getLogger(__name__)
router = APIRouter()


def require_admin_access(request: Request):
    """Check if user is admin and redirect if not"""
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        logger.warning(f"Non-admin user attempted to access settings page")
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return None


@router.get("/settings")
@require_login
async def settings_page(request: Request, db: Session = Depends(get_db)):
    """
    Settings management page - admin only.
    """
    # Check admin access
    redirect = require_admin_access(request)
    if redirect:
        return redirect
    
    try:
        # Get settings organized by category
        categories = get_settings_by_category()
        
        # Build settings data for display
        settings_data = {}
        for category, keys in categories.items():
            settings_data[category] = []
            for key in keys:
                # Get current value from settings
                value = getattr(settings, key, None)
                
                # Get metadata
                metadata = get_setting_metadata(key)
                
                # Mask sensitive values
                display_value = value
                if metadata.get("sensitive") and value:
                    display_value = mask_sensitive_value(value)
                
                settings_data[category].append({
                    "key": key,
                    "display_value": display_value if display_value is not None else "",
                    "metadata": metadata
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
