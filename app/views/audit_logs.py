"""
Audit log viewer UI — admin-only page with filtering and SIEM status.
"""

import logging

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.views.base import APIRouter, get_db, require_login, settings, templates
from app.views.settings import require_admin_access

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/admin/audit-logs")
@require_login
@require_admin_access
async def audit_logs_page(request: Request, db: Session = Depends(get_db)):
    """Comprehensive audit log viewer with filtering controls.

    Displays a chronological log of all significant actions: logins,
    document operations, settings changes, and admin actions.  The
    actual data is fetched client-side via the ``/api/audit-logs`` JSON
    endpoint so that filters, pagination, and live refresh work without
    full-page reloads.
    """
    try:
        siem_enabled = settings.audit_siem_enabled
        siem_transport = settings.audit_siem_transport if siem_enabled else None
        return templates.TemplateResponse(
            "audit_logs.html",
            {
                "request": request,
                "app_version": settings.version,
                "siem_enabled": siem_enabled,
                "siem_transport": siem_transport,
            },
        )
    except Exception as e:
        logger.error("Error loading audit logs page: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load audit logs page",
        )
