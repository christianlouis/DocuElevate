"""
OneDrive integration views for setup and OAuth callback.
"""

import json
import re
import secrets
from urllib.parse import quote

from fastapi import Form, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.models import UserIntegration
from app.utils.onedrive_oauth import OneDriveOAuthTransactionUnavailable, store_pending_onedrive_oauth
from app.utils.user_scope import get_current_owner_id
from app.views.base import APIRouter, Depends, get_db, require_login, settings, templates

router = APIRouter()


def _valid_tenant_id(value: str) -> bool:
    """Allow Microsoft tenant aliases, GUIDs, or DNS tenant names only."""
    return bool(value and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,127}", value))


@router.get("/onedrive-setup")
@require_login
async def onedrive_setup_page(
    request: Request,
    integration_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """
    Setup page for the OneDrive integration.

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
            # Support both "folder_path" (WATCH_FOLDER / ONEDRIVE destination)
            folder_path = cfg.get("folder_path", cfg.get("folder", ""))
            # Provide system-wide app credentials when available so users can
            # authorize without registering their own Azure/OneDrive app.
            has_system_credentials = bool(settings.onedrive_client_id and settings.onedrive_client_secret)
            return templates.TemplateResponse(
                "onedrive.html",
                {
                    "request": request,
                    "user_mode": True,
                    "is_configured": bool(integration.credentials),
                    "integration_id": integration_id,
                    "integration_name": integration.name,
                    "integration_type": integration.integration_type,
                    "folder_path": folder_path,
                    "has_system_credentials": has_system_credentials,
                    "server_credentials_configured": has_system_credentials,
                    "client_id": bool(settings.onedrive_client_id) if has_system_credentials else False,
                    "client_id_value": settings.onedrive_client_id or "" if has_system_credentials else "",
                    "client_secret": bool(settings.onedrive_client_secret) if has_system_credentials else False,
                    "client_secret_value": "",
                    "tenant_id": settings.onedrive_tenant_id or "common",
                    "refresh_token": False,
                    "refresh_token_value": "",
                },
            )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    # ── Admin / global mode ──────────────────────────────────────────────────
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    is_configured = bool(
        settings.onedrive_client_id and settings.onedrive_client_secret and settings.onedrive_refresh_token
    )

    return templates.TemplateResponse(
        "onedrive.html",
        {
            "request": request,
            "user_mode": False,
            "is_configured": is_configured,
            "has_system_credentials": bool(settings.onedrive_client_id and settings.onedrive_client_secret),
            "server_credentials_configured": bool(settings.onedrive_client_id and settings.onedrive_client_secret),
            "client_id": bool(settings.onedrive_client_id),
            "client_id_value": settings.onedrive_client_id or "",
            "client_secret": bool(settings.onedrive_client_secret),
            "client_secret_value": "",
            "tenant_id": settings.onedrive_tenant_id,
            "refresh_token": bool(settings.onedrive_refresh_token),
            # Never render the global bearer credential into HTML. The boolean
            # lets the admin see whether configuration exists without exposing it.
            "refresh_token_value": "",
            "folder_path": settings.onedrive_folder_path or "Documents/Uploads",
            "integration_id": integration_id,
            "integration_name": None,
            "integration_type": None,
        },
    )


@router.get("/onedrive-callback")
@require_login
async def onedrive_callback(request: Request, code: str = None, error: str = None):
    """
    Callback endpoint for OneDrive OAuth flow.
    Now automatically exchanges the code for a token and saves it to the configuration.
    """
    if error:
        return templates.TemplateResponse("onedrive_callback_error.html", {"request": request, "error": error})

    if not code:
        return templates.TemplateResponse(
            "onedrive_callback_error.html",
            {"request": request, "error": "No authorization code received from Microsoft"},
        )

    # Display the processing page with automatic token exchange
    oauth = request.session.get("onedrive_oauth", {})
    return templates.TemplateResponse(
        "onedrive_callback.html",
        {
            "request": request,
            "code": code,
            "state": request.query_params.get("state", ""),
            "tenant_id": oauth.get("tenant_id") or "common",
            "integration_id": oauth.get("integration_id"),
        },
    )


@router.post("/onedrive-auth-start")
@require_login
async def onedrive_auth_start(
    request: Request,
    integration_id: int | None = Form(None),
    client_id: str | None = Form(None),
    client_secret: str | None = Form(None),
    tenant_id: str | None = Form(None),
    folder_path: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Create a one-time, owner-bound OneDrive OAuth transaction."""
    if integration_id is None:
        user = get_current_user(request)
        if not user or not user.get("is_admin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    owner_id = get_current_owner_id(request)
    if not owner_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A stable authenticated user is required")
    if bool(client_id) != bool(client_secret):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Both OneDrive client fields are required")
    if integration_id is not None:
        integration = (
            db.query(UserIntegration)
            .filter(UserIntegration.id == integration_id, UserIntegration.owner_id == owner_id)
            .first()
        )
        if not integration:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
        if not client_id or not client_secret:
            client_id = settings.onedrive_client_id
            client_secret = settings.onedrive_client_secret
    else:
        client_id = client_id or settings.onedrive_client_id
        client_secret = client_secret or settings.onedrive_client_secret

    tenant_id = tenant_id or settings.onedrive_tenant_id or "common"
    if not client_id or not client_secret or not _valid_tenant_id(tenant_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OneDrive OAuth client is not configured")
    state = secrets.token_urlsafe(32)
    redirect_uri = (settings.public_base_url or str(request.base_url).rstrip("/")).rstrip("/") + "/onedrive-callback"
    try:
        store_pending_onedrive_oauth(
            state,
            {
                "integration_id": integration_id,
                "owner_id": owner_id,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "tenant_id": tenant_id,
                "folder_path": folder_path,
            },
        )
    except OneDriveOAuthTransactionUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    request.session["onedrive_oauth"] = {
        "integration_id": integration_id,
        "owner_id": owner_id,
        "state": state,
        "redirect_uri": redirect_uri,
        "tenant_id": tenant_id,
    }
    return {
        "authorize_url": (
            f"https://login.microsoftonline.com/{quote(tenant_id, safe='')}/oauth2/v2.0/authorize"
            f"?client_id={quote(client_id, safe='')}&response_type=code&response_mode=query"
            f"&redirect_uri={quote(redirect_uri, safe='')}&scope={quote('https://graph.microsoft.com/.default offline_access', safe='')}&state={quote(state, safe='')}&prompt=consent"
        )
    }
