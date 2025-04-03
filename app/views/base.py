"""
Base setup for views, containing shared functionality and imports.
"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session
import logging

from app.auth import require_login
from app.database import SessionLocal
from app.config import settings

# Set up Jinja2 templates
templates_dir = Path(__file__).parent.parent.parent / "frontend" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Set up logging
logger = logging.getLogger(__name__)

def get_db():
    """
    Dependency to get a database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
