"""
Dropbox integration views for setup and OAuth callback.
"""

import json

from fastapi import Query, Request
from sqlalchemy.orm import Session

from app.models import UserIntegration
from app.utils.user_scope import get_current_owner_id
from app.views.base import APIRouter, Depends, get_db, require_login, settings, templates

router = APIRouter()


def _get_dropbox_callback_url(request: Request) -> str:
    """Return the Dropbox OAuth callback URL.

    Uses ``PUBLIC_BASE_URL`` when configured so that the redirect URI displayed
    to the user (and registered in the Dropbox developer console) matches the
    one used in the OAuth authorization request.  Falls back to deriving the URL
    from the incoming request when ``PUBLIC_BASE_URL`` is not set.
    """
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/") + "/dropbox-callback"
    return f"{request.url.scheme}://{request.url.netloc}/dropbox-callback"


@router.get("/dropbox-setup")
@require_login
async def dropbox_setup_page(
    request: Request,
    integration_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """
    Setup page for the Dropbox integration.

    When ``integration_id`` is provided the page operates in **user mode**:
    the OAuth wizard saves credentials to the named per-user integration
    record rather than to the global application settings.  Only the folder
    path from the integration's existing config is pre-populated; global
    admin credentials are never exposed in this mode.
    """
    callback_url = _get_dropbox_callback_url(request)

    if integration_id is not None:
        owner_id = get_current_owner_id(request)
        integration = (
            db.query(UserIntegration)
            .filter(UserIntegration.id == integration_id, UserIntegration.owner_id == owner_id)
            .first()
        )
        if integration:
            cfg: dict = {}
            if integration.config:
                try:
                    cfg = json.loads(integration.config)
                except (json.JSONDecodeError, TypeError):
                    cfg = {}
            # Support both "folder" (DROPBOX destination) and "folder_path" (WATCH_FOLDER source)
            folder_path = cfg.get("folder", cfg.get("folder_path", ""))
            # Determine if global credentials are available for users to reuse
            global_creds_available = bool(
                settings.dropbox_allow_global_credentials_for_integrations
                and settings.dropbox_app_key
                and settings.dropbox_app_secret
            )
            return templates.TemplateResponse(
                "dropbox.html",
                {
                    "request": request,
                    "user_mode": True,
                    "is_configured": bool(integration.credentials),
                    "integration_id": integration_id,
                    "integration_name": integration.name,
                    "integration_type": integration.integration_type,
                    "folder_path": folder_path,
                    # Only expose the public app key (not the secret) when global creds are allowed
                    "app_key_value": settings.dropbox_app_key if global_creds_available else "",
                    "app_secret_value": "",
                    "refresh_token_value": "",
                    "global_creds_available": global_creds_available,
                    "callback_url": callback_url,
                },
            )

    # ── Admin / global mode ──────────────────────────────────────────────────
    is_configured = bool(settings.dropbox_app_key and settings.dropbox_app_secret and settings.dropbox_refresh_token)

    return templates.TemplateResponse(
        "dropbox.html",
        {
            "request": request,
            "user_mode": False,
            "is_configured": is_configured,
            "app_key_value": settings.dropbox_app_key or "",
            "app_secret_value": settings.dropbox_app_secret if settings.dropbox_app_secret else "",
            "refresh_token_value": settings.dropbox_refresh_token if settings.dropbox_refresh_token else "",
            "folder_path": settings.dropbox_folder or "/Documents/Uploads",
            "integration_id": integration_id,
            "integration_name": None,
            "integration_type": None,
            "callback_url": callback_url,
        },
    )


@router.get("/dropbox-callback")
@require_login
async def dropbox_callback(request: Request, code: str = None, error: str = None):
    """
    Callback endpoint for Dropbox OAuth flow.
    Automatically exchanges the code for a token and saves it to the configuration.
    """
    if error:
        return templates.TemplateResponse("dropbox_callback_error.html", {"request": request, "error": error})

    if not code:
        return templates.TemplateResponse(
            "dropbox_callback_error.html", {"request": request, "error": "No authorization code received from Dropbox"}
        )

    # Display the processing page with automatic token exchange
    # Note: We provide empty strings for app_key_value and app_secret_value
    # to prevent overriding what's in sessionStorage
    return templates.TemplateResponse(
        "dropbox_callback.html",
        {
            "request": request,
            "code": code,
            "app_key_value": "",  # The callback will prioritize sessionStorage values
            "app_secret_value": "",  # The callback will prioritize sessionStorage values
            "folder_path": "",  # The callback will prioritize sessionStorage values
            "callback_url": _get_dropbox_callback_url(request),
        },
    )
