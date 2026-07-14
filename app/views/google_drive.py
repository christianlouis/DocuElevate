"""
Google Drive integration views for setup and OAuth callback.
"""

import json
import logging
import secrets
import urllib.parse

from fastapi import Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.models import UserIntegration
from app.utils.encryption import encrypt_value
from app.utils.oauth_helper import exchange_oauth_token
from app.utils.user_scope import get_current_owner_id
from app.views.base import APIRouter, Depends, get_db, require_login, settings, templates

router = APIRouter()
logger = logging.getLogger(__name__)

GOOGLE_DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
GOOGLE_DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
GOOGLE_DRIVE_FULL_SCOPE = "https://www.googleapis.com/auth/drive"


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
            has_system_credentials = bool(settings.google_drive_client_id and settings.google_drive_client_secret)
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
                    "client_id_value": (settings.google_drive_client_id or "" if has_system_credentials else ""),
                    # App secrets are server-side bootstrap credentials and must
                    # never be rendered into the browser.
                    "client_secret": bool(settings.google_drive_client_secret) if has_system_credentials else False,
                    "client_secret_value": "",
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
            "has_system_credentials": bool(settings.google_drive_client_id and settings.google_drive_client_secret),
            "client_id": bool(settings.google_drive_client_id),
            "client_id_value": "",
            "client_secret": bool(settings.google_drive_client_secret),
            # Never render provider app secrets back to the browser.
            "client_secret_value": "",
            "refresh_token": bool(settings.google_drive_refresh_token),
            "refresh_token_value": "",
            "folder_id": settings.google_drive_folder_id or "",
            "has_credentials_json": bool(settings.google_drive_credentials_json),
            "integration_id": integration_id,
            "integration_name": None,
            "integration_type": None,
        },
    )


@router.get("/google-drive-callback")
@require_login
async def google_drive_callback(
    request: Request,
    code: str = None,
    error: str = None,
    state: str = None,
    db: Session = Depends(get_db),
):
    """
    Callback endpoint for Google Drive OAuth flow.
    Now automatically exchanges the code for a token and saves it to the configuration.
    """
    pending = request.session.get("google_drive_oauth")

    if error:
        request.session.pop("google_drive_oauth", None)
        safe_error = (
            "Google authorization was cancelled." if error == "access_denied" else "Google authorization failed."
        )
        return templates.TemplateResponse("google_drive_callback_error.html", {"request": request, "error": safe_error})

    if not code:
        return templates.TemplateResponse(
            "google_drive_callback_error.html",
            {"request": request, "error": "No authorization code received from Google"},
        )

    if not pending:
        return templates.TemplateResponse(
            "google_drive_callback_error.html",
            {"request": request, "error": "No pending Google Drive authorization was found."},
            status_code=400,
        )

    expected_state = pending.get("state", "")
    if not state or not secrets.compare_digest(state, expected_state):
        request.session.pop("google_drive_oauth", None)
        return templates.TemplateResponse(
            "google_drive_callback_error.html",
            {"request": request, "error": "OAuth state validation failed. Please start authorization again."},
            status_code=400,
        )

    owner_id = get_current_owner_id(request)
    integration = (
        db.query(UserIntegration)
        .filter(
            UserIntegration.id == pending.get("integration_id"),
            UserIntegration.owner_id == owner_id,
        )
        .first()
    )
    if not integration:
        request.session.pop("google_drive_oauth", None)
        return templates.TemplateResponse(
            "google_drive_callback_error.html",
            {"request": request, "error": "The Google Drive integration no longer exists."},
            status_code=404,
        )

    try:
        token_data = exchange_oauth_token(
            provider_name="Google Drive",
            token_url="https://oauth2.googleapis.com/token",
            payload={
                "client_id": settings.google_drive_client_id,
                "client_secret": settings.google_drive_client_secret,
                "code": code,
                "redirect_uri": pending["redirect_uri"],
                "grant_type": "authorization_code",
            },
        )
        credentials = {
            "refresh_token": token_data["refresh_token"],
            # Persist Google's actual grant when returned; it may be narrower
            # than the requested scope.
            "scope": token_data.get("scope") or pending["scope"],
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        integration.credentials = encrypt_value(json.dumps(credentials))
        integration.last_error = None
        db.commit()
        logger.info("Google Drive OAuth authorization saved for integration %s", integration.id)
    except Exception:
        db.rollback()
        logger.exception("Google Drive OAuth callback failed for integration %s", integration.id)
        return templates.TemplateResponse(
            "google_drive_callback_error.html",
            {"request": request, "error": "Google authorization could not be completed."},
            status_code=502,
        )
    finally:
        request.session.pop("google_drive_oauth", None)

    return RedirectResponse(url="/integrations?oauth=google-drive-connected", status_code=303)


@router.get("/google-drive-auth-start")
@require_login
async def google_drive_auth_start(
    request: Request,
    integration_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """
    Start the Google Drive OAuth flow by redirecting to Google's authorization page.
    """
    # Never derive an OAuth redirect target from the request Host header.
    # PUBLIC_BASE_URL is database-configurable and is hot-reloaded for API and
    # worker processes; EXTERNAL_HOSTNAME is the safe bootstrap fallback.
    configured_base_url = settings.public_base_url
    external_hostname = settings.external_hostname
    if not isinstance(configured_base_url, str) or not configured_base_url:
        hostname = external_hostname if isinstance(external_hostname, str) and external_hostname else "localhost"
        configured_base_url = f"https://{hostname}"
    public_base_url = configured_base_url.rstrip("/")
    redirect_uri = f"{public_base_url}/google-drive-callback"

    scope = GOOGLE_DRIVE_FILE_SCOPE
    if not settings.google_drive_client_id or not settings.google_drive_client_secret:
        return templates.TemplateResponse(
            "google_drive_callback_error.html",
            {"request": request, "error": "Google Drive app credentials are not configured by the operator."},
            status_code=503,
        )

    owner_id = get_current_owner_id(request)
    integration = (
        db.query(UserIntegration)
        .filter(UserIntegration.id == integration_id, UserIntegration.owner_id == owner_id)
        .first()
    )
    if not integration:
        return templates.TemplateResponse(
            "google_drive_callback_error.html",
            {"request": request, "error": "Google Drive integration not found."},
            status_code=404,
        )

    cfg = json.loads(integration.config or "{}")
    is_source = integration.direction == "SOURCE" or cfg.get("source_type") == "google_drive"
    delete_after = bool(cfg.get("delete_after_process"))
    scope = (
        GOOGLE_DRIVE_FULL_SCOPE
        if is_source and delete_after
        else GOOGLE_DRIVE_READONLY_SCOPE
        if is_source
        else GOOGLE_DRIVE_FILE_SCOPE
    )
    state = secrets.token_urlsafe(32)
    request.session["google_drive_oauth"] = {
        "integration_id": integration.id,
        "state": state,
        "scope": scope,
        "redirect_uri": redirect_uri,
    }

    # Create the authorization URL with required scopes
    # Use only drive.file scope to minimize required permissions
    scopes = [scope]

    scope_str = urllib.parse.quote(" ".join(scopes))

    auth_url = (
        f"https://accounts.google.com/o/oauth2/auth"
        f"?client_id={settings.google_drive_client_id}"
        f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
        f"&response_type=code"
        f"&scope={scope_str}"
        f"&access_type=offline"
        f"&prompt=consent"  # Force to show consent screen to get refresh token
    )
    auth_url += f"&state={urllib.parse.quote(state)}"

    return RedirectResponse(url=auth_url)
