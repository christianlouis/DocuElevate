# app/frontend.py (new file or inline in main.py)
from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.auth import require_login
import os

router = APIRouter()

# 1) Serve the folder that contains index.html, etc.
#    e.g. "frontend" is relative to your project root
frontend_folder = os.path.join(os.path.dirname(__file__), "..", "frontend")

# If you just want to serve the entire folder as static:
router.mount("/static", StaticFiles(directory=frontend_folder), name="static")

# 2) For the root route ("/"), return the index.html

@router.get("/upload", response_class=FileResponse)
@require_login
def serve_ui():
    return os.path.join(frontend_folder, "index.html")

# 3) Serve favicon.ico from the frontend folder
@router.get("/favicon.ico", response_class=FileResponse)
def favicon():
    return os.path.join(frontend_folder, "favicon.ico")