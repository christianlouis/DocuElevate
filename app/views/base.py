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


def _inject_global_context(ctx: dict) -> None:
    """Inject shared global variables into every template context dict."""
    ctx.setdefault("version", settings.version)
    ctx.setdefault("release_name", getattr(settings, "release_name", None))
    ctx.setdefault("ui_default_color_scheme", getattr(settings, "ui_default_color_scheme", "system"))
    ctx.setdefault("multi_user_enabled", getattr(settings, "multi_user_enabled", False))
    ctx.setdefault("auth_enabled", getattr(settings, "auth_enabled", True))
    ctx.setdefault(
        "allow_signup",
        getattr(settings, "multi_user_enabled", False) and getattr(settings, "allow_local_signup", False),
    )

    req = ctx.get("request")
    if req is not None:
        # CSRF token
        if hasattr(req, "state") and hasattr(req.state, "csrf_token"):
            ctx.setdefault("csrf_token", req.state.csrf_token)
        # Determine whether the current visitor is authenticated
        session_user = None
        if hasattr(req, "session"):
            session_user = req.session.get("user")
        # When auth is disabled every visitor is effectively "logged in"
        ctx.setdefault("is_logged_in", not getattr(settings, "auth_enabled", True) or session_user is not None)
    else:
        ctx.setdefault("is_logged_in", not getattr(settings, "auth_enabled", True))


def template_response_with_version(*args, **kwargs):
    """Wrapper for TemplateResponse to include version and CSRF token in all templates"""
    # If context dict is provided, add version to it
    if len(args) >= 2 and isinstance(args[1], dict):
        _inject_global_context(args[1])
    elif "context" in kwargs and isinstance(kwargs["context"], dict):
        _inject_global_context(kwargs["context"])
    return original_template_response(*args, **kwargs)


templates.TemplateResponse = template_response_with_version

# Set up logging
logger = logging.getLogger(__name__)
