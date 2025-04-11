from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, HTMLResponse
from pathlib import Path
import os

from app.views.base import templates, require_login

router = APIRouter()

@router.get("/licenses/lgpl.txt", response_class=PlainTextResponse)
async def get_lgpl_license():
    """
    Serve the LGPL license text file
    """
    license_path = Path("frontend/static/licenses/lgpl.txt")
    if not license_path.exists():
        raise HTTPException(status_code=404, detail="License file not found")
    
    with open(license_path, "r") as f:
        return f.read()

@router.get("/attribution", response_class=HTMLResponse, include_in_schema=False)
async def serve_attribution(request: Request):
    """
    Serve the third-party attribution page
    """
    return templates.TemplateResponse("attribution.html", {"request": request})
