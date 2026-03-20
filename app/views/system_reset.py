"""
System reset view — admin-only UI page.

Renders a confirmation-heavy page that allows administrators to:
1. **Full Reset** — wipe all user data (DB + disk) for a fresh start.
2. **Reset & Re-import** — move originals to a reimport folder, wipe,
   and let the watch-folder mechanism re-ingest them.

Both options are gated behind the ``ENABLE_FACTORY_RESET`` feature flag.
"""

import logging

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.views.base import APIRouter, get_db, require_login, templates
from app.views.settings import require_admin_access

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/admin/system-reset")
@require_login
@require_admin_access
async def system_reset_page(request: Request, db: Session = Depends(get_db)) -> Response:
    """Render the system reset administration page."""
    if not settings.enable_factory_reset:
        return RedirectResponse(url="/settings", status_code=302)

    return templates.TemplateResponse(
        "system_reset.html",
        {
            "request": request,
            "factory_reset_on_startup": settings.factory_reset_on_startup,
        },
    )
