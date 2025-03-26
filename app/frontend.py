# app/frontend.py
import os
from pathlib import Path
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import SessionLocal

router = APIRouter()

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

# ... existing routes for /, /upload, /about, etc. ...


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
