"""Pipelines view: management UI for processing pipelines."""

import logging

from fastapi import HTTPException, Request, status

from app.views.base import APIRouter, require_login, settings, templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/pipelines")
@require_login
async def pipelines_page(request: Request):
    """Processing pipeline management page for the current user.

    Regular users manage their own pipelines.  Admins additionally have access
    to system-level pipelines through the same UI.
    """
    try:
        return templates.TemplateResponse(
            "pipelines.html",
            {
                "request": request,
                "app_version": settings.version,
            },
        )
    except Exception as exc:
        logger.error(f"Error loading pipelines page: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load pipelines page",
        )
