#!/usr/bin/env python3

import os
import logging
import requests
import dropbox
from dropbox.exceptions import ApiError, AuthError
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.celery_app import celery
from app.utils.filename_utils import get_unique_filename, sanitize_filename, extract_remote_path

logger = logging.getLogger(__name__)

def _validate_dropbox_settings():
    """Validate that all required Dropbox settings are available."""
    missing = []
    
    if not hasattr(settings, 'dropbox_refresh_token') or not settings.dropbox_refresh_token:
        missing.append("refresh token")
    
    if not hasattr(settings, 'dropbox_app_key') or not settings.dropbox_app_key:
        missing.append("app key")
    
    if not hasattr(settings, 'dropbox_app_secret') or not settings.dropbox_app_secret:
        missing.append("app secret")
    
    if missing:
        logger.error(f"Cannot refresh Dropbox token: Missing {', '.join(missing)}")
        return False
    
    return True

def get_dropbox_access_token():
    """Refresh the Dropbox access token using the stored refresh token from ENV."""
    
    # Check if needed settings are available
    if not _validate_dropbox_settings():
        return None

    token_url = "https://api.dropbox.com/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "refresh_token",
        "refresh_token": settings.dropbox_refresh_token,
        "client_id": settings.dropbox_app_key,
        "client_secret": settings.dropbox_app_secret,
    }

    response = requests.post(token_url, headers=headers, data=data)

    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        error_msg = f"Failed to refresh Dropbox token: {response.status_code} - {response.text}"
        logger.error(error_msg)
        raise Exception(error_msg)

@celery.task(base=BaseTaskWithRetry)
def upload_to_dropbox(file_path: str):
    """
    Upload a file to Dropbox.
    """
    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)
    
    # Check if Dropbox is properly configured
    if not (hasattr(settings, 'dropbox_app_key') and settings.dropbox_app_key and
            hasattr(settings, 'dropbox_app_secret') and settings.dropbox_app_secret and
            hasattr(settings, 'dropbox_refresh_token') and settings.dropbox_refresh_token):
        logger.info("Dropbox upload skipped: Missing configuration")
        return {"status": "Skipped", "reason": "Dropbox settings not configured"}
    
    filename = os.path.basename(file_path)
    
    try:
        # Get access token from refresh token
        access_token = get_dropbox_access_token()
        if not access_token:
            return {"status": "Failed", "reason": "Could not obtain access token"}
            
        dbx = dropbox.Dropbox(access_token)
        
        # Calculate remote path based on local file structure
        remote_base = settings.dropbox_folder or ""
        remote_path = extract_remote_path(file_path, settings.workdir, remote_base)
        
        # Function to check if file exists in Dropbox
        def check_exists_in_dropbox(path):
            try:
                dbx.files_get_metadata(path)
                return True
            except ApiError as e:
                if e.error.is_path() and e.error.get_path().is_not_found():
                    return False
                raise
        
        # Get a unique path in case of collision
        remote_full_path = f"/{remote_path}"  # Dropbox paths should start with /
        remote_full_path = remote_full_path.replace('//', '/')  # Clean double slashes
        
        # Check for potential file collision and get a unique name if needed
        dropbox_path = get_unique_filename(remote_full_path, check_exists_in_dropbox)
        
        # Upload the file
        logger.info(f"Uploading {filename} to Dropbox at {dropbox_path}")
        with open(file_path, 'rb') as file_data:
            # Use files_upload_session for large files to avoid timeouts
            file_size = os.path.getsize(file_path)
            if file_size > 10 * 1024 * 1024:  # 10 MB threshold for chunked upload
                cursor = None
                chunk_size = 4 * 1024 * 1024  # 4 MB chunks
                file_data.seek(0)
                
                # Start upload session
                session_start = dbx.files_upload_session_start(file_data.read(chunk_size))
                cursor = dropbox.files.UploadSessionCursor(session_start.session_id, file_data.tell())
                
                # Upload chunks until we reach the end
                while file_data.tell() < file_size:
                    if (file_size - file_data.tell()) <= chunk_size:
                        # Last chunk
                        dbx.files_upload_session_finish(
                            file_data.read(chunk_size),
                            cursor,
                            dropbox.files.CommitInfo(path=dropbox_path, mode=dropbox.files.WriteMode.overwrite)
                        )
                    else:
                        # More chunks to upload
                        dbx.files_upload_session_append_v2(file_data.read(chunk_size), cursor)
                        cursor.offset = file_data.tell()
            else:
                # Small file, direct upload
                file_data.seek(0)
                dbx.files_upload(
                    file_data.read(),
                    dropbox_path,
                    mode=dropbox.files.WriteMode.overwrite
                )
        
        logger.info(f"Successfully uploaded {filename} to Dropbox at {dropbox_path}")
        return {
            "status": "Completed",
            "file_path": file_path,
            "dropbox_path": dropbox_path
        }
    
    except AuthError:
        error_msg = f"[ERROR] Authentication failed while uploading {filename} to Dropbox. Check token."
        logger.error(error_msg)
        raise Exception(error_msg)
    except ApiError as e:
        error_msg = f"[ERROR] Failed to upload {filename} to Dropbox: {e}"
        logger.error(error_msg)
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"[ERROR] Unexpected error uploading {filename} to Dropbox: {e}"
        logger.error(error_msg)
        raise Exception(error_msg)
