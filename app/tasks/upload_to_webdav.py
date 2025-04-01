#!/usr/bin/env python3

import os
import requests
from urllib.parse import urljoin
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.celery_app import celery
import logging

logger = logging.getLogger(__name__)

@celery.task(base=BaseTaskWithRetry)
def upload_to_webdav(file_path: str):
    """Uploads a file to a WebDAV server in the configured folder."""

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Extract filename
    filename = os.path.basename(file_path)

    # Check if WebDAV settings are configured
    if not settings.webdav_url:
        error_msg = "WebDAV URL is not configured"
        logger.error(error_msg)
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
                verify=settings.webdav_verify_ssl if hasattr(settings, "webdav_verify_ssl") else True
            )

        # Check if upload was successful
        if response.status_code in (200, 201, 204):
            logger.info(f"Successfully uploaded {filename} to WebDAV at {webdav_url}.")
            return {"status": "Completed", "file": file_path, "url": webdav_url}
        else:
            error_msg = f"Failed to upload {filename} to WebDAV: {response.status_code} - {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    except Exception as e:
        error_msg = f"Error uploading {filename} to WebDAV: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
