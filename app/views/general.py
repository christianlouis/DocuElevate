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

@router.get("/license", include_in_schema=False)
async def serve_license(request: Request):
    """Serve the license page."""
    # Try multiple possible locations for the license file
    possible_locations = [
        Path(__file__).parent.parent.parent / "LICENSE",  # Repository root
        Path("/app/LICENSE"),  # Docker container path
        Path.home() / "LICENSE",  # Home directory (fallback)
    ]
    
    license_text = None
    
    # Try to read from any of the possible locations
    for path in possible_locations:
        try:
            with open(path, "r") as f:
                license_text = f.read()
                break  # File found and read, exit loop
        except (FileNotFoundError, PermissionError):
            continue  # Try next location
    
    # If license text is still None, use embedded text
    if license_text is None:
        license_text = """
Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

This software is licensed under the Apache License 2.0.
The full license text could not be located on this system.
Please visit http://www.apache.org/licenses/LICENSE-2.0 for the complete license text.
"""
    
    return templates.TemplateResponse(
        "license.html", 
        {
            "request": request,
            "license_text": license_text
        }
    )
