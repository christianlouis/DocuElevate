"""
Database configuration wizard view.

Serves the guided UI for configuring a database connection string
and migrating data from one database to another.
"""

import logging

from fastapi import Request

from app.config import settings
from app.views.base import APIRouter, templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/database-wizard")
async def database_wizard(request: Request) -> templates.TemplateResponse:
    """Render the database configuration wizard page."""
    return templates.TemplateResponse(
        "db_wizard.html",
        {
            "request": request,
            "current_database_url": settings.database_url,
        },
    )
