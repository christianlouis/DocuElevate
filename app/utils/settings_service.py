"""
Service for managing application settings with database persistence.

This module provides functionality to:
- Load settings from database with precedence over environment variables
- Save settings to database
- Get setting metadata (descriptions, types, categories)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models import ApplicationSettings

logger = logging.getLogger(__name__)

# Define setting metadata for UI display
SETTING_METADATA = {
    # Core Settings
    "database_url": {
        "category": "Core",
        "description": "Database connection URL (e.g., sqlite:///path/to/db.sqlite)",
        "type": "string",
        "sensitive": False,
        "required": True,
        "restart_required": True,
    },
    "redis_url": {
        "category": "Core",
        "description": "Redis connection URL for Celery task queue",
        "type": "string",
        "sensitive": False,
        "required": True,
        "restart_required": True,
    },
    "workdir": {
        "category": "Core",
        "description": "Working directory for file storage and processing",
        "type": "string",
        "sensitive": False,
        "required": True,
        "restart_required": True,
    },
    "external_hostname": {
        "category": "Core",
        "description": "External hostname for the application (e.g., docuelevate.example.com)",
        "type": "string",
        "sensitive": False,
        "required": True,  # Required for OAuth redirects and external URLs
        "restart_required": True,
    },
    "debug": {
        "category": "Core",
        "description": "Enable debug mode for verbose logging",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "gotenberg_url": {
        "category": "Core",
        "description": "Gotenberg service URL for document conversion",
        "type": "string",
        "sensitive": False,
        "required": True,
        "restart_required": True,
    },
    
    # Authentication Settings
    "auth_enabled": {
        "category": "Authentication",
        "description": "Enable authentication for the application",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "session_secret": {
        "category": "Authentication",
        "description": "Secret key for session encryption (min 32 characters)",
        "type": "string",
        "sensitive": True,
        "required": True,  # Required when auth_enabled=True (validated in config.py)
        "restart_required": True,
    },
    "admin_username": {
        "category": "Authentication",
        "description": "Admin username for local authentication",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "admin_password": {
        "category": "Authentication",
        "description": "Admin password for local authentication",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": True,
    },
    "authentik_client_id": {
        "category": "Authentication",
        "description": "Authentik OAuth2 client ID",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "authentik_client_secret": {
        "category": "Authentication",
        "description": "Authentik OAuth2 client secret",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": True,
    },
    "authentik_config_url": {
        "category": "Authentication",
        "description": "Authentik OpenID Connect configuration URL",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "oauth_provider_name": {
        "category": "Authentication",
        "description": "Display name for OAuth provider (e.g., 'Authentik', 'Keycloak')",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    
    # AI Services
    "openai_api_key": {
        "category": "AI Services",
        "description": "OpenAI API key for metadata extraction",
        "type": "string",
        "sensitive": True,
        "required": True,
        "restart_required": False,
    },
    "openai_base_url": {
        "category": "AI Services",
        "description": "OpenAI API base URL (default: https://api.openai.com/v1)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "openai_model": {
        "category": "AI Services",
        "description": "OpenAI model to use (e.g., gpt-4o-mini)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "azure_ai_key": {
        "category": "AI Services",
        "description": "Azure AI key for document intelligence",
        "type": "string",
        "sensitive": True,
        "required": True,
        "restart_required": False,
    },
    "azure_region": {
        "category": "AI Services",
        "description": "Azure region for AI services",
        "type": "string",
        "sensitive": False,
        "required": True,
        "restart_required": False,
    },
    "azure_endpoint": {
        "category": "AI Services",
        "description": "Azure AI endpoint URL",
        "type": "string",
        "sensitive": False,
        "required": True,
        "restart_required": False,
    },
    
    # Storage Providers - Dropbox
    "dropbox_app_key": {
        "category": "Storage Providers",
        "description": "Dropbox app key for OAuth authentication",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "dropbox_app_secret": {
        "category": "Storage Providers",
        "description": "Dropbox app secret for OAuth authentication",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "dropbox_folder": {
        "category": "Storage Providers",
        "description": "Dropbox folder path for document storage",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "dropbox_refresh_token": {
        "category": "Storage Providers",
        "description": "Dropbox OAuth refresh token",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    
    # Storage Providers - Nextcloud
    "nextcloud_upload_url": {
        "category": "Storage Providers",
        "description": "Nextcloud WebDAV upload URL",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "nextcloud_username": {
        "category": "Storage Providers",
        "description": "Nextcloud username for authentication",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "nextcloud_password": {
        "category": "Storage Providers",
        "description": "Nextcloud password or app password",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "nextcloud_folder": {
        "category": "Storage Providers",
        "description": "Nextcloud folder path for document storage",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    
    # Storage Providers - Paperless-ngx
    "paperless_ngx_api_token": {
        "category": "Storage Providers",
        "description": "Paperless-ngx API authentication token",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "paperless_host": {
        "category": "Storage Providers",
        "description": "Paperless-ngx host URL (e.g., https://paperless.example.com)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    
    # Storage Providers - Google Drive
    "google_drive_credentials_json": {
        "category": "Storage Providers",
        "description": "Google Drive service account credentials JSON",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "google_drive_folder_id": {
        "category": "Storage Providers",
        "description": "Google Drive folder ID for document storage",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "google_drive_delegate_to": {
        "category": "Storage Providers",
        "description": "Optional delegated user email for Google Drive service account",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "google_drive_use_oauth": {
        "category": "Storage Providers",
        "description": "Use OAuth instead of service account for Google Drive",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "google_drive_client_id": {
        "category": "Storage Providers",
        "description": "Google Drive OAuth client ID",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "google_drive_client_secret": {
        "category": "Storage Providers",
        "description": "Google Drive OAuth client secret",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "google_drive_refresh_token": {
        "category": "Storage Providers",
        "description": "Google Drive OAuth refresh token",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    
    # Storage Providers - OneDrive
    "onedrive_client_id": {
        "category": "Storage Providers",
        "description": "OneDrive OAuth client ID",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "onedrive_client_secret": {
        "category": "Storage Providers",
        "description": "OneDrive OAuth client secret",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "onedrive_tenant_id": {
        "category": "Storage Providers",
        "description": "OneDrive tenant ID (use 'common' for personal accounts)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "onedrive_refresh_token": {
        "category": "Storage Providers",
        "description": "OneDrive OAuth refresh token",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "onedrive_folder_path": {
        "category": "Storage Providers",
        "description": "OneDrive folder path for document storage",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    
    # Storage Providers - WebDAV
    "webdav_url": {
        "category": "Storage Providers",
        "description": "WebDAV server URL",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "webdav_username": {
        "category": "Storage Providers",
        "description": "WebDAV username for authentication",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "webdav_password": {
        "category": "Storage Providers",
        "description": "WebDAV password for authentication",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "webdav_folder": {
        "category": "Storage Providers",
        "description": "WebDAV folder path for document storage",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "webdav_verify_ssl": {
        "category": "Storage Providers",
        "description": "Verify SSL certificates for WebDAV connections",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    
    # Storage Providers - FTP
    "ftp_host": {
        "category": "Storage Providers",
        "description": "FTP server hostname or IP address",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "ftp_port": {
        "category": "Storage Providers",
        "description": "FTP server port (default: 21)",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "ftp_username": {
        "category": "Storage Providers",
        "description": "FTP username for authentication",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "ftp_password": {
        "category": "Storage Providers",
        "description": "FTP password for authentication",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "ftp_folder": {
        "category": "Storage Providers",
        "description": "FTP folder path for document storage",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "ftp_use_tls": {
        "category": "Storage Providers",
        "description": "Use TLS encryption for FTP connections (FTPS)",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "ftp_allow_plaintext": {
        "category": "Storage Providers",
        "description": "Allow fallback to plaintext FTP if TLS fails",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    
    # Storage Providers - SFTP
    "sftp_host": {
        "category": "Storage Providers",
        "description": "SFTP server hostname or IP address",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "sftp_port": {
        "category": "Storage Providers",
        "description": "SFTP server port (default: 22)",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "sftp_username": {
        "category": "Storage Providers",
        "description": "SFTP username for authentication",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "sftp_password": {
        "category": "Storage Providers",
        "description": "SFTP password for authentication",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "sftp_folder": {
        "category": "Storage Providers",
        "description": "SFTP folder path for document storage",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "sftp_private_key": {
        "category": "Storage Providers",
        "description": "SFTP private key for key-based authentication",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "sftp_private_key_passphrase": {
        "category": "Storage Providers",
        "description": "Passphrase for encrypted SFTP private key",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "sftp_disable_host_key_verification": {
        "category": "Storage Providers",
        "description": "Disable host key verification (not recommended for production)",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    
    # Storage Providers - AWS S3
    "aws_access_key_id": {
        "category": "Storage Providers",
        "description": "AWS access key ID for S3",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "aws_secret_access_key": {
        "category": "Storage Providers",
        "description": "AWS secret access key for S3",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "aws_region": {
        "category": "Storage Providers",
        "description": "AWS region for S3 bucket (default: us-east-1)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "s3_bucket_name": {
        "category": "Storage Providers",
        "description": "S3 bucket name for document storage",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "s3_folder_prefix": {
        "category": "Storage Providers",
        "description": "Optional folder prefix in S3 bucket (e.g., 'uploads/')",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "s3_storage_class": {
        "category": "Storage Providers",
        "description": "S3 storage class (e.g., STANDARD, INTELLIGENT_TIERING)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "s3_acl": {
        "category": "Storage Providers",
        "description": "S3 object ACL (e.g., private, public-read)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    
    # Email Settings
    "email_host": {
        "category": "Email",
        "description": "SMTP server hostname",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "email_port": {
        "category": "Email",
        "description": "SMTP server port (default: 587)",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "email_username": {
        "category": "Email",
        "description": "SMTP username for authentication",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "email_password": {
        "category": "Email",
        "description": "SMTP password for authentication",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "email_use_tls": {
        "category": "Email",
        "description": "Use TLS encryption for SMTP",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "email_sender": {
        "category": "Email",
        "description": "From address for outgoing emails (defaults to email_username)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "email_default_recipient": {
        "category": "Email",
        "description": "Default recipient email address",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    
    # IMAP Settings - Account 1
    "imap1_host": {
        "category": "IMAP",
        "description": "IMAP server hostname for account 1",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "imap1_port": {
        "category": "IMAP",
        "description": "IMAP server port for account 1 (default: 993)",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "imap1_username": {
        "category": "IMAP",
        "description": "IMAP username for account 1",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "imap1_password": {
        "category": "IMAP",
        "description": "IMAP password for account 1",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "imap1_ssl": {
        "category": "IMAP",
        "description": "Use SSL for IMAP account 1",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "imap1_poll_interval_minutes": {
        "category": "IMAP",
        "description": "Poll interval in minutes for IMAP account 1 (default: 5)",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "imap1_delete_after_process": {
        "category": "IMAP",
        "description": "Delete emails after processing for IMAP account 1",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    
    # IMAP Settings - Account 2
    "imap2_host": {
        "category": "IMAP",
        "description": "IMAP server hostname for account 2",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "imap2_port": {
        "category": "IMAP",
        "description": "IMAP server port for account 2 (default: 993)",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "imap2_username": {
        "category": "IMAP",
        "description": "IMAP username for account 2",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "imap2_password": {
        "category": "IMAP",
        "description": "IMAP password for account 2",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "imap2_ssl": {
        "category": "IMAP",
        "description": "Use SSL for IMAP account 2",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "imap2_poll_interval_minutes": {
        "category": "IMAP",
        "description": "Poll interval in minutes for IMAP account 2 (default: 10)",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "imap2_delete_after_process": {
        "category": "IMAP",
        "description": "Delete emails after processing for IMAP account 2",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    
    # Monitoring - Uptime Kuma
    "uptime_kuma_url": {
        "category": "Monitoring",
        "description": "Uptime Kuma push monitor URL",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "uptime_kuma_ping_interval": {
        "category": "Monitoring",
        "description": "Uptime Kuma ping interval in minutes (default: 5)",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    
    # Processing Settings
    "http_request_timeout": {
        "category": "Processing",
        "description": "Timeout for HTTP requests in seconds (default: 120)",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "processall_throttle_threshold": {
        "category": "Processing",
        "description": "Number of files above which throttling is applied in /processall",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "processall_throttle_delay": {
        "category": "Processing",
        "description": "Delay in seconds between task submissions when throttling in /processall",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    
    # Notifications Settings
    "notification_urls": {
        "category": "Notifications",
        "description": "Comma-separated list of Apprise notification URLs (e.g., discord://, telegram://)",
        "type": "list",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "notify_on_task_failure": {
        "category": "Notifications",
        "description": "Send notifications when Celery tasks fail",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "notify_on_credential_failure": {
        "category": "Notifications",
        "description": "Send notifications when credential checks fail",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "notify_on_startup": {
        "category": "Notifications",
        "description": "Send notifications when application starts",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "notify_on_shutdown": {
        "category": "Notifications",
        "description": "Send notifications when application shuts down",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "notify_on_file_processed": {
        "category": "Notifications",
        "description": "Send notifications when files are successfully processed",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    
    # Feature Flags
    "allow_file_delete": {
        "category": "Feature Flags",
        "description": "Allow deleting files from the database",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
}


def get_setting_from_db(db: Session, key: str) -> Optional[str]:
    """
    Retrieve a setting value from the database.
    
    Automatically decrypts sensitive values if encryption is enabled.
    
    Args:
        db: Database session
        key: Setting key to retrieve
        
    Returns:
        Setting value as string (decrypted if necessary), or None if not found
    """
    try:
        setting = db.query(ApplicationSettings).filter(ApplicationSettings.key == key).first()
        if not setting:
            return None
        
        # Check if this setting is sensitive and should be decrypted
        metadata = get_setting_metadata(key)
        if metadata.get("sensitive", False):
            from app.utils.encryption import decrypt_value
            return decrypt_value(setting.value)
        
        return setting.value
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving setting {key} from database: {e}")
        return None


def save_setting_to_db(db: Session, key: str, value: Optional[str]) -> bool:
    """
    Save or update a setting in the database.
    
    Automatically encrypts sensitive values if encryption is enabled.
    
    Args:
        db: Database session
        key: Setting key
        value: Setting value (as string)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Check if this setting is sensitive and should be encrypted
        metadata = get_setting_metadata(key)
        storage_value = value
        
        if metadata.get("sensitive", False) and value:
            from app.utils.encryption import encrypt_value, is_encryption_available
            
            if is_encryption_available():
                storage_value = encrypt_value(value)
                logger.debug(f"Encrypted sensitive setting: {key}")
            else:
                logger.warning(f"Storing sensitive setting {key} in plaintext (encryption unavailable)")
        
        setting = db.query(ApplicationSettings).filter(ApplicationSettings.key == key).first()
        if setting:
            setting.value = storage_value
        else:
            setting = ApplicationSettings(key=key, value=storage_value)
            db.add(setting)
        db.commit()
        logger.info(f"Saved setting {key} to database")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Error saving setting {key} to database: {e}")
        db.rollback()
        return False


def get_all_settings_from_db(db: Session) -> Dict[str, str]:
    """
    Retrieve all settings from the database.
    
    Automatically decrypts sensitive values if encryption is enabled.
    
    Args:
        db: Database session
        
    Returns:
        Dictionary of setting key-value pairs (decrypted)
    """
    try:
        settings = db.query(ApplicationSettings).all()
        result = {}
        
        for setting in settings:
            # Check if this setting is sensitive and should be decrypted
            metadata = get_setting_metadata(setting.key)
            if metadata.get("sensitive", False):
                from app.utils.encryption import decrypt_value
                result[setting.key] = decrypt_value(setting.value)
            else:
                result[setting.key] = setting.value
        
        return result
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving all settings from database: {e}")
        return {}


def delete_setting_from_db(db: Session, key: str) -> bool:
    """
    Delete a setting from the database.
    
    Args:
        db: Database session
        key: Setting key to delete
        
    Returns:
        True if successful, False otherwise
    """
    try:
        setting = db.query(ApplicationSettings).filter(ApplicationSettings.key == key).first()
        if setting:
            db.delete(setting)
            db.commit()
            logger.info(f"Deleted setting {key} from database")
            return True
        return False
    except SQLAlchemyError as e:
        logger.error(f"Error deleting setting {key} from database: {e}")
        db.rollback()
        return False


def get_setting_metadata(key: str) -> Dict[str, Any]:
    """
    Get metadata for a specific setting.
    
    Args:
        key: Setting key
        
    Returns:
        Dictionary containing setting metadata
    """
    return SETTING_METADATA.get(key, {
        "category": "Other",
        "description": f"Setting: {key}",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    })


def get_settings_by_category() -> Dict[str, List[str]]:
    """
    Get settings organized by category.
    
    Returns:
        Dictionary mapping category names to lists of setting keys
    """
    categories = {}
    for key, metadata in SETTING_METADATA.items():
        category = metadata.get("category", "Other")
        if category not in categories:
            categories[category] = []
        categories[category].append(key)
    return categories


def validate_setting_value(key: str, value: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a setting value based on its metadata.
    
    Args:
        key: Setting key
        value: Setting value to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    metadata = get_setting_metadata(key)
    setting_type = metadata.get("type", "string")
    
    # Check required fields
    if metadata.get("required", False) and not value:
        return False, f"{key} is required"
    
    # Type-specific validation
    if setting_type == "boolean":
        if value.lower() not in ["true", "false", "1", "0", "yes", "no"]:
            return False, f"{key} must be a boolean value (true/false)"
    
    elif setting_type == "integer":
        try:
            int(value)
        except ValueError:
            return False, f"{key} must be an integer"
    
    # Special validation for specific keys
    if key == "session_secret" and value and len(value) < 32:
        return False, "session_secret must be at least 32 characters"
    
    return True, None
