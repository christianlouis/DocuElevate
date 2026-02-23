"""
OneDrive API endpoints
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Annotated, Optional

import requests
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import require_login
from app.config import settings
from app.database import get_db
from app.utils.oauth_helper import exchange_oauth_token
from app.utils.settings_service import save_setting_to_db
from app.utils.settings_sync import notify_settings_updated

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/onedrive/exchange-token")
@require_login
async def exchange_onedrive_token(
    request: Request,
    client_id: Annotated[str, Form(...)],
    client_secret: Annotated[str, Form(...)],
    redirect_uri: Annotated[str, Form(...)],
    code: Annotated[str, Form(...)],
    tenant_id: Annotated[str, Form(...)],
):
    """
    Exchange an authorization code for a refresh token.
    This is done on the server to avoid exposing client secret in the browser.
    """
    # Prepare the token request
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    payload = {
        "client_id": client_id,
        "scope": "https://graph.microsoft.com/.default offline_access",
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "client_secret": client_secret,
    }

    # Use shared OAuth helper (handles secure logging and error handling)
    token_data = exchange_oauth_token(
        provider_name="OneDrive", token_url=token_url, payload=payload
    )

    # Return just what's needed by the frontend
    return {
        "refresh_token": token_data["refresh_token"],
        "expires_in": token_data.get("expires_in", 3600),
    }


@router.get("/onedrive/test-token")
@require_login
async def test_onedrive_token(request: Request):
    """
    Test if the configured OneDrive token is valid and return expiration information.
    """
    try:
        logger.info("Testing OneDrive token validity")

        if (
            not settings.onedrive_refresh_token
            or not settings.onedrive_client_id
            or not settings.onedrive_client_secret
        ):
            logger.warning("OneDrive credentials not fully configured")
            return {
                "status": "error",
                "message": "OneDrive credentials are not fully configured",
            }

        # Refresh token to get a new access token and expiration info
        tenant_id = settings.onedrive_tenant_id or "common"
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

        refresh_data = {
            "client_id": settings.onedrive_client_id,
            "client_secret": settings.onedrive_client_secret,
            "refresh_token": settings.onedrive_refresh_token,
            "grant_type": "refresh_token",
            "scope": "offline_access Files.ReadWrite",
        }

        response = requests.post(
            token_url, data=refresh_data, timeout=settings.http_request_timeout
        )

        if response.status_code != 200:
            logger.error(f"Failed to refresh OneDrive token: {response.text}")
            return {
                "status": "error",
                "message": "Refresh token has expired or is invalid",
                "needs_reauth": True,
            }

        token_data = response.json()
        access_token = token_data.get("access_token")
        expires_in = token_data.get(
            "expires_in", 3600
        )  # Default to 1 hour if not specified

        # Check if we got a new refresh token (Microsoft sometimes issues a new one)
        new_refresh_token = token_data.get("refresh_token")
        if new_refresh_token and new_refresh_token != settings.onedrive_refresh_token:
            logger.info(
                "Received new refresh token from Microsoft - will update configuration"
            )

            # Update refresh token in memory
            settings.onedrive_refresh_token = new_refresh_token

            # Also try to update .env file if it exists
            try:
                env_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
                )
                if os.path.exists(env_path):
                    with open(env_path, "r") as f:
                        env_lines = f.readlines()

                    updated_lines = []
                    updated = False

                    for line in env_lines:
                        if line.startswith("ONEDRIVE_REFRESH_TOKEN="):
                            updated_lines.append(
                                f"ONEDRIVE_REFRESH_TOKEN={new_refresh_token}\n"
                            )
                            updated = True
                        else:
                            updated_lines.append(line)

                    if not updated:
                        updated_lines.append(
                            f"ONEDRIVE_REFRESH_TOKEN={new_refresh_token}\n"
                        )

                    with open(env_path, "w") as f:
                        f.writelines(updated_lines)

                    logger.info("Updated refresh token in .env file")

            except Exception as e:
                logger.warning(f"Failed to update refresh token in .env file: {e}")

            # Persist the rotated refresh token to the database
            try:
                from app.database import SessionLocal

                _db = SessionLocal()
                try:
                    save_setting_to_db(
                        _db,
                        "onedrive_refresh_token",
                        new_refresh_token,
                        changed_by="onedrive_token_rotation",
                    )
                    notify_settings_updated()
                finally:
                    _db.close()
            except Exception as _e:
                logger.warning(
                    f"Failed to persist rotated OneDrive refresh token to database: {_e}"
                )

        # Test the access token by getting user information
        user_info_url = "https://graph.microsoft.com/v1.0/me"
        headers = {"Authorization": f"Bearer {access_token}"}

        user_response = requests.get(
            user_info_url, headers=headers, timeout=settings.http_request_timeout
        )

        if user_response.status_code != 200:
            logger.error(
                f"OneDrive token test failed: {user_response.status_code} {user_response.text}"
            )
            return {
                "status": "error",
                "message": f"Token validation failed with status {user_response.status_code}: {user_response.text}",
            }

        # Get user info
        user_info = user_response.json()
        display_name = user_info.get("displayName", "Unknown user")
        email = user_info.get("userPrincipalName", "Unknown email")

        # Calculate expiration time
        now = datetime.now()
        expiry_time = now + timedelta(seconds=expires_in)

        # Format expiration info
        time_left = expiry_time - now
        token_info = {
            "expires_at": expiry_time.isoformat(),
            "expires_in_seconds": expires_in,
            "expires_in_human": format_time_remaining(time_left),
            "refresh_token_validity": "Refresh token is valid for 90 days of inactivity",
        }

        logger.info(f"Successfully connected to OneDrive as {email}")

        return {
            "status": "success",
            "message": "OneDrive connection successful",
            "account": email,
            "account_name": display_name,
            "token_info": token_info,
        }

    except Exception as e:
        logger.exception(f"Unexpected error testing OneDrive token: {str(e)}")
        return {"status": "error", "message": f"Connection error: {str(e)}"}


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


@router.post("/onedrive/save-settings")
@require_login
async def save_onedrive_settings(
    request: Request,
    refresh_token: Annotated[str, Form(...)],
    client_id: Annotated[Optional[str], Form()] = None,
    client_secret: Annotated[Optional[str], Form()] = None,
    tenant_id: Annotated[str, Form()] = "common",
    folder_path: Annotated[Optional[str], Form()] = None,
    db: Session = Depends(get_db),
):
    """
    Saves to database (primary) and .env file (best-effort).
    """
    try:
        user = request.session.get("user", {}) if hasattr(request, "session") else {}
        changed_by = (
            user.get("preferred_username")
            or user.get("username")
            or user.get("email")
            or user.get("id")
            or "wizard"
        )

        # Best-effort .env file write
        try:
            env_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
            )
            if not os.path.exists(env_path):
                logger.warning(
                    f".env file not found at {env_path}, skipping file write"
                )
            else:
                logger.info(f"Updating OneDrive settings in {env_path}")

                with open(env_path, "r") as f:
                    env_lines = f.readlines()

                onedrive_settings = {"ONEDRIVE_REFRESH_TOKEN": refresh_token}
                if client_id:
                    onedrive_settings["ONEDRIVE_CLIENT_ID"] = client_id
                if client_secret:
                    onedrive_settings["ONEDRIVE_CLIENT_SECRET"] = client_secret
                if tenant_id:
                    onedrive_settings["ONEDRIVE_TENANT_ID"] = tenant_id
                if folder_path:
                    onedrive_settings["ONEDRIVE_FOLDER_PATH"] = folder_path

                updated = set()
                new_env_lines = []
                for line in env_lines:
                    stripped_line = line.rstrip()
                    is_updated = False
                    for key, value in onedrive_settings.items():
                        if stripped_line.startswith(
                            f"{key}="
                        ) or stripped_line.startswith(f"# {key}="):
                            new_env_lines.append(f"{key}={value}")
                            updated.add(key)
                            is_updated = True
                            break
                    if not is_updated:
                        new_env_lines.append(stripped_line)

                for key, value in onedrive_settings.items():
                    if key not in updated:
                        new_env_lines.append(f"{key}={value}")

                with open(env_path, "w") as f:
                    f.write("\n".join(new_env_lines) + "\n")

                logger.info("Successfully updated OneDrive settings in .env file")
        except Exception as env_err:
            logger.warning(f"Failed to write .env file (non-fatal): {env_err}")

        # Update the settings in memory
        if refresh_token:
            settings.onedrive_refresh_token = refresh_token
        if client_id:
            settings.onedrive_client_id = client_id
        if client_secret:
            settings.onedrive_client_secret = client_secret
        if tenant_id:
            settings.onedrive_tenant_id = tenant_id
        if folder_path:
            settings.onedrive_folder_path = folder_path

        # Persist to database (primary)
        if refresh_token:
            save_setting_to_db(
                db, "onedrive_refresh_token", refresh_token, changed_by=changed_by
            )
        if client_id:
            save_setting_to_db(
                db, "onedrive_client_id", client_id, changed_by=changed_by
            )
        if client_secret:
            save_setting_to_db(
                db, "onedrive_client_secret", client_secret, changed_by=changed_by
            )
        if tenant_id:
            save_setting_to_db(
                db, "onedrive_tenant_id", tenant_id, changed_by=changed_by
            )
        if folder_path:
            save_setting_to_db(
                db, "onedrive_folder_path", folder_path, changed_by=changed_by
            )

        notify_settings_updated()

        logger.info("Successfully saved OneDrive settings")
        return {"status": "success", "message": "OneDrive settings have been saved"}

    except Exception as e:
        logger.exception(f"Unexpected error saving OneDrive settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save OneDrive settings: {str(e)}",
        )


@router.post("/onedrive/update-settings")
@require_login
async def update_onedrive_settings(
    request: Request,
    refresh_token: Annotated[str, Form(...)],
    client_id: Annotated[Optional[str], Form()] = None,
    client_secret: Annotated[Optional[str], Form()] = None,
    tenant_id: Annotated[str, Form()] = "common",
    folder_path: Annotated[Optional[str], Form()] = None,
    db: Session = Depends(get_db),
):
    """
    Update OneDrive settings in memory and persist to database
    """
    try:
        logger.info("Updating OneDrive settings in memory and database")

        user = request.session.get("user", {}) if hasattr(request, "session") else {}
        changed_by = (
            user.get("preferred_username")
            or user.get("username")
            or user.get("email")
            or user.get("id")
            or "wizard"
        )

        # Update settings in memory and persist to database
        if refresh_token:
            settings.onedrive_refresh_token = refresh_token
            save_setting_to_db(
                db, "onedrive_refresh_token", refresh_token, changed_by=changed_by
            )
            logger.info("Updated ONEDRIVE_REFRESH_TOKEN in memory and database")

        if client_id:
            settings.onedrive_client_id = client_id
            save_setting_to_db(
                db, "onedrive_client_id", client_id, changed_by=changed_by
            )
            logger.info("Updated ONEDRIVE_CLIENT_ID in memory and database")

        if client_secret:
            settings.onedrive_client_secret = client_secret
            save_setting_to_db(
                db, "onedrive_client_secret", client_secret, changed_by=changed_by
            )
            logger.info("Updated ONEDRIVE_CLIENT_SECRET in memory and database")

        if tenant_id:
            settings.onedrive_tenant_id = tenant_id
            save_setting_to_db(
                db, "onedrive_tenant_id", tenant_id, changed_by=changed_by
            )
            logger.info("Updated ONEDRIVE_TENANT_ID in memory and database")

        if folder_path:
            settings.onedrive_folder_path = folder_path
            save_setting_to_db(
                db, "onedrive_folder_path", folder_path, changed_by=changed_by
            )
            logger.info("Updated ONEDRIVE_FOLDER_PATH in memory and database")

        notify_settings_updated()

        # Test the token to make sure it works
        try:
            from app.tasks.upload_to_onedrive import get_onedrive_token

            get_onedrive_token()  # Test that token can be retrieved
            logger.info("Successfully tested OneDrive token")
        except Exception as e:
            logger.error(f"Token test failed after updating settings: {str(e)}")
            return {
                "status": "warning",
                "message": "Settings updated but token test failed: " + str(e),
            }

        return {
            "status": "success",
            "message": "OneDrive settings have been updated in memory and database",
        }

    except Exception as e:
        logger.exception(f"Unexpected error updating OneDrive settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update OneDrive settings: {str(e)}",
        )


@router.get("/onedrive/get-full-config")
@require_login
async def get_onedrive_full_config(request: Request):
    """
    Get the full OneDrive configuration for sharing with worker nodes
    """
    try:
        # Create a configuration object with all OneDrive settings
        config = {
            "client_id": settings.onedrive_client_id or "",
            "client_secret": settings.onedrive_client_secret or "",
            "tenant_id": settings.onedrive_tenant_id or "common",
            "refresh_token": settings.onedrive_refresh_token or "",
            "folder_path": settings.onedrive_folder_path or "Documents/Uploads",
        }

        # Generate environment variable format
        env_format = "\n".join(
            [
                f"ONEDRIVE_CLIENT_ID={config['client_id']}",
                f"ONEDRIVE_CLIENT_SECRET={config['client_secret']}",
                f"ONEDRIVE_TENANT_ID={config['tenant_id']}",
                f"ONEDRIVE_REFRESH_TOKEN={config['refresh_token']}",
                f"ONEDRIVE_FOLDER_PATH={config['folder_path']}",
            ]
        )

        return {"status": "success", "config": config, "env_format": env_format}
    except Exception as e:
        logger.exception("Error getting OneDrive configuration")
        return {"status": "error", "message": str(e)}
