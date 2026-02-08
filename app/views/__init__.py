"""
Aggregated view routers for the application.
"""
from fastapi import APIRouter

# Import all the view routers
from app.views.general import router as general_router
from app.views.status import router as status_router
from app.views.onedrive import router as onedrive_router
from app.views.dropbox import router as dropbox_router
from app.views.google_drive import router as google_drive_router
from app.views.license_routes import router as license_router  # Add the license router
from app.views.settings import router as settings_router

# Create a main router that includes all the view routers
router = APIRouter()
router.include_router(general_router)
router.include_router(status_router)
router.include_router(onedrive_router)
router.include_router(dropbox_router)
router.include_router(google_drive_router)
router.include_router(license_router)  # Include the license router
router.include_router(settings_router)
