"""Admin view: user management dashboard."""

import logging

from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.views.base import APIRouter, get_db, require_login, settings, templates  # noqa: F401

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_admin(request: Request):
    """Return the session user if they are an admin, else redirect."""
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        logger.warning("Non-admin user attempted to access /admin/users")
        return None
    return user


@router.get("/admin/users")
@require_login
async def admin_users_page(request: Request):
    """Admin user management dashboard — lists all known users."""
    user = _require_admin(request)
    if user is None:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    try:
        return templates.TemplateResponse(
            "admin_users.html",
            {
                "request": request,
                "app_version": settings.version,
            },
        )
    except Exception as e:
        logger.error(f"Error loading admin users page: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load admin users page",
        )
