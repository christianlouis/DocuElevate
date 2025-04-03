"""
Dropbox API endpoints
"""
from fastapi import APIRouter, Request, HTTPException, status, Form
import logging
import os
import requests

from app.auth import require_login
from app.config import settings

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
    try:
        logger.info("Starting Dropbox token exchange process")
        
        # Prepare the token request
        token_url = "https://api.dropboxapi.com/oauth2/token"
        
        payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }
        
        # Log request details (excluding secret)
        safe_payload = payload.copy()
        safe_payload['client_secret'] = '[REDACTED]' 
        safe_payload['code'] = f"{code[:5]}...{code[-5:]}" if len(code) > 10 else '[REDACTED]'
        logger.info(f"Token exchange request payload: {safe_payload}")
        
        # Make the token request
        logger.info("Sending POST request to Dropbox for token exchange")
        response = requests.post(token_url, data=payload)
        
        # Check if the request was successful
        logger.info(f"Token exchange response status: {response.status_code}")
        
        if response.status_code != 200:
            # Log the error response for debugging
            try:
                error_json = response.json()
                logger.error(f"Token exchange failed with status {response.status_code}: {error_json}")
                error_detail = error_json
            except Exception as json_err:
                logger.error(f"Failed to parse error response as JSON: {str(json_err)}")
                logger.error(f"Raw response content: {response.content[:500]}")  # Limit log size
                error_detail = {"error": "Unknown error", "raw_content_snippet": str(response.content[:100])}
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Token exchange failed: {error_detail}"
            )
            
        # Return the token response
        token_data = response.json()
        
        # Validate the token response
        if "refresh_token" not in token_data:
            logger.error(f"Dropbox returned success but no refresh token found in response: {token_data.keys()}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Dropbox OAuth server returned success but no refresh token was included"
            )
        
        # Calculate token length for logging
        refresh_token_length = len(token_data.get("refresh_token", ""))
        access_token_length = len(token_data.get("access_token", ""))
        
        logger.info(f"Successfully exchanged authorization code for Dropbox tokens. "
                   f"Refresh token length: {refresh_token_length}, "
                   f"Access token length: {access_token_length}")
        
        # Return just what's needed by the frontend
        return {
            "refresh_token": token_data["refresh_token"],
            "access_token": token_data["access_token"],
            "expires_in": token_data.get("expires_in", 14400)
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as they already have appropriate status codes
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during Dropbox token exchange: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to exchange token: {str(e)}"
        )

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
    Test if the configured Dropbox refresh token is valid.
    """
    try:
        from app.tasks.upload_to_dropbox import get_dropbox_client
        
        logger.info("Testing Dropbox token validity")
        if not settings.dropbox_refresh_token:
            logger.warning("No Dropbox refresh token configured")
            return {
                "status": "error", 
                "message": "No Dropbox refresh token is configured"
            }
        
        # Check if app key and app secret are configured
        if not settings.dropbox_app_key or not settings.dropbox_app_secret:
            logger.warning("Dropbox app key or app secret is missing")
            return {
                "status": "error",
                "message": "Dropbox app key or app secret is missing",
                "missing_config": True
            }
        
        # Try to get a client using the configured refresh token
        try:
            dbx = get_dropbox_client()
            # Test connection by getting account info
            account = dbx.users_get_current_account()
            logger.info(f"Successfully connected to Dropbox as {account.name.display_name}")
            
            return {
                "status": "success",
                "message": f"Token is valid! Connected as {account.name.display_name}",
                "account": account.name.display_name,
                "email": account.email
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Dropbox token test failed: {error_msg}")
            
            # Determine if this is an authentication error
            is_auth_error = "auth" in error_msg.lower() or "invalid" in error_msg.lower()
            
            return {
                "status": "error",
                "message": f"Token validation failed: {error_msg}",
                "is_auth_error": is_auth_error,
                "needs_reauth": is_auth_error
            }
    
    except Exception as e:
        logger.exception("Unexpected error testing Dropbox token")
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}"
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
