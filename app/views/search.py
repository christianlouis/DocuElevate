"""
Search view for dedicated full-text document search page.

Provides a Google-style search experience with content previews,
powered by Meilisearch via the existing ``/api/search`` backend.
"""

import logging
from typing import Optional

from fastapi import Query, Request

from app.views.base import APIRouter, require_login, templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/search")
@require_login
def search_page(
    request: Request,
    q: Optional[str] = Query(None, max_length=512, description="Full-text search query"),
):
    """Render the dedicated search page.

    The page loads with an empty search box (or pre-filled when *q* is given).
    Actual searching is performed client-side via ``fetch('/api/search')`` so
    that results stream in without a full page reload.
    """
    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "query": q or "",
        },
    )
