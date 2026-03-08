"""View route for the notifications dashboard."""

import logging

from fastapi import Request

from app.views.base import APIRouter, require_login, templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/notifications")
@require_login
async def notifications_dashboard(request: Request):
    """Render the notifications dashboard."""
    return templates.TemplateResponse(
        "notifications_dashboard.html",
        {"request": request, "page_title": "Notifications"},
    )
