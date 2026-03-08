"""View route for the API Tokens management page.

Renders the ``api_tokens.html`` template where users can create, view,
and revoke their personal API tokens for programmatic access.
"""

import logging

from fastapi import APIRouter, Request

from app.views.base import require_login, templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api-tokens")
@require_login
async def api_tokens_page(request: Request):
    """Render the API Tokens management page."""
    return templates.TemplateResponse(
        "api_tokens.html",
        {"request": request, "page_title": "API Tokens"},
    )
