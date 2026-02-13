"""
Google Drive API endpoints
"""

import logging
import os
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Form, HTTPException, Request, status

from app.auth import require_login
from app.config import settings
from app.utils.oauth_helper import exchange_oauth_token

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/google-drive/exchange-token")
@require_login
async def exchange_google_drive_token(
    request: Request,
    client_id: Annotated[str, Form(...)],
    client_secret: Annotated[str, Form(...)],
    redirect_uri: Annotated[str, Form(...)],
    code: Annotated[str, Form(...)],
    folder_id: Annotated[Optional[str], Form()] = None,
):
    """
    Exchange an authorization code for refresh and access tokens from Google.
    This is done on the server to avoid exposing client secret in the browser.
    """
    # Prepare the token request
    token_url = "https://oauth2.googleapis.com/token"

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    # Use shared OAuth helper (handles secure logging and error handling)
    token_data = exchange_oauth_token(provider_name="Google Drive", token_url=token_url, payload=payload)

    # Return just what's needed by the frontend
    return {
        "refresh_token": token_data["refresh_token"],
        "access_token": token_data["access_token"],
        "expires_in": token_data.get("expires_in", 3600),
    }


@router.post("/google-drive/update-settings")
@require_login
async def update_google_drive_settings(
    request: Request,
    refresh_token: Annotated[str, Form(...)],
    client_id: Annotated[Optional[str], Form()] = None,
    client_secret: Annotated[Optional[str], Form()] = None,
    folder_id: Annotated[Optional[str], Form()] = None,
    use_oauth: Annotated[str, Form()] = "true",
):
    """
    Update Google Drive settings in memory
    """
    try:
        logger.info("Updating Google Drive settings in memory")

        # Convert use_oauth string to boolean
        use_oauth_bool = use_oauth.lower() in ("true", "1", "yes", "y", "t")

        # Update settings in memory
        if refresh_token:
            settings.google_drive_refresh_token = refresh_token
            logger.info("Updated GOOGLE_DRIVE_REFRESH_TOKEN in memory")

        if client_id:
            settings.google_drive_client_id = client_id
            logger.info("Updated GOOGLE_DRIVE_CLIENT_ID in memory")

        if client_secret:
            settings.google_drive_client_secret = client_secret
            logger.info("Updated GOOGLE_DRIVE_CLIENT_SECRET in memory")

        if folder_id:
            settings.google_drive_folder_id = folder_id
            logger.info("Updated GOOGLE_DRIVE_FOLDER_ID in memory")

        # Set the OAuth flag
        settings.google_drive_use_oauth = use_oauth_bool
        logger.info(f"Updated GOOGLE_DRIVE_USE_OAUTH in memory to {use_oauth_bool}")

        return {"status": "success", "message": "Google Drive settings have been updated in memory"}

    except Exception as e:
        logger.exception(f"Unexpected error updating Google Drive settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update Google Drive settings: {str(e)}",
        )


@router.get("/google-drive/test-token")
@require_login
async def test_google_drive_token(request: Request):
    """
    Test if the configured Google Drive token is valid.
    Tests both OAuth and service account approaches based on configuration.
    """
    try:
        from app.tasks.upload_to_google_drive import get_drive_service_oauth, get_google_drive_service

        logger.info("Testing Google Drive token validity")

        # Check if OAuth is enabled and configured
        if getattr(settings, "google_drive_use_oauth", False):
            if not (
                settings.google_drive_client_id
                and settings.google_drive_client_secret
                and settings.google_drive_refresh_token
            ):
                logger.warning("Google Drive OAuth credentials not fully configured")
                return {"status": "error", "message": "Google Drive OAuth credentials are not fully configured"}

            try:
                # Test OAuth connection
                service = get_drive_service_oauth()

                # Get credentials for checking token validity
                import google.oauth2.credentials
                from google.auth.transport.requests import Request

                credentials = google.oauth2.credentials.Credentials(
                    token=None,
                    refresh_token=settings.google_drive_refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=settings.google_drive_client_id,
                    client_secret=settings.google_drive_client_secret,
                )

                # Force a refresh to update the token expiration
                if not credentials.valid:
                    credentials.refresh(Request())

                # Get token expiration info
                expiration_info = {}
                if hasattr(credentials, "expiry") and credentials.expiry:
                    now = datetime.now()
                    expiry = credentials.expiry
                    time_left = expiry - now
                    expiration_info = {
                        "expires_at": expiry.isoformat(),
                        "expires_in_seconds": max(0, int(time_left.total_seconds())),
                        "expires_in_human": format_time_remaining(time_left),
                    }

                # Test basic API operation
                about = service.about().get(fields="user").execute()
                user_email = about.get("user", {}).get("emailAddress", "Unknown")

                logger.info(f"Successfully connected to Google Drive as {user_email}")

                return {
                    "status": "success",
                    "message": f"OAuth token is valid! Connected as {user_email}",
                    "account": user_email,
                    "auth_type": "oauth",
                    "token_info": expiration_info,
                }
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Google Drive OAuth token test failed: {error_msg}")

                # Check if this is a token-related error
                if "invalid_grant" in error_msg.lower() or "token" in error_msg.lower():
                    return {
                        "status": "error",
                        "message": f"OAuth token validation failed: {error_msg}",
                        "needs_reauth": True,
                    }
                return {"status": "error", "message": f"Connection error: {error_msg}"}
        else:
            # Test service account connection
            if not settings.google_drive_credentials_json:
                logger.warning("Google Drive service account credentials not configured")
                return {"status": "error", "message": "Google Drive service account credentials are not configured"}

            try:
                service = get_google_drive_service()
                about = service.about().get(fields="user").execute()

                # For service accounts, try to show the delegated user if available
                user_email = about.get("user", {}).get("emailAddress", "Unknown")
                delegated_user = getattr(settings, "google_drive_delegate_to", None)

                if delegated_user:
                    user_display = f"{user_email} (delegating as {delegated_user})"
                else:
                    user_display = user_email

                logger.info(f"Successfully connected to Google Drive using service account as {user_display}")

                return {
                    "status": "success",
                    "message": f"Service account is valid! Connected as {user_display}",
                    "account": user_email,
                    "auth_type": "service_account",
                }
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Google Drive service account test failed: {error_msg}")
                return {"status": "error", "message": f"Service account validation failed: {error_msg}"}

    except Exception as e:
        logger.exception("Unexpected error testing Google Drive token")
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}


@router.get("/google-drive/get-token-info")
@require_login
async def get_google_drive_token_info(request: Request):
    """
    Get information about the current Google Drive token.
    Returns the access token if one exists and is valid.
    Used by the frontend to access the Google Picker API.
    """
    try:
        logger.info("Getting Google Drive token information")

        # Check if OAuth is enabled and configured
        if not getattr(settings, "google_drive_use_oauth", False):
            logger.warning("OAuth is not enabled, using service account instead")
            return {
                "status": "error",
                "message": "OAuth is not enabled. Service accounts don't support user-facing features.",
            }

        if not (
            settings.google_drive_client_id
            and settings.google_drive_client_secret
            and settings.google_drive_refresh_token
        ):
            logger.warning("Google Drive OAuth credentials not fully configured")
            return {"status": "error", "message": "Google Drive OAuth credentials are not fully configured"}

        try:
            # Get credentials and access token
            import google.oauth2.credentials
            from google.auth.transport.requests import Request

            credentials = google.oauth2.credentials.Credentials(
                token=None,
                refresh_token=settings.google_drive_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.google_drive_client_id,
                client_secret=settings.google_drive_client_secret,
            )

            # Force a refresh to get a fresh access token
            if not credentials.valid:
                credentials.refresh(Request())

            # Get token expiration info
            expiration_info = {}
            if hasattr(credentials, "expiry") and credentials.expiry:
                now = datetime.now()
                expiry = credentials.expiry
                time_left = expiry - now
                expiration_info = {
                    "expires_at": expiry.isoformat(),
                    "expires_in_seconds": max(0, int(time_left.total_seconds())),
                    "expires_in_human": format_time_remaining(time_left),
                }

            # Return the token info
            logger.info("Successfully retrieved Google Drive access token")

            return {
                "status": "success",
                "message": "Access token successfully retrieved",
                "access_token": credentials.token,
                "token_info": expiration_info,
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to get Google Drive token: {error_msg}")

            # Check if this is a token-related error
            if "invalid_grant" in error_msg.lower() or "token" in error_msg.lower():
                return {
                    "status": "error",
                    "message": f"OAuth token retrieval failed: {error_msg}",
                    "needs_reauth": True,
                }
            return {"status": "error", "message": f"Token retrieval error: {error_msg}"}

    except Exception as e:
        logger.exception("Unexpected error getting Google Drive token info")
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}


def format_time_remaining(time_delta):
    """Format a timedelta into a human-readable string."""
    if time_delta.total_seconds() <= 0:
        return "Expired"

    days = time_delta.days
    hours, remainder = divmod(time_delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0 and days == 0:  # Only show minutes if less than a day
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

    return ", ".join(parts)


@router.post("/google-drive/save-settings")
@require_login
async def save_dropbox_settings(
    request: Request,
    refresh_token: Annotated[str, Form(...)],
    client_id: Annotated[Optional[str], Form()] = None,
    client_secret: Annotated[Optional[str], Form()] = None,
    folder_id: Annotated[Optional[str], Form()] = None,
    use_oauth: Annotated[str, Form()] = "true",
):
    """
    Save Google Drive settings to the .env file
    """
    try:
        # Get the path to the .env file
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")

        # Convert use_oauth string to boolean
        use_oauth_bool = use_oauth.lower() in ("true", "1", "yes", "y", "t")

        # Define settings to update
        drive_settings = {"GOOGLE_DRIVE_USE_OAUTH": str(use_oauth_bool).lower()}

        # Only update these if provided
        if use_oauth_bool:
            if refresh_token:
                drive_settings["GOOGLE_DRIVE_REFRESH_TOKEN"] = refresh_token
            if client_id:
                drive_settings["GOOGLE_DRIVE_CLIENT_ID"] = client_id
            if client_secret:
                drive_settings["GOOGLE_DRIVE_CLIENT_SECRET"] = client_secret

        # Always include folder ID if provided
        if folder_id:
            drive_settings["GOOGLE_DRIVE_FOLDER_ID"] = folder_id

        # Try to update the .env file, but don't fail if it doesn't exist (for Docker containers)
        if os.path.exists(env_path):
            try:
                logger.info(f"Updating Google Drive settings in {env_path}")

                # Read the current .env file
                with open(env_path, "r") as f:
                    env_lines = f.readlines()

                # Process each line and update or add settings
                updated = set()
                new_env_lines = []
                for line in env_lines:
                    stripped_line = line.rstrip()
                    is_updated = False
                    for key, value in drive_settings.items():
                        if stripped_line.startswith(f"{key}=") or stripped_line.startswith(f"# {key}="):
                            # Uncomment if commented out - check the original stripped line
                            new_env_lines.append(f"{key}={value}")
                            updated.add(key)
                            is_updated = True
                            break
                    if not is_updated:
                        new_env_lines.append(stripped_line)

                # Add any settings that weren't updated (they weren't in the file)
                for key, value in drive_settings.items():
                    if key not in updated:
                        new_env_lines.append(f"{key}={value}")

                # Write the updated .env file
                with open(env_path, "w") as f:
                    f.write("\n".join(new_env_lines) + "\n")

                logger.info("Successfully updated Google Drive settings in .env file")
            except Exception as e:
                logger.warning(f"Failed to update .env file: {str(e)}, but will continue with in-memory update")
        else:
            logger.warning(
                f".env file not found at {env_path}, skipping file update but continuing with in-memory update"
            )

        # Update the settings in memory (this always happens)
        if refresh_token:
            settings.google_drive_refresh_token = refresh_token
        if client_id:
            settings.google_drive_client_id = client_id
        if client_secret:
            settings.google_drive_client_secret = client_secret
        if folder_id:
            settings.google_drive_folder_id = folder_id

        # Set OAuth flag
        settings.google_drive_use_oauth = use_oauth_bool

        logger.info("Successfully updated Google Drive settings in memory")

        return {
            "status": "success",
            "message": "Google Drive settings have been saved",
            "in_memory_only": not os.path.exists(env_path),
        }

    except Exception as e:
        logger.exception(f"Unexpected error saving Google Drive settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save Google Drive settings: {str(e)}"
        )
