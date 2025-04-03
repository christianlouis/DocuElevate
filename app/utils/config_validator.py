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
    
    # Validate Uptime Kuma
    uptime_kuma_issues = []
    if not getattr(settings, 'uptime_kuma_url', None):
        uptime_kuma_issues.append("UPTIME_KUMA_URL is not configured")
    issues['uptime_kuma'] = uptime_kuma_issues
    
    return issues

def mask_sensitive_value(value):
    """Helper function to mask sensitive values consistently"""
    if not value:
        return "Not set"
    
    if isinstance(value, str):
        if len(value) > 10:
            visible_start = max(1, len(value) // 3)
            visible_end = max(1, len(value) // 4)
            return f"{value[:visible_start]}{'*' * (len(value) - visible_start - visible_end)}{value[-visible_end:]}"
        else:
            return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}" if len(value) > 4 else "****"
    elif not isinstance(value, (bool, int, float)):
        return "**Configured Value**"
    return str(value)

def get_provider_status():
    """
    Returns status information for all configured providers
    
    Font Awesome icons used:
    - fa-brands fa-dropbox: Dropbox icon
    - fa-solid fa-envelope: Email icon
    - fa-solid fa-server: FTP Server icon
    - fa-brands fa-google-drive: Google Drive icon
    - fa-solid fa-cloud: NextCloud icon
    - fa-brands fa-microsoft: Microsoft/OneDrive icon
    - fa-solid fa-file-lines: Document/Paperless icon
    - fa-brands fa-aws: AWS/S3 icon
    - fa-solid fa-lock: SFTP icon (secure)
    - fa-solid fa-heart-pulse: Uptime/health monitoring
    - fa-solid fa-globe: WebDAV/web icon
    """
    providers = {}
    
    # Add Dropbox configuration - alphabetically ordered providers
    providers["Dropbox"] = {
        "name": "Dropbox", 
        "icon": "fa-brands fa-dropbox",
        "configured": bool(getattr(settings, 'dropbox_app_key', None) and
                          getattr(settings, 'dropbox_app_secret', None) and
                          getattr(settings, 'dropbox_refresh_token', None)),
        "enabled": True,
        "description": "Upload files to Dropbox cloud storage",
        "details": {
            "folder": getattr(settings, 'dropbox_folder', 'Not set'),
            "app_key": getattr(settings, 'dropbox_app_key', 'Not set'),
            "app_secret": mask_sensitive_value(getattr(settings, 'dropbox_app_secret', None)),
            "refresh_token": mask_sensitive_value(getattr(settings, 'dropbox_refresh_token', None))
        }
    }
    
    # Add Email configuration
    providers["Email"] = {
        "name": "Email", 
        "icon": "fa-solid fa-envelope",
        "configured": bool(getattr(settings, 'email_host', None) and 
                         getattr(settings, 'email_default_recipient', None)),
        "enabled": True,
        "description": "Send documents via email",
        "details": {
            "host": getattr(settings, 'email_host', 'Not set'),
            "port": getattr(settings, 'email_port', 'Not set'),
            "username": getattr(settings, 'email_username', 'Not set'),
            "password": mask_sensitive_value(getattr(settings, 'email_password', None)),
            "use_tls": getattr(settings, 'email_use_tls', 'Not set'),
            "sender": getattr(settings, 'email_sender', 'Not set'),
            "default_recipient": getattr(settings, 'email_default_recipient', 'Not set')
        }
    }
    
    # Add FTP configuration to providers
    providers["FTP Storage"] = {
        "name": "FTP Storage",
        "icon": "fa-solid fa-server",
        "configured": bool(getattr(settings, 'ftp_host', None) and
                          getattr(settings, 'ftp_username', None) and
                          getattr(settings, 'ftp_password', None)),
        "enabled": True,
        "description": "Upload files to FTP server",
        "details": {
            "host": getattr(settings, 'ftp_host', 'Not set'),
            "port": getattr(settings, 'ftp_port', 'Not set'),
            "username": getattr(settings, 'ftp_username', 'Not set'),
            "password": mask_sensitive_value(getattr(settings, 'ftp_password', None)),
            "folder": getattr(settings, 'ftp_folder', 'Not set'),
            "tls": getattr(settings, 'ftp_use_tls', True),
            "allow_plaintext": getattr(settings, 'ftp_allow_plaintext', True)
        }
    }
    
    # Check Google Drive configuration
    providers["Google Drive"] = {
        "name": "Google Drive", 
        "icon": "fa-brands fa-google-drive",
        "configured": bool(getattr(settings, 'google_drive_credentials_json', None) and 
                          getattr(settings, 'google_drive_folder_id', None)),
        "enabled": True,
        "description": "Store documents in Google Drive",
        "details": {
            "credentials_json": mask_sensitive_value(getattr(settings, 'google_drive_credentials_json', None)),
            "folder_id": getattr(settings, 'google_drive_folder_id', 'Not set'),
            "delegate": getattr(settings, 'google_drive_delegate_to', 'Not set')
        }
    }
    
    # Check NextCloud configuration
    nextcloud_url = getattr(settings, 'nextcloud_upload_url', 'Not set')
    # Extract base URL from WebDAV URL (remove the /remote.php part and everything after it)
    nextcloud_base_url = nextcloud_url
    if nextcloud_url != 'Not set' and nextcloud_url is not None and '/remote.php' in nextcloud_url:
        nextcloud_base_url = nextcloud_url.split('/remote.php')[0]
        
    providers["NextCloud"] = {
        "name": "NextCloud", 
        "icon": "fa-solid fa-cloud",
        "configured": bool(getattr(settings, 'nextcloud_upload_url', None) and 
                          getattr(settings, 'nextcloud_username', None) and 
                          getattr(settings, 'nextcloud_password', None)),
        "enabled": True,
        "description": "Store documents in NextCloud",
        "details": {
            "url": getattr(settings, 'nextcloud_upload_url', 'Not set'),
            "base_url": nextcloud_base_url,
            "username": getattr(settings, 'nextcloud_username', 'Not set'),
            "password": mask_sensitive_value(getattr(settings, 'nextcloud_password', None)),
            "folder": getattr(settings, 'nextcloud_folder', 'Not set')
        }
    }
    
    # Check OneDrive configuration
    providers["OneDrive"] = {
        "name": "OneDrive", 
        "icon": "fa-brands fa-microsoft",
        "configured": bool(getattr(settings, 'onedrive_client_id', None) and 
                          getattr(settings, 'onedrive_client_secret', None) and 
                          getattr(settings, 'onedrive_refresh_token', None)),
        "enabled": True,
        "description": "Store documents in Microsoft OneDrive",
        "details": {
            "client_id": getattr(settings, 'onedrive_client_id', 'Not set'),
            "client_secret": mask_sensitive_value(getattr(settings, 'onedrive_client_secret', None)),
            "tenant_id": getattr(settings, 'onedrive_tenant_id', 'Not set'),
            "refresh_token": mask_sensitive_value(getattr(settings, 'onedrive_refresh_token', None)),
            "folder": getattr(settings, 'onedrive_folder_path', 'Not set')
        }
    }
    
    # Check Paperless configuration
    providers["Paperless-ngx"] = {
        "name": "Paperless-ngx", 
        "icon": "fa-solid fa-file-lines",
        "configured": bool(getattr(settings, 'paperless_host', None) and 
                         getattr(settings, 'paperless_ngx_api_token', None)),
        "enabled": True,
        "description": "Document management system for digital archives",
        "details": {
            "host": getattr(settings, 'paperless_host', 'Not set'),
            "api_token": mask_sensitive_value(getattr(settings, 'paperless_ngx_api_token', None))
        }
    }
    
    # Check S3 configuration
    providers["S3 Storage"] = {
        "name": "S3 Storage",
        "icon": "fa-brands fa-aws",
        "configured": bool(getattr(settings, 's3_bucket_name', None) and 
                          getattr(settings, 'aws_access_key_id', None) and 
                          getattr(settings, 'aws_secret_access_key', None)),
        "enabled": True,
        "description": "Store documents in S3-compatible object storage",
        "details": {
            "bucket": getattr(settings, 's3_bucket_name', 'Not set'),
            "region": getattr(settings, 'aws_region', 'Not set'),
            "access_key_id": getattr(settings, 'aws_access_key_id', 'Not set'),
            "secret_access_key": mask_sensitive_value(getattr(settings, 'aws_secret_access_key', None)),
            "folder_prefix": getattr(settings, 's3_folder_prefix', 'Not set'),
            "storage_class": getattr(settings, 's3_storage_class', 'Not set'),
            "acl": getattr(settings, 's3_acl', 'Not set')
        }
    }
    
    # Check SFTP configuration
    providers["SFTP Storage"] = {
        "name": "SFTP Storage", 
        "icon": "fa-solid fa-lock",
        "configured": bool(getattr(settings, 'sftp_host', None) and 
                          getattr(settings, 'sftp_username', None) and 
                          (getattr(settings, 'sftp_password', None) or 
                           getattr(settings, 'sftp_private_key', None))),
        "enabled": True,
        "description": "Upload files to SFTP server",
        "details": {
            "host": getattr(settings, 'sftp_host', 'Not set'),
            "port": getattr(settings, 'sftp_port', 'Not set'),
            "username": getattr(settings, 'sftp_username', 'Not set'),
            "password": mask_sensitive_value(getattr(settings, 'sftp_password', None)),
            "private_key": getattr(settings, 'sftp_private_key', 'Not set'),
            "private_key_passphrase": mask_sensitive_value(getattr(settings, 'sftp_private_key_passphrase', None)),
            "folder": getattr(settings, 'sftp_folder', 'Not set')
        }
    }

    # Add Uptime Kuma configuration
    providers["Uptime Kuma"] = {
        "name": "Uptime Kuma",
        "icon": "fa-solid fa-heart-pulse",
        "configured": bool(getattr(settings, 'uptime_kuma_url', None)),
        "enabled": True,
        "description": "Server monitoring and status page",
        "details": {
            "url": getattr(settings, 'uptime_kuma_url', 'Not set'),
            "ping_interval": getattr(settings, 'uptime_kuma_ping_interval', 'Not set')
        }
    }

    # Check WebDAV configuration
    providers["WebDAV"] = {
        "name": "WebDAV", 
        "icon": "fa-solid fa-globe",
        "configured": bool(getattr(settings, 'webdav_url', None) and 
                          getattr(settings, 'webdav_username', None) and 
                          getattr(settings, 'webdav_password', None)),
        "enabled": True,
        "description": "Store documents on WebDAV servers",
        "details": {
            "url": getattr(settings, 'webdav_url', 'Not set'),
            "username": getattr(settings, 'webdav_username', 'Not set'),
            "password": mask_sensitive_value(getattr(settings, 'webdav_password', None)),
            "folder": getattr(settings, 'webdav_folder', 'Not set'),
            "verify_ssl": getattr(settings, 'webdav_verify_ssl', 'Not set')
        }
    }
    
    return providers

def dump_all_settings():
    """Log all settings values for diagnostic purposes"""
    logger.info("--- DUMPING ALL SETTINGS FOR DIAGNOSTIC PURPOSES ---")
    for key in dir(settings):
        if not key.startswith('_') and not callable(getattr(settings, key)):
            value = getattr(settings, key)
            # Mask sensitive values in logs
            if key.lower().find('password') >= 0 or key.lower().find('secret') >= 0 or key.lower().find('token') >= 0 or key.lower().find('key') >= 0:
                if value:
                    if isinstance(value, str) and len(value) > 10:
                        visible_start = max(1, len(value) // 3)
                        visible_end = max(1, len(value) // 4)
                        value = f"{value[:visible_start]}{'*' * (len(value) - visible_start - visible_end)}{value[-visible_end:]}"
                    else:
                        value = f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}" if isinstance(value, str) and len(value) > 4 else "****"
            logger.info(f"{key}: {value}")
    logger.info("--- END OF SETTINGS DUMP ---")

def get_settings_for_display(show_values=False):
    """
    Group settings into logical categories and check if they are configured.
    Returns a dictionary with categories as keys and lists of setting items as values.
    Each setting item is a dict with name, value, and is_configured.
    
    If show_values is False, sensitive values are masked.
    """
    # First include system info with version in result
    result = {
        "System Info": [
            {
                "name": "App Version",
                "value": settings.version,
                "is_configured": True
            }
        ]
    }
    
    # Define categories and their settings
    categories = {
        "Core": [
            "debug", # Explicitly include debug setting
            "external_hostname",
            "workdir",
            "database_url",
            "redis_url",
            "gotenberg_url"
        ],
        "Authentication": [
            "auth_enabled",
            "authentik_client_id",
            "authentik_client_secret",
            "authentik_config_url"
        ],
        "Email": [
            "email_host",
            "email_port",
            "email_username",
            "email_password",
            "email_use_tls",
            "email_sender",
            "email_default_recipient"
        ],
        "IMAP": [
            "imap1_host",
            "imap1_port",
            "imap1_username",
            "imap1_password",
            "imap1_ssl",
            "imap1_poll_interval_minutes",
            "imap1_delete_after_process",
            "imap2_host",
            "imap2_port",
            "imap2_username",
            "imap2_password",
            "imap2_ssl",
            "imap2_poll_interval_minutes",
            "imap2_delete_after_process"
        ],
        "Dropbox": [
            "dropbox_app_key",
            "dropbox_app_secret",
            "dropbox_folder",
            "dropbox_refresh_token"
        ],
        "NextCloud": [
            "nextcloud_upload_url",
            "nextcloud_username",
            "nextcloud_password",
            "nextcloud_folder"
        ],
        "Paperless": [
            "paperless_host",
            "paperless_ngx_api_token"
        ],
        "Google Drive": [
            "google_drive_credentials_json",
            "google_drive_folder_id",
            "google_drive_delegate_to"
        ],
        "OneDrive": [
            "onedrive_client_id",
            "onedrive_client_secret",
            "onedrive_tenant_id",
            "onedrive_refresh_token",
            "onedrive_folder_path"
        ],
        "WebDAV": [
            "webdav_url",
            "webdav_username",
            "webdav_password",
            "webdav_folder",
            "webdav_verify_ssl"
        ],
        "SFTP": [
            "sftp_host",
            "sftp_port",
            "sftp_username",
            "sftp_password",
            "sftp_folder",
            "sftp_private_key",
            "sftp_private_key_passphrase"
        ],
        "FTP": [
            "ftp_host",
            "ftp_port",
            "ftp_username",
            "ftp_password",
            "ftp_folder",
            "ftp_use_tls",
            "ftp_allow_plaintext"
        ],
        "S3/AWS": [
            "aws_access_key_id",
            "aws_secret_access_key",
            "aws_region",
            "s3_bucket_name",
            "s3_folder_prefix",
            "s3_storage_class",
            "s3_acl"
        ],
        "AI Services": [
            "openai_api_key",
            "openai_base_url",
            "openai_model",
            "azure_ai_key",
            "azure_endpoint",
            "azure_region"
        ],
        "Monitoring": [
            "uptime_kuma_url",
            "uptime_kuma_ping_interval"
        ]
    }
    
    # Handle any settings that don't fit into the predefined categories
    all_settings = set([key for key in dir(settings) 
                        if not key.startswith('_') and 
                        not callable(getattr(settings, key)) and
                        key not in ["model_computed_fields", "model_config", 
                                    "model_extra", "model_fields",
                                    "model_fields_set"]])
    
    # Ensure 'version' is excluded since we display it separately
    all_settings.discard("version")
    
    categorized_settings = set()
    for cat_settings in categories.values():
        categorized_settings.update(cat_settings)
    
    uncategorized = all_settings - categorized_settings
    if uncategorized:
        categories["Other"] = list(uncategorized)
    
    # Build the result
    for category, setting_keys in categories.items():
        items = []
        for key in setting_keys:
            if hasattr(settings, key):
                value = getattr(settings, key)
                
                # List of patterns that indicate sensitive values
                sensitive_patterns = [
                    'password', 'secret', 'token', 'api_key', 'private_key',
                    'credentials', 'access_key', 'ai_key'
                ]
                
                # Check if this is a sensitive value that should be masked
                is_sensitive = any(
                    pattern in key.lower() for pattern in sensitive_patterns
                )
                
                # Special handling for "auth" to avoid matching prefixes like "authentik"
                if not is_sensitive and "auth" in key.lower():
                    # Only mark as sensitive if "auth" is a standalone word or at the end
                    # This avoids matching "authentik" as sensitive
                    parts = key.lower().split('_')
                    is_sensitive = any(part == "auth" for part in parts) or key.lower().endswith("auth")
                
                # Mask sensitive values regardless of debug mode
                # Other values are only hidden if debug mode is off AND show_values is False
                if (is_sensitive or not show_values) and value:
                    if is_sensitive:
                        value = mask_sensitive_value(value)
                
                # Check if the setting is configured (has a non-None value)
                # For boolean settings, consider them configured even if False
                is_configured = value is not None
                if is_configured and isinstance(value, str):
                    is_configured = len(value) > 0
                
                items.append({
                    "name": key,
                    "value": value,
                    "is_configured": is_configured
                })
        
        if items:  # Only add categories that have items
            result[category] = items
    
    return result

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
