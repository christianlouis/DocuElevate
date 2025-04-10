"""
Google Drive integration views for setup and OAuth callback.
"""
from fastapi import Request
from fastapi.responses import RedirectResponse
import urllib.parse

from app.views.base import APIRouter, templates, require_login, settings

router = APIRouter()

@router.get("/google-drive-setup")
@require_login
async def google_drive_setup_page(request: Request):
    """
    Setup page for the Google Drive integration.
    Shows configuration status and setup instructions.
    """
    # Check if using OAuth
    use_oauth = getattr(settings, 'google_drive_use_oauth', False)
    
    # Check Google Drive OAuth configuration
    oauth_configured = bool(settings.google_drive_client_id and 
                         settings.google_drive_client_secret and 
                         settings.google_drive_refresh_token)
    
    # Check Google Drive service account configuration
    sa_configured = bool(settings.google_drive_credentials_json)
    
    # Overall configuration status
    is_configured = (use_oauth and oauth_configured) or (not use_oauth and sa_configured)
    
    if settings.google_drive_folder_id:
        is_configured = is_configured and True
    else:
        is_configured = False
    
    # Get configuration values to display status (hide sensitive values)
    return templates.TemplateResponse(
        "google_drive.html",
        {
            "request": request,
            "is_configured": is_configured,
            "use_oauth": use_oauth,
            "oauth_configured": oauth_configured,
            "sa_configured": sa_configured,
            "client_id": bool(settings.google_drive_client_id),
            "client_id_value": settings.google_drive_client_id or "",
            "client_secret": bool(settings.google_drive_client_secret),
            "client_secret_value": settings.google_drive_client_secret or "",
            "refresh_token": bool(settings.google_drive_refresh_token),
            "refresh_token_value": settings.google_drive_refresh_token or "",
            "folder_id": settings.google_drive_folder_id or "",
            "has_credentials_json": bool(settings.google_drive_credentials_json)
        }
    )

@router.get("/google-drive-callback")
@require_login
async def google_drive_callback(request: Request, code: str = None, error: str = None, state: str = None):
    """
    Callback endpoint for Google Drive OAuth flow.
    Now automatically exchanges the code for a token and saves it to the configuration.
    """
    if error:
        return templates.TemplateResponse(
            "google_drive_callback_error.html",
            {"request": request, "error": error}
        )
    
    if not code:
        return templates.TemplateResponse(
            "google_drive_callback_error.html",
            {"request": request, "error": "No authorization code received from Google"}
        )
    
    # Display the processing page with automatic token exchange
    return templates.TemplateResponse(
        "google_drive_callback.html",
        {
            "request": request, 
            "code": code,
            "state": state
        }
    )

@router.get("/google-drive-auth-start")
@require_login
async def google_drive_auth_start(
    request: Request, 
    client_id: str,
    redirect_uri: str = None
):
    """
    Start the Google Drive OAuth flow by redirecting to Google's authorization page.
    """
    if not redirect_uri:
        redirect_uri = f"{request.url.scheme}://{request.url.netloc}/google-drive-callback"
    
    # Create the authorization URL with required scopes
    # Use only drive.file scope to minimize required permissions
    scopes = [
        "https://www.googleapis.com/auth/drive.file"  # Access to files created or opened by the app
    ]
    
    scope_str = urllib.parse.quote(' '.join(scopes))
    
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
