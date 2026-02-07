#!/usr/bin/env python3

import os
import logging
import requests
from requests.auth import HTTPBasicAuth
from app.config import settings
from app.celery_app import celery
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils.filename_utils import get_unique_filename, sanitize_filename, extract_remote_path
from app.utils import log_task_progress
from app.database import SessionLocal
from app.models import FileRecord

logger = logging.getLogger(__name__)

@celery.task(base=BaseTaskWithRetry, bind=True)
def upload_to_nextcloud(self, file_path: str, file_id: int = None):
    """
    Upload a file to Nextcloud WebDAV.
    
    Args:
        file_path: Path to the file to upload
        file_id: Optional file ID to associate with logs
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting Nextcloud upload: {file_path}")
    log_task_progress(task_id, "upload_to_nextcloud", "in_progress", f"Uploading to Nextcloud: {os.path.basename(file_path)}", file_id=file_id)
    
    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_nextcloud", "failure", error_msg, file_id=file_id)
        raise FileNotFoundError(error_msg)
    
    # For Nextcloud, we need to check for 'nextcloud_upload_url' instead of 'nextcloud_url'
    # This is what's shown in your env view
    if not (getattr(settings, 'nextcloud_upload_url', None) and 
            getattr(settings, 'nextcloud_username', None) and 
            getattr(settings, 'nextcloud_password', None)):
        logger.info(f"[{task_id}] Nextcloud upload skipped: Missing configuration")
        log_task_progress(task_id, "upload_to_nextcloud", "success", "Skipped: Not configured", file_id=file_id)
        return {"status": "Skipped", "reason": "Nextcloud settings not configured"}
    
    filename = os.path.basename(file_path)
    sanitized_filename = sanitize_filename(filename)
    
    try:
        # Prepare WebDAV URL - use nextcloud_upload_url instead of nextcloud_url
        webdav_url = settings.nextcloud_upload_url
        if not webdav_url.endswith('/'):
            webdav_url += '/'
            
        # Calculate remote path based on local file structure
        remote_base = getattr(settings, 'nextcloud_folder', '') or ""
        remote_path = extract_remote_path(file_path, settings.workdir, remote_base)
        full_url = f"{webdav_url}/{remote_path}"
        
        # Remove any double slashes (except in http://)
        full_url = full_url.replace('://', '$PLACEHOLDER$')
        while '//' in full_url:
            full_url = full_url.replace('//', '/')
        full_url = full_url.replace('$PLACEHOLDER$', '://')
        
        # Function to check if file exists in Nextcloud
        def check_exists_in_nextcloud(path):
            check_url = f"{webdav_url}{os.path.dirname(path)}"
            try:
                response = requests.request(
                    'PROPFIND',
                    check_url,
                    auth=HTTPBasicAuth(settings.nextcloud_username, settings.nextcloud_password),
                    headers={'Depth': '1'},
                    timeout=10
                )
                
                return path in response.text
            except Exception:
                # If we can't check, assume it doesn't exist
                return False
        
        # Check for potential file collision and get a unique name if needed
        remote_path = get_unique_filename(remote_path, check_exists_in_nextcloud)
        full_url = f"{webdav_url}/{remote_path}"
        
        # Fix double slashes again
        full_url = full_url.replace('://', '$PLACEHOLDER$')
        while '//' in full_url:
            full_url = full_url.replace('//', '/')
        full_url = full_url.replace('$PLACEHOLDER$', '://')
        
        # Create necessary parent folders
        parent_dirs = os.path.dirname(remote_path)
        if parent_dirs:
            current_path = ""
            for folder in parent_dirs.split('/'):
                if not folder:
                    continue
                current_path += f"{folder}/"
                mkdir_url = f"{webdav_url}/{current_path}"
                # Fix double slashes
                mkdir_url = mkdir_url.replace('://', '$PLACEHOLDER$')
                while '//' in mkdir_url:
                    mkdir_url = mkdir_url.replace('//', '/')
                mkdir_url = mkdir_url.replace('$PLACEHOLDER$', '://')
                
                requests.request(
                    'MKCOL',
                    mkdir_url,
                    auth=HTTPBasicAuth(settings.nextcloud_username, settings.nextcloud_password),
                    timeout=10
                )
        
        # Upload the file
        logger.info(f"[{task_id}] Uploading {filename} to Nextcloud at {full_url}")
        log_task_progress(task_id, "upload_file", "in_progress", f"Uploading to {remote_path}", file_id=file_id)
        with open(file_path, 'rb') as file_data:
            response = requests.put(
                full_url,
                data=file_data,
                auth=HTTPBasicAuth(settings.nextcloud_username, settings.nextcloud_password),
                headers={'Content-Type': 'application/octet-stream'},
                timeout=60  # Longer timeout for larger files
            )
        
        if response.status_code in (201, 204):  # Created or No Content
            logger.info(f"[{task_id}] Successfully uploaded {filename} to Nextcloud at {remote_path}")
            log_task_progress(task_id, "upload_to_nextcloud", "success", f"Uploaded to Nextcloud: {remote_path}", file_id=file_id)
            return {
                "status": "Completed",
                "file_path": file_path,
                "nextcloud_path": remote_path,
                "response_code": response.status_code
            }
        else:
            error_msg = f"Failed to upload {filename} to Nextcloud: {response.status_code} - {response.text}"
            logger.error(f"[{task_id}] {error_msg}")
            log_task_progress(task_id, "upload_to_nextcloud", "failure", error_msg, file_id=file_id)
            raise Exception(error_msg)
    
    except Exception as e:
        error_msg = f"Failed to upload {filename} to Nextcloud: {str(e)}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_nextcloud", "failure", error_msg, file_id=file_id)
        raise Exception(error_msg)
