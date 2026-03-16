"""Admin view: compliance templates dashboard page."""

import logging

from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.views.base import APIRouter, require_login, settings, templates

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_admin(request: Request):
    """Return the session user if they are an admin, else None."""
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        logger.warning("Non-admin user attempted to access /admin/compliance")
        return None
    return user


@router.get("/admin/compliance")
@require_login
async def compliance_page(request: Request):
    """Admin compliance templates dashboard page.

    Displays GDPR, HIPAA, and SOC2 compliance templates with their current
    status and one-click apply functionality.
    """
    user = _require_admin(request)
    if user is None:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    try:
        return templates.TemplateResponse(
            "compliance.html",
            {
                "request": request,
                "app_version": settings.version,
            },
        )
    except Exception as e:
        logger.error(f"Error loading compliance page: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load compliance page",
        )
