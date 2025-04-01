#!/usr/bin/env python3

from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    openai_api_key: str
    openai_base_url: str = "https://api.openai.com/v1"  # Default to OpenAI's endpoint
    openai_model: str = "gpt-4o-mini"  # Default model
    workdir: str
    
    # Making Dropbox optional
    dropbox_app_key: Optional[str] = None
    dropbox_app_secret: Optional[str] = None
    dropbox_folder: Optional[str] = None
    dropbox_refresh_token: Optional[str] = None
    
    # Making Nextcloud optional
    nextcloud_upload_url: Optional[str] = None
    nextcloud_username: Optional[str] = None
    nextcloud_password: Optional[str] = None
    nextcloud_folder: Optional[str] = None
    
    # Making Paperless optional
    paperless_ngx_api_token: Optional[str] = None
    paperless_host: Optional[str] = None
    
    azure_ai_key: str
    azure_region: str
    azure_endpoint: str
    gotenberg_url: str
    external_hostname: str = "localhost"  # Default to localhost

    # Authentik
    authentik_client_id: Optional[str] = None
    authentik_client_secret: Optional[str] = None
    authentik_config_url: Optional[str] = None
    auth_enabled: bool = True  # Default to enabled

    # IMAP 1
    imap1_host: Optional[str] = None
    imap1_port: Optional[int] = 993
    imap1_username: Optional[str] = None
    imap1_password: Optional[str] = None
    imap1_ssl: bool = True
    imap1_poll_interval_minutes: int = 5
    imap1_delete_after_process: bool = False

    # IMAP 2
    imap2_host: Optional[str] = None
    imap2_port: Optional[int] = 993
    imap2_username: Optional[str] = None
    imap2_password: Optional[str] = None
    imap2_ssl: bool = True
    imap2_poll_interval_minutes: int = 10
    imap2_delete_after_process: bool = False

    # Google Drive settings
    google_drive_credentials_json: str = ""
    google_drive_folder_id: str = ""
    google_drive_delegate_to: str = ""  # Optional delegated user email

    # WebDAV settings
    webdav_url: Optional[str] = None
    webdav_username: Optional[str] = None
    webdav_password: Optional[str] = None
    webdav_folder: Optional[str] = None
    webdav_verify_ssl: bool = True

    # FTP settings
    ftp_host: Optional[str] = None
    ftp_port: Optional[int] = 21
    ftp_username: Optional[str] = None
    ftp_password: Optional[str] = None
    ftp_folder: Optional[str] = None

    # SFTP settings
    sftp_host: Optional[str] = None
    sftp_port: Optional[int] = 22
    sftp_username: Optional[str] = None
    sftp_password: Optional[str] = None
    sftp_folder: Optional[str] = None
    sftp_private_key: Optional[str] = None
    sftp_private_key_passphrase: Optional[str] = None

    # Email settings
    email_host: Optional[str] = None
    email_port: Optional[int] = 587
    email_username: Optional[str] = None
    email_password: Optional[str] = None
    email_use_tls: bool = True
    email_sender: Optional[str] = None  # From address, defaults to email_username if not set
    email_default_recipient: Optional[str] = None

    # OneDrive settings
    onedrive_client_id: Optional[str] = None
    onedrive_client_secret: Optional[str] = None
    onedrive_tenant_id: Optional[str] = "common"  # Default to "common" for personal accounts
    onedrive_refresh_token: Optional[str] = None  # Required for personal accounts
    onedrive_folder_path: Optional[str] = None

    # AWS S3 settings
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: Optional[str] = "us-east-1"  # Default region
    s3_bucket_name: Optional[str] = None
    s3_folder_prefix: Optional[str] = ""  # Optional folder prefix (e.g. "uploads/")
    s3_storage_class: Optional[str] = "STANDARD"  # Default storage class
    s3_acl: Optional[str] = "private"  # Default ACL

    class Config:
        env_file = ".env"

settings = Settings()
