#!/usr/bin/env python3

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
    portkey_virtual_key: Optional[str] = None   # Routes to a specific provider via Portkey vault
    portkey_config: Optional[str] = None         # Portkey Config ID for advanced routing rules
    portkey_base_url: str = "https://api.portkey.ai/v1"

    # Azure OpenAI API version (used when ai_provider="azure")
    azure_openai_api_version: str = "2024-02-01"
    workdir: str
    debug: bool = False  # Default to False

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
    paperless_custom_field_absender: Optional[str] = None  # Name of the "absender" custom field in Paperless
    # JSON mapping of metadata field names to Paperless custom field names
    # Example: {"absender": "Sender", "empfaenger": "Recipient",
    #           "language": "Language", "correspondent": "Correspondent"}
    paperless_custom_fields_mapping: Optional[str] = None

    azure_ai_key: str
    azure_region: str
    azure_endpoint: str
    gotenberg_url: str
    external_hostname: str = "localhost"  # Default to localhost

    # Authentication settings
    auth_enabled: bool = True  # Default to enabled
    admin_username: Optional[str] = None
    admin_password: Optional[str] = None
    session_secret: Optional[str] = None
    admin_group_name: str = "admin"

    # Authentik
    authentik_client_id: Optional[str] = None
    authentik_client_secret: Optional[str] = None
    authentik_config_url: Optional[str] = None
    oauth_provider_name: Optional[str] = None  # Name to display for the OAuth provider

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
    google_drive_credentials_json: Optional[str] = ""
    google_drive_folder_id: Optional[str] = ""
    google_drive_delegate_to: Optional[str] = ""  # Optional delegated user email

    # Google Drive OAuth settings
    google_drive_use_oauth: bool = False  # Default to service account method
    google_drive_client_id: Optional[str] = ""
    google_drive_client_secret: Optional[str] = ""
    google_drive_refresh_token: Optional[str] = ""

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
    ftp_use_tls: bool = True  # Default to attempting TLS connection first
    ftp_allow_plaintext: bool = True  # Default to allowing plaintext fallback

    # SFTP settings
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

    # Uptime Kuma settings
    uptime_kuma_url: Optional[str] = None
    uptime_kuma_ping_interval: int = 5  # Default ping interval in minutes

    # HTTP request settings
    http_request_timeout: int = 120  # Default timeout for HTTP requests in seconds (handles large file operations)

    # Feature flags
    allow_file_delete: bool = True  # Default to allowing file deletion from database

    # Batch processing settings
    processall_throttle_threshold: int = Field(
        default=20,
        description="Number of files above which throttling is applied in /processall endpoint",
    )
    processall_throttle_delay: int = Field(
        default=3,
        description="Delay in seconds between each task submission when throttling in /processall",
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


settings = Settings()
