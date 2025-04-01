#!/usr/bin/env python3

import os
import logging
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.upload_to_dropbox import upload_to_dropbox
from app.tasks.upload_to_nextcloud import upload_to_nextcloud
from app.tasks.upload_to_paperless import upload_to_paperless
from app.tasks.upload_to_google_drive import upload_to_google_drive
from app.tasks.upload_to_webdav import upload_to_webdav
from app.tasks.upload_to_ftp import upload_to_ftp
from app.tasks.upload_to_sftp import upload_to_sftp
from app.tasks.upload_to_email import upload_to_email
from app.tasks.upload_to_onedrive import upload_to_onedrive
from app.tasks.upload_to_s3 import upload_to_s3
from app.celery_app import celery

logger = logging.getLogger(__name__)

def _should_upload_to_dropbox():
    return (settings.dropbox_app_key and 
            settings.dropbox_app_secret and 
            settings.dropbox_refresh_token)

def _should_upload_to_nextcloud():
    return (settings.nextcloud_upload_url and 
            settings.nextcloud_username and 
            settings.nextcloud_password)

def _should_upload_to_paperless():
    return (settings.paperless_ngx_api_token and 
            settings.paperless_host)

def _should_upload_to_google_drive():
    return settings.google_drive_credentials_json

def _should_upload_to_webdav():
    return (settings.webdav_url and 
            settings.webdav_username and 
            settings.webdav_password)

def _should_upload_to_ftp():
    return (settings.ftp_host and 
            settings.ftp_username and 
            settings.ftp_password)

def _should_upload_to_sftp():
    return (settings.sftp_host and 
            settings.sftp_username and 
            (settings.sftp_password or settings.sftp_private_key))

def _should_upload_to_email():
    return (settings.email_host and 
            settings.email_username and 
            settings.email_password and 
            settings.email_default_recipient)

def _should_upload_to_onedrive():
    return (settings.onedrive_client_id and 
            settings.onedrive_client_secret and 
            (settings.onedrive_refresh_token or 
             (settings.onedrive_tenant_id and settings.onedrive_tenant_id != "common")))

def _should_upload_to_s3():
    return (settings.s3_bucket_name and 
            settings.aws_access_key_id and 
            settings.aws_secret_access_key)

@celery.task(base=BaseTaskWithRetry)
def send_to_all_destinations(file_path: str):
    """Distribute a file to all configured storage destinations."""
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    logger.info(f"Sending {file_path} to all configured destinations")
    results = {}
    
    # Define service configurations
    services = [
        {
            "name": "dropbox",
            "should_upload": _should_upload_to_dropbox,
            "upload_func": upload_to_dropbox,
        },
        {
            "name": "nextcloud",
            "should_upload": _should_upload_to_nextcloud,
            "upload_func": upload_to_nextcloud,
        },
        {
            "name": "paperless",
            "should_upload": _should_upload_to_paperless,
            "upload_func": upload_to_paperless,
        },
        {
            "name": "google_drive",
            "should_upload": _should_upload_to_google_drive,
            "upload_func": upload_to_google_drive,
        },
        {
            "name": "webdav",
            "should_upload": _should_upload_to_webdav,
            "upload_func": upload_to_webdav,
        },
        {
            "name": "ftp",
            "should_upload": _should_upload_to_ftp,
            "upload_func": upload_to_ftp,
        },
        {
            "name": "sftp",
            "should_upload": _should_upload_to_sftp,
            "upload_func": upload_to_sftp,
        },
        {
            "name": "email",
            "should_upload": _should_upload_to_email,
            "upload_func": upload_to_email,
        },
        {
            "name": "onedrive",
            "should_upload": _should_upload_to_onedrive,
            "upload_func": upload_to_onedrive,
        },
        {
            "name": "s3",
            "should_upload": _should_upload_to_s3,
            "upload_func": upload_to_s3,
        },
    ]
    
    # Process each service
    for service in services:
        if service["should_upload"]():
            logger.info(f"Queueing {file_path} for {service['name']} upload")
            task = service["upload_func"].delay(file_path)
            results[f"{service['name']}_task_id"] = task.id
    
    return {
        "status": "Queued",
        "file_path": file_path,
        "tasks": results
    }
