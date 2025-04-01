#!/usr/bin/env python3

import os
import time
import logging
import requests
import msal
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.celery_app import celery

logger = logging.getLogger(__name__)

def get_onedrive_token():
    """
    Get an access token for Microsoft Graph API using the appropriate flow.
    For personal accounts, uses refresh token flow.
    For organizational accounts, uses client credentials flow if refresh token isn't provided.
    """
    # Check for required settings
    if not settings.onedrive_client_id or not settings.onedrive_client_secret:
        raise ValueError("OneDrive client ID and client secret must be configured")
    
    # Use refresh token flow (works for both personal and org accounts)
    if settings.onedrive_refresh_token:
        # Use MSAL to get token from refresh token
        app = msal.PublicClientApplication(settings.onedrive_client_id)
        
        # Request new token using refresh token
        token_response = app.acquire_token_by_refresh_token(
            refresh_token=settings.onedrive_refresh_token,
            scopes=["https://graph.microsoft.com/Files.ReadWrite"]
        )
        
        if "access_token" not in token_response:
            error = token_response.get("error", "")
            error_desc = token_response.get("error_description", "Unknown error")
            raise ValueError(f"Failed to get access token: {error} - {error_desc}")
            
        return token_response["access_token"]
    
    # No refresh token - try client credentials (only works for org accounts)
    elif settings.onedrive_tenant_id and settings.onedrive_tenant_id != "common":
        authority = f"https://login.microsoftonline.com/{settings.onedrive_tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id=settings.onedrive_client_id,
            client_credential=settings.onedrive_client_secret,
            authority=authority
        )
        
        # Acquire token for application
        token_response = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        
        if "access_token" not in token_response:
            error = token_response.get("error", "")
            error_desc = token_response.get("error_description", "Unknown error")
            raise ValueError(f"Failed to get access token: {error} - {error_desc}")
            
        return token_response["access_token"]
    
    else:
        raise ValueError("For personal Microsoft accounts, ONEDRIVE_REFRESH_TOKEN must be configured")

def create_upload_session(filename, folder_path, access_token):
    """Creates an upload session for large files in Microsoft Graph API."""
    # Construct the API endpoint
    base_url = "https://graph.microsoft.com/v1.0/me/drive"
    
    # Format the folder path correctly
    if folder_path:
        # Remove leading/trailing slashes
        folder_path = folder_path.strip('/')
        # Replace spaces with %20
        folder_path = folder_path.replace(' ', '%20')
        item_path = f"/root:/{folder_path}/{filename}:/createUploadSession"
    else:
        item_path = f"/root:/{filename}:/createUploadSession"
    
    url = f"{base_url}{item_path}"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(url, headers=headers)
    
    if response.status_code == 200:
        return response.json().get("uploadUrl")
    else:
        error_msg = f"Failed to create upload session: {response.status_code} - {response.text}"
        logger.error(error_msg)
        raise Exception(error_msg)

def upload_large_file(file_path, upload_url):
    """
    Upload a large file to OneDrive using the upload session URL.
    Uses chunked upload for reliability.
    """
    # Get file size
    file_size = os.path.getsize(file_path)
    
    # Define chunk size (10 MB)
    chunk_size = 10 * 1024 * 1024
    
    # Open and read file in chunks
    with open(file_path, 'rb') as f:
        # Process file in chunks
        chunk_number = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
                
            # Get the position in the file
            chunk_start = chunk_number * chunk_size
            chunk_end = chunk_start + len(chunk) - 1
            
            # Prepare content range header
            content_range = f"bytes {chunk_start}-{chunk_end}/{file_size}"
            
            # Upload chunk
            headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": content_range
            }
            
            # Try to upload chunk with retries
            max_retries = 3
            retry_delay = 2  # seconds
            
            for attempt in range(max_retries):
                try:
                    response = requests.put(
                        upload_url,
                        headers=headers,
                        data=chunk
                    )
                    
                    # Check if successful
                    if response.status_code in (201, 202):
                        # 201 = Created (final chunk), 202 = Accepted (more chunks coming)
                        break
                    else:
                        logger.warning(f"Chunk upload failed (attempt {attempt+1}): {response.status_code}")
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay * (attempt + 1))
                except Exception as e:
                    logger.warning(f"Chunk upload error (attempt {attempt+1}): {str(e)}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))
            
            if response.status_code not in (201, 202):
                raise Exception(f"Failed to upload chunk after {max_retries} attempts: {response.status_code} - {response.text}")
            
            # Move to next chunk
            chunk_number += 1
            
    # If we get here, all chunks were uploaded successfully
    # The last response should contain the file metadata
    return response.json()

@celery.task(base=BaseTaskWithRetry)
def upload_to_onedrive(file_path: str):
    """Uploads a file to OneDrive in the configured folder."""
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Extract filename
    filename = os.path.basename(file_path)

    # Check if OneDrive settings are configured
    if not settings.onedrive_client_id:
        error_msg = "OneDrive client ID is not configured"
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        # Get access token
        access_token = get_onedrive_token()
        
        # Create upload session
        upload_url = create_upload_session(filename, settings.onedrive_folder_path, access_token)
        
        # Upload the file
        result = upload_large_file(file_path, upload_url)
        
        # Log success
        web_url = result.get("webUrl", "Not available")
        logger.info(f"Successfully uploaded {filename} to OneDrive at path {settings.onedrive_folder_path}")
        logger.info(f"File accessible at: {web_url}")
        
        return {
            "status": "Completed",
            "file_path": file_path,
            "onedrive_path": f"{settings.onedrive_folder_path}/{filename}",
            "web_url": web_url
        }
        
    except Exception as e:
        error_msg = f"Failed to upload {filename} to OneDrive: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
