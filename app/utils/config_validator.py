#!/usr/bin/env python3

import os
import socket
import logging
import inspect
from app.config import settings

logger = logging.getLogger(__name__)

def validate_email_config():
    """Validates email configuration settings"""
    issues = []
    
    # Check for required email settings
    if not getattr(settings, 'email_host', None):
        issues.append("EMAIL_HOST is not configured")
    if not getattr(settings, 'email_port', None):
        issues.append("EMAIL_PORT is not configured")
    
    # Test SMTP server connectivity if host is configured
    if getattr(settings, 'email_host', None) and getattr(settings, 'email_port', None):
        try:
            # Attempt to resolve the hostname
            socket.gethostbyname(settings.email_host)
        except socket.gaierror:
            issues.append(f"Cannot resolve email host: {settings.email_host}")

    # Check for authentication settings
    if not getattr(settings, 'email_username', None):
        issues.append("EMAIL_USERNAME is not configured")
    if not getattr(settings, 'email_password', None):
        issues.append("EMAIL_PASSWORD is not configured")
    
    return issues

def validate_storage_configs():
    """Validates configuration for all storage providers"""
    issues = {}
    
    # Validate Dropbox config
    dropbox_issues = []
    if not (getattr(settings, 'dropbox_app_key', None) and 
            getattr(settings, 'dropbox_app_secret', None) and 
            getattr(settings, 'dropbox_refresh_token', None)):
        dropbox_issues.append("Dropbox credentials are not fully configured")
    issues['dropbox'] = dropbox_issues
    
    # Validate Nextcloud config
    nextcloud_issues = []
    if not (getattr(settings, 'nextcloud_upload_url', None) and 
            getattr(settings, 'nextcloud_username', None) and 
            getattr(settings, 'nextcloud_password', None)):
        nextcloud_issues.append("Nextcloud credentials are not fully configured")
    issues['nextcloud'] = nextcloud_issues
    
    # Validate SFTP config
    sftp_issues = []
    if not getattr(settings, 'sftp_host', None):
        sftp_issues.append("SFTP_HOST is not configured")
    
    sftp_key_path = getattr(settings, 'sftp_private_key', None)
    if sftp_key_path and not os.path.exists(sftp_key_path):
        sftp_issues.append(f"SFTP_KEY_PATH file not found: {sftp_key_path}")
    
    if not sftp_key_path and not getattr(settings, 'sftp_password', None):
        sftp_issues.append("Neither SFTP_KEY_PATH nor SFTP_PASSWORD is configured")
    
    issues['sftp'] = sftp_issues
    
    # Validate Email sending
    email_issues = []
    if not getattr(settings, 'email_host', None):
        email_issues.append("EMAIL_HOST is not configured")
    if not getattr(settings, 'email_default_recipient', None):
        email_issues.append("EMAIL_DEFAULT_RECIPIENT is not configured")
    issues['email'] = email_issues
    
    # Validate S3
    s3_issues = []
    if not getattr(settings, 's3_bucket_name', None):
        s3_issues.append("S3_BUCKET_NAME is not configured")
    if not (getattr(settings, 'aws_access_key_id', None) and 
            getattr(settings, 'aws_secret_access_key', None)):
        s3_issues.append("AWS credentials are not configured")
    issues['s3'] = s3_issues
    
    # Validate FTP
    ftp_issues = []
    if not getattr(settings, 'ftp_host', None):
        ftp_issues.append("FTP_HOST is not configured")
    if not getattr(settings, 'ftp_username', None):
        ftp_issues.append("FTP_USERNAME is not configured")
    if not getattr(settings, 'ftp_password', None):
        ftp_issues.append("FTP_PASSWORD is not configured")
    issues['ftp'] = ftp_issues
    
    # Validate WebDAV
    webdav_issues = []
    if not getattr(settings, 'webdav_url', None):
        webdav_issues.append("WEBDAV_URL is not configured")
    if not getattr(settings, 'webdav_username', None):
        webdav_issues.append("WEBDAV_USERNAME is not configured")
    if not getattr(settings, 'webdav_password', None):
        webdav_issues.append("WEBDAV_PASSWORD is not configured")
    issues['webdav'] = webdav_issues
    
    # Validate Google Drive
    gdrive_issues = []
    if not getattr(settings, 'google_drive_credentials_json', None):
        gdrive_issues.append("GOOGLE_DRIVE_CREDENTIALS_JSON is not configured")
    if not getattr(settings, 'google_drive_folder_id', None):
        gdrive_issues.append("GOOGLE_DRIVE_FOLDER_ID is not configured")
    issues['google_drive'] = gdrive_issues
    
    # Validate Paperless
    paperless_issues = []
    if not getattr(settings, 'paperless_host', None):
        paperless_issues.append("PAPERLESS_HOST is not configured")
    if not getattr(settings, 'paperless_ngx_api_token', None):
        paperless_issues.append("PAPERLESS_NGX_API_TOKEN is not configured")
    issues['paperless'] = paperless_issues
    
    # Validate OneDrive
    onedrive_issues = []
    if not (getattr(settings, 'onedrive_client_id', None) and 
            getattr(settings, 'onedrive_client_secret', None) and
            getattr(settings, 'onedrive_refresh_token', None)):
        onedrive_issues.append("OneDrive credentials are not fully configured")
    issues['onedrive'] = onedrive_issues
    
    return issues

def get_provider_status():
    """Get the status of each provider for the dashboard"""
    providers = {
        "Email": {
            "configured": bool(getattr(settings, 'email_host', None) and 
                               getattr(settings, 'email_username', None) and
                               getattr(settings, 'email_password', None)),
            "icon": "mail",
            "url": getattr(settings, 'email_host', None) or "",
            "description": f"Send to {getattr(settings, 'email_default_recipient', 'Not configured')}"
        },
        "Dropbox": {
            "configured": bool(getattr(settings, 'dropbox_app_key', None) and 
                               getattr(settings, 'dropbox_app_secret', None) and
                               getattr(settings, 'dropbox_refresh_token', None)),
            "icon": "dropbox",
            "url": "https://dropbox.com",
            "description": f"Upload to folder: {getattr(settings, 'dropbox_folder', 'Root')}"
        },
        "Nextcloud": {
            "configured": bool(getattr(settings, 'nextcloud_upload_url', None) and
                               getattr(settings, 'nextcloud_username', None)),
            "icon": "cloud",
            "url": getattr(settings, 'nextcloud_upload_url', "").split('/remote.php')[0] if getattr(settings, 'nextcloud_upload_url', None) else "",
            "description": f"Upload to folder: {getattr(settings, 'nextcloud_folder', 'Root')}"
        },
        "SFTP": {
            "configured": bool(getattr(settings, 'sftp_host', None) and
                               getattr(settings, 'sftp_username', None) and
                               (getattr(settings, 'sftp_password', None) or getattr(settings, 'sftp_private_key', None))),
            "icon": "server",
            "url": f"sftp://{getattr(settings, 'sftp_host', '')}:{getattr(settings, 'sftp_port', 22)}",
            "description": f"Upload to {getattr(settings, 'sftp_host', 'Not configured')}:{getattr(settings, 'sftp_folder', '/')}"
        },
        "Paperless": {
            "configured": bool(getattr(settings, 'paperless_host', None) and
                               getattr(settings, 'paperless_ngx_api_token', None)),
            "icon": "file-text",
            "url": getattr(settings, 'paperless_host', ""),
            "description": "Document management system"
        },
        "S3": {
            "configured": bool(getattr(settings, 's3_bucket_name', None) and
                              getattr(settings, 'aws_access_key_id', None)),
            "icon": "database",
            "url": f"https://s3.console.aws.amazon.com/s3/buckets/{getattr(settings, 's3_bucket_name', '')}",
            "description": f"Bucket: {getattr(settings, 's3_bucket_name', 'Not configured')}"
        },
        "FTP": {
            "configured": bool(getattr(settings, 'ftp_host', None) and
                              getattr(settings, 'ftp_username', None)),
            "icon": "hard-drive",
            "url": f"ftp://{getattr(settings, 'ftp_host', '')}:{getattr(settings, 'ftp_port', 21)}",
            "description": f"Upload to {getattr(settings, 'ftp_host', 'Not configured')}:{getattr(settings, 'ftp_folder', '/')}"
        },
        "WebDAV": {
            "configured": bool(getattr(settings, 'webdav_url', None) and
                              getattr(settings, 'webdav_username', None)),
            "icon": "globe",
            "url": getattr(settings, 'webdav_url', ""),
            "description": f"Upload to {getattr(settings, 'webdav_folder', '/')}"
        },
        "Google Drive": {
            "configured": bool(getattr(settings, 'google_drive_credentials_json', None)),
            "icon": "google",
            "url": "https://drive.google.com",
            "description": f"Folder ID: {getattr(settings, 'google_drive_folder_id', 'Not configured')}"
        },
        "OneDrive": {
            "configured": bool(getattr(settings, 'onedrive_client_id', None) and
                               getattr(settings, 'onedrive_refresh_token', None)),
            "icon": "microsoft",
            "url": "https://onedrive.live.com",
            "description": f"Upload to folder: {getattr(settings, 'onedrive_folder_path', 'Not configured')}"
        }
    }
    
    return providers

def dump_all_settings():
    """Dump all settings to the log for debugging"""
    logger.info("================ SETTINGS DUMP ================")
    
    # Get all attributes from settings object
    attributes = inspect.getmembers(settings, lambda a: not inspect.isroutine(a))
    settings_dict = {a[0]: a[1] for a in attributes 
                    if not a[0].startswith('_') and not callable(a[1])}
    
    # Sort keys for better readability
    for key in sorted(settings_dict.keys()):
        value = settings_dict[key]
        # Hide sensitive values
        if any(sensitive in key.lower() for sensitive in ['password', 'secret', 'token', 'key']):
            if value:
                value = "******** [HIDDEN FOR SECURITY]"
        logger.info(f"  {key} = {value}")
    
    # Also log all environment variables
    logger.info("----------- ENVIRONMENT VARIABLES -----------")
    env_vars_to_log = {}
    for key in sorted(os.environ.keys()):
        value = os.environ[key]
        # Hide sensitive values
        if any(sensitive in key.lower() for sensitive in ['password', 'secret', 'token', 'key']):
            if value:
                value = "******** [HIDDEN FOR SECURITY]"
        env_vars_to_log[key] = value
    
    for key in sorted(env_vars_to_log.keys()):
        logger.info(f"  {key} = {env_vars_to_log[key]}")
    
    logger.info("=============================================")

def get_settings_for_display(show_values=False):
    """Get all settings organized by category for display in UI"""
    # Get all attributes from settings object
    attributes = inspect.getmembers(settings, lambda a: not inspect.isroutine(a))
    settings_dict = {a[0]: a[1] for a in attributes 
                    if not a[0].startswith('_') and not callable(a[1])}
    
    # Categorize settings
    categories = {
        "Core": [],
        "Email": [],
        "IMAP": [],
        "Storage": [],
        "Authentication": [],
        "Integration": [],
        "Other": []
    }
    
    # Sort keys for better readability
    for key in sorted(settings_dict.keys()):
        value = settings_dict[key]
        # Mask sensitive values if show_values is False
        display_value = value
        if not show_values or any(sensitive in key.lower() for sensitive in ['password', 'secret', 'token', 'key']):
            if value:
                display_value = "******** [HIDDEN]"
            else:
                display_value = None
        
        # Categorize by key prefix
        setting_item = {"name": key, "value": display_value, "is_configured": value is not None and value != ""}
        
        if key.startswith(('email_', 'smtp_')):
            categories["Email"].append(setting_item)
        elif key.startswith('imap'):
            categories["IMAP"].append(setting_item)
        elif key.startswith(('s3_', 'aws_', 'dropbox_', 'nextcloud_', 'sftp_', 'ftp_', 'google_drive_')):
            categories["Storage"].append(setting_item)
        elif key.startswith(('auth_', 'jwt_', 'oauth_')):
            categories["Authentication"].append(setting_item)
        elif key.startswith(('paperless_', 'tesseract_', 'azure_')):
            categories["Integration"].append(setting_item)
        elif key in ('workdir', 'external_hostname', 'debug', 'version', 'env', 'log_level'):
            categories["Core"].append(setting_item)
        else:
            categories["Other"].append(setting_item)
    
    # Remove empty categories
    return {k: v for k, v in categories.items() if v}

def check_all_configs():
    """Run all configuration validations and log results"""
    logger.info("Validating application configuration...")
    
    # Check if debug is enabled and dump all settings if it is
    if hasattr(settings, 'debug') and settings.debug:
        dump_all_settings()
    
    # Check email config
    email_issues = validate_email_config()
    if email_issues:
        logger.warning(f"Email configuration issues: {', '.join(email_issues)}")
    else:
        logger.info("Email configuration OK")
    
    # Check storage configs
    storage_issues = validate_storage_configs()
    for provider, issues in storage_issues.items():
        if issues:
            logger.warning(f"{provider.capitalize()} configuration issues: {', '.join(issues)}")
        else:
            logger.info(f"{provider.capitalize()} configuration OK")
    
    # Return all identified issues
    return {
        'email': email_issues,
        'storage': storage_issues
    }
