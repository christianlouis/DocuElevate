# app/frontend.py
import os
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from app.auth import require_login

router = APIRouter()

# Point templates_dir to "frontend/templates"
templates_dir = Path(__file__).parent.parent / "frontend" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

  
@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    # If you have a real favicon in `frontend/static/favicon.ico`:
    favicon_path = Path(__file__).parent.parent / "frontend" / "static" / "favicon.ico"
    return str(favicon_path)
