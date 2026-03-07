"""
Service for managing application settings with database persistence.

This module provides functionality to:
- Load settings from database with precedence over environment variables
- Save settings to database
- Get setting metadata (descriptions, types, categories)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import ApplicationSettings, SettingsAuditLog
from app.utils.ocr_provider import KNOWN_OCR_PROVIDERS

logger = logging.getLogger(__name__)

# Define setting metadata for UI display
SETTING_METADATA = {
    # Core Settings
    "database_url": {
        "category": "Core",
        "description": "Database connection URL (e.g., sqlite:///path/to/db.sqlite). Use the Database Wizard for guided setup.",
        "type": "string",
        "sensitive": False,
        "required": True,
        "restart_required": True,
        "help_link": "/database-wizard",
        "help_link_label": "Open Database Wizard",
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
    "multi_user_enabled": {
        "category": "Authentication",
        "description": (
            "Enable multi-user mode with individual document spaces per user. "
            "Each user sees only their own documents, uploads, and search results. "
            "Requires auth_enabled=True."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "default_daily_upload_limit": {
        "category": "Authentication",
        "description": (
            "Default maximum document uploads allowed per user per day in multi-user mode. Set to 0 for unlimited."
        ),
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "unowned_docs_visible_to_all": {
        "category": "Authentication",
        "description": (
            "In multi-user mode, controls whether documents without an owner are visible to all users. "
            "When True, unowned documents appear alongside each user's own files. "
            "When False, only admins can see unowned documents."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "default_owner_id": {
        "category": "Authentication",
        "description": (
            "Automatically assigns this owner ID to newly ingested documents that would otherwise "
            "have no owner. Start typing to search existing users, or leave empty to keep documents "
            "unowned until claimed."
        ),
        "type": "user_autocomplete",
        "sensitive": False,
        "required": False,
        "restart_required": False,
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
        "description": "API key for the AI provider (required for OpenAI, Azure, LiteLLM; unused for Ollama)",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "openai_base_url": {
        "category": "AI Services",
        "description": "API base URL – override for Azure endpoints, local proxies, or LiteLLM (default: https://api.openai.com/v1)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "openai_model": {
        "category": "AI Services",
        "description": "Fallback model name used when AI_MODEL is not set (e.g. gpt-4o-mini)",
        "type": "model_picker",
        "sensitive": False,
        "required": False,
        "restart_required": False,
        "suggested_models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "o1",
            "o1-mini",
            "o3",
            "o3-mini",
            "gpt-5",
            "gpt-5-nano",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-2.0-flash-exp",
            "llama3.2",
            "qwen2.5:7b",
            "phi3",
            "mistral",
        ],
    },
    "ai_provider": {
        "category": "AI Services",
        "description": "Active AI provider for metadata extraction and OCR refinement",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
        "options": ["openai", "azure", "anthropic", "gemini", "ollama", "openrouter", "portkey", "litellm"],
    },
    "ai_model": {
        "category": "AI Services",
        "description": "Model name for the selected provider (overrides OPENAI_MODEL). E.g. gpt-4o, claude-3-5-sonnet-20241022, gemini-1.5-pro, llama3.2",
        "type": "model_picker",
        "sensitive": False,
        "required": False,
        "restart_required": False,
        "suggested_models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "o1",
            "o1-mini",
            "o3",
            "o3-mini",
            "gpt-5",
            "gpt-5-nano",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-2.0-flash-exp",
            "llama3.2",
            "qwen2.5:7b",
            "phi3",
            "mistral",
        ],
    },
    "anthropic_api_key": {
        "category": "AI Services",
        "description": "Anthropic API key (required when AI_PROVIDER=anthropic)",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "gemini_api_key": {
        "category": "AI Services",
        "description": "Google AI Studio API key (required when AI_PROVIDER=gemini)",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "ollama_base_url": {
        "category": "AI Services",
        "description": "Ollama server URL for local LLM inference (used when AI_PROVIDER=ollama)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "openrouter_api_key": {
        "category": "AI Services",
        "description": "OpenRouter API key (required when AI_PROVIDER=openrouter)",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "openrouter_base_url": {
        "category": "AI Services",
        "description": "OpenRouter gateway URL (default: https://openrouter.ai/api/v1)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "portkey_api_key": {
        "category": "AI Services",
        "description": "Portkey account API key (required when AI_PROVIDER=portkey)",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "portkey_virtual_key": {
        "category": "AI Services",
        "description": "Portkey Virtual Key – routes to provider credentials stored in the Portkey vault (optional)",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "portkey_config": {
        "category": "AI Services",
        "description": "Portkey Config ID for advanced routing, fallbacks, and load balancing (optional, e.g. pc-my-config-abc123)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "portkey_base_url": {
        "category": "AI Services",
        "description": "Portkey gateway URL (default: https://api.portkey.ai/v1; override for self-hosted deployments)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "azure_openai_api_version": {
        "category": "AI Services",
        "description": "Azure OpenAI API version string (used when AI_PROVIDER=azure, default: 2024-02-01)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Azure Document Intelligence (OCR) – separate from the AI provider above
    "azure_ai_key": {
        "category": "AI Services",
        "description": "Azure Document Intelligence API key for OCR processing",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "azure_region": {
        "category": "AI Services",
        "description": "Azure region for Document Intelligence services (e.g., eastus)",
        "type": "autocomplete",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "azure_endpoint": {
        "category": "AI Services",
        "description": "Azure Document Intelligence endpoint URL",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # OCR Engine Configuration
    "ocr_providers": {
        "category": "OCR Engines",
        "description": (
            "Active OCR engines. Select one or more engines to enable. "
            "When multiple engines are selected all run in parallel and results are merged. "
            "Stored as a comma-separated list (e.g. azure,tesseract)."
        ),
        "type": "multiselect",
        "sensitive": False,
        "required": False,
        "restart_required": False,
        "options": KNOWN_OCR_PROVIDERS,
    },
    "ocr_merge_strategy": {
        "category": "OCR Engines",
        "description": (
            "Strategy for merging results from multiple OCR providers. "
            "ai_merge: use AI to produce best merged text (default); "
            "longest: return the result with most characters; "
            "primary: return only the first provider's result."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
        "options": ["ai_merge", "longest", "primary"],
    },
    # OCR – Tesseract
    "tesseract_cmd": {
        "category": "OCR Engines",
        "description": "Path to the Tesseract binary (e.g. /usr/bin/tesseract). Leave blank to use system PATH.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "tesseract_language": {
        "category": "OCR Engines",
        "description": (
            "Tesseract language code(s), e.g. 'eng' or 'eng+deu'. "
            "Combine multiple with '+'. Default: eng+deu (English + German)."
        ),
        "type": "autocomplete",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # OCR – EasyOCR
    "easyocr_languages": {
        "category": "OCR Engines",
        "description": ("Comma-separated EasyOCR language codes, e.g. 'en,de,fr'. Default: en,de (English + German)."),
        "type": "autocomplete",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "easyocr_gpu": {
        "category": "OCR Engines",
        "description": "Enable GPU acceleration for EasyOCR (requires CUDA). Default: False.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # OCR – Mistral
    "mistral_api_key": {
        "category": "OCR Engines",
        "description": "Mistral API key (required when 'mistral' is in OCR_PROVIDERS).",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "mistral_ocr_model": {
        "category": "OCR Engines",
        "description": "Mistral OCR model name. Default: mistral-ocr-latest.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # OCR – Google Cloud Document AI
    "google_docai_credentials_json": {
        "category": "OCR Engines",
        "description": (
            "Google Cloud service account credentials JSON for Document AI "
            "(optional; falls back to google_drive_credentials_json or Application Default Credentials)."
        ),
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "google_docai_project_id": {
        "category": "OCR Engines",
        "description": "GCP project ID for Google Cloud Document AI (required when 'google_docai' is in OCR_PROVIDERS).",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "google_docai_processor_id": {
        "category": "OCR Engines",
        "description": "Document AI processor ID (required when 'google_docai' is in OCR_PROVIDERS).",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "google_docai_location": {
        "category": "OCR Engines",
        "description": "Document AI processor location (e.g. 'us' or 'eu'). Default: us.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
        "options": ["us", "eu"],
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
        "type": "autocomplete",
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
        "options": [
            "STANDARD",
            "REDUCED_REDUNDANCY",
            "STANDARD_IA",
            "ONEZONE_IA",
            "INTELLIGENT_TIERING",
            "GLACIER",
            "DEEP_ARCHIVE",
            "GLACIER_IR",
        ],
    },
    "s3_acl": {
        "category": "Storage Providers",
        "description": "S3 object ACL (e.g., private, public-read)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
        "options": [
            "private",
            "public-read",
            "public-read-write",
            "authenticated-read",
            "aws-exec-read",
            "bucket-owner-read",
            "bucket-owner-full-control",
        ],
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
    "imap_readonly_mode": {
        "category": "IMAP",
        "description": (
            "When enabled, IMAP processing fetches and processes attachments but does NOT modify "
            "the mailbox (no starring, labeling, deleting, or flag changes). "
            "Use for preprod instances sharing a mailbox with production."
        ),
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
    "upload_concurrency": {
        "category": "Processing",
        "description": (
            "Maximum number of files uploaded simultaneously from the browser. "
            "Limits parallel uploads to prevent API overload when dragging directories. Default: 3."
        ),
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "upload_queue_delay_ms": {
        "category": "Processing",
        "description": (
            "Delay in milliseconds between starting each upload slot when queue is active. "
            "Staggers upload starts to smooth out server load. Default: 500 ms."
        ),
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "enable_text_quality_check": {
        "category": "Processing",
        "description": (
            "Enable AI-based quality check for embedded PDF text. "
            "When enabled, text extracted from non-digital PDFs is evaluated by the AI model. "
            "Poor-quality text (OCR artefacts, typos, incoherence) triggers automatic re-OCR. "
            "Digitally-created PDFs (Word, LibreOffice, LaTeX, etc.) are always trusted and skip the check."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "text_quality_threshold": {
        "category": "Processing",
        "description": (
            "Minimum quality score (0–100) required to accept embedded PDF text without re-OCR. "
            "Text scoring below this threshold triggers a fresh OCR pass. "
            "Default: 85. Lower values are more permissive; higher values enforce stricter quality."
        ),
        "type": "slider",
        "sensitive": False,
        "required": False,
        "restart_required": False,
        "min": 0,
        "max": 100,
        "step": 1,
    },
    "text_quality_significant_issues": {
        "category": "Processing",
        "description": (
            "Comma-separated list of quality issue labels that force OCR re-run even when the quality "
            "score meets TEXT_QUALITY_THRESHOLD. Any matching issue in the AI assessment will trigger "
            "re-OCR regardless of the numeric score. "
            "Default: excessive_typos,garbage_characters,incoherent_text,fragmented_sentences"
        ),
        "type": "list",
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
    "enable_search": {
        "category": "Feature Flags",
        "description": "Enable Meilisearch full-text search integration. Default: True.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "webhook_enabled": {
        "category": "Feature Flags",
        "description": "Enable webhook delivery for document events. Default: True.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # UI / Appearance
    "ui_default_color_scheme": {
        "category": "UI",
        "description": (
            "Default color scheme for the web interface. "
            "Options: 'system' (follow OS preference), 'light', 'dark'. "
            "Individual users can override this with the in-app toggle; their choice is persisted in localStorage."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
        "options": ["system", "light", "dark"],
    },
    # Authentication – additional
    "admin_group_name": {
        "category": "Authentication",
        "description": "Name of the admin group in the OAuth provider (e.g. Authentik). Default: admin.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    # Storage Providers – S3 (additional)
    # (s3_bucket_name, s3_folder_prefix, s3_storage_class, s3_acl already in Storage Providers above)
    # Paperless – additional
    "paperless_custom_field_absender": {
        "category": "Storage Providers",
        "description": "Name of the 'absender' (sender) custom field in Paperless-ngx.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "paperless_custom_fields_mapping": {
        "category": "Storage Providers",
        "description": (
            "JSON mapping of metadata field names to Paperless custom field names. "
            'Example: {"absender": "Sender", "empfaenger": "Recipient", "language": "Language"}.'
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Meilisearch / Search
    "meilisearch_url": {
        "category": "Core",
        "description": "URL of the Meilisearch search engine instance. Default: http://meilisearch:7700.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "meilisearch_api_key": {
        "category": "Core",
        "description": "Meilisearch API key (master key or search-only key). Optional for local development.",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": True,
    },
    "meilisearch_index_name": {
        "category": "Core",
        "description": "Name of the Meilisearch index for documents. Default: documents.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    # PDF/A Archival Conversion
    "enable_pdfa_conversion": {
        "category": "PDF/A Archival",
        "description": (
            "Master switch: enable PDF/A archival variant generation. "
            "When enabled, PDF/A copies of both the original and processed files are created. "
            "Uses ocrmypdf with Ghostscript for the conversion. Default: False."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "pdfa_format": {
        "category": "PDF/A Archival",
        "description": "PDF/A format variant to produce: 1 = PDF/A-1b, 2 = PDF/A-2b, 3 = PDF/A-3b. Default: 2.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
        "options": ["1", "2", "3"],
    },
    "pdfa_upload_original": {
        "category": "PDF/A Archival",
        "description": (
            "Upload the original-file PDF/A variant to all configured storage providers. "
            "Files are placed in the provider's folder + PDFA_UPLOAD_FOLDER subfolder. Default: False."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "pdfa_upload_processed": {
        "category": "PDF/A Archival",
        "description": (
            "Upload the processed-file PDF/A variant to all configured storage providers. "
            "Files are placed in the provider's folder + PDFA_UPLOAD_FOLDER subfolder. Default: False."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "pdfa_upload_folder": {
        "category": "PDF/A Archival",
        "description": (
            "Subfolder name appended to each storage provider's configured folder for PDF/A uploads. "
            "For example if Dropbox folder is '/Documents' and this is 'pdfa', files go to '/Documents/pdfa'. "
            "Set to empty string to upload into the same folder. Default: pdfa."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "google_drive_pdfa_folder_id": {
        "category": "PDF/A Archival",
        "description": (
            "Google Drive folder ID for PDF/A uploads (Drive uses IDs not paths). "
            "If empty, uses the standard google_drive_folder_id."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "pdfa_timestamp_enabled": {
        "category": "PDF/A Archival",
        "description": (
            "Enable RFC 3161 timestamping of PDF/A files via a Timestamp Authority (TSA). "
            "Creates a .tsr file alongside each PDF/A file for legal proof of existence. "
            "Requires openssl binary on PATH. Default: False."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "pdfa_timestamp_url": {
        "category": "PDF/A Archival",
        "description": (
            "URL of the RFC 3161 Timestamp Authority (TSA). "
            "Default: FreeTSA (https://freetsa.org/tsr). Other options: GlobalSign, DigiStamp, "
            "or any RFC 3161-compliant TSA."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Deduplication
    "enable_deduplication": {
        "category": "Processing",
        "description": (
            "Enable deduplication check before processing. Files with the same SHA-256 hash "
            "as previously processed files will be skipped. Default: True."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "show_deduplication_step": {
        "category": "Processing",
        "description": (
            "Show the 'Check for Duplicates' step in processing history. "
            "If False, the check is still performed but not displayed. Default: True."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "near_duplicate_threshold": {
        "category": "Processing",
        "description": (
            "Minimum cosine similarity score (0.0–1.0) between two documents' text embeddings "
            "to consider them near-duplicates. Higher values require closer content matches. Default: 0.85."
        ),
        "type": "slider",
        "sensitive": False,
        "required": False,
        "restart_required": False,
        "min": 0,
        "max": 1,
        "step": 0.01,
    },
    # Embeddings
    "embedding_model": {
        "category": "AI Services",
        "description": (
            "Model name used for generating text embeddings via the OpenAI-compatible API. "
            "Embeddings drive the document similarity feature. Default: text-embedding-3-small."
        ),
        "type": "autocomplete",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "embedding_max_tokens": {
        "category": "AI Services",
        "description": (
            "Maximum number of tokens to send to the embedding model. "
            "Text is truncated to approximately this many tokens before calling the API. Default: 8000."
        ),
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "embedding_backfill_batch_size": {
        "category": "AI Services",
        "description": (
            "Maximum number of files to queue for embedding computation per backfill run. "
            "Keeps the worker and embedding API load bounded. Default: 50."
        ),
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # File upload size limits
    "max_upload_size": {
        "category": "Core",
        "description": (
            "Maximum file upload size in bytes. Prevents resource exhaustion attacks. Default: 1073741824 (1 GB)."
        ),
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "max_single_file_size": {
        "category": "Core",
        "description": (
            "Maximum size for a single file chunk in bytes. If set and file exceeds this, "
            "it will be split into smaller chunks for processing. Default: None (no splitting)."
        ),
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "max_request_body_size": {
        "category": "Core",
        "description": (
            "Maximum request body size in bytes for non-file-upload requests. "
            "Prevents memory exhaustion via oversized JSON/form payloads. Default: 1048576 (1 MB)."
        ),
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    # Task Retry Settings
    "task_retry_max_retries": {
        "category": "Processing",
        "description": "Maximum number of automatic retry attempts for failed Celery tasks. Default: 3.",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "task_retry_delays": {
        "category": "Processing",
        "description": (
            "Comma-separated list of retry countdown values in seconds. "
            "Each value is the delay before the corresponding retry attempt. "
            "Default: 60,300,900 (1 min, 5 min, 15 min)."
        ),
        "type": "list",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "task_retry_jitter": {
        "category": "Processing",
        "description": (
            "Apply ±20% random jitter to retry countdowns to prevent thundering-herd problems. Default: True."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "step_timeout": {
        "category": "Processing",
        "description": (
            "Timeout in seconds for processing steps. Steps stuck in 'in_progress' longer "
            "than this are marked as failed. Default: 600 (10 minutes)."
        ),
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Security Headers
    "security_headers_enabled": {
        "category": "Security",
        "description": (
            "Enable security headers middleware. Set to True if deploying without a reverse proxy. "
            "Default: False (most deployments use Traefik/Nginx which add headers)."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "security_header_hsts_enabled": {
        "category": "Security",
        "description": "Enable HTTP Strict Transport Security (HSTS) header. Only effective over HTTPS. Default: True.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "security_header_hsts_value": {
        "category": "Security",
        "description": "HSTS header value. Default: max-age=31536000; includeSubDomains.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "security_header_csp_enabled": {
        "category": "Security",
        "description": "Enable Content-Security-Policy (CSP) header. Default: True.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "security_header_csp_value": {
        "category": "Security",
        "description": (
            "CSP header value. Customize based on your application's resource loading needs. "
            "Default: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; font-src 'self' data:;"
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "security_header_x_frame_options_enabled": {
        "category": "Security",
        "description": "Enable X-Frame-Options header to prevent clickjacking. Default: True.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "security_header_x_frame_options_value": {
        "category": "Security",
        "description": "X-Frame-Options header value.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
        "options": ["DENY", "SAMEORIGIN"],
    },
    "security_header_x_content_type_options_enabled": {
        "category": "Security",
        "description": "Enable X-Content-Type-Options header (always set to 'nosniff'). Default: True.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    # Audit Logging
    "audit_logging_enabled": {
        "category": "Security",
        "description": (
            "Enable audit/request logging middleware. Logs every HTTP request with method, path, "
            "status code, response time, and username. Sensitive query-parameter values are automatically masked. "
            "Default: True."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "audit_log_include_client_ip": {
        "category": "Security",
        "description": (
            "Include the client IP address in audit log entries. "
            "Disable for privacy-sensitive deployments where IP logging is restricted. Default: True."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    # Rate Limiting
    "rate_limiting_enabled": {
        "category": "Security",
        "description": "Enable rate limiting middleware. Recommended for production to prevent abuse. Default: True.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "rate_limit_default": {
        "category": "Security",
        "description": (
            "Default rate limit for all endpoints (format: 'count/period', e.g. '100/minute'). Default: 100/minute."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "rate_limit_upload": {
        "category": "Security",
        "description": "Rate limit for file upload endpoints to prevent resource exhaustion. Default: 600/minute.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "rate_limit_auth": {
        "category": "Security",
        "description": (
            "Stricter rate limit for authentication endpoints to prevent brute force attacks. Default: 10/minute."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    # CORS
    "cors_enabled": {
        "category": "Security",
        "description": (
            "Enable CORS middleware. Set to False if reverse proxy (Traefik, Nginx) handles CORS headers. "
            "Default: False."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "cors_allowed_origins": {
        "category": "Security",
        "description": (
            "Comma-separated list of allowed CORS origins. Use '*' to allow all origins "
            "(not recommended with cors_allow_credentials=True). "
            "Default: * (all origins)."
        ),
        "type": "list",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "cors_allow_credentials": {
        "category": "Security",
        "description": (
            "Allow credentials (cookies, Authorization headers) in CORS requests. "
            "Cannot be True when cors_allowed_origins is '*'. Default: False."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "cors_allowed_methods": {
        "category": "Security",
        "description": (
            "Comma-separated list of allowed HTTP methods for CORS requests. "
            "Default: GET,POST,PUT,DELETE,OPTIONS,PATCH."
        ),
        "type": "list",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "cors_allowed_headers": {
        "category": "Security",
        "description": "Comma-separated list of allowed request headers for CORS. Use '*' to allow all. Default: *.",
        "type": "list",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "subscription_overage_percent": {
        "category": "Subscriptions",
        "description": (
            "Soft-limit overage buffer in percent (0–200). The announced monthly quota is increased by this "
            "percentage for actual enforcement. For example, 20 means a 150-doc/month plan enforces at 180 docs "
            "(150 × 1.20). Set to 0 to enforce exactly at the announced limit. Per-plan overage_percent configured "
            "in the Plan Designer overrides this global default. Default: 20."
        ),
        "type": "integer",
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


def save_setting_to_db(db: Session, key: str, value: Optional[str], changed_by: str = "system") -> bool:
    """
    Save or update a setting in the database.

    Automatically encrypts sensitive values if encryption is enabled.
    Records an entry in the settings audit log.

    Args:
        db: Database session
        key: Setting key
        value: Setting value (as string)
        changed_by: Username of the admin performing the change (for audit log)

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
        old_storage_value = setting.value if setting else None

        if setting:
            setting.value = storage_value
        else:
            setting = ApplicationSettings(key=key, value=storage_value)
            db.add(setting)

        # Determine human-readable old value for audit log (decrypt if needed)
        old_display_value = None
        if old_storage_value is not None:
            if metadata.get("sensitive", False):
                try:
                    from app.utils.encryption import decrypt_value

                    old_display_value = decrypt_value(old_storage_value)
                except Exception:
                    old_display_value = old_storage_value
            else:
                old_display_value = old_storage_value

        # Write audit log entry
        audit_entry = SettingsAuditLog(
            key=key,
            old_value=old_display_value,
            new_value=value,
            changed_by=changed_by,
            action="update",
        )
        db.add(audit_entry)

        db.commit()
        logger.info(f"Saved setting {key} to database (changed_by={changed_by})")
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


def delete_setting_from_db(db: Session, key: str, changed_by: str = "system") -> bool:
    """
    Delete a setting from the database.

    Records an entry in the settings audit log.

    Args:
        db: Database session
        key: Setting key to delete
        changed_by: Username of the admin performing the change (for audit log)

    Returns:
        True if successful, False otherwise
    """
    try:
        setting = db.query(ApplicationSettings).filter(ApplicationSettings.key == key).first()
        if setting:
            # Capture old value for audit log (decrypt if sensitive)
            metadata = get_setting_metadata(key)
            old_display_value = None
            if setting.value is not None:
                if metadata.get("sensitive", False):
                    try:
                        from app.utils.encryption import decrypt_value

                        old_display_value = decrypt_value(setting.value)
                    except Exception:
                        old_display_value = setting.value
                else:
                    old_display_value = setting.value

            db.delete(setting)

            audit_entry = SettingsAuditLog(
                key=key,
                old_value=old_display_value,
                new_value=None,
                changed_by=changed_by,
                action="delete",
            )
            db.add(audit_entry)

            db.commit()
            logger.info(f"Deleted setting {key} from database (changed_by={changed_by})")
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
    return SETTING_METADATA.get(
        key,
        {
            "category": "Other",
            "description": f"Setting: {key}",
            "type": "string",
            "sensitive": False,
            "required": False,
            "restart_required": False,
        },
    )


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

    elif setting_type == "slider":
        try:
            num = float(value)
            min_val = metadata.get("min")
            max_val = metadata.get("max")
            if min_val is not None and num < min_val:
                return False, f"{key} must be >= {min_val}"
            if max_val is not None and num > max_val:
                return False, f"{key} must be <= {max_val}"
        except ValueError:
            return False, f"{key} must be a number"

    # Special validation for specific keys
    if key == "session_secret" and value and len(value) < 32:
        return False, "session_secret must be at least 32 characters"

    return True, None


def get_audit_log(db: Session, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Retrieve the settings audit log, most recent first.

    Sensitive values are masked in the returned list so the log is safe to
    display in the admin UI without leaking secrets.

    Args:
        db: Database session
        limit: Maximum number of entries to return
        offset: Number of entries to skip (for pagination)

    Returns:
        List of audit log entry dicts ordered by changed_at descending
    """
    try:
        entries = (
            db.query(SettingsAuditLog).order_by(SettingsAuditLog.changed_at.desc()).limit(limit).offset(offset).all()
        )
        result = []
        for entry in entries:
            meta = get_setting_metadata(entry.key)
            is_sensitive = meta.get("sensitive", False)
            result.append(
                {
                    "id": entry.id,
                    "key": entry.key,
                    "old_value": ("[REDACTED]" if is_sensitive and entry.old_value else entry.old_value),
                    "new_value": ("[REDACTED]" if is_sensitive and entry.new_value else entry.new_value),
                    "changed_by": entry.changed_by,
                    "changed_at": (entry.changed_at.isoformat() if entry.changed_at else None),
                    "action": entry.action,
                }
            )
        return result
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving audit log: {e}")
        return []


def get_setting_history(db: Session, key: str) -> List[Dict[str, Any]]:
    """
    Retrieve the change history for a specific setting key, most recent first.

    Sensitive values are masked so the response is safe to surface in the UI.

    Args:
        db: Database session
        key: Setting key

    Returns:
        List of audit log entry dicts for this key
    """
    try:
        entries = (
            db.query(SettingsAuditLog)
            .filter(SettingsAuditLog.key == key)
            .order_by(SettingsAuditLog.changed_at.desc())
            .all()
        )
        meta = get_setting_metadata(key)
        is_sensitive = meta.get("sensitive", False)
        result = []
        for entry in entries:
            result.append(
                {
                    "id": entry.id,
                    "key": entry.key,
                    "old_value": ("[REDACTED]" if is_sensitive and entry.old_value else entry.old_value),
                    "new_value": ("[REDACTED]" if is_sensitive and entry.new_value else entry.new_value),
                    "changed_by": entry.changed_by,
                    "changed_at": (entry.changed_at.isoformat() if entry.changed_at else None),
                    "action": entry.action,
                }
            )
        return result
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving history for setting {key}: {e}")
        return []


def rollback_setting(db: Session, key: str, history_id: int, changed_by: str = "system") -> bool:
    """
    Revert a setting to the value it had *before* a specific audit log entry.

    The value stored in the chosen history entry's ``old_value`` field is
    re-applied as the current database value, effectively undoing that change.
    If ``old_value`` is ``None`` (i.e. the setting did not exist before that
    change) the setting is removed from the database entirely, reverting to
    ENV/defaults.

    A new audit log entry is written to record the rollback operation.

    Args:
        db: Database session
        key: Setting key to roll back
        history_id: ID of the SettingsAuditLog entry whose ``old_value``
                    should become the restored value
        changed_by: Username performing the rollback (for audit log)

    Returns:
        True if successful, False if the history entry was not found or an
        error occurred
    """
    try:
        history_entry = (
            db.query(SettingsAuditLog).filter(SettingsAuditLog.id == history_id, SettingsAuditLog.key == key).first()
        )
        if not history_entry:
            logger.warning(f"Rollback failed: audit log entry {history_id} not found for key '{key}'")
            return False

        target_value = history_entry.old_value

        if target_value is None:
            # The old value was empty – remove the current db value to revert to ENV/default
            return delete_setting_from_db(db, key, changed_by=changed_by)
        else:
            return save_setting_to_db(db, key, target_value, changed_by=changed_by)
    except SQLAlchemyError as e:
        logger.error(f"Error rolling back setting {key} to history entry {history_id}: {e}")
        db.rollback()
        return False


def get_settings_for_export(db: Session, source: str = "db") -> Dict[str, str]:
    """
    Collect settings for export as environment variables.

    Args:
        db: Database session
        source: ``"db"`` to export only database-persisted settings (default);
                ``"effective"`` to export the full current runtime configuration
                (DB overrides ENV overrides application defaults) for every key
                listed in SETTING_METADATA.

    Returns:
        Ordered dict mapping uppercase ENV variable names to their string values.
        Sensitive values are included (the caller is responsible for access control).
    """
    if source == "effective":
        from app.config import settings as app_settings

        db_settings = get_all_settings_from_db(db)
        result = {}
        for key in sorted(SETTING_METADATA.keys()):
            # DB wins, then live settings object (ENV/default)
            if key in db_settings and db_settings[key] is not None:
                value = db_settings[key]
            else:
                value = getattr(app_settings, key, None)
            if value is not None:
                result[key.upper()] = str(value)
        return result
    else:
        # DB only
        db_settings = get_all_settings_from_db(db)
        return {k.upper(): v for k, v in sorted(db_settings.items()) if v is not None}
