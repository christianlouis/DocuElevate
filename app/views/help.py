"""
Help documentation view routes.

Serves the built MkDocs documentation site at /help.
The static site is built during the Docker image build and placed at docs_build/.
"""

import logging
import pathlib

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.views.base import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()

# Path to the built MkDocs documentation
_DOCS_BUILD_DIR = pathlib.Path(__file__).parents[2] / "docs_build"


@router.get("/help", include_in_schema=False)
async def help_redirect(request: Request) -> RedirectResponse:
    """Redirect /help to /help/ so the MkDocs index is served correctly."""
    return RedirectResponse(url="/help/", status_code=301)
