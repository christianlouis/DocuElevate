"""View route for the QR code mobile login page.

Route:
  GET /qr-login  — renders the QR login page (requires login)
"""

from __future__ import annotations

import logging

from fastapi import Request

from app.views.base import APIRouter, require_login, templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/qr-login", include_in_schema=False)
@require_login
async def qr_login_page(request: Request):
    """Serve the QR code login page for mobile app authentication."""
    return templates.TemplateResponse(
        "qr_login.html",
        {"request": request},
    )
