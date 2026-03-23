"""Public view for accessing a shared document link.

This route does NOT require authentication — it is the landing page
that link recipients visit.  The page fetches link metadata via the
public ``/api/share/{token}/info`` JSON endpoint and then renders the
appropriate download UI (password gate or direct download button).
"""

import logging
import pathlib

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)
router = APIRouter()

_templates_dir = pathlib.Path(__file__).parents[2] / "frontend" / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


@router.get("/share/{token}")
async def shared_link_view(request: Request, token: str):
    """Render the public share landing page for a given token."""
    return templates.TemplateResponse(
        "shared_link_view.html",
        {"request": request, "token": token},
    )
