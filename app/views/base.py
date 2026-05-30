"""
Base setup for views, containing shared functionality and imports.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: F401
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session  # noqa: F401

from app.auth import require_login  # noqa: F401
from app.config import settings
from app.database import get_db  # noqa: F401

# Set up Jinja2 templates
templates_dir = Path(__file__).parent.parent.parent / "frontend" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Add Python built-in functions to Jinja2 template globals
templates.env.globals["min"] = min
templates.env.globals["max"] = max

# Customize Jinja2Templates to include app_version in all templates
original_template_response = templates.TemplateResponse


def template_response_with_version(*args, **kwargs):
    """Wrapper for TemplateResponse to include version in all templates"""
    if args and isinstance(args[0], str):
        name = args[0]
        context = args[1] if len(args) >= 2 and isinstance(args[1], dict) else kwargs.pop("context", {})
        if isinstance(context, dict):
            context.setdefault("version", settings.version)
            request = context.get("request") or kwargs.pop("request", None)
            if request is not None:
                return original_template_response(request, name, context, *args[2:], **kwargs)
    elif len(args) >= 3 and isinstance(args[2], dict):
        args[2].setdefault("version", settings.version)
    elif "context" in kwargs and isinstance(kwargs["context"], dict):
        kwargs["context"].setdefault("version", settings.version)
    return original_template_response(*args, **kwargs)


templates.TemplateResponse = template_response_with_version

# Set up logging
logger = logging.getLogger(__name__)
