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
from app.utils.config_validator import get_provider_status
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
    # Check for OAuth configuration
    if getattr(settings, 'google_drive_use_oauth', False):
        return (settings.google_drive_client_id and 
                settings.google_drive_client_secret and 
                settings.google_drive_refresh_token and
                settings.google_drive_folder_id)
    # Or check for service account configuration
    else:
        return (settings.google_drive_credentials_json and
                settings.google_drive_folder_id)

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
            settings.onedrive_refresh_token)

def _should_upload_to_s3():
    return (settings.s3_bucket_name and 
            settings.aws_access_key_id and 
            settings.aws_secret_access_key)

def get_configured_services_from_validator():
    """
    Use the config validator to determine which services are configured properly.
    Returns a dictionary with service names as keys and boolean values indicating
    whether they're properly configured.
    """
    providers = get_provider_status()
    
    service_map = {
        "Dropbox": "dropbox",
        "NextCloud": "nextcloud",
        "Paperless-ngx": "paperless",
        "Google Drive": "google_drive",
        "WebDAV": "webdav",
        "FTP Storage": "ftp",
        "SFTP Storage": "sftp",
        "Email": "email",
        "OneDrive": "onedrive",
        "S3 Storage": "s3"
    }
    
    result = {}
    for provider_name, internal_name in service_map.items():
        if provider_name in providers:
            result[internal_name] = providers[provider_name].get('configured', False)
    
    return result

@celery.task(base=BaseTaskWithRetry)
def send_to_all_destinations(file_path: str, use_validator=True):
    """
    Distribute a file to all configured storage destinations.
    
    Args:
        file_path: Path to the file to distribute
        use_validator: Whether to use the config validator to determine enabled services
                       (if False, falls back to individual checks)
    """
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
    
    # Optionally get configuration status from validator
    configured_services = {}
    if use_validator:
        try:
            configured_services = get_configured_services_from_validator()
            logger.info(f"Configured services according to validator: {configured_services}")
        except Exception as e:
            logger.warning(f"Failed to get configuration from validator: {str(e)}")
            use_validator = False
    
    # Process each service
    for service in services:
        service_name = service["name"]
        
        # Determine if service is configured
        is_configured = False
        if use_validator and service_name in configured_services:
            is_configured = configured_services[service_name]
            logger.debug(f"{service_name} configuration from validator: {is_configured}")
        else:
            try:
                is_configured = service["should_upload"]()
                logger.debug(f"{service_name} configuration from function: {is_configured}")
            except Exception as e:
                logger.error(f"Error checking configuration for {service_name}: {str(e)}")
                is_configured = False
        
        # Queue the upload task if service is configured
        if is_configured:
            logger.info(f"Queueing {file_path} for {service_name} upload")
            try:
                task = service["upload_func"].delay(file_path)
                results[f"{service_name}_task_id"] = task.id
            except Exception as e:
                logger.error(f"Failed to queue {service_name} task: {str(e)}")
                results[f"{service_name}_error"] = str(e)
    
    return {
        "status": "Queued",
        "file_path": file_path,
        "tasks": results
    }
