"""
Dropbox API endpoints
"""
from fastapi import APIRouter, Request, HTTPException, status, Form
import logging
import os
import requests
import json
from datetime import datetime, timedelta
from typing import Optional

from app.auth import require_login
from app.config import settings
from app.utils.oauth_helper import exchange_oauth_token

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/dropbox/exchange-token")
@require_login
async def exchange_dropbox_token(
    request: Request,
    client_id: str = Form(...),
    client_secret: str = Form(...),
    redirect_uri: str = Form(...),
    code: str = Form(...),
    folder_path: str = Form(None)
):
    """
    Exchange an authorization code for a refresh token from Dropbox.
    This is done on the server to avoid exposing client secret in the browser.
    """
    # Prepare the token request
    token_url = "https://api.dropboxapi.com/oauth2/token"
    
    payload = {
        'client_id': client_id,
        'client_secret': client_secret,
        'code': code,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    }
    
    # Use shared OAuth helper (handles secure logging and error handling)
    token_data = exchange_oauth_token(
        provider_name="Dropbox",
        token_url=token_url,
        payload=payload
    )
    
    # Return just what's needed by the frontend
    return {
        "refresh_token": token_data["refresh_token"],
        "access_token": token_data["access_token"],
        "expires_in": token_data.get("expires_in", 14400)
    }

@router.post("/dropbox/update-settings")
@require_login
async def update_dropbox_settings(
    request: Request,
    app_key: str = Form(None),
    app_secret: str = Form(None),
    refresh_token: str = Form(...),
    folder_path: str = Form(None)
):
    """
    Update Dropbox settings in memory
    """
    try:
        logger.info("Updating Dropbox settings in memory")
        
        # Update settings in memory
        if refresh_token:
            settings.dropbox_refresh_token = refresh_token
            logger.info("Updated DROPBOX_REFRESH_TOKEN in memory")
            
        if app_key:
            settings.dropbox_app_key = app_key
            logger.info("Updated DROPBOX_APP_KEY in memory")
            
        if app_secret:
            settings.dropbox_app_secret = app_secret
            logger.info("Updated DROPBOX_APP_SECRET in memory")
            
        if folder_path:
            settings.dropbox_folder = folder_path
            logger.info("Updated DROPBOX_FOLDER in memory")
        
        # Test token validity would be here, but we'll skip it for now
        
        return {
            "status": "success",
            "message": "Dropbox settings have been updated in memory"
        }
        
    except Exception as e:
        logger.exception(f"Unexpected error updating Dropbox settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update Dropbox settings: {str(e)}"
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
                "message": "Dropbox credentials are not fully configured"
            }
        
        # Check token validity by getting current account info
        headers = {"Authorization": f"Bearer {settings.dropbox_refresh_token}"}
        response = requests.post(
            "https://api.dropboxapi.com/2/users/get_current_account",
            headers=headers,
            timeout=settings.http_request_timeout
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
                "client_secret": settings.dropbox_app_secret
            }
            
            refresh_response = requests.post(refresh_url, data=refresh_data, timeout=settings.http_request_timeout)
            
            if refresh_response.status_code != 200:
                logger.error(f"Failed to refresh Dropbox token: {refresh_response.text}")
                return {
                    "status": "error",
                    "message": "Refresh token has expired or is invalid",
                    "needs_reauth": True
                }
            
            token_info = refresh_response.json()
            access_token = token_info.get("access_token")
            
            # Try again with the new access token
            headers = {"Authorization": f"Bearer {access_token}"}
            response = requests.post(
                "https://api.dropboxapi.com/2/users/get_current_account",
                headers=headers,
                timeout=settings.http_request_timeout
            )
        
        if response.status_code != 200:
            logger.error(f"Dropbox token test failed: {response.status_code} {response.text}")
            return {
                "status": "error",
                "message": f"Token validation failed with status {response.status_code}: {response.text}"
            }
        
        # Get account info
        account_info = response.json()
        account_email = account_info.get("email", "Unknown account")
        account_name = account_info.get("name", {}).get("display_name", "Unknown user")
        
        # Dropbox refresh tokens don't expire, but we should note that in our response
        token_info = {
            "expires_in_human": "Never expires (perpetual token)",
            "is_perpetual": True
        }
        
        logger.info(f"Successfully connected to Dropbox as {account_email}")
        
        return {
            "status": "success",
            "message": f"Dropbox connection successful",
            "account": account_email,
            "account_name": account_name,
            "token_info": token_info
        }
        
    except Exception as e:
        logger.exception(f"Unexpected error testing Dropbox token: {str(e)}")
        return {
            "status": "error",
            "message": f"Connection error: {str(e)}"
        }

@router.post("/dropbox/save-settings")
@require_login
async def save_dropbox_settings(
    request: Request,
    app_key: str = Form(None),
    app_secret: str = Form(None),
    refresh_token: str = Form(...),
    folder_path: str = Form(None)
):
    """
    Save Dropbox settings to the .env file
    """
    try:
        # Get the path to the .env file
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        
        if not os.path.exists(env_path):
            logger.error(f".env file not found at {env_path}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not find .env file to update"
            )
            
        logger.info(f"Updating Dropbox settings in {env_path}")
        
        # Read the current .env file
        with open(env_path, "r") as f:
            env_lines = f.readlines()
            
        # Define settings to update
        dropbox_settings = {
            "DROPBOX_REFRESH_TOKEN": refresh_token,
        }
        
        # Only update these if provided
        if app_key:
            dropbox_settings["DROPBOX_APP_KEY"] = app_key
        if app_secret:
            dropbox_settings["DROPBOX_APP_SECRET"] = app_secret
        if folder_path:
            dropbox_settings["DROPBOX_FOLDER"] = folder_path
            
        # Process each line and update or add settings
        updated = set()
        new_env_lines = []
        for line in env_lines:
            line = line.rstrip()
            is_updated = False
            for key, value in dropbox_settings.items():
                if line.startswith(f"{key}=") or line.startswith(f"# {key}="):
                    if line.startswith("# "):  # Uncomment if commented out
                        line = line[2:]
                    new_env_lines.append(f"{key}={value}")
                    updated.add(key)
                    is_updated = True
                    break
            if not is_updated:
                new_env_lines.append(line)
                
        # Add any settings that weren't updated (they weren't in the file)
        for key, value in dropbox_settings.items():
            if key not in updated:
                new_env_lines.append(f"{key}={value}")
                
        # Write the updated .env file
        with open(env_path, "w") as f:
            f.write("\n".join(new_env_lines) + "\n")
            
        # Update the settings in memory
        if refresh_token:
            settings.dropbox_refresh_token = refresh_token
        if app_key:
            settings.dropbox_app_key = app_key
        if app_secret:
            settings.dropbox_app_secret = app_secret
        if folder_path:
            settings.dropbox_folder = folder_path
            
        logger.info("Successfully updated Dropbox settings")
        
        return {
            "status": "success",
            "message": "Dropbox settings have been saved"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error saving Dropbox settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save Dropbox settings: {str(e)}"
        )
