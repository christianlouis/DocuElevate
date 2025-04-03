"""
Frontend views/pages for the application.
This module combines all the individual view routers into a single router.
"""
from fastapi import APIRouter

# Import routers from view modules
from app.views.general import router as general_router
from app.views.files import router as files_router
from app.views.status import router as status_router
from app.views.dropbox import router as dropbox_router
from app.views.onedrive import router as onedrive_router

# Create a combined router
router = APIRouter()

# Include all view routers
router.include_router(general_router)
router.include_router(files_router)
router.include_router(status_router)
router.include_router(dropbox_router)
router.include_router(onedrive_router)
