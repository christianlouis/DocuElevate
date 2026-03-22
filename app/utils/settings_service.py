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
    "db_pool_size": {
        "category": "Core",
        "description": (
            "Number of persistent database connections kept in the pool per worker process. "
            "Ignored for SQLite (which uses NullPool). Default: 10."
        ),
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "db_max_overflow": {
        "category": "Core",
        "description": (
            "Additional database connections allowed beyond db_pool_size under burst load. "
            "Ignored for SQLite. Default: 20."
        ),
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "db_pool_timeout": {
        "category": "Core",
        "description": (
            "Seconds to wait for a database connection from the pool before raising a TimeoutError. "
            "Ignored for SQLite. Default: 30."
        ),
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "db_pool_recycle": {
        "category": "Core",
        "description": (
            "Recycle (close and reopen) database connections after this many seconds "
            "to avoid stale connections. Ignored for SQLite. Default: 1800."
        ),
        "type": "integer",
        "sensitive": False,
        "required": False,
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
    "public_base_url": {
        "category": "Core",
        "description": (
            "Full public base URL including scheme (e.g., https://docuelevate.example.com). "
            "When set, overrides auto-detected URLs for OAuth redirect URIs. "
            "Required when behind a reverse proxy that does not forward X-Forwarded-Proto."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
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
    "session_lifetime_days": {
        "category": "Authentication",
        "description": "Session lifetime in days (default 30). Determines how long a user stays logged in.",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "session_lifetime_custom_days": {
        "category": "Authentication",
        "description": "Override session_lifetime_days with a custom value. Takes precedence when set.",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "qr_login_challenge_ttl_seconds": {
        "category": "Authentication",
        "description": "Time-to-live in seconds for QR login challenges (default 120).",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
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
    "sso_auto_login": {
        "category": "Authentication",
        "description": (
            "Automatically redirect to SSO login when authentication is required. "
            "Skips the login page and sends users directly to the configured SSO provider."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Social Login Providers
    "social_auth_google_enabled": {
        "category": "Social Login",
        "description": (
            "Enable Google Sign-In. Requires SOCIAL_AUTH_GOOGLE_CLIENT_ID and "
            "SOCIAL_AUTH_GOOGLE_CLIENT_SECRET from the Google Cloud Console."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
        "help_link": "https://console.cloud.google.com/apis/credentials",
        "help_link_label": "Google Cloud Console",
    },
    "social_auth_google_client_id": {
        "category": "Social Login",
        "description": "Google OAuth2 client ID from the Google Cloud Console.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_google_client_secret": {
        "category": "Social Login",
        "description": "Google OAuth2 client secret from the Google Cloud Console.",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": True,
    },
    "social_auth_microsoft_enabled": {
        "category": "Social Login",
        "description": (
            "Enable Microsoft Sign-In (Azure AD / Microsoft Entra ID). Requires "
            "SOCIAL_AUTH_MICROSOFT_CLIENT_ID and SOCIAL_AUTH_MICROSOFT_CLIENT_SECRET "
            "from Azure App Registrations."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
        "help_link": "https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
        "help_link_label": "Azure Portal",
    },
    "social_auth_microsoft_client_id": {
        "category": "Social Login",
        "description": "Microsoft OAuth2 application (client) ID from Azure App Registrations.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_microsoft_client_secret": {
        "category": "Social Login",
        "description": "Microsoft OAuth2 client secret from Azure App Registrations.",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": True,
    },
    "social_auth_microsoft_tenant": {
        "category": "Social Login",
        "description": (
            "Azure AD tenant ID or one of 'common', 'organizations', 'consumers'. "
            "Use 'common' to allow any Microsoft account. Use a specific GUID to "
            "restrict to a single organization."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_apple_enabled": {
        "category": "Social Login",
        "description": (
            "Enable Sign in with Apple. Requires an Apple Developer account with "
            "a Services ID configured for Sign in with Apple."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
        "help_link": "https://developer.apple.com/account/resources/identifiers/list/serviceId",
        "help_link_label": "Apple Developer Portal",
    },
    "social_auth_apple_client_id": {
        "category": "Social Login",
        "description": "Apple Services ID (e.g. com.example.docuelevate).",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_apple_team_id": {
        "category": "Social Login",
        "description": "Apple Developer Team ID (10-character alphanumeric string).",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_apple_key_id": {
        "category": "Social Login",
        "description": "Apple Sign-In private key ID from the Apple Developer Portal.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_apple_private_key": {
        "category": "Social Login",
        "description": (
            "Apple Sign-In private key (PEM format). Generate this in the Apple Developer Portal. "
            "Paste the entire key content including BEGIN/END headers."
        ),
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": True,
    },
    "social_auth_dropbox_use_global_credentials": {
        "category": "Social Login",
        "description": (
            "When True, Dropbox social login uses the global DROPBOX_APP_KEY / DROPBOX_APP_SECRET "
            "credentials instead of requiring separate SOCIAL_AUTH_DROPBOX_CLIENT_ID / "
            "SOCIAL_AUTH_DROPBOX_CLIENT_SECRET values. "
            "Requires SOCIAL_AUTH_DROPBOX_ENABLED=True and global Dropbox credentials to be set."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_dropbox_enabled": {
        "category": "Social Login",
        "description": (
            "Enable Dropbox Sign-In. Uses the same Dropbox App you may already have "
            "configured for storage, or a separate one."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_dropbox_client_id": {
        "category": "Social Login",
        "description": "Dropbox OAuth2 App Key from the Dropbox App Console.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_dropbox_client_secret": {
        "category": "Social Login",
        "description": "Dropbox OAuth2 App Secret from the Dropbox App Console.",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": True,
    },
    "social_auth_github_enabled": {
        "category": "Social Login",
        "description": (
            "Enable GitHub Sign-In. Requires SOCIAL_AUTH_GITHUB_CLIENT_ID and "
            "SOCIAL_AUTH_GITHUB_CLIENT_SECRET from GitHub Developer Settings."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
        "help_link": "https://github.com/settings/developers",
        "help_link_label": "GitHub Developer Settings",
    },
    "social_auth_github_client_id": {
        "category": "Social Login",
        "description": "GitHub OAuth2 client ID from GitHub Developer Settings.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_github_client_secret": {
        "category": "Social Login",
        "description": "GitHub OAuth2 client secret from GitHub Developer Settings.",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": True,
    },
    # Keycloak SSO
    "social_auth_keycloak_enabled": {
        "category": "Social Login",
        "description": "Enable Keycloak SSO. Requires server URL, realm, client ID, and client secret.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_keycloak_client_id": {
        "category": "Social Login",
        "description": "Keycloak OAuth2 client ID.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_keycloak_client_secret": {
        "category": "Social Login",
        "description": "Keycloak OAuth2 client secret.",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": True,
    },
    "social_auth_keycloak_server_url": {
        "category": "Social Login",
        "description": "Keycloak server base URL (e.g. https://keycloak.example.com).",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_keycloak_realm": {
        "category": "Social Login",
        "description": "Keycloak realm name.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    # Generic OAuth2 SSO
    "social_auth_generic_oauth2_enabled": {
        "category": "Social Login",
        "description": "Enable a generic OAuth2 SSO provider.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_generic_oauth2_client_id": {
        "category": "Social Login",
        "description": "Generic OAuth2 client ID.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_generic_oauth2_client_secret": {
        "category": "Social Login",
        "description": "Generic OAuth2 client secret.",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": True,
    },
    "social_auth_generic_oauth2_authorize_url": {
        "category": "Social Login",
        "description": "Generic OAuth2 authorization URL.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_generic_oauth2_token_url": {
        "category": "Social Login",
        "description": "Generic OAuth2 token endpoint URL.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_generic_oauth2_userinfo_url": {
        "category": "Social Login",
        "description": "Generic OAuth2 userinfo endpoint URL.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_generic_oauth2_scope": {
        "category": "Social Login",
        "description": "Space-separated list of OAuth2 scopes to request (default: openid profile email).",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_generic_oauth2_name": {
        "category": "Social Login",
        "description": "Display name for the generic OAuth2 provider button on the login page.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    # SAML2 SSO
    "social_auth_saml2_enabled": {
        "category": "Social Login",
        "description": "Enable SAML2 SSO authentication.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_saml2_entity_id": {
        "category": "Social Login",
        "description": "SAML2 Identity Provider Entity ID.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_saml2_sso_url": {
        "category": "Social Login",
        "description": "SAML2 Identity Provider SSO URL.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "social_auth_saml2_certificate": {
        "category": "Social Login",
        "description": "SAML2 Identity Provider X.509 certificate (PEM format).",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": True,
    },
    "social_auth_saml2_name": {
        "category": "Social Login",
        "description": "Display name for the SAML2 provider.",
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
    # Document Translation
    "default_document_language": {
        "category": "AI Services",
        "description": (
            "ISO 639-1 language code for the default document translation target "
            "(e.g. 'en', 'de', 'fr'). Documents whose detected language differs "
            "are automatically translated into this language after processing."
        ),
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
    "dropbox_enabled": {
        "category": "Storage Providers",
        "description": "Enable Dropbox as an upload destination. When disabled, no documents will be sent to Dropbox even if credentials are configured.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
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
    "dropbox_allow_global_credentials_for_integrations": {
        "category": "Storage Providers",
        "description": (
            "When True, users may authorize their personal Dropbox integrations using the global "
            "DROPBOX_APP_KEY / DROPBOX_APP_SECRET credentials configured by the admin, without "
            "needing to create their own Dropbox app."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Storage Providers - Nextcloud
    "nextcloud_enabled": {
        "category": "Storage Providers",
        "description": "Enable Nextcloud as an upload destination. When disabled, no documents will be sent to Nextcloud even if credentials are configured.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
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
    "paperless_enabled": {
        "category": "Storage Providers",
        "description": "Enable Paperless-ngx as an upload destination. When disabled, no documents will be sent to Paperless-ngx even if credentials are configured.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
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
    "google_drive_enabled": {
        "category": "Storage Providers",
        "description": "Enable Google Drive as an upload destination. When disabled, no documents will be sent to Google Drive even if credentials are configured.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
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
    "onedrive_enabled": {
        "category": "Storage Providers",
        "description": "Enable OneDrive as an upload destination. When disabled, no documents will be sent to OneDrive even if credentials are configured.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
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
    # Storage Providers - SharePoint
    "sharepoint_client_id": {
        "category": "Storage Providers",
        "description": "SharePoint Azure AD application (client) ID",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "sharepoint_client_secret": {
        "category": "Storage Providers",
        "description": "SharePoint Azure AD client secret",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "sharepoint_tenant_id": {
        "category": "Storage Providers",
        "description": "SharePoint Azure AD tenant ID (use 'common' for multi-tenant apps)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "sharepoint_refresh_token": {
        "category": "Storage Providers",
        "description": "SharePoint OAuth refresh token",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "sharepoint_site_url": {
        "category": "Storage Providers",
        "description": "SharePoint site URL (e.g. https://tenant.sharepoint.com/sites/sitename)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "sharepoint_document_library": {
        "category": "Storage Providers",
        "description": "SharePoint document library name (default: 'Documents')",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "sharepoint_folder_path": {
        "category": "Storage Providers",
        "description": "Subfolder path inside the SharePoint document library",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Storage Providers - WebDAV
    "webdav_enabled": {
        "category": "Storage Providers",
        "description": "Enable WebDAV as an upload destination. When disabled, no documents will be sent to WebDAV even if credentials are configured.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
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
    "ftp_enabled": {
        "category": "Storage Providers",
        "description": "Enable FTP as an upload destination. When disabled, no documents will be sent to FTP even if credentials are configured.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
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
    "sftp_enabled": {
        "category": "Storage Providers",
        "description": "Enable SFTP as an upload destination. When disabled, no documents will be sent to SFTP even if credentials are configured.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
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
    # Storage Providers - iCloud Drive
    "icloud_enabled": {
        "category": "Storage Providers",
        "description": "Enable iCloud Drive as an upload destination. When disabled, no documents will be sent to iCloud Drive even if credentials are configured.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "icloud_username": {
        "category": "Storage Providers",
        "description": "Apple ID email address for iCloud Drive authentication",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "icloud_password": {
        "category": "Storage Providers",
        "description": "App-specific password for iCloud Drive (generate at https://appleid.apple.com)",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "icloud_folder": {
        "category": "Storage Providers",
        "description": "Target folder path in iCloud Drive (e.g. Documents/Uploads)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "icloud_cookie_directory": {
        "category": "Storage Providers",
        "description": "Directory for persisting iCloud session cookies (default: ~/.pyicloud)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Storage Providers - AWS S3
    "s3_enabled": {
        "category": "Storage Providers",
        "description": "Enable Amazon S3 as an upload destination. When disabled, no documents will be sent to S3 even if credentials are configured.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
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
        "description": "SMTP server hostname (shared – used for password reset and verification emails)",
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
        "description": "Default recipient email address (shared – used for system notifications)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Email Destination Settings (dedicated SMTP for document delivery)
    "dest_email_enabled": {
        "category": "Email Destination",
        "description": "Enable Email as an upload destination. When disabled, no documents will be delivered via email even if credentials are configured.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "dest_email_host": {
        "category": "Email Destination",
        "description": "SMTP server hostname for document delivery (separate from shared email settings)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "dest_email_port": {
        "category": "Email Destination",
        "description": "SMTP port for document delivery (default: 587)",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "dest_email_username": {
        "category": "Email Destination",
        "description": "SMTP username for document delivery",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "dest_email_password": {
        "category": "Email Destination",
        "description": "SMTP password for document delivery",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "dest_email_use_tls": {
        "category": "Email Destination",
        "description": "Use TLS encryption for document delivery SMTP",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "dest_email_sender": {
        "category": "Email Destination",
        "description": "From address for document delivery emails (defaults to dest_email_username)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "dest_email_default_recipient": {
        "category": "Email Destination",
        "description": "Default recipient email for document delivery when none is specified",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Watch Folder / Ingest Settings
    "watch_folders": {
        "category": "Watch Folders",
        "description": (
            "Comma-separated list of absolute local filesystem paths that DocuElevate will "
            "poll for new files to ingest. Works with any mounted path (SMB/CIFS, NFS, etc.). "
            "Example: /watchfolders/scanner,/mnt/shared/inbox"
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "watch_folder_poll_interval": {
        "category": "Watch Folders",
        "description": "Poll interval in minutes for local watch folder scanning (default: 1)",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "watch_folder_delete_after_process": {
        "category": "Watch Folders",
        "description": (
            "Delete files from local watch folders after they have been enqueued for processing. "
            "When False (default), processed files are tracked via cache to avoid re-ingestion."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # FTP Ingest
    "ftp_ingest_enabled": {
        "category": "Watch Folders",
        "description": "Enable FTP watch folder ingestion (requires FTP_INGEST_FOLDER and FTP connection settings)",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "ftp_ingest_folder": {
        "category": "Watch Folders",
        "description": (
            "FTP folder path to poll for new documents to ingest. "
            "Uses the existing FTP connection settings (FTP_HOST, FTP_USERNAME, FTP_PASSWORD)."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "ftp_ingest_delete_after_process": {
        "category": "Watch Folders",
        "description": "Delete files from the FTP ingest folder after they have been downloaded and enqueued",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # SFTP Ingest
    "sftp_ingest_enabled": {
        "category": "Watch Folders",
        "description": "Enable SFTP watch folder ingestion (requires SFTP_INGEST_FOLDER and SFTP connection settings)",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "sftp_ingest_folder": {
        "category": "Watch Folders",
        "description": (
            "SFTP folder path to poll for new documents to ingest. "
            "Uses the existing SFTP connection settings (SFTP_HOST, SFTP_USERNAME, SFTP_PASSWORD/SFTP_PRIVATE_KEY)."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "sftp_ingest_delete_after_process": {
        "category": "Watch Folders",
        "description": "Delete files from the SFTP ingest folder after they have been downloaded and enqueued",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Cloud Provider Watch Folders — Dropbox
    "dropbox_ingest_enabled": {
        "category": "Watch Folders",
        "description": "Enable Dropbox watch folder ingestion (requires Dropbox OAuth credentials)",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "dropbox_ingest_folder": {
        "category": "Watch Folders",
        "description": "Dropbox folder path to poll for new documents (e.g. /Inbox/Scanner). Uses existing Dropbox credentials.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "dropbox_ingest_delete_after_process": {
        "category": "Watch Folders",
        "description": "Delete files from Dropbox ingest folder after download and enqueue",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Cloud Provider Watch Folders — Google Drive
    "google_drive_ingest_enabled": {
        "category": "Watch Folders",
        "description": "Enable Google Drive watch folder ingestion (requires Google Drive credentials)",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "google_drive_ingest_folder_id": {
        "category": "Watch Folders",
        "description": "Google Drive folder ID to poll for new documents. Uses existing Google Drive credentials.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "google_drive_ingest_delete_after_process": {
        "category": "Watch Folders",
        "description": "Delete files from Google Drive ingest folder after download and enqueue",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Cloud Provider Watch Folders — OneDrive
    "onedrive_ingest_enabled": {
        "category": "Watch Folders",
        "description": "Enable OneDrive watch folder ingestion (requires OneDrive MSAL credentials)",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "onedrive_ingest_folder_path": {
        "category": "Watch Folders",
        "description": "OneDrive folder path to poll for new documents (e.g. /Inbox/Scanner). Uses existing OneDrive credentials.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "onedrive_ingest_delete_after_process": {
        "category": "Watch Folders",
        "description": "Delete files from OneDrive ingest folder after download and enqueue",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Cloud Provider Watch Folders — Nextcloud
    "nextcloud_ingest_enabled": {
        "category": "Watch Folders",
        "description": "Enable Nextcloud watch folder ingestion (requires Nextcloud WebDAV credentials)",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "nextcloud_ingest_folder": {
        "category": "Watch Folders",
        "description": "Nextcloud folder path to poll for new documents (e.g. /Scans/Inbox). Uses existing Nextcloud credentials.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "nextcloud_ingest_delete_after_process": {
        "category": "Watch Folders",
        "description": "Delete files from Nextcloud ingest folder after download and enqueue",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Cloud Provider Watch Folders — S3
    "s3_ingest_enabled": {
        "category": "Watch Folders",
        "description": "Enable Amazon S3 prefix (watch folder) ingestion (requires S3/AWS credentials)",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "s3_ingest_prefix": {
        "category": "Watch Folders",
        "description": "S3 key prefix to poll for new objects to ingest (e.g. inbox/scanner/). Uses existing S3 credentials.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "s3_ingest_delete_after_process": {
        "category": "Watch Folders",
        "description": "Delete objects from S3 ingest prefix after download and enqueue",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Cloud Provider Watch Folders — WebDAV
    "webdav_ingest_enabled": {
        "category": "Watch Folders",
        "description": "Enable WebDAV watch folder ingestion (requires WebDAV URL and credentials)",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "webdav_ingest_folder": {
        "category": "Watch Folders",
        "description": "WebDAV folder path to poll for new documents. Uses existing WebDAV URL and credentials.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "webdav_ingest_delete_after_process": {
        "category": "Watch Folders",
        "description": "Delete files from WebDAV ingest folder after download and enqueue",
        "type": "boolean",
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
    "imap_attachment_filter": {
        "category": "IMAP",
        "description": (
            "Controls which attachment types are ingested from IMAP emails. "
            "Accepted values: 'documents_only' (PDFs and office files only, default) or 'all' (including images). "
            "Per-user IMAP accounts can override this global default."
        ),
        "type": "string",
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
    "telegram_enabled": {
        "category": "Notifications",
        "description": "Enable Telegram bot notifications.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "telegram_bot_token": {
        "category": "Notifications",
        "description": "Telegram Bot API token from @BotFather.",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "telegram_chat_id": {
        "category": "Notifications",
        "description": "Telegram chat ID to send notifications to.",
        "type": "string",
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
    "notify_on_user_signup": {
        "category": "Notifications",
        "description": "Send admin notifications when a new user signs up",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "notify_on_plan_change": {
        "category": "Notifications",
        "description": "Send admin notifications when a user changes their subscription plan",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "notify_on_payment_issue": {
        "category": "Notifications",
        "description": "Send admin notifications when a payment issue is reported for a user",
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
    "automation_hooks_enabled": {
        "category": "Feature Flags",
        "description": (
            "Enable Zapier / Make.com automation hook subscriptions and delivery. "
            "When enabled, external automation platforms can subscribe to DocuElevate events "
            "via the REST hooks protocol. Default: True."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "compliance_enabled": {
        "category": "Feature Flags",
        "description": (
            "Enable the compliance templates dashboard (GDPR, HIPAA, SOC 2). "
            "When enabled, admins can view compliance status and apply "
            "pre-built regulatory configurations. Default: True."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "factory_reset_on_startup": {
        "category": "Feature Flags",
        "description": (
            "Wipe all user data on every startup so the instance always starts fresh. "
            "Useful for demo/testing environments. Default: False."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "enable_factory_reset": {
        "category": "Feature Flags",
        "description": (
            "Show the System Reset page in the admin UI.  Allows administrators to "
            "trigger a full data wipe or a wipe-and-reimport from the web interface. Default: False."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Backup / Restore
    "backup_enabled": {
        "category": "Backup",
        "description": ("Enable automatic scheduled database backups (hourly, daily, weekly). Default: True."),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "backup_dir": {
        "category": "Backup",
        "description": (
            "Directory where local backup archives are stored. Defaults to <workdir>/backups when not set."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "backup_remote_destination": {
        "category": "Backup",
        "description": (
            "Storage provider for remote backup copies. "
            "Accepted values: s3, dropbox, google_drive, onedrive, sharepoint, nextcloud, webdav, ftp, sftp, email. "
            "Leave empty to keep backups local only."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
        "options": [
            "",
            "s3",
            "dropbox",
            "google_drive",
            "onedrive",
            "sharepoint",
            "nextcloud",
            "webdav",
            "ftp",
            "sftp",
            "email",
        ],
    },
    "backup_remote_folder": {
        "category": "Backup",
        "description": (
            "Sub-folder / key prefix used when uploading backup archives to the remote destination. Default: 'backups'."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "backup_retain_hourly": {
        "category": "Backup",
        "description": "Number of hourly backups to retain (default 96 = 4 days × 24 h).",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "backup_retain_daily": {
        "category": "Backup",
        "description": "Number of daily backups to retain (default 21 = 3 weeks).",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "backup_retain_weekly": {
        "category": "Backup",
        "description": "Number of weekly backups to retain (default 13 ≈ 3 months / 91 days).",
        "type": "integer",
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
    "audit_siem_enabled": {
        "category": "Security",
        "description": "Enable forwarding of audit events to an external SIEM system (Syslog, Splunk, Logstash, etc.).",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "audit_siem_transport": {
        "category": "Security",
        "description": (
            "Transport used to forward audit events. 'syslog' sends RFC 5424 messages over UDP/TCP. "
            "'http' sends JSON POST payloads to a webhook URL (Splunk HEC, Logstash, Grafana Loki, etc.)."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
        "options": ["syslog", "http"],
    },
    "audit_siem_syslog_host": {
        "category": "Security",
        "description": "Hostname or IP of the syslog receiver.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "audit_siem_syslog_port": {
        "category": "Security",
        "description": "Port of the syslog receiver. Default: 514.",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "audit_siem_syslog_protocol": {
        "category": "Security",
        "description": "Protocol for syslog transport: 'udp' or 'tcp'. Default: udp.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
        "options": ["udp", "tcp"],
    },
    "audit_siem_http_url": {
        "category": "Security",
        "description": (
            "HTTP endpoint URL for SIEM webhook delivery. Supports Splunk HEC, "
            "Logstash HTTP input, Grafana Loki push API, or any JSON-accepting endpoint."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "audit_siem_http_token": {
        "category": "Security",
        "description": "Bearer / HEC token included in the Authorization header of SIEM HTTP requests.",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "audit_siem_http_custom_headers": {
        "category": "Security",
        "description": "Comma-separated 'Key:Value' pairs of extra headers for SIEM HTTP requests.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Per-user upload rate limiting
    "upload_rate_limit_per_user": {
        "category": "Security",
        "description": (
            "Maximum number of uploads a single user may submit within upload_rate_limit_window seconds. "
            "The health-aware limiter may reduce this dynamically under high Redis queue depth or CPU load. "
            "Default: 20."
        ),
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "upload_rate_limit_window": {
        "category": "Security",
        "description": ("Sliding window in seconds over which upload_rate_limit_per_user is enforced. Default: 60."),
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
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
    # Local User Signup
    "allow_local_signup": {
        "category": "Authentication",
        "description": (
            "Allow users to self-register with email and password. "
            "Has no effect unless MULTI_USER_ENABLED is also True. "
            "Requires SMTP (EMAIL_HOST) to be configured so verification emails can be sent."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Stripe Billing
    "stripe_secret_key": {
        "category": "Billing",
        "description": "Stripe secret API key (starts with sk_). Required for payment processing.",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "stripe_publishable_key": {
        "category": "Billing",
        "description": "Stripe publishable key (starts with pk_). Exposed to the browser for Checkout.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "stripe_webhook_secret": {
        "category": "Billing",
        "description": "Stripe webhook signing secret (starts with whsec_). Used to verify incoming webhook payloads.",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": False,
    },
    "stripe_success_url": {
        "category": "Billing",
        "description": "Absolute URL Stripe redirects to after a successful checkout (e.g. https://app.example.com/billing/success).",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "stripe_cancel_url": {
        "category": "Billing",
        "description": "Absolute URL Stripe redirects to when a user cancels the checkout flow (e.g. https://app.example.com/pricing).",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Support / Help Center – Zammad integration
    "zammad_url": {
        "category": "Support",
        "description": "Base URL of your Zammad instance (e.g. https://zammad.example.com). Required for the chat widget and feedback form.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "zammad_chat_enabled": {
        "category": "Support",
        "description": "Show a Zammad live-chat widget on the Help Center page.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "zammad_chat_id": {
        "category": "Support",
        "description": "Zammad chat topic ID (see Channels → Chat → Topics in Zammad admin). Default: 1.",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "zammad_form_enabled": {
        "category": "Support",
        "description": "Show a 'Submit a Ticket' feedback form on the Help Center page.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "support_email": {
        "category": "Support",
        "description": "Support e-mail address displayed on the Help Center page.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    # Logging
    "log_level": {
        "category": "Observability",
        "description": (
            "Python logging level for the application root logger. "
            "Accepts: DEBUG, INFO, WARNING, ERROR, CRITICAL. "
            "When DEBUG=True and LOG_LEVEL is not explicitly set, "
            "the effective level is automatically lowered to DEBUG."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "log_format": {
        "category": "Observability",
        "description": (
            "Log output format: 'text' (human-readable, default) or "
            "'json' (structured JSON lines for SIEM / log aggregation)."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "log_syslog_enabled": {
        "category": "Observability",
        "description": "Forward application logs to a syslog receiver in addition to stdout.",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "log_syslog_host": {
        "category": "Observability",
        "description": "Hostname or IP of the syslog receiver for application logs.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "log_syslog_port": {
        "category": "Observability",
        "description": "Port of the syslog receiver for application logs.",
        "type": "integer",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "log_syslog_protocol": {
        "category": "Observability",
        "description": "Protocol for syslog transport: 'udp' or 'tcp'.",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    # Observability – Sentry
    "sentry_dsn": {
        "category": "Observability",
        "description": (
            "Sentry DSN (Data Source Name) URL. When set, runtime errors and "
            "performance traces are automatically sent to Sentry. "
            "Leave blank to disable Sentry entirely."
        ),
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": True,
    },
    "sentry_environment": {
        "category": "Observability",
        "description": (
            "Environment label attached to every Sentry event "
            "(e.g. 'development', 'staging', 'production'). "
            "Helps you filter events in the Sentry dashboard. Default: 'production'."
        ),
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "sentry_traces_sample_rate": {
        "category": "Observability",
        "description": (
            "Fraction of transactions captured for Sentry performance monitoring (0.0–1.0). "
            "0.0 disables tracing; 1.0 captures every request. Default: 0.1 (10%)."
        ),
        "type": "float",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "sentry_profiles_sample_rate": {
        "category": "Observability",
        "description": (
            "Fraction of profiled transactions sent to Sentry (0.0–1.0). "
            "Only active when sentry_traces_sample_rate > 0. Default: 0.0 (disabled)."
        ),
        "type": "float",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "sentry_send_default_pii": {
        "category": "Observability",
        "description": (
            "Attach personally identifiable information (PII) such as IP addresses "
            "to Sentry events. Disabled by default for GDPR/CCPA compliance."
        ),
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "sentry_js_traces_sample_rate": {
        "category": "Observability",
        "description": (
            "Fraction of browser page-loads captured for client-side Sentry performance tracing (0.0–1.0). "
            "0.0 (default) disables browser tracing; 1.0 captures every navigation. "
            "Only active when SENTRY_DSN is set."
        ),
        "type": "float",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "sentry_js_replay_session_sample_rate": {
        "category": "Observability",
        "description": (
            "Fraction of sessions recorded by Sentry Session Replay (0.0–1.0). "
            "0.0 (default) disables session recording; 1.0 records every session. "
            "Only active when SENTRY_DSN is set."
        ),
        "type": "float",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "sentry_js_replay_on_error_sample_rate": {
        "category": "Observability",
        "description": (
            "Fraction of error sessions recorded by Sentry Session Replay (0.0–1.0). "
            "Defaults to 0.1 (10%) so that errors are captured with replay context "
            "even when session-level recording is disabled. "
            "Only active when SENTRY_DSN is set."
        ),
        "type": "float",
        "sensitive": False,
        "required": False,
        "restart_required": True,
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
