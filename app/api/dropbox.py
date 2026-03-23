"""
Dropbox API endpoints
"""

import logging
import os
from typing import Annotated, Optional

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import require_login
from app.config import settings
from app.database import get_db
from app.utils.oauth_helper import exchange_oauth_token
from app.utils.settings_service import save_setting_to_db, update_env_file
from app.utils.settings_sync import notify_settings_updated

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()


def _require_admin(request: Request) -> dict:
    """Dependency to ensure the current user is an admin."""
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


AdminUser = Annotated[dict, Depends(_require_admin)]


@router.post("/dropbox/exchange-token")
@require_login
async def exchange_dropbox_token(
    request: Request,
    client_id: Annotated[str, Form(...)],
    client_secret: Annotated[str, Form(...)],
    redirect_uri: Annotated[str, Form(...)],
    code: Annotated[str, Form(...)],
    folder_path: Annotated[Optional[str], Form()] = None,
):
    """
    Exchange an authorization code for a refresh token from Dropbox.
    This is done on the server to avoid exposing client secret in the browser.
    """
    # Prepare the token request
    token_url = "https://api.dropboxapi.com/oauth2/token"

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    # Use shared OAuth helper (handles secure logging and error handling)
    token_data = exchange_oauth_token(provider_name="Dropbox", token_url=token_url, payload=payload)

    # Return just what's needed by the frontend
    return {
        "refresh_token": token_data["refresh_token"],
        "access_token": token_data["access_token"],
        "expires_in": token_data.get("expires_in", 14400),
    }


@router.post("/dropbox/update-settings")
@require_login
async def update_dropbox_settings(
    request: Request,
    refresh_token: Annotated[str, Form(...)],
    app_key: Annotated[Optional[str], Form()] = None,
    app_secret: Annotated[Optional[str], Form()] = None,
    folder_path: Annotated[Optional[str], Form()] = None,
    db: Session = Depends(get_db),
):
    """
    Update Dropbox settings in memory and persist to the database.
    """
    try:
        logger.info("Updating Dropbox settings in memory and database")

        user = request.session.get("user", {}) if hasattr(request, "session") else {}
        changed_by = (
            user.get("preferred_username") or user.get("username") or user.get("email") or user.get("id") or "wizard"
        )

        # Update settings in memory and persist to database
        if refresh_token:
            settings.dropbox_refresh_token = refresh_token
            save_setting_to_db(db, "dropbox_refresh_token", refresh_token, changed_by=changed_by)
            logger.info("Updated DROPBOX_REFRESH_TOKEN in memory and database")

        if app_key:
            settings.dropbox_app_key = app_key
            save_setting_to_db(db, "dropbox_app_key", app_key, changed_by=changed_by)
            logger.info("Updated DROPBOX_APP_KEY in memory and database")

        if app_secret:
            settings.dropbox_app_secret = app_secret
            save_setting_to_db(db, "dropbox_app_secret", app_secret, changed_by=changed_by)
            logger.info("Updated DROPBOX_APP_SECRET in memory and database")

        if folder_path:
            settings.dropbox_folder = folder_path
            save_setting_to_db(db, "dropbox_folder", folder_path, changed_by=changed_by)
            logger.info("Updated DROPBOX_FOLDER in memory and database")

        notify_settings_updated()

        return {
            "status": "success",
            "message": "Dropbox settings have been updated in memory and saved to database",
        }

    except Exception as e:
        logger.exception(f"Unexpected error updating Dropbox settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update Dropbox settings: {str(e)}",
        )


@router.get("/dropbox/test-token")
@require_login
async def test_dropbox_token(request: Request):
    """
    Test if the configured Dropbox token is valid and return expiration information.
    """
    try:
        logger.info("Testing Dropbox token validity")

        if not settings.dropbox_refresh_token or not settings.dropbox_app_key or not settings.dropbox_app_secret:
            logger.warning("Dropbox credentials not fully configured")
            return {
                "status": "error",
                "message": "Dropbox credentials are not fully configured",
            }

        async with httpx.AsyncClient() as client:
            # Check token validity by getting current account info
            headers = {"Authorization": f"Bearer {settings.dropbox_refresh_token}"}
            response = await client.post(
                "https://api.dropboxapi.com/2/users/get_current_account",
                headers=headers,
                timeout=settings.http_request_timeout,
            )

            # If token is invalid, try refreshing it
            if response.status_code == 401:
                logger.info("Dropbox access token invalid or expired, trying to refresh")

                # Get a new access token using the refresh token
                refresh_url = "https://api.dropbox.com/oauth2/token"
                refresh_data = {
                    "grant_type": "refresh_token",
                    "refresh_token": settings.dropbox_refresh_token,
                    "client_id": settings.dropbox_app_key,
                    "client_secret": settings.dropbox_app_secret,
                }

                refresh_response = await client.post(
                    refresh_url, data=refresh_data, timeout=settings.http_request_timeout
                )

                if refresh_response.status_code != 200:
                    logger.error(f"Failed to refresh Dropbox token: {refresh_response.text}")
                    return {
                        "status": "error",
                        "message": "Refresh token has expired or is invalid",
                        "needs_reauth": True,
                    }

                token_info = refresh_response.json()
                access_token = token_info.get("access_token")

                # Try again with the new access token
                headers = {"Authorization": f"Bearer {access_token}"}
                response = await client.post(
                    "https://api.dropboxapi.com/2/users/get_current_account",
                    headers=headers,
                    timeout=settings.http_request_timeout,
                )

            if response.status_code != 200:
                logger.error(f"Dropbox token test failed: {response.status_code} {response.text}")
                return {
                    "status": "error",
                    "message": f"Token validation failed with status {response.status_code}: {response.text}",
                }

            # Get account info
            account_info = response.json()
        account_email = account_info.get("email", "Unknown account")
        account_name = account_info.get("name", {}).get("display_name", "Unknown user")

        # Dropbox refresh tokens don't expire, but we should note that in our response
        token_info = {
            "expires_in_human": "Never expires (perpetual token)",
            "is_perpetual": True,
        }

        logger.info(f"Successfully connected to Dropbox as {account_email}")

        return {
            "status": "success",
            "message": "Dropbox connection successful",
            "account": account_email,
            "account_name": account_name,
            "token_info": token_info,
        }

    except Exception as e:
        logger.exception(f"Unexpected error testing Dropbox token: {str(e)}")
        return {"status": "error", "message": f"Connection error: {str(e)}"}


@router.post("/dropbox/save-settings")
async def save_dropbox_settings(
    request: Request,
    _admin: AdminUser,
    refresh_token: Annotated[str, Form(...)],
    app_key: Annotated[Optional[str], Form()] = None,
    app_secret: Annotated[Optional[str], Form()] = None,
    folder_path: Annotated[Optional[str], Form()] = None,
    db: Session = Depends(get_db),
):
    """
    Save Dropbox settings to database (primary) and .env file (best-effort).
    """
    try:
        user = request.session.get("user", {}) if hasattr(request, "session") else {}
        changed_by = (
            user.get("preferred_username") or user.get("username") or user.get("email") or user.get("id") or "wizard"
        )

        # Update settings in memory
        if refresh_token:
            settings.dropbox_refresh_token = refresh_token
        if app_key:
            settings.dropbox_app_key = app_key
        if app_secret:
            settings.dropbox_app_secret = app_secret
        if folder_path:
            settings.dropbox_folder = folder_path

        # Persist to database (primary storage)
        if refresh_token:
            save_setting_to_db(db, "dropbox_refresh_token", refresh_token, changed_by=changed_by)
        if app_key:
            save_setting_to_db(db, "dropbox_app_key", app_key, changed_by=changed_by)
        if app_secret:
            save_setting_to_db(db, "dropbox_app_secret", app_secret, changed_by=changed_by)
        if folder_path:
            save_setting_to_db(db, "dropbox_folder", folder_path, changed_by=changed_by)

        # Best-effort .env file write
        try:
            env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
            dropbox_settings = {"DROPBOX_REFRESH_TOKEN": refresh_token}
            if app_key:
                dropbox_settings["DROPBOX_APP_KEY"] = app_key
            if app_secret:
                dropbox_settings["DROPBOX_APP_SECRET"] = app_secret
            if folder_path:
                dropbox_settings["DROPBOX_FOLDER"] = folder_path

            if not update_env_file(env_path, dropbox_settings):
                logger.info("Continuing with in-memory update despite .env file update failure or skip")
        except Exception as env_err:
            logger.warning(f"Failed to write .env file (non-fatal): {env_err}")

        notify_settings_updated()

        logger.info("Successfully saved Dropbox settings")
        return {"status": "success", "message": "Dropbox settings have been saved"}

    except Exception as e:
        logger.exception(f"Unexpected error saving Dropbox settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save Dropbox settings: {str(e)}",
        )
