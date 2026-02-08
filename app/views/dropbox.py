"""
Dropbox integration views for setup and OAuth callback.
"""

from fastapi import Request

from app.views.base import APIRouter, require_login, settings, templates

router = APIRouter()


@router.get("/dropbox-setup")
@require_login
async def dropbox_setup_page(request: Request):
    """
    Setup page for the Dropbox integration.
    Shows configuration status and setup instructions.
    """
    # Check Dropbox configuration
    is_configured = bool(settings.dropbox_app_key and settings.dropbox_app_secret and settings.dropbox_refresh_token)

    return templates.TemplateResponse(
        "dropbox.html",
        {
            "request": request,
            "is_configured": is_configured,
            "app_key_value": settings.dropbox_app_key or "",
            "app_secret_value": settings.dropbox_app_secret if settings.dropbox_app_secret else "",
            "refresh_token_value": settings.dropbox_refresh_token if settings.dropbox_refresh_token else "",
            "folder_path": settings.dropbox_folder or "/Documents/Uploads",  # Default folder path
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
        },
    )
