"""
Frontend routes for the application.
This module is now a re-export of the modularized view routers.
"""
# Import and re-export the router from the views package
from app.views import router

# Keep the original router name for compatibility
# This allows existing imports in main.py to continue working

