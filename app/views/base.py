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
from app.database import SessionLocal, get_db  # noqa: F401
from app.models import UserProfile
from app.utils.i18n import (
    SUPPORTED_LANGUAGES,
    detect_language,
    format_date,
    format_datetime,
    format_number,
    get_suggested_languages,
    translate,
)

# Set up Jinja2 templates
templates_dir = Path(__file__).parent.parent.parent / "frontend" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Add Python built-in functions to Jinja2 template globals
templates.env.globals["min"] = min
templates.env.globals["max"] = max

# ---------------------------------------------------------------------------
# i18n Jinja2 integration
# ---------------------------------------------------------------------------
# The _() function is available in every template to translate UI strings.
# Usage: {{ _("nav.dashboard") }} or {{ _("upload.max_size", size="10 MB") }}
# The locale is automatically resolved from the request context.
# A default English implementation is registered as a global so error handlers
# that don't go through _inject_global_context still have the function available.
# ---------------------------------------------------------------------------

templates.env.globals["supported_languages"] = SUPPORTED_LANGUAGES
templates.env.globals["_"] = lambda key, **kwargs: translate(key, "en", **kwargs)

# Customize Jinja2Templates to include app_version in all templates
original_template_response = templates.TemplateResponse


def _hydrate_language_from_db(request: Request, session_user: object) -> None:
    """Load the user's preferred language from the DB into the session.

    Called once per session when ``preferred_language`` is not yet in the
    session.  A lightweight DB query fetches the stored preference so that
    :func:`detect_language` picks it up from the session on all subsequent
    requests without further DB access.
    """
    from app.utils.i18n import SUPPORTED_LANGUAGE_CODES

    user_id: str | None = None
    if isinstance(session_user, dict):
        user_id = (
            session_user.get("sub")
            or session_user.get("preferred_username")
            or session_user.get("email")
            or session_user.get("id")
        )
    elif isinstance(session_user, str):
        user_id = session_user

    if not user_id:
        return

    db = SessionLocal()
    try:
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if profile and profile.preferred_language and profile.preferred_language in SUPPORTED_LANGUAGE_CODES:
            request.session["preferred_language"] = profile.preferred_language
    except Exception:  # noqa: BLE001 — intentionally broad; DB may be temporarily unavailable
        logger.debug("Could not hydrate language preference for user_id=%s", user_id)
    finally:
        db.close()


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
    ctx.setdefault("enable_factory_reset", getattr(settings, "enable_factory_reset", False))

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

        # --- Hydrate session language from DB (once per session) ---
        # If the session doesn't have a preferred_language yet but the user
        # is logged in, load the stored preference from the database so that
        # detect_language() picks it up from the session on this and all
        # subsequent requests.
        if hasattr(req, "session") and "preferred_language" not in req.session and session_user is not None:
            _hydrate_language_from_db(req, session_user)

        # --- i18n: detect language and register template helpers ---
        current_locale = detect_language(req)
        ctx.setdefault("current_locale", current_locale)

        # Smart language suggestions for the compact nav-bar dropdown (5-7 languages)
        accept_header = req.headers.get("accept-language", "") if hasattr(req, "headers") else ""
        ctx.setdefault("suggested_languages", get_suggested_languages(current_locale, accept_header))

        def _translate(key: str, **kwargs: object) -> str:
            return translate(key, current_locale, **kwargs)

        def _format_date(value: object, short: bool = False) -> str:
            return format_date(value, current_locale, short=short)  # type: ignore[arg-type]

        def _format_datetime(value: object) -> str:
            return format_datetime(value, current_locale)  # type: ignore[arg-type]

        def _format_number(value: object) -> str:
            return format_number(value, current_locale)  # type: ignore[arg-type]

        ctx.setdefault("_", _translate)
        ctx.setdefault("format_date_l10n", _format_date)
        ctx.setdefault("format_datetime_l10n", _format_datetime)
        ctx.setdefault("format_number_l10n", _format_number)
    else:
        ctx.setdefault("is_logged_in", not getattr(settings, "auth_enabled", True))
        ctx.setdefault("current_locale", "en")
        ctx.setdefault("_", lambda key, **kw: translate(key, "en", **kw))


def template_response_with_version(*args, **kwargs):
    """Wrapper for TemplateResponse to include version and CSRF token in all templates.

    Handles both old-style and new-style Starlette TemplateResponse calls:
      - Old-style (Starlette <1.0): TemplateResponse(name, {"request": req, ...}, ...)
      - New-style (Starlette 1.0+): TemplateResponse(request, name, context={...}, ...)
    """
    if len(args) >= 1 and isinstance(args[0], str):
        # Old-style call: first positional arg is the template name (string).
        # Convert to new-style: (request, name, context=..., ...)
        name = args[0]
        if len(args) >= 2 and isinstance(args[1], dict):
            context = args[1]
            # Old-style may have status_code as 3rd positional arg
            if len(args) >= 3 and "status_code" not in kwargs:
                kwargs["status_code"] = args[2]
        else:
            context = kwargs.pop("context", {})
        request_obj = context.pop("request", None)
        if request_obj is not None:
            context["request"] = request_obj
        _inject_global_context(context)
        if request_obj is not None:
            return original_template_response(request_obj, name, context=context, **kwargs)
        return original_template_response(name, context=context, **kwargs)

    # New-style call: (request, name, context=..., ...)
    if "context" in kwargs and isinstance(kwargs["context"], dict):
        _inject_global_context(kwargs["context"])
    elif len(args) >= 3 and isinstance(args[2], dict):
        _inject_global_context(args[2])
    return original_template_response(*args, **kwargs)


templates.TemplateResponse = template_response_with_version

# Set up logging
logger = logging.getLogger(__name__)
