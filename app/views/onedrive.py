"""
OneDrive integration views for setup and OAuth callback.
"""

import json

from fastapi import HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.models import UserIntegration
from app.utils.user_scope import get_current_owner_id
from app.views.base import APIRouter, Depends, get_db, require_login, settings, templates

router = APIRouter()


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
    return templates.TemplateResponse(
        "onedrive_callback.html",
        {
            "request": request,
            "code": code,
            "client_id_value": settings.onedrive_client_id or "",
            "client_secret_value": "",
            "tenant_id": settings.onedrive_tenant_id or "common",
            "server_credentials_configured": bool(settings.onedrive_client_id and settings.onedrive_client_secret),
        },
    )
