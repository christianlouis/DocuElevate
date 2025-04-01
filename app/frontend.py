# app/frontend.py
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session
from datetime import datetime

from app.auth import require_login
from app.database import SessionLocal
from app.config import settings

router = APIRouter()

# Set up Jinja2 templates
templates_dir = Path(__file__).parent.parent / "frontend" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

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
    # If you have a real favicon in `frontend/static/favicon.ico`:
    favicon_path = Path(__file__).parent.parent / "frontend" / "static" / "favicon.ico"
    return str(favicon_path)

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
            "debug_enabled": getattr(settings, 'debug', False),
            "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    )

@router.get("/env")
@require_login
async def env_debug(request: Request):
    """
    Debug endpoint to view environment variables and settings
    Only shows values when DEBUG is True
    """
    # Default DEBUG to True for this route
    debug_enabled = True
    
    # Get settings data
    from app.utils.config_validator import get_settings_for_display
    settings_data = get_settings_for_display(show_values=debug_enabled)
    
    return templates.TemplateResponse(
        "env_debug.html",
        {
            "request": request, 
            "settings": settings_data,
            "debug_enabled": debug_enabled,
            "app_version": getattr(settings, 'version', 'Unknown')
        }
    )

# Note: The frontend/router.py is now a submodule organization, 
# but we're keeping this file for compatibility until we've fully migrated
