"""
Module for handling provider status information
"""

from app.config import settings
from app.utils.config_validator.masking import mask_sensitive_value

def get_provider_status():
    """
    Returns status information for all configured providers
    """
    providers = {}
    
    # Add Notification configuration - Make sure this provider is near the top of the list
    providers["Notifications"] = {
        "name": "Notifications", 
        "icon": "fa-solid fa-bell",
        "configured": bool(getattr(settings, 'notification_urls', None)),
        "enabled": True,
        "description": "Send system notifications via various services",
        "details": {
            "services": str(len(getattr(settings, 'notification_urls', []))) + " service(s) configured" if getattr(settings, 'notification_urls', None) else "Not configured",
            "task_failure": getattr(settings, 'notify_on_task_failure', True),
            "credential_failure": getattr(settings, 'notify_on_credential_failure', True),
            "startup": getattr(settings, 'notify_on_startup', True),
            "shutdown": getattr(settings, 'notify_on_shutdown', False)
        },
        "testable": True,
        "test_endpoint": "/api/diagnostic/test-notification"
    }
    
    # Add AI services first
    providers["OpenAI"] = {
        "name": "OpenAI", 
        "icon": "fa-brands fa-openai",
        "configured": bool(getattr(settings, 'openai_api_key', None) and 
                           str(getattr(settings, 'openai_api_key', '')).startswith('sk-')),
        "enabled": True,
        "description": "AI-powered document analysis and metadata extraction",
        "details": {
            "api_key": mask_sensitive_value(getattr(settings, 'openai_api_key', None)),
            "base_url": getattr(settings, 'openai_base_url', 'https://api.openai.com/v1'),
            "model": getattr(settings, 'openai_model', 'gpt-4')
        }
    }
    
    providers["Azure AI"] = {
        "name": "Azure AI", 
        "icon": "fa-solid fa-robot",
        "configured": bool(getattr(settings, 'azure_ai_key', None) and 
                          getattr(settings, 'azure_endpoint', None)),
        "enabled": True,
        "description": "Microsoft Azure Document Intelligence",
        "details": {
            "api_key": mask_sensitive_value(getattr(settings, 'azure_ai_key', None)),
            "endpoint": getattr(settings, 'azure_endpoint', 'Not set'),
            "region": getattr(settings, 'azure_region', 'Not set')
        }
    }
    
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
    gdrive_oauth_configured = bool(getattr(settings, 'google_drive_client_id', None) and 
                                  getattr(settings, 'google_drive_client_secret', None) and
                                  getattr(settings, 'google_drive_refresh_token', None))
    
    gdrive_sa_configured = bool(getattr(settings, 'google_drive_credentials_json', None))
    
    # Determine if using OAuth or service account
    use_oauth = getattr(settings, 'google_drive_use_oauth', False)
    
    is_configured = (use_oauth and gdrive_oauth_configured) or (not use_oauth and gdrive_sa_configured)
    
    providers["Google Drive"] = {
        "name": "Google Drive", 
        "icon": "fa-brands fa-google-drive",
        "configured": is_configured and bool(getattr(settings, 'google_drive_folder_id', None)),
        "enabled": True,
        "description": "Store documents in Google Drive",
        "details": {
            "auth_type": "OAuth" if use_oauth else "Service Account",
            "client_id": getattr(settings, 'google_drive_client_id', 'Not set') if use_oauth else 'N/A',
            "client_secret": mask_sensitive_value(getattr(settings, 'google_drive_client_secret', None)) if use_oauth else 'N/A',
            "refresh_token": mask_sensitive_value(getattr(settings, 'google_drive_refresh_token', None)) if use_oauth else 'N/A',
            "credentials_json": mask_sensitive_value(getattr(settings, 'google_drive_credentials_json', None)) if not use_oauth else 'N/A',
            "folder_id": getattr(settings, 'google_drive_folder_id', 'Not set'),
            "delegate": getattr(settings, 'google_drive_delegate_to', 'Not set') if not use_oauth else 'N/A'
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
