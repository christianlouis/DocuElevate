"""Admin view for outbound webhook endpoint management."""

from fastapi import Request

from app.views.base import APIRouter, require_login, templates
from app.views.settings import require_admin_access

router = APIRouter()


@router.get("/admin/webhooks")
@require_login
@require_admin_access
async def webhooks_dashboard(request: Request):
    """Render the admin webhook management dashboard."""
    return templates.TemplateResponse(
        "webhooks_dashboard.html",
        {"request": request, "page_title": "Webhooks"},
    )
