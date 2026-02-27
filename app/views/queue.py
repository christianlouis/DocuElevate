"""
Queue monitoring view for the admin dashboard.
"""

import logging

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.views.base import APIRouter, get_db, require_login, templates
from app.views.settings import require_admin_access

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/admin/queue")
@require_login
@require_admin_access
async def queue_dashboard(request: Request, db: Session = Depends(get_db)):
    """
    Queue monitoring dashboard — admin only.

    Displays Celery/Redis queue statistics and database processing summaries
    so administrators can monitor the document processing pipeline.
    """
    return templates.TemplateResponse(
        "queue_dashboard.html",
        {
            "request": request,
        },
    )
