"""
OneDrive API endpoints
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

@router.post("/onedrive/exchange-token")
@require_login
async def exchange_onedrive_token(
    request: Request,
    client_id: str = Form(...),
    client_secret: str = Form(...),
    redirect_uri: str = Form(...),
    code: str = Form(...),
    tenant_id: str = Form(...)
):
    """
    Exchange an authorization code for a refresh token.
    This is done on the server to avoid exposing client secret in the browser.
    """
    try:
        logger.info(f"Starting OneDrive token exchange process with tenant_id: {tenant_id}")
        
        # Prepare the token request
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        logger.info(f"Using token URL: {token_url}")
        
        payload = {
            'client_id': client_id,
            'scope': 'https://graph.microsoft.com/.default offline_access',
            'code': code,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
            'client_secret': client_secret
        }
        
        # Log request details (excluding secret)
        safe_payload = payload.copy()
        safe_payload['client_secret'] = '[REDACTED]' 
        safe_payload['code'] = f"{code[:5]}...{code[-5:]}" if len(code) > 10 else '[REDACTED]'
        logger.info(f"Token exchange request payload: {safe_payload}")
        
        # Make the token request
        logger.info("Sending POST request to Microsoft for token exchange")
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
            logger.error(f"Microsoft returned success but no refresh token found in response: {token_data.keys()}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Microsoft OAuth server returned success but no refresh token was included"
            )
        
        # Calculate token length for logging
        refresh_token_length = len(token_data.get("refresh_token", ""))
        access_token_length = len(token_data.get("access_token", ""))
        
        logger.info(f"Successfully exchanged authorization code for OneDrive tokens. "
                   f"Refresh token length: {refresh_token_length}, "
                   f"Access token length: {access_token_length}")
        
        # Return just what's needed by the frontend
        return {
            "refresh_token": token_data["refresh_token"],
            "expires_in": token_data.get("expires_in", 3600)
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as they already have appropriate status codes
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during OneDrive token exchange: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to exchange token: {str(e)}"
        )

@router.get("/onedrive/test-token")
@require_login
async def test_onedrive_token(request: Request):
    """
    Test if the configured OneDrive refresh token is valid.
    Provides detailed error information if token is invalid.
    """
    try:
        from app.tasks.upload_to_onedrive import get_onedrive_token
        
        logger.info("Testing OneDrive token validity")
        if not settings.onedrive_refresh_token:
            logger.warning("No OneDrive refresh token configured")
            return {
                "status": "error", 
                "message": "No OneDrive refresh token is configured"
            }
        
        # Check if client ID and client secret are configured
        if not settings.onedrive_client_id or not settings.onedrive_client_secret:
            logger.warning("OneDrive client ID or client secret is missing")
            return {
                "status": "error",
                "message": "OneDrive client ID or client secret is missing",
                "missing_config": True
            }
        
        # Try to get an access token using the configured refresh token
        try:
            access_token = get_onedrive_token()
            
            # If we got here, token is valid
            logger.info("OneDrive token is valid")
            return {
                "status": "success",
                "message": "OneDrive token is valid",
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"OneDrive token test failed: {error_msg}")
            
            # Determine if this is an invalid_grant error (expired token)
            is_expired = "invalid_grant" in error_msg.lower()
            
            return {
                "status": "error",
                "message": f"Token validation failed: {error_msg}",
                "is_expired": is_expired,
                "needs_reauth": True
            }
    
    except Exception as e:
        logger.exception("Unexpected error testing OneDrive token")
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}"
        }

@router.post("/onedrive/save-settings")
@require_login
async def save_onedrive_settings(
    request: Request,
    client_id: str = Form(None),
    client_secret: str = Form(None),
    refresh_token: str = Form(...),
    tenant_id: str = Form("common"),
    folder_path: str = Form(None)
):
    """
    Save OneDrive settings to the .env file
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
            
        logger.info(f"Updating OneDrive settings in {env_path}")
        
        # Read the current .env file
        with open(env_path, "r") as f:
            env_lines = f.readlines()
            
        # Define settings to update
        onedrive_settings = {
            "ONEDRIVE_REFRESH_TOKEN": refresh_token,
        }
        
        # Only update these if provided
        if client_id:
            onedrive_settings["ONEDRIVE_CLIENT_ID"] = client_id
        if client_secret:
            onedrive_settings["ONEDRIVE_CLIENT_SECRET"] = client_secret
        if tenant_id:
            onedrive_settings["ONEDRIVE_TENANT_ID"] = tenant_id
        if folder_path:
            onedrive_settings["ONEDRIVE_FOLDER_PATH"] = folder_path
            
        # Process each line and update or add settings
        updated = set()
        new_env_lines = []
        for line in env_lines:
            line = line.rstrip()
            is_updated = False
            for key, value in onedrive_settings.items():
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
        for key, value in onedrive_settings.items():
            if key not in updated:
                new_env_lines.append(f"{key}={value}")
                
        # Write the updated .env file
        with open(env_path, "w") as f:
            f.write("\n".join(new_env_lines) + "\n")
            
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
            
        logger.info("Successfully updated OneDrive settings")
        
        return {
            "status": "success",
            "message": "OneDrive settings have been saved"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error saving OneDrive settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save OneDrive settings: {str(e)}"
        )

@router.post("/onedrive/update-settings")
@require_login
async def update_onedrive_settings(
    request: Request,
    client_id: str = Form(None),
    client_secret: str = Form(None),
    refresh_token: str = Form(...),
    tenant_id: str = Form("common"),
    folder_path: str = Form(None)
):
    """
    Update OneDrive settings in memory (without modifying .env file)
    """
    try:
        logger.info("Updating OneDrive settings in memory")
        
        # Update settings in memory
        if refresh_token:
            settings.onedrive_refresh_token = refresh_token
            logger.info("Updated ONEDRIVE_REFRESH_TOKEN in memory")
            
        if client_id:
            settings.onedrive_client_id = client_id
            logger.info("Updated ONEDRIVE_CLIENT_ID in memory")
            
        if client_secret:
            settings.onedrive_client_secret = client_secret
            logger.info("Updated ONEDRIVE_CLIENT_SECRET in memory")
            
        if tenant_id:
            settings.onedrive_tenant_id = tenant_id
            logger.info("Updated ONEDRIVE_TENANT_ID in memory")
            
        if folder_path:
            settings.onedrive_folder_path = folder_path
            logger.info("Updated ONEDRIVE_FOLDER_PATH in memory")
        
        # Test the token to make sure it works
        try:
            from app.tasks.upload_to_onedrive import get_onedrive_token
            access_token = get_onedrive_token()
            logger.info("Successfully tested OneDrive token")
        except Exception as e:
            logger.error(f"Token test failed after updating settings: {str(e)}")
            return {
                "status": "warning",
                "message": "Settings updated but token test failed: " + str(e)
            }
            
        return {
            "status": "success",
            "message": "OneDrive settings have been updated in memory"
        }
        
    except Exception as e:
        logger.exception(f"Unexpected error updating OneDrive settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update OneDrive settings: {str(e)}"
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
            "folder_path": settings.onedrive_folder_path or "Documents/Uploads"
        }
        
        # Generate environment variable format
        env_format = "\n".join([
            f"ONEDRIVE_CLIENT_ID={config['client_id']}",
            f"ONEDRIVE_CLIENT_SECRET={config['client_secret']}",
            f"ONEDRIVE_TENANT_ID={config['tenant_id']}",
            f"ONEDRIVE_REFRESH_TOKEN={config['refresh_token']}",
            f"ONEDRIVE_FOLDER_PATH={config['folder_path']}"
        ])
        
        return {
            "status": "success",
            "config": config,
            "env_format": env_format
        }
    except Exception as e:
        logger.exception("Error getting OneDrive configuration")
        return {
            "status": "error",
            "message": str(e)
        }
