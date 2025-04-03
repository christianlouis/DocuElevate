# app/frontend.py
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session
from datetime import datetime
import logging
from fastapi.responses import FileResponse  # Add this import

from app.auth import require_login
from app.database import SessionLocal
from app.config import settings

router = APIRouter()

# Set up Jinja2 templates
templates_dir = Path(__file__).parent.parent / "frontend" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Set up logging
logger = logging.getLogger(__name__)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/files")
@require_login
def files_page(request: Request):
    """
    Return the 'files.html' template. 
    The actual file data is fetched via XHR from /api/files in the template.
    """
    return templates.TemplateResponse("files.html", {"request": request})

@router.get("/", include_in_schema=False)
async def serve_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.get("/about", include_in_schema=False)
async def serve_about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})

@router.get("/upload", include_in_schema=False)
@require_login
async def serve_upload(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    # Return the favicon file as a FileResponse instead of the path string
    favicon_path = Path(__file__).parent.parent / "frontend" / "static" / "favicon.ico"
    if not favicon_path.exists():
        # If favicon doesn't exist, return a 404
        raise HTTPException(status_code=404, detail="Favicon not found")
    return FileResponse(favicon_path)

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
            "app_version": settings.version,  # Add app version to the context
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

@router.get("/onedrive-setup")
@require_login
async def onedrive_setup_page(request: Request):
    """
    Setup page for the OneDrive integration.
    Shows configuration status and setup instructions.
    """
    # Check OneDrive configuration
    is_configured = bool(settings.onedrive_client_id and 
                         settings.onedrive_client_secret and 
                         settings.onedrive_refresh_token)
    
    # Get configuration values to display status (hide sensitive values)
    return templates.TemplateResponse(
        "onedrive.html",
        {
            "request": request,
            "is_configured": is_configured,
            "client_id": bool(settings.onedrive_client_id),
            "client_id_value": settings.onedrive_client_id or "",  # Pass the actual value for the form
            "client_secret": bool(settings.onedrive_client_secret),
            "client_secret_value": settings.onedrive_client_secret if settings.onedrive_client_secret else "",
            "tenant_id": settings.onedrive_tenant_id,
            "refresh_token": bool(settings.onedrive_refresh_token),
            "refresh_token_value": settings.onedrive_refresh_token if settings.onedrive_refresh_token else "",
            "folder_path": settings.onedrive_folder_path or "Documents/Uploads"  # Default folder path
        }
    )

@router.get("/onedrive-callback")
@require_login
async def onedrive_callback(request: Request, code: str = None, error: str = None):
    """
    Callback endpoint for OneDrive OAuth flow.
    Now automatically exchanges the code for a token and saves it to the configuration.
    """
    if error:
        return templates.TemplateResponse(
            "onedrive_callback_error.html",
            {"request": request, "error": error}
        )
    
    if not code:
        return templates.TemplateResponse(
            "onedrive_callback_error.html",
            {"request": request, "error": "No authorization code received from Microsoft"}
        )
    
    # Display the processing page with automatic token exchange
    return templates.TemplateResponse(
        "onedrive_callback.html",
        {
            "request": request, 
            "code": code,
            "client_id_value": settings.onedrive_client_id or "",
            "client_secret_value": settings.onedrive_client_secret or "",
            "tenant_id": settings.onedrive_tenant_id or "common"
        }
    )

@router.get("/dropbox-setup")
@require_login
async def dropbox_setup_page(request: Request):
    """
    Setup page for the Dropbox integration.
    Shows configuration status and setup instructions.
    """
    # Check Dropbox configuration
    is_configured = bool(settings.dropbox_app_key and 
                         settings.dropbox_app_secret and 
                         settings.dropbox_refresh_token)
    
    return templates.TemplateResponse(
        "dropbox.html",
        {
            "request": request,
            "is_configured": is_configured,
            "app_key_value": settings.dropbox_app_key or "",
            "app_secret_value": settings.dropbox_app_secret if settings.dropbox_app_secret else "",
            "refresh_token_value": settings.dropbox_refresh_token if settings.dropbox_refresh_token else "",
            "folder_path": settings.dropbox_folder or "/Documents/Uploads"  # Default folder path
        }
    )

@router.get("/dropbox-callback")
@require_login
async def dropbox_callback(request: Request, code: str = None, error: str = None):
    """
    Callback endpoint for Dropbox OAuth flow.
    Automatically exchanges the code for a token and saves it to the configuration.
    """
    if error:
        return templates.TemplateResponse(
            "dropbox_callback_error.html",
            {"request": request, "error": error}
        )
    
    if not code:
        return templates.TemplateResponse(
            "dropbox_callback_error.html",
            {"request": request, "error": "No authorization code received from Dropbox"}
        )
    
    # Display the processing page with automatic token exchange
    # Note: We provide empty strings for app_key_value and app_secret_value
    # to prevent overriding what's in sessionStorage
    return templates.TemplateResponse(
        "dropbox_callback.html",
        {
            "request": request, 
            "code": code,
            "app_key_value": "",  # The callback will prioritize sessionStorage values
            "app_secret_value": "",  # The callback will prioritize sessionStorage values
            "folder_path": ""  # The callback will prioritize sessionStorage values
        }
    )

