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
    providers["Authentication"] = _get_auth_provider()
    providers["Notifications"] = _get_notifications_provider()
    providers["OpenAI"] = _get_openai_provider()
    providers["Azure AI"] = _get_azure_ai_provider()
    providers["Dropbox"] = _get_dropbox_provider()
    providers["Email"] = _get_email_provider()
    providers["FTP Storage"] = _get_ftp_provider()
    providers["Google Drive"] = _get_google_drive_provider()
    providers["NextCloud"] = _get_nextcloud_provider()
    providers["OneDrive"] = _get_onedrive_provider()
    providers["Paperless-ngx"] = _get_paperless_provider()
    providers["S3 Storage"] = _get_s3_provider()
    providers["SFTP Storage"] = _get_sftp_provider()
    providers["Uptime Kuma"] = _get_uptime_kuma_provider()
    providers["WebDAV"] = _get_webdav_provider()
    return providers


def _get_auth_provider():
    """Returns Authentication provider status."""
    auth_enabled = getattr(settings, "auth_enabled", False)
    using_oidc = bool(
        getattr(settings, "authentik_client_id", None)
        and getattr(settings, "authentik_client_secret", None)
        and getattr(settings, "authentik_config_url", None)
    )
    auth_method = "OIDC" if using_oidc else "Basic Auth" if auth_enabled else "None"
    return {
        "name": "Authentication",
        "icon": "fa-solid fa-lock",
        "configured": bool(auth_enabled and (getattr(settings, "admin_username", None) or using_oidc)),
        "enabled": auth_enabled,
        "description": "Access control and user authentication",
        "details": {
            "method": auth_method,
            "provider_name": getattr(settings, "oauth_provider_name", "Not set") if using_oidc else "N/A",
            "session_security": "Configured" if getattr(settings, "session_secret", None) else "Not configured",
        },
    }


def _get_notifications_provider():
    """Returns Notifications provider status."""
    return {
        "name": "Notifications",
        "icon": "fa-solid fa-bell",
        "configured": bool(getattr(settings, "notification_urls", None)),
        "enabled": True,
        "description": "Send system notifications via various services",
        "details": {
            "services": (
                str(len(getattr(settings, "notification_urls", []))) + " service(s) configured"
                if getattr(settings, "notification_urls", None)
                else "Not configured"
            ),
            "task_failure": getattr(settings, "notify_on_task_failure", True),
            "credential_failure": getattr(settings, "notify_on_credential_failure", True),
            "startup": getattr(settings, "notify_on_startup", True),
            "shutdown": getattr(settings, "notify_on_shutdown", False),
        },
        "testable": True,
        "test_endpoint": "/api/diagnostic/test-notification",
    }


def _get_openai_provider():
    """Returns OpenAI provider status."""
    return {
        "name": "OpenAI",
        "icon": "fa-brands fa-openai",
        "configured": bool(
            getattr(settings, "openai_api_key", None) and str(getattr(settings, "openai_api_key", "")).startswith("sk-")
        ),
        "enabled": True,
        "description": "AI-powered document analysis and metadata extraction",
        "details": {
            "api_key": mask_sensitive_value(getattr(settings, "openai_api_key", None)),
            "base_url": getattr(settings, "openai_base_url", "https://api.openai.com/v1"),
            "model": getattr(settings, "openai_model", "gpt-4"),
        },
    }


def _get_azure_ai_provider():
    """Returns Azure AI provider status."""
    return {
        "name": "Azure AI",
        "icon": "fa-solid fa-robot",
        "configured": bool(getattr(settings, "azure_ai_key", None) and getattr(settings, "azure_endpoint", None)),
        "enabled": True,
        "description": "Microsoft Azure Document Intelligence",
        "details": {
            "api_key": mask_sensitive_value(getattr(settings, "azure_ai_key", None)),
            "endpoint": getattr(settings, "azure_endpoint", "Not set"),
            "region": getattr(settings, "azure_region", "Not set"),
        },
    }


def _get_dropbox_provider():
    """Returns Dropbox provider status."""
    return {
        "name": "Dropbox",
        "icon": "fa-brands fa-dropbox",
        "configured": bool(
            getattr(settings, "dropbox_app_key", None)
            and getattr(settings, "dropbox_app_secret", None)
            and getattr(settings, "dropbox_refresh_token", None)
        ),
        "enabled": True,
        "description": "Upload files to Dropbox cloud storage",
        "details": {
            "folder": getattr(settings, "dropbox_folder", "Not set"),
            "app_key": getattr(settings, "dropbox_app_key", "Not set"),
            "app_secret": mask_sensitive_value(getattr(settings, "dropbox_app_secret", None)),
            "refresh_token": mask_sensitive_value(getattr(settings, "dropbox_refresh_token", None)),
        },
    }


def _get_email_provider():
    """Returns Email provider status."""
    return {
        "name": "Email",
        "icon": "fa-solid fa-envelope",
        "configured": bool(
            getattr(settings, "email_host", None) and getattr(settings, "email_default_recipient", None)
        ),
        "enabled": True,
        "description": "Send documents via email",
        "details": {
            "host": getattr(settings, "email_host", "Not set"),
            "port": getattr(settings, "email_port", "Not set"),
            "username": getattr(settings, "email_username", "Not set"),
            "password": mask_sensitive_value(getattr(settings, "email_password", None)),
            "use_tls": getattr(settings, "email_use_tls", "Not set"),
            "sender": getattr(settings, "email_sender", "Not set"),
            "default_recipient": getattr(settings, "email_default_recipient", "Not set"),
        },
    }


def _get_ftp_provider():
    """Returns FTP Storage provider status."""
    return {
        "name": "FTP Storage",
        "icon": "fa-solid fa-server",
        "configured": bool(
            getattr(settings, "ftp_host", None)
            and getattr(settings, "ftp_username", None)
            and getattr(settings, "ftp_password", None)
        ),
        "enabled": True,
        "description": "Upload files to FTP server",
        "details": {
            "host": getattr(settings, "ftp_host", "Not set"),
            "port": getattr(settings, "ftp_port", "Not set"),
            "username": getattr(settings, "ftp_username", "Not set"),
            "password": mask_sensitive_value(getattr(settings, "ftp_password", None)),
            "folder": getattr(settings, "ftp_folder", "Not set"),
            "tls": getattr(settings, "ftp_use_tls", True),
            "allow_plaintext": getattr(settings, "ftp_allow_plaintext", True),
        },
    }


def _get_google_drive_provider():
    """Returns Google Drive provider status."""
    gdrive_oauth_configured = bool(
        getattr(settings, "google_drive_client_id", None)
        and getattr(settings, "google_drive_client_secret", None)
        and getattr(settings, "google_drive_refresh_token", None)
    )
    gdrive_sa_configured = bool(getattr(settings, "google_drive_credentials_json", None))
    use_oauth = getattr(settings, "google_drive_use_oauth", False)
    is_configured = (use_oauth and gdrive_oauth_configured) or (not use_oauth and gdrive_sa_configured)

    return {
        "name": "Google Drive",
        "icon": "fa-brands fa-google-drive",
        "configured": is_configured and bool(getattr(settings, "google_drive_folder_id", None)),
        "enabled": True,
        "description": "Store documents in Google Drive",
        "details": {
            "auth_type": "OAuth" if use_oauth else "Service Account",
            "client_id": getattr(settings, "google_drive_client_id", "Not set") if use_oauth else "N/A",
            "client_secret": (
                mask_sensitive_value(getattr(settings, "google_drive_client_secret", None)) if use_oauth else "N/A"
            ),
            "refresh_token": (
                mask_sensitive_value(getattr(settings, "google_drive_refresh_token", None)) if use_oauth else "N/A"
            ),
            "credentials_json": (
                mask_sensitive_value(getattr(settings, "google_drive_credentials_json", None))
                if not use_oauth
                else "N/A"
            ),
            "folder_id": getattr(settings, "google_drive_folder_id", "Not set"),
            "delegate": getattr(settings, "google_drive_delegate_to", "Not set") if not use_oauth else "N/A",
        },
    }


def _get_nextcloud_provider():
    """Returns NextCloud provider status."""
    nextcloud_url = getattr(settings, "nextcloud_upload_url", "Not set")
    nextcloud_base_url = nextcloud_url
    if nextcloud_url != "Not set" and nextcloud_url is not None and "/remote.php" in nextcloud_url:
        nextcloud_base_url = nextcloud_url.split("/remote.php")[0]

    return {
        "name": "NextCloud",
        "icon": "fa-solid fa-cloud",
        "configured": bool(
            getattr(settings, "nextcloud_upload_url", None)
            and getattr(settings, "nextcloud_username", None)
            and getattr(settings, "nextcloud_password", None)
        ),
        "enabled": True,
        "description": "Store documents in NextCloud",
        "details": {
            "url": getattr(settings, "nextcloud_upload_url", "Not set"),
            "base_url": nextcloud_base_url,
            "username": getattr(settings, "nextcloud_username", "Not set"),
            "password": mask_sensitive_value(getattr(settings, "nextcloud_password", None)),
            "folder": getattr(settings, "nextcloud_folder", "Not set"),
        },
    }


def _get_onedrive_provider():
    """Returns OneDrive provider status."""
    return {
        "name": "OneDrive",
        "icon": "fa-brands fa-microsoft",
        "configured": bool(
            getattr(settings, "onedrive_client_id", None)
            and getattr(settings, "onedrive_client_secret", None)
            and getattr(settings, "onedrive_refresh_token", None)
        ),
        "enabled": True,
        "description": "Store documents in Microsoft OneDrive",
        "details": {
            "client_id": getattr(settings, "onedrive_client_id", "Not set"),
            "client_secret": mask_sensitive_value(getattr(settings, "onedrive_client_secret", None)),
            "tenant_id": getattr(settings, "onedrive_tenant_id", "Not set"),
            "refresh_token": mask_sensitive_value(getattr(settings, "onedrive_refresh_token", None)),
            "folder": getattr(settings, "onedrive_folder_path", "Not set"),
        },
    }


def _get_paperless_provider():
    """Returns Paperless-ngx provider status."""
    return {
        "name": "Paperless-ngx",
        "icon": "fa-solid fa-file-lines",
        "configured": bool(
            getattr(settings, "paperless_host", None) and getattr(settings, "paperless_ngx_api_token", None)
        ),
        "enabled": True,
        "description": "Document management system for digital archives",
        "details": {
            "host": getattr(settings, "paperless_host", "Not set"),
            "api_token": mask_sensitive_value(getattr(settings, "paperless_ngx_api_token", None)),
        },
    }


def _get_s3_provider():
    """Returns S3 Storage provider status."""
    return {
        "name": "S3 Storage",
        "icon": "fa-brands fa-aws",
        "configured": bool(
            getattr(settings, "s3_bucket_name", None)
            and getattr(settings, "aws_access_key_id", None)
            and getattr(settings, "aws_secret_access_key", None)
        ),
        "enabled": True,
        "description": "Store documents in S3-compatible object storage",
        "details": {
            "bucket": getattr(settings, "s3_bucket_name", "Not set"),
            "region": getattr(settings, "aws_region", "Not set"),
            "access_key_id": getattr(settings, "aws_access_key_id", "Not set"),
            "secret_access_key": mask_sensitive_value(getattr(settings, "aws_secret_access_key", None)),
            "folder_prefix": getattr(settings, "s3_folder_prefix", "Not set"),
            "storage_class": getattr(settings, "s3_storage_class", "Not set"),
            "acl": getattr(settings, "s3_acl", "Not set"),
        },
    }


def _get_sftp_provider():
    """Returns SFTP Storage provider status."""
    return {
        "name": "SFTP Storage",
        "icon": "fa-solid fa-lock",
        "configured": bool(
            getattr(settings, "sftp_host", None)
            and getattr(settings, "sftp_username", None)
            and (getattr(settings, "sftp_password", None) or getattr(settings, "sftp_private_key", None))
        ),
        "enabled": True,
        "description": "Upload files to SFTP server",
        "details": {
            "host": getattr(settings, "sftp_host", "Not set"),
            "port": getattr(settings, "sftp_port", "Not set"),
            "username": getattr(settings, "sftp_username", "Not set"),
            "password": mask_sensitive_value(getattr(settings, "sftp_password", None)),
            "private_key": getattr(settings, "sftp_private_key", "Not set"),
            "private_key_passphrase": mask_sensitive_value(getattr(settings, "sftp_private_key_passphrase", None)),
            "folder": getattr(settings, "sftp_folder", "Not set"),
        },
    }


def _get_uptime_kuma_provider():
    """Returns Uptime Kuma provider status."""
    return {
        "name": "Uptime Kuma",
        "icon": "fa-solid fa-heart-pulse",
        "configured": bool(getattr(settings, "uptime_kuma_url", None)),
        "enabled": True,
        "description": "Server monitoring and status page",
        "details": {
            "url": getattr(settings, "uptime_kuma_url", "Not set"),
            "ping_interval": getattr(settings, "uptime_kuma_ping_interval", "Not set"),
        },
    }


def _get_webdav_provider():
    """Returns WebDAV provider status."""
    return {
        "name": "WebDAV",
        "icon": "fa-solid fa-globe",
        "configured": bool(
            getattr(settings, "webdav_url", None)
            and getattr(settings, "webdav_username", None)
            and getattr(settings, "webdav_password", None)
        ),
        "enabled": True,
        "description": "Store documents on WebDAV servers",
        "details": {
            "url": getattr(settings, "webdav_url", "Not set"),
            "username": getattr(settings, "webdav_username", "Not set"),
            "password": mask_sensitive_value(getattr(settings, "webdav_password", None)),
            "folder": getattr(settings, "webdav_folder", "Not set"),
            "verify_ssl": getattr(settings, "webdav_verify_ssl", "Not set"),
        },
    }
