#!/usr/bin/env python3

import logging
import os
from urllib.parse import urljoin

import requests

from app.celery_app import celery
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import log_task_progress

logger = logging.getLogger(__name__)


@celery.task(base=BaseTaskWithRetry, bind=True)
def upload_to_webdav(self, file_path: str, file_id: int = None):
    """
    Uploads a file to a WebDAV server in the configured folder.

    Args:
        file_path: Path to the file to upload
        file_id: Optional file ID to associate with logs
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting WebDAV upload: {file_path}")
    log_task_progress(
        task_id,
        "upload_to_webdav",
        "in_progress",
        f"Uploading to WebDAV: {os.path.basename(file_path)}",
        file_id=file_id,
    )

    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_webdav", "failure", error_msg, file_id=file_id)
        raise FileNotFoundError(error_msg)

    # Extract filename
    filename = os.path.basename(file_path)

    # Check if WebDAV settings are configured
    if not settings.webdav_url:
        error_msg = "WebDAV URL is not configured"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_webdav", "failure", error_msg, file_id=file_id)
        raise ValueError(error_msg)

    # Construct the full upload URL
    webdav_folder = settings.webdav_folder or ""
    # Ensure folder doesn't have leading slash if we're joining it to the base URL
    if webdav_folder and webdav_folder.startswith("/"):
        webdav_folder = webdav_folder[1:]

    # Join the base URL and folder path
    target_url = urljoin(settings.webdav_url, webdav_folder)
    # Ensure URL ends with a slash for proper joining with filename
    if not target_url.endswith("/"):
        target_url += "/"

    # Construct final URL with filename
    webdav_url = urljoin(target_url, filename)

    # Read file content
    try:
        with open(file_path, "rb") as file_data:
            response = requests.put(
                webdav_url,
                auth=(settings.webdav_username, settings.webdav_password),
                data=file_data,
                verify=settings.webdav_verify_ssl if hasattr(settings, "webdav_verify_ssl") else True,
                timeout=settings.http_request_timeout,
            )

        # Check if upload was successful
        if response.status_code in (200, 201, 204):
            logger.info(f"[{task_id}] Successfully uploaded {filename} to WebDAV at {webdav_url}.")
            log_task_progress(
                task_id, "upload_to_webdav", "success", f"Uploaded to WebDAV: {filename}", file_id=file_id
            )
            return {"status": "Completed", "file": file_path, "url": webdav_url}
        else:
            error_msg = f"Failed to upload {filename} to WebDAV: {response.status_code} - {response.text}"
            logger.error(f"[{task_id}] {error_msg}")
            log_task_progress(task_id, "upload_to_webdav", "failure", error_msg, file_id=file_id)
            raise Exception(error_msg)

    except Exception as e:
        error_msg = f"Error uploading {filename} to WebDAV: {str(e)}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_webdav", "failure", error_msg, file_id=file_id)
        raise Exception(error_msg)
