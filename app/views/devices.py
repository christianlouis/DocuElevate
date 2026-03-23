"""View route for the Devices management page.

Renders the ``devices.html`` template where users can see their registered
mobile devices, mobile API tokens (created via the mobile SSO flow or QR
code login), and revoke access per-device.
"""

import logging

from fastapi import APIRouter, Request

from app.views.base import require_login, templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/devices", include_in_schema=False)
@require_login
async def devices_page(request: Request):
    """Render the Devices management page."""
    return templates.TemplateResponse(
        "devices.html",
        {"request": request, "page_title": "Devices"},
    )
