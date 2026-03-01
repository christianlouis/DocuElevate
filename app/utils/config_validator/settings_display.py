"""
Module for displaying and organizing settings information
"""

import logging

from app.config import settings
from app.utils.config_validator.masking import mask_sensitive_value

logger = logging.getLogger(__name__)

# Pydantic model attributes that should not be iterated as user settings
_PYDANTIC_INTERNALS = {"model_computed_fields", "model_config", "model_extra", "model_fields", "model_fields_set"}


def dump_all_settings() -> None:
    """Log all settings values for diagnostic purposes"""
    logger.info("--- DUMPING ALL SETTINGS FOR DIAGNOSTIC PURPOSES ---")
    for key in dir(settings):
        if not key.startswith("_") and key not in _PYDANTIC_INTERNALS and not callable(getattr(settings, key)):
            value = getattr(settings, key)
            # Mask sensitive values in logs
            if (
                key.lower().find("password") >= 0
                or key.lower().find("secret") >= 0
                or key.lower().find("token") >= 0
                or key.lower().find("key") >= 0
            ):
                if value:
                    if isinstance(value, str) and len(value) > 10:
                        visible_start = max(1, len(value) // 3)
                        visible_end = max(1, len(value) // 4)
                        value = (
                            f"{value[:visible_start]}"
                            f"{'*' * (len(value) - visible_start - visible_end)}"
                            f"{value[-visible_end:]}"
                        )
                    else:
                        value = (
                            f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"
                            if isinstance(value, str) and len(value) > 4
                            else "****"
                        )

            # Special handling for notification URLs
            if key == "notification_urls" and value:
                try:
                    from app.utils.notification import _mask_sensitive_url

                    if isinstance(value, list):
                        masked_urls = [_mask_sensitive_url(url) for url in value]
                        logger.info(f"{key}: {masked_urls}")
                    else:
                        logger.info(f"{key}: {_mask_sensitive_url(value)}")
                    continue  # Skip the default logging
                except (ImportError, AttributeError):
                    pass  # Fall back to default logging if _mask_sensitive_url is not available

            logger.info(f"{key}: {value}")
    logger.info("--- END OF SETTINGS DUMP ---")


def get_settings_for_display(show_values: bool = False) -> dict[str, list[dict[str, object]]]:
    """
    Group settings into logical categories and check if they are configured.
    Returns a dictionary with categories as keys and lists of setting items as values.
    Each setting item is a dict with name, value, and is_configured.

    If show_values is False, sensitive values are masked.
    """
    # First include system info with version in result
    result = {
        "System Info": [
            {"name": "App Version", "value": settings.version, "is_configured": True},
            {"name": "Build Date", "value": settings.build_date, "is_configured": True},
        ]
    }

    # Define categories and their settings
    categories = {
        "Core": [
            "debug",  # Explicitly include debug setting
            "external_hostname",
            "workdir",
            "database_url",
            "redis_url",
            "gotenberg_url",
            "allow_file_delete",  # Added allow_file_delete to Core settings
        ],
        "Authentication": [
            "auth_enabled",
            "session_secret",
            "admin_username",
            "admin_password",
            "authentik_client_id",
            "authentik_client_secret",
            "authentik_config_url",
            "oauth_provider_name",
        ],
        "Email": [
            "email_host",
            "email_port",
            "email_username",
            "email_password",
            "email_use_tls",
            "email_sender",
            "email_default_recipient",
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
            "imap2_delete_after_process",
            "imap_readonly_mode",
        ],
        "Dropbox": ["dropbox_app_key", "dropbox_app_secret", "dropbox_folder", "dropbox_refresh_token"],
        "NextCloud": ["nextcloud_upload_url", "nextcloud_username", "nextcloud_password", "nextcloud_folder"],
        "Paperless": ["paperless_host", "paperless_ngx_api_token"],
        "Google Drive": [
            "google_drive_use_oauth",
            "google_drive_client_id",
            "google_drive_client_secret",
            "google_drive_refresh_token",
            "google_drive_credentials_json",
            "google_drive_folder_id",
            "google_drive_delegate_to",
        ],
        "OneDrive": [
            "onedrive_client_id",
            "onedrive_client_secret",
            "onedrive_tenant_id",
            "onedrive_refresh_token",
            "onedrive_folder_path",
        ],
        "WebDAV": ["webdav_url", "webdav_username", "webdav_password", "webdav_folder", "webdav_verify_ssl"],
        "SFTP": [
            "sftp_host",
            "sftp_port",
            "sftp_username",
            "sftp_password",
            "sftp_folder",
            "sftp_private_key",
            "sftp_private_key_passphrase",
        ],
        "FTP": [
            "ftp_host",
            "ftp_port",
            "ftp_username",
            "ftp_password",
            "ftp_folder",
            "ftp_use_tls",
            "ftp_allow_plaintext",
        ],
        "S3/AWS": [
            "aws_access_key_id",
            "aws_secret_access_key",
            "aws_region",
            "s3_bucket_name",
            "s3_folder_prefix",
            "s3_storage_class",
            "s3_acl",
        ],
        "AI Services": [
            "ai_provider",
            "ai_model",
            "openai_api_key",
            "openai_base_url",
            "openai_model",
            "anthropic_api_key",
            "gemini_api_key",
            "ollama_base_url",
            "openrouter_api_key",
            "openrouter_base_url",
            "portkey_api_key",
            "portkey_virtual_key",
            "portkey_config",
            "portkey_base_url",
            "azure_openai_api_version",
            "azure_ai_key",
            "azure_endpoint",
            "azure_region",
        ],
        "Monitoring": ["uptime_kuma_url", "uptime_kuma_ping_interval"],
        "Notifications": [
            "notification_urls",
            "notify_on_task_failure",
            "notify_on_credential_failure",
            "notify_on_startup",
            "notify_on_shutdown",
        ],
    }

    # Handle any settings that don't fit into the predefined categories
    all_settings = set(
        [
            key
            for key in dir(settings)
            if not key.startswith("_") and key not in _PYDANTIC_INTERNALS and not callable(getattr(settings, key))
        ]
    )

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
                    "password",
                    "secret",
                    "token",
                    "api_key",
                    "private_key",
                    "credentials",
                    "access_key",
                    "ai_key",
                ]

                # Check if this is a sensitive value that should be masked
                is_sensitive = any(pattern in key.lower() for pattern in sensitive_patterns)

                # Special handling for "auth" to avoid matching prefixes like "authentik"
                if not is_sensitive and "auth" in key.lower():
                    # Only mark as sensitive if "auth" is a standalone word or at the end
                    # This avoids matching "authentik" as sensitive
                    parts = key.lower().split("_")
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

                items.append({"name": key, "value": value, "is_configured": is_configured})

        if items:  # Only add categories that have items
            result[category] = items

    return result
