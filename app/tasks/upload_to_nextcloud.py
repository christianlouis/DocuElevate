#!/usr/bin/env python3

import os
import requests
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.celery_app import celery

@celery.task(base=BaseTaskWithRetry)
def upload_to_nextcloud(file_path: str):
    """Uploads a file to Nextcloud in the configured folder."""

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Extract filename
    filename = os.path.basename(file_path)

    # Construct the full upload URL
    nextcloud_url = f"{settings.nextcloud_upload_url}/{settings.nextcloud_folder}/{filename}"

    # Read file content
    with open(file_path, "rb") as file_data:
        response = requests.put(
            nextcloud_url,
            auth=(settings.nextcloud_username, settings.nextcloud_password),
            data=file_data
        )

    # Check if upload was successful
    if response.status_code in (200, 201):
        print(f"[INFO] Successfully uploaded {filename} to Nextcloud at {nextcloud_url}.")
        return {"status": "Completed", "file": file_path}
    else:
        error_msg = f"[ERROR] Failed to upload {filename} to Nextcloud: {response.status_code} - {response.text}"
        print(error_msg)
        raise Exception(error_msg)
