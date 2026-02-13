from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from app.views.base import templates

router = APIRouter()


@router.get(
    "/licenses/lgpl.txt",
    response_class=PlainTextResponse,
    responses={404: {"description": "License file not found"}},
)
async def get_lgpl_license():
    """
    Serve the LGPL license text file
    """
    license_path = Path("frontend/static/licenses/lgpl.txt")
    if not license_path.exists():
        raise HTTPException(status_code=404, detail="License file not found")

    return license_path.read_text(encoding="utf-8")


@router.get("/attribution", response_class=HTMLResponse, include_in_schema=False)
async def serve_attribution(request: Request):
    """
    Serve the third-party attribution page
    """
    return templates.TemplateResponse("attribution.html", {"request": request})
