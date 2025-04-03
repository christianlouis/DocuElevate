"""
General routes for the application homepage and basic pages.
"""
from fastapi import Request, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

from app.views.base import APIRouter, templates, require_login

router = APIRouter()

@router.get("/", include_in_schema=False)
async def serve_index(request: Request):
    """Serve the index/home page."""
    return templates.TemplateResponse("index.html", {"request": request})

@router.get("/about", include_in_schema=False)
async def serve_about(request: Request):
    """Serve the about page."""
    return templates.TemplateResponse("about.html", {"request": request})

@router.get("/upload", include_in_schema=False)
@require_login
async def serve_upload(request: Request):
    """Serve the upload page."""
    return templates.TemplateResponse("upload.html", {"request": request})

@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Serve the favicon."""
    favicon_path = Path(__file__).parent.parent.parent / "frontend" / "static" / "favicon.ico"
    if not favicon_path.exists():
        # If favicon doesn't exist, return a 404
        raise HTTPException(status_code=404, detail="Favicon not found")
    return FileResponse(favicon_path)
