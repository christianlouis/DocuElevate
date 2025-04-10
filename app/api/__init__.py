"""
API Router module that combines all API endpoints
"""
from fastapi import APIRouter
import logging

# Import all the individual routers
from app.api.user import router as user_router
from app.api.files import router as files_router
from app.api.process import router as process_router
from app.api.diagnostic import router as diagnostic_router
from app.api.onedrive import router as onedrive_router
from app.api.dropbox import router as dropbox_router
from app.api.openai import router as openai_router
from app.api.azure import router as azure_router
from app.api.google_drive import router as google_drive_router

# Set up logging
logger = logging.getLogger(__name__)

# Create the main router that includes all the others
router = APIRouter()

# Include all the routers
router.include_router(user_router)
router.include_router(files_router)
router.include_router(process_router)
router.include_router(diagnostic_router)
router.include_router(onedrive_router)
router.include_router(dropbox_router)
router.include_router(openai_router)
router.include_router(azure_router)
router.include_router(google_drive_router)
