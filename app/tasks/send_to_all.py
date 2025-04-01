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

@celery.task(base=BaseTaskWithRetry)
def send_to_all_destinations(file_path: str):
    """Distribute a file to all configured storage destinations."""
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    logger.info(f"Sending {file_path} to all configured destinations")
    results = {}
    
    # Send to Dropbox if configured
    if settings.dropbox_app_key and settings.dropbox_app_secret and settings.dropbox_refresh_token:
        logger.info(f"Queueing {file_path} for Dropbox upload")
        task = upload_to_dropbox.delay(file_path)
        results["dropbox_task_id"] = task.id
    
    # Send to Nextcloud if configured
    if settings.nextcloud_upload_url and settings.nextcloud_username and settings.nextcloud_password:
        logger.info(f"Queueing {file_path} for Nextcloud upload")
        task = upload_to_nextcloud.delay(file_path)
        results["nextcloud_task_id"] = task.id
    
    # Send to Paperless if configured
    if settings.paperless_ngx_api_token and settings.paperless_host:
        logger.info(f"Queueing {file_path} for Paperless upload")
        task = upload_to_paperless.delay(file_path)
        results["paperless_task_id"] = task.id
    
    # Send to Google Drive if configured
    if settings.google_drive_credentials_json:
        logger.info(f"Queueing {file_path} for Google Drive upload")
        task = upload_to_google_drive.delay(file_path)
        results["google_drive_task_id"] = task.id

    # Send to WebDAV if configured
    if settings.webdav_url and settings.webdav_username and settings.webdav_password:
        logger.info(f"Queueing {file_path} for WebDAV upload")
        task = upload_to_webdav.delay(file_path)
        results["webdav_task_id"] = task.id
        
    # Send to FTP if configured
    if settings.ftp_host and settings.ftp_username and settings.ftp_password:
        logger.info(f"Queueing {file_path} for FTP upload")
        task = upload_to_ftp.delay(file_path)
        results["ftp_task_id"] = task.id
        
    # Send to SFTP if configured
    if settings.sftp_host and settings.sftp_username and (settings.sftp_password or settings.sftp_private_key):
        logger.info(f"Queueing {file_path} for SFTP upload")
        task = upload_to_sftp.delay(file_path)
        results["sftp_task_id"] = task.id

    # Send via email if configured
    if settings.email_host and settings.email_username and settings.email_password and settings.email_default_recipient:
        logger.info(f"Queueing {file_path} for email delivery")
        task = upload_to_email.delay(file_path)
        results["email_task_id"] = task.id
        
    # Send to OneDrive if configured
    if settings.onedrive_client_id and settings.onedrive_client_secret and (
        settings.onedrive_refresh_token or 
        (settings.onedrive_tenant_id and settings.onedrive_tenant_id != "common")
    ):
        logger.info(f"Queueing {file_path} for OneDrive upload")
        task = upload_to_onedrive.delay(file_path)
        results["onedrive_task_id"] = task.id
        
    # Send to Amazon S3 if configured
    if settings.s3_bucket_name and settings.aws_access_key_id and settings.aws_secret_access_key:
        logger.info(f"Queueing {file_path} for S3 upload")
        task = upload_to_s3.delay(file_path)
        results["s3_task_id"] = task.id
    
    return {
        "status": "Queued",
        "file_path": file_path,
        "tasks": results
    }
