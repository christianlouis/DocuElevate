"""
OneDrive integration views for setup and OAuth callback.
"""

from fastapi import Request

from app.views.base import APIRouter, require_login, settings, templates

router = APIRouter()


@router.get("/onedrive-setup")
@require_login
async def onedrive_setup_page(request: Request):
    """
    Setup page for the OneDrive integration.
    Shows configuration status and setup instructions.
    """
    # Check OneDrive configuration
    is_configured = bool(
        settings.onedrive_client_id and settings.onedrive_client_secret and settings.onedrive_refresh_token
    )

    # Get configuration values to display status (hide sensitive values)
    return templates.TemplateResponse(
        "onedrive.html",
        {
            "request": request,
            "is_configured": is_configured,
            "client_id": bool(settings.onedrive_client_id),
            "client_id_value": settings.onedrive_client_id or "",  # Pass the actual value for the form
            "client_secret": bool(settings.onedrive_client_secret),
            "client_secret_value": settings.onedrive_client_secret if settings.onedrive_client_secret else "",
            "tenant_id": settings.onedrive_tenant_id,
            "refresh_token": bool(settings.onedrive_refresh_token),
            "refresh_token_value": settings.onedrive_refresh_token if settings.onedrive_refresh_token else "",
            "folder_path": settings.onedrive_folder_path or "Documents/Uploads",  # Default folder path
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
            "client_secret_value": settings.onedrive_client_secret or "",
            "tenant_id": settings.onedrive_tenant_id or "common",
        },
    )
