"""Owner self-service page for automatic document privacy rules."""

from fastapi import Request

from app.views.base import APIRouter, require_login, templates

router = APIRouter()


@router.get("/privacy-rules", include_in_schema=False)
@require_login
async def privacy_rules_page(request: Request):
    return templates.TemplateResponse("privacy_rules.html", {"request": request})
