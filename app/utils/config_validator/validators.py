#!/usr/bin/env python3

import logging
import os
import socket

from app.config import settings

logger = logging.getLogger(__name__)


def validate_email_config() -> list[str]:
    """Validates email configuration settings"""
    issues = []

    # Check for required email settings
    if not getattr(settings, "email_host", None):
        issues.append("EMAIL_HOST is not configured")
    if not getattr(settings, "email_port", None):
        issues.append("EMAIL_PORT is not configured")

    # Test SMTP server connectivity if host is configured
    if getattr(settings, "email_host", None) and getattr(settings, "email_port", None):
        try:
            # Attempt to resolve the hostname
            socket.gethostbyname(settings.email_host)
        except socket.gaierror:
            issues.append(f"Cannot resolve email host: {settings.email_host}")

    # Check for authentication settings
    if not getattr(settings, "email_username", None):
        issues.append("EMAIL_USERNAME is not configured")
    if not getattr(settings, "email_password", None):
        issues.append("EMAIL_PASSWORD is not configured")

    return issues


def validate_auth_config() -> list[str]:
    """Validates authentication configuration settings"""
    issues = []

    # If auth is enabled, check for required settings
    if getattr(settings, "auth_enabled", False):
        # Check for session secret
        if not getattr(settings, "session_secret", None):
            issues.append("SESSION_SECRET is not configured but AUTH_ENABLED is True")
        elif len(getattr(settings, "session_secret", "")) < 32:
            issues.append("SESSION_SECRET must be at least 32 characters long")

        # Check if using simple authentication or OIDC
        using_simple_auth = bool(
            getattr(settings, "admin_username", None) and getattr(settings, "admin_password", None)
        )

        using_oidc = bool(
            getattr(settings, "authentik_client_id", None)
            and getattr(settings, "authentik_client_secret", None)
            and getattr(settings, "authentik_config_url", None)
        )

        if not using_simple_auth and not using_oidc:
            issues.append("Neither simple authentication nor OIDC are properly configured")

        # If using OIDC, check for provider name
        if using_oidc and not getattr(settings, "oauth_provider_name", None):
            issues.append("OAUTH_PROVIDER_NAME is not configured but OIDC is enabled")

    return issues


def validate_storage_configs() -> dict[str, list[str]]:
    """Validates configuration for all storage providers"""
    issues = {}

    # Validate Dropbox config
    dropbox_issues = []
    if not (
        getattr(settings, "dropbox_app_key", None)
        and getattr(settings, "dropbox_app_secret", None)
        and getattr(settings, "dropbox_refresh_token", None)
    ):
        dropbox_issues.append("Dropbox credentials are not fully configured")
    issues["dropbox"] = dropbox_issues

    # Validate Nextcloud config
    nextcloud_issues = []
    if not (
        getattr(settings, "nextcloud_upload_url", None)
        and getattr(settings, "nextcloud_username", None)
        and getattr(settings, "nextcloud_password", None)
    ):
        nextcloud_issues.append("Nextcloud credentials are not fully configured")
    issues["nextcloud"] = nextcloud_issues

    # Validate SFTP config
    sftp_issues = []
    if not getattr(settings, "sftp_host", None):
        sftp_issues.append("SFTP_HOST is not configured")

    sftp_key_path = getattr(settings, "sftp_private_key", None)
    if sftp_key_path and not os.path.exists(sftp_key_path):
        sftp_issues.append(f"SFTP_KEY_PATH file not found: {sftp_key_path}")

    if not sftp_key_path and not getattr(settings, "sftp_password", None):
        sftp_issues.append("Neither SFTP_KEY_PATH nor SFTP_PASSWORD is configured")

    issues["sftp"] = sftp_issues

    # Validate Email sending
    email_issues = []
    if not getattr(settings, "email_host", None):
        email_issues.append("EMAIL_HOST is not configured")
    if not getattr(settings, "email_default_recipient", None):
        email_issues.append("EMAIL_DEFAULT_RECIPIENT is not configured")
    issues["email"] = email_issues

    # Validate S3
    s3_issues = []
    if not getattr(settings, "s3_bucket_name", None):
        s3_issues.append("S3_BUCKET_NAME is not configured")
    if not (getattr(settings, "aws_access_key_id", None) and getattr(settings, "aws_secret_access_key", None)):
        s3_issues.append("AWS credentials are not configured")
    issues["s3"] = s3_issues

    # Validate FTP
    ftp_issues = []
    if not getattr(settings, "ftp_host", None):
        ftp_issues.append("FTP_HOST is not configured")
    if not getattr(settings, "ftp_username", None):
        ftp_issues.append("FTP_USERNAME is not configured")
    if not getattr(settings, "ftp_password", None):
        ftp_issues.append("FTP_PASSWORD is not configured")
    issues["ftp"] = ftp_issues

    # Validate WebDAV
    webdav_issues = []
    if not getattr(settings, "webdav_url", None):
        webdav_issues.append("WEBDAV_URL is not configured")
    if not getattr(settings, "webdav_username", None):
        webdav_issues.append("WEBDAV_USERNAME is not configured")
    if not getattr(settings, "webdav_password", None):
        webdav_issues.append("WEBDAV_PASSWORD is not configured")
    issues["webdav"] = webdav_issues

    # Validate Google Drive
    gdrive_issues = []
    if not getattr(settings, "google_drive_credentials_json", None):
        gdrive_issues.append("GOOGLE_DRIVE_CREDENTIALS_JSON is not configured")
    if not getattr(settings, "google_drive_folder_id", None):
        gdrive_issues.append("GOOGLE_DRIVE_FOLDER_ID is not configured")
    issues["google_drive"] = gdrive_issues

    # Validate Paperless
    paperless_issues = []
    if not getattr(settings, "paperless_host", None):
        paperless_issues.append("PAPERLESS_HOST is not configured")
    if not getattr(settings, "paperless_ngx_api_token", None):
        paperless_issues.append("PAPERLESS_NGX_API_TOKEN is not configured")
    issues["paperless"] = paperless_issues

    # Validate OneDrive
    onedrive_issues = []
    if not (
        getattr(settings, "onedrive_client_id", None)
        and getattr(settings, "onedrive_client_secret", None)
        and getattr(settings, "onedrive_refresh_token", None)
    ):
        onedrive_issues.append("OneDrive credentials are not fully configured")
    issues["onedrive"] = onedrive_issues

    # Validate Uptime Kuma
    uptime_kuma_issues = []
    if not getattr(settings, "uptime_kuma_url", None):
        uptime_kuma_issues.append("UPTIME_KUMA_URL is not configured")
    issues["uptime_kuma"] = uptime_kuma_issues

    return issues


def validate_notification_config() -> list[str]:
    """Check notification configuration"""
    issues = []

    # Check if any notification URLs are configured
    if not getattr(settings, "notification_urls", None):
        issues.append("No notification URLs configured")
    else:
        try:
            # Try initializing Apprise to validate URLs
            import apprise

            a = apprise.Apprise()

            for url in settings.notification_urls:
                try:
                    if not a.add(url):
                        issues.append(f"Invalid notification URL format: {url}")
                except Exception as e:
                    issues.append(f"Error with notification URL: {str(e)}")

        except ImportError:
            issues.append("Apprise module not installed")

    if not issues:
        logger.info("Notification configuration valid")
    else:
        logger.warning(f"Notification configuration issues: {', '.join(issues)}")

    return issues


def check_all_configs() -> dict[str, list[str] | dict[str, list[str]]]:
    """Run all configuration validations and log results"""
    from app.utils.config_validator.settings_display import dump_all_settings

    logger.info("Validating application configuration...")

    # Check if debug is enabled and dump all settings if it is
    if hasattr(settings, "debug") and settings.debug:
        dump_all_settings()

    # Check auth config
    auth_issues = validate_auth_config()
    if auth_issues:
        logger.warning(f"Authentication configuration issues: {', '.join(auth_issues)}")
    else:
        logger.info("Authentication configuration OK")

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

    # Check notification configuration
    notification_issues = validate_notification_config()
    if notification_issues:
        logger.warning(f"Notification configuration issues: {', '.join(notification_issues)}")
    else:
        logger.info("Notification configuration OK")

    # Return all identified issues
    return {"auth": auth_issues, "email": email_issues, "storage": storage_issues, "notification": notification_issues}
