"""Admin view: scheduled batch processing jobs management page."""

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
        logger.warning("Non-admin user attempted to access /admin/scheduled-jobs")
        return None
    return user


@router.get("/admin/scheduled-jobs")
@require_login
async def scheduled_jobs_page(request: Request):
    """Admin scheduled jobs management page."""
    user = _require_admin(request)
    if user is None:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    try:
        return templates.TemplateResponse(
            "admin_scheduled_jobs.html",
            {
                "request": request,
                "app_version": settings.version,
            },
        )
    except Exception as e:
        logger.error(f"Error loading scheduled jobs page: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load scheduled jobs page",
        )
