"""
Status and configuration views for the application.
"""
from fastapi import Request
from datetime import datetime

from app.views.base import APIRouter, templates, require_login, settings

router = APIRouter()

@router.get("/status")
@require_login
async def status_dashboard(request: Request):
    """
    Status dashboard showing all configured integration targets
    """
    from app.utils.config_validator import get_provider_status
    
    # Get provider status
    providers = get_provider_status()
    
    return templates.TemplateResponse(
        "status_dashboard.html",
        {
            "request": request, 
            "providers": providers,
            "app_version": settings.version,
            "debug_enabled": getattr(settings, 'debug', False),
            "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
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
            "app_version": settings.version
        }
    )
