"""
Help Center view routes.

Renders a user-facing, SEO-optimised Help Center page at ``/help``.
The page is designed for SaaS end-users and includes guidance on
features, integrations, workflows, and optional Zammad support widgets
(live-chat and feedback form).

The developer-oriented MkDocs documentation is served separately at
``/docs`` and is intentionally **not** cross-linked from this page.
"""

import logging
import pathlib

from fastapi import Request

from app.config import settings
from app.views.base import APIRouter, templates

logger = logging.getLogger(__name__)

router = APIRouter()

# Path to the built MkDocs documentation (kept for reference / backwards compat)
_DOCS_BUILD_DIR = pathlib.Path(__file__).parents[2] / "docs_build"


@router.get("/help", include_in_schema=False)
async def help_center(request: Request):
    """Render the end-user Help Center page."""
    return templates.TemplateResponse(
        "help.html",
        {
            "request": request,
            "external_hostname": settings.external_hostname,
            "zammad_url": settings.zammad_url,
            "zammad_chat_enabled": settings.zammad_chat_enabled,
            "zammad_chat_id": settings.zammad_chat_id,
            "zammad_form_enabled": settings.zammad_form_enabled,
            "support_email": settings.support_email,
        },
    )
