#!/usr/bin/env python3

import os
import socket
import logging
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
    
    # Validate Uptime Kuma
    uptime_kuma_issues = []
    if not getattr(settings, 'uptime_kuma_url', None):
        uptime_kuma_issues.append("UPTIME_KUMA_URL is not configured")
    issues['uptime_kuma'] = uptime_kuma_issues
    
    return issues

def check_all_configs():
    """Run all configuration validations and log results"""
    from app.utils.config_validator.settings_display import dump_all_settings
    
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
