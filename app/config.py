#!/usr/bin/env python3

import json
import os
from typing import Any, List, Optional, Union

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str
    redis_url: str
    openai_api_key: str
    openai_base_url: str = "https://api.openai.com/v1"  # Default to OpenAI's endpoint
    openai_model: str = "gpt-4o-mini"  # Default model

    # AI provider abstraction layer
    # Supported values: openai, azure, anthropic, gemini, ollama, openrouter, litellm
    ai_provider: str = "openai"
    # Override model for any provider; falls back to openai_model when not set
    ai_model: Optional[str] = None

    # Anthropic Claude settings (used when ai_provider="anthropic")
    anthropic_api_key: Optional[str] = None

    # Google Gemini settings (used when ai_provider="gemini")
    gemini_api_key: Optional[str] = None

    # Ollama local LLM settings (used when ai_provider="ollama")
    ollama_base_url: str = "http://localhost:11434"

    # OpenRouter settings (used when ai_provider="openrouter")
    openrouter_api_key: Optional[str] = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Portkey AI gateway settings (used when ai_provider="portkey")
    # See https://portkey.ai for setup instructions
    portkey_api_key: Optional[str] = None
    portkey_virtual_key: Optional[str] = None  # Routes to a specific provider via Portkey vault
    portkey_config: Optional[str] = None  # Portkey Config ID for advanced routing rules
    portkey_base_url: str = "https://api.portkey.ai/v1"

    # Azure OpenAI API version (used when ai_provider="azure")
    azure_openai_api_version: str = "2024-02-01"
    workdir: str
    debug: bool = False  # Default to False

    # Logging level for the application.  Accepts standard Python level names:
    # DEBUG, INFO, WARNING, ERROR, CRITICAL.  When *debug* is True and
    # *log_level* has not been explicitly set, the effective level is forced to
    # DEBUG so that all ``logger.debug()`` calls produce output.
    log_level: str = Field(
        default="INFO",
        description=(
            "Python logging level for the application root logger.  "
            "Accepts: DEBUG, INFO, WARNING, ERROR, CRITICAL.  "
            "When DEBUG=True and LOG_LEVEL is not explicitly set, "
            "the effective level is automatically lowered to DEBUG."
        ),
    )

    # Log output format.  ``text`` is the human-readable default.
    # ``json`` emits one JSON object per line, ideal for log collectors
    # (Promtail, Fluentd, Filebeat, Datadog agent) and SIEM ingestion.
    log_format: str = Field(
        default="text",
        description=(
            "Log output format: 'text' (human-readable, default) or "
            "'json' (structured JSON lines for SIEM / log aggregation)."
        ),
    )

    # Optional syslog forwarding for application logs (not just audit events).
    # When enabled, a Python SysLogHandler is added to the root logger so that
    # every log message is also sent to the configured syslog receiver.
    log_syslog_enabled: bool = Field(
        default=False,
        description="Forward application logs to a syslog receiver in addition to stdout.",
    )
    log_syslog_host: str = Field(
        default="localhost",
        description="Hostname or IP of the syslog receiver for application logs.",
    )
    log_syslog_port: int = Field(
        default=514,
        description="Port of the syslog receiver for application logs.",
    )
    log_syslog_protocol: str = Field(
        default="udp",
        description="Protocol for syslog transport: 'udp' or 'tcp'.",
    )

    # Making Dropbox optional
    dropbox_enabled: bool = Field(
        default=True,
        description="Enable Dropbox as an upload destination. Set to False to disable uploads even when credentials are configured.",
    )
    dropbox_app_key: Optional[str] = None
    dropbox_app_secret: Optional[str] = None
    dropbox_folder: Optional[str] = None
    dropbox_refresh_token: Optional[str] = None

    # Making Nextcloud optional
    nextcloud_enabled: bool = Field(
        default=True,
        description="Enable Nextcloud as an upload destination. Set to False to disable uploads even when credentials are configured.",
    )
    nextcloud_upload_url: Optional[str] = None
    nextcloud_username: Optional[str] = None
    nextcloud_password: Optional[str] = None
    nextcloud_folder: Optional[str] = None

    # Making Paperless optional
    paperless_enabled: bool = Field(
        default=True,
        description="Enable Paperless-ngx as an upload destination. Set to False to disable uploads even when credentials are configured.",
    )
    paperless_ngx_api_token: Optional[str] = None
    paperless_host: Optional[str] = None
    paperless_custom_field_absender: Optional[str] = None  # Name of the "absender" custom field in Paperless
    # JSON mapping of metadata field names to Paperless custom field names
    # Example: {"absender": "Sender", "empfaenger": "Recipient",
    #           "language": "Language", "correspondent": "Correspondent"}
    paperless_custom_fields_mapping: Optional[str] = None

    azure_ai_key: str
    azure_region: str
    azure_endpoint: str
    gotenberg_url: str

    # ---------------------------------------------------------------------------
    # OCR provider settings
    # ---------------------------------------------------------------------------
    # Comma-separated list of OCR engines to use.
    # Supported values: azure, tesseract, easyocr, mistral, google_docai, aws_textract
    # When multiple engines are listed all are run and results are merged.
    # Example: OCR_PROVIDERS=azure,tesseract
    ocr_providers: str = "azure"

    # Strategy for merging results from multiple OCR providers.
    # - ai_merge  : Ask the AI model to produce the best merged text (default).
    # - longest   : Return the result with the most characters.
    # - primary   : Return only the first provider's result (no merging).
    ocr_merge_strategy: str = "ai_merge"

    # Tesseract OCR settings (used when "tesseract" is in OCR_PROVIDERS)
    tesseract_cmd: Optional[str] = None  # Path to tesseract binary (e.g. /usr/bin/tesseract)
    tesseract_language: str = "eng+deu"  # Tesseract language code(s), e.g. "eng" or "eng+deu"

    # EasyOCR settings (used when "easyocr" is in OCR_PROVIDERS)
    easyocr_languages: str = "en,de"  # Comma-separated language codes, e.g. "en,de,fr"
    easyocr_gpu: bool = False  # Enable GPU acceleration for EasyOCR

    # Mistral OCR settings (used when "mistral" is in OCR_PROVIDERS)
    mistral_api_key: Optional[str] = None
    mistral_ocr_model: str = "mistral-ocr-latest"

    # Google Cloud Document AI settings (used when "google_docai" is in OCR_PROVIDERS)
    # Falls back to google_drive_credentials_json for service account credentials.
    google_docai_credentials_json: Optional[str] = None
    google_docai_project_id: Optional[str] = None
    google_docai_processor_id: Optional[str] = None
    google_docai_location: str = "us"  # Processor location, e.g. "us" or "eu"
    external_hostname: str = "localhost"  # Default to localhost

    # Authentication settings
    auth_enabled: bool = True  # Default to enabled
    admin_username: Optional[str] = None
    admin_password: Optional[str] = None
    session_secret: Optional[str] = None
    admin_group_name: str = "admin"

    # Multi-user settings
    multi_user_enabled: bool = Field(
        default=False,
        description=(
            "Enable multi-user mode with individual document spaces per user. "
            "When enabled, each authenticated user sees only their own documents, "
            "uploads, and search results. Shared settings (AI, OCR) remain global. "
            "Requires auth_enabled=True. Default: False (single-user/shared mode)."
        ),
    )
    default_daily_upload_limit: int = Field(
        default=0,
        description=(
            "Default maximum number of document uploads allowed per user per day "
            "in multi-user mode. Set to 0 for unlimited. "
            "Individual user limits can override this default. Default: 0 (unlimited)."
        ),
    )
    unowned_docs_visible_to_all: bool = Field(
        default=True,
        description=(
            "In multi-user mode, controls whether documents without an owner (owner_id is NULL) "
            "are visible to all authenticated users. When True, unowned documents appear in every "
            "user's file list alongside their own files. When False, only admins can see unowned "
            "documents. Default: True."
        ),
    )
    default_owner_id: Optional[str] = Field(
        default=None,
        description=(
            "When set, automatically assigns this owner ID to newly ingested documents that would "
            "otherwise have no owner (e.g. documents from IMAP, API without session, or legacy imports). "
            "Use the admin /api/files/assign-owner endpoint to bulk-assign existing unclaimed documents. "
            "Default: None (documents remain unowned until claimed)."
        ),
    )

    subscription_overage_percent: int = Field(
        default=20,
        ge=0,
        le=200,
        description=(
            "Soft-limit overage buffer in percent (0–200). The announced monthly quota is "
            "increased by this percentage for actual enforcement. E.g. 20 means a 150-doc/month "
            "plan enforces at 180 docs (150 × 1.20). Set 0 to enforce exactly at the announced "
            "limit. Per-plan overage_percent (set in Plan Designer) overrides this global default. "
            "Default: 20."
        ),
    )

    # Authentik / Generic OIDC
    authentik_client_id: Optional[str] = None
    authentik_client_secret: Optional[str] = None
    authentik_config_url: Optional[str] = None
    oauth_provider_name: Optional[str] = None  # Name to display for the OAuth provider

    # Social Login Providers
    # Google OAuth2
    social_auth_google_enabled: bool = False
    social_auth_google_client_id: Optional[str] = None
    social_auth_google_client_secret: Optional[str] = None

    # Microsoft OAuth2 (Azure AD / Microsoft Entra ID)
    social_auth_microsoft_enabled: bool = False
    social_auth_microsoft_client_id: Optional[str] = None
    social_auth_microsoft_client_secret: Optional[str] = None
    social_auth_microsoft_tenant: str = Field(
        default="common",
        description=(
            "Azure AD tenant ID or one of 'common', 'organizations', 'consumers'. "
            "Use 'common' to allow any Microsoft account and any Azure AD org. "
            "Use a specific tenant ID (GUID) to restrict to a single organization. "
            "Default: common."
        ),
    )

    # Apple Sign-In
    social_auth_apple_enabled: bool = False
    social_auth_apple_client_id: Optional[str] = None
    social_auth_apple_team_id: Optional[str] = None
    social_auth_apple_key_id: Optional[str] = None
    social_auth_apple_private_key: Optional[str] = None

    # Dropbox OAuth2
    social_auth_dropbox_enabled: bool = False
    social_auth_dropbox_client_id: Optional[str] = None
    social_auth_dropbox_client_secret: Optional[str] = None

    # Local user signup
    allow_local_signup: bool = Field(
        default=False,
        description=(
            "Allow users to self-register with email and password. "
            "Has no effect unless MULTI_USER_ENABLED is also True. "
            "Requires SMTP to be configured so verification emails can be sent. "
            "Default: False (registration disabled — admin creates users manually)."
        ),
    )

    # Stripe billing
    stripe_secret_key: Optional[str] = None
    stripe_publishable_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    stripe_success_url: Optional[str] = None  # e.g. https://app.example.com/billing/success
    stripe_cancel_url: Optional[str] = None  # e.g. https://app.example.com/pricing

    # ---------------------------------------------------------------------------
    # Watch Folder Ingestion
    # ---------------------------------------------------------------------------
    # Local filesystem watch folders (comma-separated list of absolute paths).
    # DocuElevate will poll each path for new files and automatically ingest them.
    # Works with any mounted path, including SMB/CIFS (via system mount), NFS, etc.
    # Example: /watchfolders/scanner,/mnt/shared/inbox
    watch_folders: Optional[str] = Field(
        default=None,
        description=(
            "Comma-separated list of local filesystem paths (absolute) that DocuElevate will "
            "poll for new files to ingest. Each file found is enqueued for document processing. "
            "Works with any mounted path including SMB/CIFS (mounted via system) and NFS. "
            "Example: /watchfolders/scanner,/mnt/shared/inbox"
        ),
    )
    watch_folder_poll_interval: int = Field(
        default=1,
        description=("Poll interval in minutes for local watch folder scanning. Default: 1 minute."),
    )
    watch_folder_delete_after_process: bool = Field(
        default=False,
        description=(
            "Delete files from local watch folders after they have been successfully enqueued "
            "for processing. When False (default), files are left in place and tracked via a "
            "cache file to avoid re-ingesting them."
        ),
    )

    # FTP Ingest / Watch Folder
    # Uses the existing FTP credentials (ftp_host, ftp_username, ftp_password) to poll
    # a source folder on the FTP server for new files to ingest.
    ftp_ingest_folder: Optional[str] = Field(
        default=None,
        description=(
            "FTP folder path to monitor for new files to ingest. "
            "Uses the existing FTP connection settings (FTP_HOST, FTP_USERNAME, FTP_PASSWORD). "
            "When set, DocuElevate will periodically poll this folder and download new files for processing."
        ),
    )
    ftp_ingest_enabled: bool = Field(
        default=False,
        description="Enable FTP watch folder ingestion. Requires FTP_INGEST_FOLDER and FTP connection settings.",
    )
    ftp_ingest_delete_after_process: bool = Field(
        default=False,
        description=(
            "Delete files from the FTP ingest folder after they have been successfully downloaded "
            "and enqueued for processing. Default: False (files are left in place)."
        ),
    )

    # SFTP Ingest / Watch Folder
    # Uses the existing SFTP credentials (sftp_host, sftp_username, sftp_password/sftp_private_key)
    # to poll a source folder on the SFTP server for new files to ingest.
    sftp_ingest_folder: Optional[str] = Field(
        default=None,
        description=(
            "SFTP folder path to monitor for new files to ingest. "
            "Uses the existing SFTP connection settings (SFTP_HOST, SFTP_USERNAME, SFTP_PASSWORD/SFTP_PRIVATE_KEY). "
            "When set, DocuElevate will periodically poll this folder and download new files for processing."
        ),
    )
    sftp_ingest_enabled: bool = Field(
        default=False,
        description="Enable SFTP watch folder ingestion. Requires SFTP_INGEST_FOLDER and SFTP connection settings.",
    )
    sftp_ingest_delete_after_process: bool = Field(
        default=False,
        description=(
            "Delete files from the SFTP ingest folder after they have been successfully downloaded "
            "and enqueued for processing. Default: False (files are left in place)."
        ),
    )

    # ---------------------------------------------------------------------------
    # Cloud Provider Watch Folders
    # ---------------------------------------------------------------------------
    # Each cloud provider has three settings:
    #   <provider>_ingest_enabled  — enable the watch-folder for this provider
    #   <provider>_ingest_folder   — the remote path / folder ID to poll
    #   <provider>_ingest_delete_after_process — delete from cloud after download

    # Dropbox ingest — reuses existing Dropbox OAuth credentials
    dropbox_ingest_enabled: bool = Field(
        default=False,
        description="Enable Dropbox watch folder ingestion. Requires Dropbox OAuth credentials.",
    )
    dropbox_ingest_folder: Optional[str] = Field(
        default=None,
        description=(
            "Dropbox folder path to poll for new files to ingest (e.g. /Inbox/Scanner). "
            "Uses the existing Dropbox OAuth credentials."
        ),
    )
    dropbox_ingest_delete_after_process: bool = Field(
        default=False,
        description="Delete files from Dropbox ingest folder after download and enqueue.",
    )

    # Google Drive ingest — reuses existing Google Drive credentials
    google_drive_ingest_enabled: bool = Field(
        default=False,
        description="Enable Google Drive watch folder ingestion. Requires Google Drive credentials.",
    )
    google_drive_ingest_folder_id: Optional[str] = Field(
        default=None,
        description=(
            "Google Drive folder ID to poll for new files to ingest. "
            "Uses the existing Google Drive service-account or OAuth credentials."
        ),
    )
    google_drive_ingest_delete_after_process: bool = Field(
        default=False,
        description="Delete files from Google Drive ingest folder after download and enqueue.",
    )

    # OneDrive ingest — reuses existing OneDrive MSAL credentials
    onedrive_ingest_enabled: bool = Field(
        default=False,
        description="Enable OneDrive watch folder ingestion. Requires OneDrive MSAL credentials.",
    )
    onedrive_ingest_folder_path: Optional[str] = Field(
        default=None,
        description=(
            "OneDrive folder path to poll for new files to ingest (e.g. /Inbox/Scanner). "
            "Uses the existing OneDrive client credentials."
        ),
    )
    onedrive_ingest_delete_after_process: bool = Field(
        default=False,
        description="Delete files from OneDrive ingest folder after download and enqueue.",
    )

    # Nextcloud ingest — reuses existing Nextcloud WebDAV credentials
    nextcloud_ingest_enabled: bool = Field(
        default=False,
        description="Enable Nextcloud watch folder ingestion. Requires Nextcloud WebDAV credentials.",
    )
    nextcloud_ingest_folder: Optional[str] = Field(
        default=None,
        description=(
            "Nextcloud folder path to poll for new files to ingest (e.g. /Scans/Inbox). "
            "Uses the existing Nextcloud upload URL and credentials."
        ),
    )
    nextcloud_ingest_delete_after_process: bool = Field(
        default=False,
        description="Delete files from Nextcloud ingest folder after download and enqueue.",
    )

    # S3 ingest — reuses existing AWS/S3 credentials
    s3_ingest_enabled: bool = Field(
        default=False,
        description="Enable Amazon S3 watch folder (prefix) ingestion. Requires S3 credentials.",
    )
    s3_ingest_prefix: Optional[str] = Field(
        default=None,
        description=(
            "S3 key prefix to poll for new objects to ingest (e.g. inbox/scanner/). "
            "Uses the existing S3 bucket and AWS credentials."
        ),
    )
    s3_ingest_delete_after_process: bool = Field(
        default=False,
        description="Delete objects from S3 ingest prefix after download and enqueue.",
    )

    # WebDAV ingest — reuses existing WebDAV credentials
    webdav_ingest_enabled: bool = Field(
        default=False,
        description="Enable WebDAV watch folder ingestion. Requires WebDAV URL and credentials.",
    )
    webdav_ingest_folder: Optional[str] = Field(
        default=None,
        description=(
            "WebDAV folder path to poll for new files to ingest (e.g. /remote.php/webdav/Inbox). "
            "Uses the existing WebDAV URL and credentials."
        ),
    )
    webdav_ingest_delete_after_process: bool = Field(
        default=False,
        description="Delete files from WebDAV ingest folder after download and enqueue.",
    )

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
    google_drive_enabled: bool = Field(
        default=True,
        description="Enable Google Drive as an upload destination. Set to False to disable uploads even when credentials are configured.",
    )
    google_drive_credentials_json: Optional[str] = ""
    google_drive_folder_id: Optional[str] = ""
    google_drive_delegate_to: Optional[str] = ""  # Optional delegated user email

    # Google Drive OAuth settings
    google_drive_use_oauth: bool = False  # Default to service account method
    google_drive_client_id: Optional[str] = ""
    google_drive_client_secret: Optional[str] = ""
    google_drive_refresh_token: Optional[str] = ""

    # WebDAV settings
    webdav_enabled: bool = Field(
        default=True,
        description="Enable WebDAV as an upload destination. Set to False to disable uploads even when credentials are configured.",
    )
    webdav_url: Optional[str] = None
    webdav_username: Optional[str] = None
    webdav_password: Optional[str] = None
    webdav_folder: Optional[str] = None
    webdav_verify_ssl: bool = True

    # FTP settings
    ftp_enabled: bool = Field(
        default=True,
        description="Enable FTP as an upload destination. Set to False to disable uploads even when credentials are configured.",
    )
    ftp_host: Optional[str] = None
    ftp_port: Optional[int] = 21
    ftp_username: Optional[str] = None
    ftp_password: Optional[str] = None
    ftp_folder: Optional[str] = None
    ftp_use_tls: bool = True  # Default to attempting TLS connection first
    ftp_allow_plaintext: bool = True  # Default to allowing plaintext fallback

    # SFTP settings
    sftp_enabled: bool = Field(
        default=True,
        description="Enable SFTP as an upload destination. Set to False to disable uploads even when credentials are configured.",
    )
    sftp_host: Optional[str] = None
    sftp_port: Optional[int] = 22
    sftp_username: Optional[str] = None
    sftp_password: Optional[str] = None
    sftp_folder: Optional[str] = None
    sftp_private_key: Optional[str] = None
    sftp_private_key_passphrase: Optional[str] = None
    # Security: Host key verification is enabled by default for security
    # In development/testing, set to True to disable verification (not recommended)
    sftp_disable_host_key_verification: bool = False  # Default enforces host key verification

    # Email settings (shared SMTP – used for password reset, verification emails, etc.)
    email_host: Optional[str] = None
    email_port: Optional[int] = 587
    email_username: Optional[str] = None
    email_password: Optional[str] = None
    email_use_tls: bool = True
    email_sender: Optional[str] = None  # From address, defaults to email_username if not set
    email_default_recipient: Optional[str] = None

    # Email destination settings (dedicated SMTP for document delivery – decoupled from shared email above)
    dest_email_enabled: bool = Field(
        default=True,
        description="Enable Email as an upload destination. Set to False to disable document delivery via email even when credentials are configured.",
    )
    dest_email_host: Optional[str] = None
    dest_email_port: Optional[int] = 587
    dest_email_username: Optional[str] = None
    dest_email_password: Optional[str] = None
    dest_email_use_tls: bool = True
    dest_email_sender: Optional[str] = None  # From address for delivered documents
    dest_email_default_recipient: Optional[str] = None  # Fallback recipient for document delivery

    # OneDrive settings
    onedrive_enabled: bool = Field(
        default=True,
        description="Enable OneDrive as an upload destination. Set to False to disable uploads even when credentials are configured.",
    )
    onedrive_client_id: Optional[str] = None
    onedrive_client_secret: Optional[str] = None
    onedrive_tenant_id: Optional[str] = "common"  # Default to "common" for personal accounts
    onedrive_refresh_token: Optional[str] = None  # Required for personal accounts
    onedrive_folder_path: Optional[str] = None

    # AWS S3 settings
    s3_enabled: bool = Field(
        default=True,
        description="Enable Amazon S3 as an upload destination. Set to False to disable uploads even when credentials are configured.",
    )
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: Optional[str] = "us-east-1"  # Default region
    s3_bucket_name: Optional[str] = None
    s3_folder_prefix: Optional[str] = ""  # Optional folder prefix (e.g. "uploads/")
    s3_storage_class: Optional[str] = "STANDARD"  # Default storage class
    s3_acl: Optional[str] = "private"  # Default ACL

    # iCloud Drive settings
    icloud_enabled: bool = Field(
        default=True,
        description="Enable iCloud Drive as an upload destination. Set to False to disable uploads even when credentials are configured.",
    )
    icloud_username: Optional[str] = None  # Apple ID email address
    icloud_password: Optional[str] = None  # App-specific password (required for 2FA accounts)
    icloud_folder: Optional[str] = None  # Target folder path in iCloud Drive (e.g. "Documents/Uploads")
    icloud_cookie_directory: Optional[str] = None  # Directory for session cookies (default: ~/.pyicloud)

    # Uptime Kuma settings
    uptime_kuma_url: Optional[str] = None
    uptime_kuma_ping_interval: int = 5  # Default ping interval in minutes

    # Meilisearch settings (full-text search engine)
    # Default uses the Docker Compose / K8s service name so container-to-container
    # networking works without any extra configuration.  Override to
    # "http://localhost:7700" only when running the API process outside of Docker.
    meilisearch_url: str = "http://meilisearch:7700"
    meilisearch_api_key: Optional[str] = None  # Master or API key (optional for local dev)
    meilisearch_index_name: str = "documents"
    enable_search: bool = True  # Enable Meilisearch full-text search integration

    # HTTP request settings
    http_request_timeout: int = 120  # Default timeout for HTTP requests in seconds (handles large file operations)

    # Feature flags
    allow_file_delete: bool = True  # Default to allowing file deletion from database
    compliance_enabled: bool = Field(
        default=True,
        description=(
            "Enable the compliance templates dashboard (GDPR, HIPAA, SOC 2). "
            "When enabled, admins can view compliance status and apply "
            "pre-built regulatory configurations. Default: True."
        ),
    )

    # PDF/A archival conversion settings
    enable_pdfa_conversion: bool = Field(
        default=False,
        description=(
            "Enable PDF/A archival variant generation. When enabled, PDF/A copies of both the "
            "original ingested file and the processed file are created and saved alongside the "
            "standard copies. Uses ocrmypdf with Ghostscript for the conversion. "
            "This may double or triple storage but provides better legal coverage. Default: False."
        ),
    )
    pdfa_format: str = Field(
        default="2",
        description=(
            "PDF/A format variant to produce. Passed to ocrmypdf --output-type pdfa-N. "
            "Valid values: '1' (PDF/A-1b), '2' (PDF/A-2b), '3' (PDF/A-3b). Default: '2'."
        ),
    )
    pdfa_upload_original: bool = Field(
        default=False,
        description=(
            "Upload the original-file PDF/A variant to all configured storage providers. "
            "Files are placed in the provider's folder + PDFA_UPLOAD_FOLDER subfolder. Default: False."
        ),
    )
    pdfa_upload_processed: bool = Field(
        default=False,
        description=(
            "Upload the processed-file PDF/A variant to all configured storage providers. "
            "Files are placed in the provider's folder + PDFA_UPLOAD_FOLDER subfolder. Default: False."
        ),
    )
    pdfa_upload_folder: str = Field(
        default="pdfa",
        description=(
            "Subfolder name appended to each storage provider's configured folder for PDF/A uploads. "
            "For example if Dropbox folder is '/Documents' and this is 'pdfa', PDF/A files go to "
            "'/Documents/pdfa'. Set to empty string to upload into the same folder. Default: 'pdfa'."
        ),
    )
    google_drive_pdfa_folder_id: str = Field(
        default="",
        description=(
            "Google Drive folder ID for PDF/A uploads. Since Google Drive uses IDs not paths, "
            "this must be set separately. If empty, uses the standard google_drive_folder_id."
        ),
    )
    pdfa_timestamp_enabled: bool = Field(
        default=False,
        description=(
            "Enable RFC 3161 timestamping of PDF/A files via a Timestamp Authority (TSA). "
            "Creates a .tsr file alongside each PDF/A file for legal proof of existence. "
            "Requires openssl binary on PATH. Default: False."
        ),
    )
    pdfa_timestamp_url: str = Field(
        default="https://freetsa.org/tsr",
        description=(
            "URL of the RFC 3161 Timestamp Authority. Default: FreeTSA (https://freetsa.org/tsr). "
            "Other options: GlobalSign, DigiStamp, or any RFC 3161-compliant TSA."
        ),
    )

    imap_readonly_mode: bool = Field(
        default=False,
        description=(
            "When enabled, IMAP processing will fetch and process attachments but will NOT modify "
            "the mailbox state (no starring, labeling, deleting, or flag changes). "
            "Use this for pre-production instances that share a mailbox with production to prevent "
            "preprod from interfering with production email processing."
        ),
    )

    imap_attachment_filter: str = Field(
        default="documents_only",
        description=(
            "Controls which attachment types are ingested from IMAP emails. "
            "Accepted values: "
            "'documents_only' – ingest only PDFs and office files (Word, Excel, PowerPoint, ODT, etc.); "
            "'all' – ingest all supported file types including images. "
            "This is the global default; individual user IMAP accounts can override it."
        ),
    )

    # Batch processing settings
    processall_throttle_threshold: int = Field(
        default=20,
        description="Number of files above which throttling is applied in /processall endpoint",
    )
    processall_throttle_delay: int = Field(
        default=3,
        description="Delay in seconds between each task submission when throttling in /processall",
    )

    # Client-side upload throttling settings (applied when uploading files via the web UI)
    upload_concurrency: int = Field(
        default=3,
        description=(
            "Maximum number of files uploaded simultaneously from the browser. "
            "Limits parallel uploads to prevent API overload when dragging directories. Default: 3."
        ),
    )
    upload_queue_delay_ms: int = Field(
        default=500,
        description=(
            "Delay in milliseconds between starting each upload slot when queue is active. "
            "Staggers upload starts to smooth out server load. Default: 500 ms."
        ),
    )

    # Notification settings
    notification_urls: Union[List[str], str] = Field(
        default_factory=list,
        description="List of Apprise notification URLs (e.g., discord://, telegram://, etc.)",
    )
    notify_on_task_failure: bool = Field(default=True, description="Send notifications when Celery tasks fail")
    notify_on_credential_failure: bool = Field(
        default=True, description="Send notifications when credential checks fail"
    )
    notify_on_startup: bool = Field(default=True, description="Send notifications when application starts")
    notify_on_shutdown: bool = Field(default=False, description="Send notifications when application shuts down")
    notify_on_file_processed: bool = Field(
        default=True,
        description="Send notifications when files are successfully processed",
    )
    notify_on_user_signup: bool = Field(
        default=True,
        description="Send admin notifications when a new user signs up",
    )
    notify_on_plan_change: bool = Field(
        default=True,
        description="Send admin notifications when a user changes their subscription plan",
    )
    notify_on_payment_issue: bool = Field(
        default=True,
        description="Send admin notifications when a payment issue is reported for a user",
    )

    # Webhook settings
    webhook_enabled: bool = Field(
        default=True,
        description="Enable webhook delivery for document events",
    )

    # ── Backup / restore settings ──────────────────────────────────────────────
    backup_enabled: bool = Field(
        default=True,
        description=(
            "Enable automatic scheduled database backups. "
            "When enabled, hourly, daily, and weekly backups are created automatically. Default: True."
        ),
    )
    backup_dir: Optional[str] = Field(
        default=None,
        description=("Directory where local backup archives are stored. Defaults to <workdir>/backups when not set."),
    )
    # Remote destination: one of s3, dropbox, google_drive, onedrive, nextcloud,
    # webdav, ftp, sftp, email, or empty/None for local-only.
    backup_remote_destination: Optional[str] = Field(
        default=None,
        description=(
            "Storage provider to upload remote backup copies to. "
            "Accepted values: s3, dropbox, google_drive, onedrive, nextcloud, webdav, ftp, sftp, email. "
            "Leave empty to keep backups local only."
        ),
    )
    backup_remote_folder: str = Field(
        default="backups",
        description=(
            "Sub-folder / key prefix used when uploading backup archives to the remote destination. Default: 'backups'."
        ),
    )
    # Retention counts (number of snapshots to keep per tier)
    backup_retain_hourly: int = Field(
        default=96,
        description="Number of hourly backups to retain (default 96 = 4 days × 24 h).",
    )
    backup_retain_daily: int = Field(
        default=21,
        description="Number of daily backups to retain (default 21 = 3 weeks).",
    )
    backup_retain_weekly: int = Field(
        default=13,
        description="Number of weekly backups to retain (default 13 ≈ 3 months / 91 days).",
    )

    # File upload size limits (for security - see SECURITY_AUDIT.md)
    max_upload_size: int = Field(
        default=1073741824,  # 1GB in bytes (1024 * 1024 * 1024)
        description="Maximum file upload size in bytes. Default: 1GB. Prevents resource exhaustion attacks.",
    )
    max_single_file_size: Optional[int] = Field(
        default=None,
        description=(
            "Maximum size for a single file chunk in bytes. If set and file exceeds this,"
            " it will be split into smaller chunks for processing. Default: None (no splitting)."
        ),
    )
    max_request_body_size: int = Field(
        default=1048576,  # 1MB in bytes (1024 * 1024)
        description=(
            "Maximum request body size in bytes for non-file-upload requests. Default: 1MB."
            " Prevents memory exhaustion attacks via oversized JSON/form payloads."
            " File uploads are governed by MAX_UPLOAD_SIZE instead."
        ),
    )

    # Deduplication settings - prevents processing of duplicate files
    enable_deduplication: bool = Field(
        default=True,
        description=(
            "Enable deduplication check before processing. If enabled, files with the same SHA-256 hash"
            " as previously processed files will not be processed again. Default: True (enabled)."
        ),
    )
    show_deduplication_step: bool = Field(
        default=True,
        description=(
            "Show the 'Check for Duplicates' step in processing history."
            " If False, the check is still performed but not displayed. Default: True."
        ),
    )
    near_duplicate_threshold: float = Field(
        default=0.85,
        description=(
            "Minimum cosine similarity score (0–1) between two documents' text embeddings to consider "
            "them near-duplicates.  Higher values require closer content matches.  Default: 0.85."
        ),
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description=(
            "Model name used for generating text embeddings via the OpenAI-compatible API.  "
            "Embeddings drive the document similarity feature.  Default: text-embedding-3-small."
        ),
    )
    embedding_max_tokens: int = Field(
        default=8000,
        description=(
            "Maximum number of tokens to send to the embedding model.  "
            "Text is truncated to approximately this many tokens (using a "
            "conservative 3-chars-per-token estimate) before calling the API.  "
            "Set this below the model's context window (e.g. 8000 for an 8192-token model)."
        ),
    )
    embedding_backfill_batch_size: int = Field(
        default=50,
        description=(
            "Maximum number of files to queue for embedding computation per "
            "backfill run.  Keeps the worker and embedding API load bounded."
        ),
    )

    # Text quality check - AI-based assessment of embedded PDF text
    enable_text_quality_check: bool = Field(
        default=True,
        description=(
            "Enable AI-based quality check for embedded PDF text. "
            "When enabled, text extracted from non-digital PDFs is evaluated by the AI model. "
            "If the text is poor quality (OCR artefacts, typos, incoherence), the file is "
            "re-processed with OCR instead of using the embedded text. "
            "Digitally-created PDFs (Word, LibreOffice, LaTeX, etc.) are always trusted and "
            "bypass the check. Default: True (enabled)."
        ),
    )
    text_quality_threshold: int = Field(
        default=85,
        description=(
            "Minimum quality score (0–100) required to accept embedded PDF text without re-OCR. "
            "Text scoring below this threshold is discarded and the file is re-processed with OCR. "
            "Default: 85. The stricter this value, the more files will be re-OCR'd."
        ),
    )
    text_quality_significant_issues: Union[List[str], str] = Field(
        default_factory=lambda: ["excessive_typos", "garbage_characters", "incoherent_text", "fragmented_sentences"],
        description=(
            "Comma-separated list of quality issue labels that force OCR re-run even when the quality "
            "score is above TEXT_QUALITY_THRESHOLD. Any of these issues present in the AI assessment "
            "will trigger re-OCR. Default: excessive_typos,garbage_characters,incoherent_text,fragmented_sentences"
        ),
    )

    # ---------------------------------------------------------------------------
    # Task retry settings (see app/tasks/retry_config.py)
    # ---------------------------------------------------------------------------
    task_retry_max_retries: int = Field(
        default=3,
        description=("Maximum number of automatic retry attempts for failed Celery tasks. Default: 3."),
    )
    task_retry_delays: Union[List[int], str] = Field(
        default_factory=lambda: [60, 300, 900],
        description=(
            "Comma-separated list of retry countdown values in seconds. "
            "Each value is the delay before the corresponding retry attempt. "
            "If a task fails more times than entries in this list, the last delay "
            "is doubled for each additional attempt. "
            "Default: 60,300,900 (1 min, 5 min, 15 min)."
        ),
    )
    task_retry_jitter: bool = Field(
        default=True,
        description=(
            "Apply ±20 % random jitter to retry countdowns to prevent "
            "thundering-herd problems when many tasks fail simultaneously. "
            "Default: True (enabled)."
        ),
    )

    # Processing step timeout - prevents files from getting stuck in "in_progress" state
    step_timeout: int = Field(
        default=600,
        description=(
            "Timeout in seconds for processing steps. If a step is 'in_progress' for longer than this,"
            " it will be marked as failed. Default: 600 seconds (10 minutes)."
        ),
    )

    # Security Headers Configuration (see SECURITY_AUDIT.md and docs/DeploymentGuide.md)
    # Disabled by default since most deployments use a reverse proxy (Traefik, Nginx, etc.)
    # that already adds these headers. Enable if deploying directly without a reverse proxy.
    security_headers_enabled: bool = Field(
        default=False,
        description="Enable security headers middleware. Set to True if deploying without reverse proxy.",
    )

    # Strict-Transport-Security (HSTS) - Forces HTTPS connections
    security_header_hsts_enabled: bool = Field(
        default=True, description="Enable HSTS header. Only effective over HTTPS."
    )
    security_header_hsts_value: str = Field(
        default="max-age=31536000; includeSubDomains",
        description="HSTS header value. Default: 1 year with subdomains.",
    )

    # Content-Security-Policy (CSP) - Controls resource loading
    security_header_csp_enabled: bool = Field(default=True, description="Enable CSP header.")
    security_header_csp_value: str = Field(
        default=(
            "default-src 'self'; script-src 'self' 'unsafe-inline';"
            " style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:;"
        ),
        description="CSP header value. Customize based on your application's resource loading needs.",
    )

    # X-Frame-Options - Prevents clickjacking
    security_header_x_frame_options_enabled: bool = Field(default=True, description="Enable X-Frame-Options header.")
    security_header_x_frame_options_value: str = Field(
        default="DENY",
        description="X-Frame-Options header value. Options: DENY, SAMEORIGIN, or ALLOW-FROM uri",
    )

    # X-Content-Type-Options - Prevents MIME sniffing
    security_header_x_content_type_options_enabled: bool = Field(
        default=True,
        description="Enable X-Content-Type-Options header (always set to 'nosniff').",
    )

    # Audit Logging Configuration (see SECURITY_AUDIT.md – Infrastructure Security)
    # Logs every HTTP request and security-relevant events (auth failures, 5xx errors).
    # Sensitive query-parameter values (passwords, tokens, keys) are always masked.
    audit_logging_enabled: bool = Field(
        default=True,
        description=(
            "Enable audit/request logging middleware. Logs every HTTP request with "
            "method, path, status code, response time, and username. "
            "Sensitive query-parameter values are automatically masked."
        ),
    )
    audit_log_include_client_ip: bool = Field(
        default=True,
        description=(
            "Include the client IP address in audit log entries. "
            "Disable for privacy-sensitive deployments where IP logging is restricted."
        ),
    )

    # SIEM / External Audit Log Forwarding
    # Forward audit events to external SIEM systems for centralised monitoring.
    audit_siem_enabled: bool = Field(
        default=False,
        description="Enable forwarding of audit events to an external SIEM system.",
    )
    audit_siem_transport: str = Field(
        default="syslog",
        description=(
            "Transport used to forward audit events. "
            "Options: 'syslog' (RFC 5424 over UDP/TCP), 'http' (JSON POST to a webhook URL, "
            "compatible with Splunk HEC, Logstash HTTP input, Grafana Loki, etc.)."
        ),
    )
    audit_siem_syslog_host: str = Field(
        default="localhost",
        description="Hostname or IP of the syslog receiver.",
    )
    audit_siem_syslog_port: int = Field(
        default=514,
        description="Port of the syslog receiver.",
    )
    audit_siem_syslog_protocol: str = Field(
        default="udp",
        description="Protocol for syslog transport: 'udp' or 'tcp'.",
    )
    audit_siem_http_url: str = Field(
        default="",
        description=(
            "HTTP endpoint URL for SIEM webhook delivery. "
            "Supports Splunk HEC (https://splunk:8088/services/collector/event), "
            "Logstash HTTP input, Grafana Loki push API, or any JSON-accepting endpoint."
        ),
    )
    audit_siem_http_token: str = Field(
        default="",
        description="Bearer / HEC token included in the Authorization header of SIEM HTTP requests.",
    )
    audit_siem_http_custom_headers: str = Field(
        default="",
        description="Comma-separated 'Key:Value' pairs of extra headers for SIEM HTTP requests.",
    )

    # UI / Appearance
    ui_default_color_scheme: str = Field(
        default="system",
        description=(
            "Default color scheme for the web interface. "
            "Options: 'system' (follow OS preference), 'light', 'dark'. "
            "Individual users can override this with the in-app toggle; their choice is persisted in localStorage."
        ),
    )

    # Rate Limiting Configuration (see SECURITY_AUDIT.md and docs/API.md)
    # Protects against DoS attacks and API abuse
    rate_limiting_enabled: bool = Field(
        default=True,
        description="Enable rate limiting middleware. Recommended for production to prevent abuse.",
    )
    rate_limit_default: str = Field(
        default="100/minute",
        description="Default rate limit for all endpoints (format: 'count/period', e.g., '100/minute', '1000/hour').",
    )
    rate_limit_upload: str = Field(
        default="600/minute",
        description="Rate limit for file upload endpoints to prevent resource exhaustion.",
    )
    rate_limit_auth: str = Field(
        default="10/minute",
        description="Stricter rate limit for authentication endpoints to prevent brute force attacks.",
    )

    # CORS Configuration (see SECURITY_AUDIT.md – Infrastructure Security section)
    # Disabled by default since most deployments use a reverse proxy (Traefik, Nginx, etc.)
    # that already adds CORS headers. Enable only if deploying without a reverse proxy or if
    # the proxy does not handle CORS. See docs/DeploymentGuide.md for rationale.
    cors_enabled: bool = Field(
        default=False,
        description=(
            "Enable CORS middleware. Set to False if reverse proxy (Traefik, Nginx) handles CORS headers. "
            "When True, CORSMiddleware is added to the application with the settings below."
        ),
    )
    cors_allowed_origins: Union[List[str], str] = Field(
        default_factory=lambda: ["*"],
        description=(
            "List of allowed CORS origins. Use ['*'] to allow all origins (not recommended with "
            "cors_allow_credentials=True). Comma-separated string is also accepted via env var, "
            "e.g. CORS_ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com"
        ),
    )
    cors_allow_credentials: bool = Field(
        default=False,
        description=(
            "Allow credentials (cookies, Authorization headers) in CORS requests. "
            "Cannot be True when cors_allowed_origins=['*']. "
            "When True, set cors_allowed_origins to specific origins."
        ),
    )
    cors_allowed_methods: Union[List[str], str] = Field(
        default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        description="Allowed HTTP methods for CORS requests.",
    )
    cors_allowed_headers: Union[List[str], str] = Field(
        default_factory=lambda: ["*"],
        description="Allowed request headers for CORS. Use ['*'] to allow all headers.",
    )

    # ---------------------------------------------------------------------------
    # Support / Help Center – Zammad integration
    # ---------------------------------------------------------------------------
    zammad_url: Optional[str] = Field(
        default=None,
        description=(
            "Base URL of your Zammad instance (e.g. https://zammad.example.com). "
            "Required for the chat widget and feedback form on the Help Center page."
        ),
    )
    zammad_chat_enabled: bool = Field(
        default=False,
        description="Show the Zammad live-chat widget on the Help Center page.",
    )
    zammad_chat_id: int = Field(
        default=1,
        description="Zammad chat topic ID to use for the live-chat widget.",
    )
    zammad_form_enabled: bool = Field(
        default=False,
        description="Show the Zammad feedback / ticket form on the Help Center page.",
    )
    support_email: Optional[str] = Field(
        default=None,
        description="Support e-mail address displayed on the Help Center page.",
    )

    # ---------------------------------------------------------------------------
    # Observability – Sentry error & performance monitoring
    # ---------------------------------------------------------------------------
    sentry_dsn: Optional[str] = Field(
        default=None,
        description=(
            "Sentry Data Source Name (DSN).  When set, error reporting and "
            "performance tracing are enabled automatically.  Leave blank (or unset) "
            "to disable Sentry entirely."
        ),
    )
    sentry_environment: str = Field(
        default="production",
        description=(
            "Environment tag sent to Sentry (e.g. 'development', 'staging', 'production'). "
            "Helps you filter events in the Sentry dashboard."
        ),
    )
    sentry_traces_sample_rate: float = Field(
        default=0.1,
        description=(
            "Fraction of transactions to capture for performance monitoring (0.0–1.0). "
            "Set to 0.0 to disable tracing, 1.0 to capture every transaction. "
            "Values above 0 may increase Sentry quota usage."
        ),
    )
    sentry_profiles_sample_rate: float = Field(
        default=0.0,
        description=(
            "Fraction of profiled transactions to send to Sentry (0.0–1.0). "
            "Profiling is only active when traces_sample_rate > 0. "
            "Defaults to 0.0 (disabled) to minimise overhead."
        ),
    )
    sentry_send_default_pii: bool = Field(
        default=False,
        description=(
            "Whether to attach personally identifiable information (PII) – such as "
            "IP addresses and user agents – to Sentry events.  Disabled by default "
            "for privacy compliance (GDPR / CCPA).  Enable only if your Sentry "
            "project is configured to handle PII."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def strip_outer_quotes(cls, data: Any) -> Any:
        """
        Strip matching surrounding quotes from string values.

        In Kubernetes (and some other environments) env var values can arrive
        with literal quote characters included, e.g. the value for DATABASE_URL
        may be ``"postgresql://..."`` (with the quotes as part of the string)
        rather than just ``postgresql://...``.  Docker Compose strips these
        automatically; Kubernetes does not.
        """
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str) and len(value) >= 2:
                    if (value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'"):
                        data[key] = value[1:-1]
        return data

    @field_validator("notification_urls", mode="before")
    @classmethod
    def parse_notification_urls(cls, v: str | list[str]) -> list[str]:
        """Parse notification URLs from string or list"""
        if isinstance(v, str):
            if "," in v:
                return [url.strip() for url in v.split(",") if url.strip()]
            elif v.strip():
                return [v.strip()]
            return []
        return v

    @field_validator("text_quality_significant_issues", mode="before")
    @classmethod
    def parse_text_quality_significant_issues(cls, v: str | list[str]) -> list[str]:
        """Parse significant issue labels from comma-separated string or list."""
        if isinstance(v, str):
            if "," in v:
                return [item.strip() for item in v.split(",") if item.strip()]
            elif v.strip():
                return [v.strip()]
            return []
        return v

    @field_validator("cors_allowed_origins", "cors_allowed_methods", "cors_allowed_headers", mode="before")
    @classmethod
    def parse_comma_separated_list(cls, v: str | list[str]) -> list[str]:
        """Parse comma-separated string or list for CORS list settings."""
        if isinstance(v, str):
            if "," in v:
                return [item.strip() for item in v.split(",") if item.strip()]
            elif v.strip():
                return [v.strip()]
            return []
        return v

    @field_validator("task_retry_delays", mode="before")
    @classmethod
    def parse_task_retry_delays(cls, v: str | list) -> list[int]:
        """Parse task retry delays from comma-separated string or list of ints."""
        if isinstance(v, str):
            parts = [p.strip() for p in v.split(",") if p.strip()]
            return [int(p) for p in parts]
        return [int(item) for item in v]

    @field_validator("session_secret")
    @classmethod
    def validate_session_secret(cls, v: str | None, info: object) -> str | None:
        """Validate that session_secret is set and has sufficient length when auth is enabled"""
        if info.data.get("auth_enabled") and not v:
            raise ValueError("SESSION_SECRET must be set when AUTH_ENABLED=True")
        if info.data.get("auth_enabled") and v and len(v) < 32:
            raise ValueError("SESSION_SECRET must be at least 32 characters long")
        return v

    # Get build date from environment or file
    @property
    def build_date(self) -> str:
        # First try to get build date from environment
        env_build_date = os.environ.get("BUILD_DATE")
        if env_build_date:
            return env_build_date

        # Then try to get build date from BUILD_DATE file
        build_date_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "BUILD_DATE")
        if os.path.exists(build_date_file):
            with open(build_date_file, "r") as f:
                return f.read().strip()

        # Default to unknown if not found
        return "Unknown build date"

    # Get version from file or environment
    @property
    def version(self) -> str:
        # First try to get version from environment
        env_version = os.environ.get("APP_VERSION")
        if env_version:
            return env_version

        # Then try to get version from VERSION file
        version_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "VERSION")
        if os.path.exists(version_file):
            with open(version_file, "r") as f:
                return f.read().strip()

        # Default version if not found
        return "unknown"

    @property
    def git_sha(self) -> str:
        """Get Git commit SHA from environment or file."""
        # First try to get from environment
        env_sha = os.environ.get("GIT_COMMIT_SHA")
        if env_sha:
            return env_sha

        # Then try to get from GIT_SHA file
        git_sha_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "GIT_SHA")
        if os.path.exists(git_sha_file):
            with open(git_sha_file, "r") as f:
                return f.read().strip()

        # Default if not found
        return "unknown"

    @property
    def runtime_info(self) -> str:
        """Get runtime information from file."""
        runtime_info_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "RUNTIME_INFO")
        if os.path.exists(runtime_info_file):
            with open(runtime_info_file, "r") as f:
                return f.read().strip()

        # Return basic info if file not found
        return f"Version: {self.version}\nBuild Date: {self.build_date}\nGit SHA: {self.git_sha}"

    @property
    def release_name(self) -> str | None:
        """Get the release codename for the current version from release_names.json.

        Looks up the current version's minor version prefix (e.g., '0.5' for '0.5.3')
        in release_names.json to find the associated codename. Returns None if no
        codename is defined for the current version.

        Returns:
            The release codename string, or None if not found.
        """
        version = self.version
        if not version or version == "unknown":
            return None

        release_names_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "release_names.json")
        if not os.path.exists(release_names_file):
            return None

        try:
            with open(release_names_file, "r") as f:
                data = json.load(f)

            releases = data.get("releases", {})

            # Try exact version match first (e.g., "0.5.0")
            if version in releases:
                return releases[version].get("codename")

            # Try minor version prefix (e.g., "0.5" for "0.5.3")
            parts = version.split(".")
            if len(parts) >= 2:
                minor_prefix = f"{parts[0]}.{parts[1]}"
                if minor_prefix in releases:
                    return releases[minor_prefix].get("codename")

            # Try major version prefix (e.g., "1" for "1.0.0")
            if len(parts) >= 1:
                major_prefix = parts[0]
                if major_prefix in releases:
                    return releases[major_prefix].get("codename")

            return None
        except (json.JSONDecodeError, KeyError, IndexError):
            return None


settings = Settings()
