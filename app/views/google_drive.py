"""
Google Drive integration views for setup and OAuth callback.
"""

import json
import urllib.parse

from fastapi import Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.models import UserIntegration
from app.utils.user_scope import get_current_owner_id
from app.views.base import APIRouter, Depends, get_db, require_login, settings, templates

router = APIRouter()


@router.get("/google-drive-setup")
@require_login
async def google_drive_setup_page(
    request: Request,
    integration_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """
    Setup page for the Google Drive integration.

    When ``integration_id`` is provided the page operates in **user mode**:
    the OAuth wizard saves credentials to the named per-user integration
    record rather than to the global application settings.
    """
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
            folder_id = cfg.get("folder_id", "")
            # Provide system-wide OAuth credentials when available so users can
            # authorize without registering their own Google Cloud app.
            has_system_credentials = bool(
                settings.google_drive_client_id and settings.google_drive_client_secret
            )
            return templates.TemplateResponse(
                "google_drive.html",
                {
                    "request": request,
                    "user_mode": True,
                    "is_configured": bool(integration.credentials),
                    "integration_id": integration_id,
                    "integration_name": integration.name,
                    "integration_type": integration.integration_type,
                    "folder_id": folder_id,
                    "use_oauth": True,
                    "oauth_configured": bool(integration.credentials),
                    "sa_configured": False,
                    "has_system_credentials": has_system_credentials,
                    "client_id": bool(settings.google_drive_client_id) if has_system_credentials else False,
                    "client_id_value": (
                        settings.google_drive_client_id or "" if has_system_credentials else ""
                    ),
                    "client_secret": bool(settings.google_drive_client_secret) if has_system_credentials else False,
                    "client_secret_value": (
                        settings.google_drive_client_secret or "" if has_system_credentials else ""
                    ),
                    "refresh_token": False,
                    "refresh_token_value": "",
                    "has_credentials_json": False,
                },
            )

    # ── Admin / global mode ──────────────────────────────────────────────────
    use_oauth = getattr(settings, "google_drive_use_oauth", False)

    oauth_configured = bool(
        settings.google_drive_client_id and settings.google_drive_client_secret and settings.google_drive_refresh_token
    )
    sa_configured = bool(settings.google_drive_credentials_json)
    is_configured = (use_oauth and oauth_configured) or (not use_oauth and sa_configured)
    if settings.google_drive_folder_id:
        is_configured = is_configured and True
    else:
        is_configured = False

    return templates.TemplateResponse(
        "google_drive.html",
        {
            "request": request,
            "user_mode": False,
            "is_configured": is_configured,
            "use_oauth": use_oauth,
            "oauth_configured": oauth_configured,
            "sa_configured": sa_configured,
            "has_system_credentials": bool(
                settings.google_drive_client_id and settings.google_drive_client_secret
            ),
            "client_id": bool(settings.google_drive_client_id),
            "client_id_value": settings.google_drive_client_id or "",
            "client_secret": bool(settings.google_drive_client_secret),
            "client_secret_value": settings.google_drive_client_secret or "",
            "refresh_token": bool(settings.google_drive_refresh_token),
            "refresh_token_value": settings.google_drive_refresh_token or "",
            "folder_id": settings.google_drive_folder_id or "",
            "has_credentials_json": bool(settings.google_drive_credentials_json),
            "integration_id": integration_id,
            "integration_name": None,
            "integration_type": None,
        },
    )


@router.get("/google-drive-callback")
@require_login
async def google_drive_callback(request: Request, code: str = None, error: str = None, state: str = None):
    """
    Callback endpoint for Google Drive OAuth flow.
    Now automatically exchanges the code for a token and saves it to the configuration.
    """
    if error:
        return templates.TemplateResponse("google_drive_callback_error.html", {"request": request, "error": error})

    if not code:
        return templates.TemplateResponse(
            "google_drive_callback_error.html",
            {"request": request, "error": "No authorization code received from Google"},
        )

    # Display the processing page with automatic token exchange
    return templates.TemplateResponse("google_drive_callback.html", {"request": request, "code": code, "state": state})


@router.get("/google-drive-auth-start")
@require_login
async def google_drive_auth_start(request: Request, client_id: str, redirect_uri: str = None):
    """
    Start the Google Drive OAuth flow by redirecting to Google's authorization page.
    """
    if not redirect_uri:
        redirect_uri = f"{request.url.scheme}://{request.url.netloc}/google-drive-callback"

    # Create the authorization URL with required scopes
    # Use only drive.file scope to minimize required permissions
    scopes = ["https://www.googleapis.com/auth/drive.file"]  # Access to files created or opened by the app

    scope_str = urllib.parse.quote(" ".join(scopes))

    auth_url = (
        f"https://accounts.google.com/o/oauth2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
        f"&response_type=code"
        f"&scope={scope_str}"
        f"&access_type=offline"
        f"&prompt=consent"  # Force to show consent screen to get refresh token
    )

    return RedirectResponse(url=auth_url)
