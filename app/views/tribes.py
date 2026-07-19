"""Self-service Tribe membership and invitation journey."""

from fastapi import Request

from app.views.base import APIRouter, require_login, templates

router = APIRouter()


@router.get("/tribes", include_in_schema=False)
@require_login
async def tribes_page(request: Request):
    """Render the tenant-safe Tribe management page."""
    return templates.TemplateResponse("tribes.html", {"request": request})
