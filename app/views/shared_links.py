"""View route for the Shared Links management page.

Renders the ``shared_links.html`` template where authenticated users can
create, view, and revoke their document share links.
"""

import logging

from fastapi import APIRouter, Request

from app.views.base import require_login, templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/shared-links")
@require_login
async def shared_links_page(request: Request):
    """Render the Shared Links management page."""
    return templates.TemplateResponse(
        "shared_links.html",
        {"request": request, "page_title": "Shared Links"},
    )
