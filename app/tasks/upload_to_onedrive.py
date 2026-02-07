#!/usr/bin/env python3

import os
import time
import logging
import requests
import msal
import urllib.parse
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.celery_app import celery
from app.utils import log_task_progress

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
    
    # Log more details about the configuration
    tenant = settings.onedrive_tenant_id or "common"
    logger.info(f"Using OneDrive tenant: {tenant}")
    
    # Define scopes consistently
    scopes = ["https://graph.microsoft.com/.default"]
    
    # Use refresh token flow (works for both personal and org accounts)
    if settings.onedrive_refresh_token:
        # Use MSAL's ConfidentialClientApplication instead of PublicClientApplication
        app = msal.ConfidentialClientApplication(
            client_id=settings.onedrive_client_id,
            client_credential=settings.onedrive_client_secret,
            authority=f"https://login.microsoftonline.com/{tenant}"
        )
        
        # Request new token using refresh token
        logger.info("Attempting to acquire token using refresh token")
        token_response = app.acquire_token_by_refresh_token(
            refresh_token=settings.onedrive_refresh_token,
            scopes=scopes
        )
        
        if "access_token" not in token_response:
            error = token_response.get("error", "")
            error_desc = token_response.get("error_description", "Unknown error")
            
            # Log more details about the error
            logger.error(f"Failed to get access token using refresh token")
            logger.error(f"Error code: {error}")
            logger.error(f"Error description: {error_desc}")
            
            if error == "invalid_grant":
                logger.error("The refresh token appears to be expired or revoked")
                logger.error("A new authorization flow is required to obtain a fresh token")
                
            raise ValueError(f"Failed to get access token: {error} - {error_desc}")
        
        # Check if we received a new refresh token and update it
        if "refresh_token" in token_response:
            new_refresh_token = token_response["refresh_token"]
            logger.info("Received new refresh token from Microsoft")
            
            # Update the refresh token in memory
            settings.onedrive_refresh_token = new_refresh_token
            logger.info("Updated refresh token in memory")
            
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
            scopes=scopes
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
    
    # Format the folder path correctly and properly encode for URL
    if folder_path:
        # Remove leading/trailing slashes
        folder_path = folder_path.strip('/')
        
        # URL encode the path components separately
        path_components = folder_path.split('/')
        encoded_path = '/'.join(urllib.parse.quote(component) for component in path_components)
        
        # Also encode the filename
        encoded_filename = urllib.parse.quote(filename)
        item_path = f"/root:/{encoded_path}/{encoded_filename}:/createUploadSession"
    else:
        # Just encode the filename
        encoded_filename = urllib.parse.quote(filename)
        item_path = f"/root:/{encoded_filename}:/createUploadSession"
    
    url = f"{base_url}{item_path}"
    
    # Add required request body (can be empty JSON object)
    request_body = {
        "item": {
            "@microsoft.graph.conflictBehavior": "replace"
        }
    }
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    logger.info(f"Creating upload session for {filename} at path {folder_path}")
    
    response = requests.post(url, headers=headers, json=request_body)
    
    if response.status_code == 200:
        upload_url = response.json().get("uploadUrl")
        logger.info(f"Upload session created successfully for {filename}")
        return upload_url
    else:
        error_msg = f"Failed to create upload session: {response.status_code} - {response.text}"
        logger.error(error_msg)
        logger.error(f"Request URL was: {url}")
        logger.error(f"Request headers: {headers}")
        logger.error(f"Request body: {request_body}")
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

@celery.task(base=BaseTaskWithRetry, bind=True)
def upload_to_onedrive(self, file_path: str, file_id: int = None):
    """
    Uploads a file to OneDrive in the configured folder.
    
    Args:
        file_path: Path to the file to upload
        file_id: Optional file ID to associate with logs
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting OneDrive upload: {file_path}")
    log_task_progress(
        task_id,
        "upload_to_onedrive",
        "in_progress",
        f"Uploading to OneDrive: {os.path.basename(file_path)}",
        file_id=file_id,
    )
    
    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_onedrive", "failure", error_msg, file_id=file_id)
        raise FileNotFoundError(error_msg)

    # Extract filename
    filename = os.path.basename(file_path)

    # Check if OneDrive settings are configured
    if not settings.onedrive_client_id:
        error_msg = "OneDrive client ID is not configured"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_onedrive", "failure", error_msg, file_id=file_id)
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
        logger.info(f"[{task_id}] Successfully uploaded {filename} to OneDrive at path {settings.onedrive_folder_path}")
        logger.info(f"[{task_id}] File accessible at: {web_url}")
        log_task_progress(
            task_id, "upload_to_onedrive", "success", f"Uploaded to OneDrive: {filename}", file_id=file_id
        )
        
        return {
            "status": "Completed",
            "file_path": file_path,
            "onedrive_path": f"{settings.onedrive_folder_path}/{filename}",
            "web_url": web_url
        }
        
    except Exception as e:
        error_msg = f"Failed to upload {filename} to OneDrive: {str(e)}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_onedrive", "failure", error_msg, file_id=file_id)
        raise Exception(error_msg)
