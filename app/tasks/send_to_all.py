#!/usr/bin/env python3

import logging
import os

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import FileRecord, IntegrationDirection, UserIntegration
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.upload_to_dropbox import upload_to_dropbox
from app.tasks.upload_to_email import upload_to_email
from app.tasks.upload_to_ftp import upload_to_ftp
from app.tasks.upload_to_google_drive import upload_to_google_drive
from app.tasks.upload_to_icloud import upload_to_icloud
from app.tasks.upload_to_nextcloud import upload_to_nextcloud
from app.tasks.upload_to_onedrive import upload_to_onedrive
from app.tasks.upload_to_paperless import upload_to_paperless
from app.tasks.upload_to_s3 import upload_to_s3
from app.tasks.upload_to_sftp import upload_to_sftp
from app.tasks.upload_to_webdav import upload_to_webdav
from app.utils.config_validator import get_provider_status
from app.utils.logging import log_task_progress

logger = logging.getLogger(__name__)


def _should_upload_to_dropbox():
    return bool(
        getattr(settings, "dropbox_enabled", True)
        and settings.dropbox_app_key
        and settings.dropbox_app_secret
        and settings.dropbox_refresh_token
    )


def _should_upload_to_nextcloud():
    return bool(
        getattr(settings, "nextcloud_enabled", True)
        and settings.nextcloud_upload_url
        and settings.nextcloud_username
        and settings.nextcloud_password
    )


def _should_upload_to_paperless():
    return bool(
        getattr(settings, "paperless_enabled", True) and settings.paperless_ngx_api_token and settings.paperless_host
    )


def _should_upload_to_google_drive():
    if not getattr(settings, "google_drive_enabled", True):
        return False
    # Check for OAuth configuration
    if getattr(settings, "google_drive_use_oauth", False):
        return bool(
            settings.google_drive_client_id
            and settings.google_drive_client_secret
            and settings.google_drive_refresh_token
            and settings.google_drive_folder_id
        )
    # Or check for service account configuration
    else:
        return bool(settings.google_drive_credentials_json and settings.google_drive_folder_id)


def _should_upload_to_webdav():
    return bool(
        getattr(settings, "webdav_enabled", True)
        and settings.webdav_url
        and settings.webdav_username
        and settings.webdav_password
    )


def _should_upload_to_ftp():
    return bool(
        getattr(settings, "ftp_enabled", True) and settings.ftp_host and settings.ftp_username and settings.ftp_password
    )


def _should_upload_to_sftp():
    return bool(
        getattr(settings, "sftp_enabled", True)
        and settings.sftp_host
        and settings.sftp_username
        and (settings.sftp_password or settings.sftp_private_key)
    )


def _should_upload_to_email():
    return bool(
        getattr(settings, "dest_email_enabled", True)
        and settings.dest_email_host
        and settings.dest_email_username
        and settings.dest_email_password
        and settings.dest_email_default_recipient
    )


def _should_upload_to_onedrive():
    return bool(
        getattr(settings, "onedrive_enabled", True)
        and settings.onedrive_client_id
        and settings.onedrive_client_secret
        and settings.onedrive_refresh_token
    )


def _should_upload_to_s3():
    return bool(
        getattr(settings, "s3_enabled", True)
        and settings.s3_bucket_name
        and settings.aws_access_key_id
        and settings.aws_secret_access_key
    )


def _should_upload_to_icloud():
    return bool(getattr(settings, "icloud_enabled", True) and settings.icloud_username and settings.icloud_password)


def get_configured_services_from_validator():
    """
    Use the config validator to determine which services are configured and enabled.
    Returns a dictionary with service names as keys and boolean values indicating
    whether they're properly configured AND explicitly enabled.
    """
    providers = get_provider_status()

    service_map = {
        "Dropbox": "dropbox",
        "NextCloud": "nextcloud",
        "Paperless-ngx": "paperless",
        "Google Drive": "google_drive",
        "WebDAV": "webdav",
        "FTP Storage": "ftp",
        "SFTP Storage": "sftp",
        "Email": "email",
        "OneDrive": "onedrive",
        "S3 Storage": "s3",
        "iCloud Drive": "icloud",
    }

    result = {}
    for provider_name, internal_name in service_map.items():
        if provider_name in providers:
            provider = providers[provider_name]
            result[internal_name] = provider.get("configured", False) and provider.get("enabled", True)

    return result


@celery.task(base=BaseTaskWithRetry, bind=True)
def send_to_all_destinations(self, file_path: str, use_validator=True, file_id: int = None, folder_overrides=None):
    """
    Distribute a file to all configured storage destinations.

    Args:
        file_path: Path to the file to distribute
        use_validator: Whether to use the config validator to determine enabled services
                       (if False, falls back to individual checks)
        file_id: Optional file ID to associate with logs
        folder_overrides: Optional dict mapping provider names to folder override strings.
                          When set, the override is passed to the upload task which uses it
                          instead of the provider's default folder.  Example:
                          {"dropbox": "/Documents/pdfa", "s3": "docs/pdfa/"}
    """
    task_id = self.request.id

    if not os.path.exists(file_path):
        logger.error(f"[{task_id}] File not found: {file_path}")
        log_task_progress(task_id, "send_to_all_destinations", "failure", "File not found", file_id=file_id)
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info(f"[{task_id}] Sending {file_path} to all configured destinations")
    log_task_progress(
        task_id,
        "send_to_all_destinations",
        "in_progress",
        f"Distributing: {os.path.basename(file_path)}",
        file_id=file_id,
    )

    # Get file_id from database if not provided (fallback only, prefer passing file_id explicitly)
    if file_id is None:
        with SessionLocal() as db:
            # Only as a last resort, try to find by basename match
            # This should not be needed if file_id is passed correctly through the chain
            file_record = (
                db.query(FileRecord)
                .filter(FileRecord.local_filename == os.path.join(settings.workdir, "tmp", os.path.basename(file_path)))
                .first()
            )
            if file_record:
                file_id = file_record.id

    results = {}

    # Define service configurations
    services = [
        {
            "name": "dropbox",
            "should_upload": _should_upload_to_dropbox,
            "upload_func": upload_to_dropbox,
        },
        {
            "name": "nextcloud",
            "should_upload": _should_upload_to_nextcloud,
            "upload_func": upload_to_nextcloud,
        },
        {
            "name": "paperless",
            "should_upload": _should_upload_to_paperless,
            "upload_func": upload_to_paperless,
        },
        {
            "name": "google_drive",
            "should_upload": _should_upload_to_google_drive,
            "upload_func": upload_to_google_drive,
        },
        {
            "name": "webdav",
            "should_upload": _should_upload_to_webdav,
            "upload_func": upload_to_webdav,
        },
        {
            "name": "ftp",
            "should_upload": _should_upload_to_ftp,
            "upload_func": upload_to_ftp,
        },
        {
            "name": "sftp",
            "should_upload": _should_upload_to_sftp,
            "upload_func": upload_to_sftp,
        },
        {
            "name": "email",
            "should_upload": _should_upload_to_email,
            "upload_func": upload_to_email,
        },
        {
            "name": "onedrive",
            "should_upload": _should_upload_to_onedrive,
            "upload_func": upload_to_onedrive,
        },
        {
            "name": "s3",
            "should_upload": _should_upload_to_s3,
            "upload_func": upload_to_s3,
        },
        {
            "name": "icloud",
            "should_upload": _should_upload_to_icloud,
            "upload_func": upload_to_icloud,
        },
    ]

    # Optionally get configuration status from validator
    configured_services = {}
    if use_validator:
        try:
            configured_services = get_configured_services_from_validator()
            logger.info(f"[{task_id}] Configured services according to validator: {configured_services}")
        except Exception as e:
            logger.warning(f"[{task_id}] Failed to get configuration from validator: {str(e)}")
            use_validator = False

    # Process each service
    queued_count = 0
    for service in services:
        service_name = service["name"]

        # Determine if service is configured
        is_configured = False
        if use_validator and service_name in configured_services:
            is_configured = configured_services[service_name]
            logger.debug(f"[{task_id}] {service_name} configuration from validator: {is_configured}")
        else:
            try:
                is_configured = service["should_upload"]()
                logger.debug(f"[{task_id}] {service_name} configuration from function: {is_configured}")
            except Exception as e:
                logger.error(f"[{task_id}] Error checking configuration for {service_name}: {str(e)}")
                is_configured = False

        # Queue the upload task if service is configured
        if is_configured:
            logger.info(f"[{task_id}] Queueing {file_path} for {service_name} upload")
            log_task_progress(
                task_id, f"queue_{service_name}", "in_progress", f"Queueing upload to {service_name}", file_id=file_id
            )
            try:
                kwargs = {"file_id": file_id}
                if folder_overrides and service_name in folder_overrides:
                    kwargs["folder_override"] = folder_overrides[service_name]
                task = service["upload_func"].delay(file_path, **kwargs)
                results[f"{service_name}_task_id"] = task.id
                queued_count += 1
                log_task_progress(
                    task_id, f"queue_{service_name}", "success", f"Queued for {service_name}", file_id=file_id
                )
            except Exception as e:
                logger.error(f"[{task_id}] Failed to queue {service_name} task: {str(e)}")
                results[f"{service_name}_error"] = str(e)
                log_task_progress(task_id, f"queue_{service_name}", "failure", f"Failed: {str(e)}", file_id=file_id)

    logger.info(f"[{task_id}] Queued {queued_count} upload tasks")
    log_task_progress(task_id, "send_to_all_destinations", "success", f"Queued {queued_count} uploads", file_id=file_id)

    return {"status": "Queued", "file_path": file_path, "tasks": results}


@celery.task(base=BaseTaskWithRetry, bind=True)
def send_to_user_destinations(self, file_path: str, owner_id: str, file_id: int | None = None):
    """Dispatch uploads to all active DESTINATION UserIntegrations for *owner_id*.

    This is the user-specific counterpart of :func:`send_to_all_destinations`.
    It queries the ``user_integrations`` table for records where:

    * ``owner_id`` matches the document owner,
    * ``direction == "DESTINATION"``, and
    * ``is_active == True``.

    One :func:`upload_to_user_integration` Celery task is queued for each
    matching integration so that uploads proceed asynchronously and
    independently.

    Args:
        file_path: Absolute path to the processed document file.
        owner_id: The stable user identifier from ``FileRecord.owner_id``.
        file_id: Optional ``FileRecord.id`` used for progress logging.

    Returns:
        A dict summarising how many integrations were queued.
    """
    from app.tasks.upload_to_user_integration import upload_to_user_integration

    task_id = self.request.id
    filename = os.path.basename(file_path)

    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error("[%s] %s", task_id, error_msg)
        log_task_progress(task_id, "send_to_user_destinations", "failure", error_msg, file_id=file_id)
        raise FileNotFoundError(error_msg)

    logger.info("[%s] Sending %s to user destinations for owner=%s", task_id, filename, owner_id)
    log_task_progress(
        task_id,
        "send_to_user_destinations",
        "in_progress",
        f"Distributing {filename} to user integrations",
        file_id=file_id,
    )

    with SessionLocal() as db:
        integrations = (
            db.query(UserIntegration)
            .filter(
                UserIntegration.owner_id == owner_id,
                UserIntegration.direction == IntegrationDirection.DESTINATION,
                UserIntegration.is_active.is_(True),
            )
            .all()
        )
        # Snapshot the IDs so we don't keep the session open
        integration_ids = [(i.id, i.name, i.integration_type) for i in integrations]

    queued = 0
    task_results: dict[str, str] = {}

    for int_id, int_name, int_type in integration_ids:
        logger.info("[%s] Queueing upload for integration %d (%s '%s')", task_id, int_id, int_type, int_name)
        log_task_progress(
            task_id,
            f"queue_user_integration_{int_id}",
            "in_progress",
            f"Queueing upload to {int_type} '{int_name}'",
            file_id=file_id,
        )
        try:
            celery_task = upload_to_user_integration.delay(file_path, int_id, file_id)
            task_results[f"integration_{int_id}_task_id"] = celery_task.id
            queued += 1
            log_task_progress(
                task_id,
                f"queue_user_integration_{int_id}",
                "success",
                f"Queued upload to {int_type} '{int_name}'",
                file_id=file_id,
            )
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            logger.error("[%s] Failed to queue upload for integration %d: %s", task_id, int_id, error_msg)
            task_results[f"integration_{int_id}_error"] = error_msg
            log_task_progress(
                task_id,
                f"queue_user_integration_{int_id}",
                "failure",
                f"Failed to queue {int_type} '{int_name}': {error_msg}",
                file_id=file_id,
            )

    logger.info("[%s] Queued %d user-integration upload(s) for owner=%s", task_id, queued, owner_id)
    log_task_progress(
        task_id,
        "send_to_user_destinations",
        "success",
        f"Queued {queued} user-integration upload(s)",
        file_id=file_id,
    )
    return {"status": "Queued", "file_path": file_path, "queued": queued, "tasks": task_results}


def get_user_destination_count(owner_id: str) -> int:
    """Return the number of active DESTINATION integrations for *owner_id*.

    A count of zero means no user-specific destinations are configured and
    the caller should fall back to the global :func:`send_to_all_destinations`.
    """
    with SessionLocal() as db:
        return (
            db.query(UserIntegration)
            .filter(
                UserIntegration.owner_id == owner_id,
                UserIntegration.direction == IntegrationDirection.DESTINATION,
                UserIntegration.is_active.is_(True),
            )
            .count()
        )
