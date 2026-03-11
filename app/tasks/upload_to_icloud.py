#!/usr/bin/env python3

"""Upload files to Apple iCloud Drive via the pyicloud library.

This module uses the ``pyicloud`` library to authenticate with Apple's iCloud
service and upload files to iCloud Drive.  Because Apple does not offer a public
REST API for iCloud Drive, this integration relies on the *unofficial*
reverse-engineered protocol implemented by ``pyicloud``.

Requirements
~~~~~~~~~~~~
* An Apple ID with iCloud Drive enabled.
* An **app-specific password** generated at https://appleid.apple.com (required
  when two-factor authentication is active – which is the default for all modern
  Apple IDs).
* The ``pyicloud`` Python package (``pip install pyicloud``).

Configuration
~~~~~~~~~~~~~
Set the following environment variables (or ``app/config.py`` fields):

* ``ICLOUD_USERNAME`` – Apple ID email address.
* ``ICLOUD_PASSWORD`` – App-specific password.
* ``ICLOUD_FOLDER``   – Target folder path inside iCloud Drive, using ``/`` as
  the separator (e.g. ``Documents/Uploads``).  The folder is created
  automatically if it does not exist.
* ``ICLOUD_COOKIE_DIRECTORY`` – (Optional) Directory for persisting session
  cookies so that re-authentication is avoided between task runs.  Defaults to
  ``~/.pyicloud``.
"""

import logging
import os

from app.celery_app import celery
from app.config import settings
from app.tasks.retry_config import UploadTaskWithRetry
from app.utils import log_task_progress

logger = logging.getLogger(__name__)


def _get_icloud_api(
    username: str,
    password: str,
    cookie_directory: str | None = None,
):
    """Return an authenticated ``PyiCloudService`` instance.

    Args:
        username: Apple ID email address.
        password: App-specific password.
        cookie_directory: Optional directory for session cookies.

    Returns:
        An authenticated ``PyiCloudService`` instance.

    Raises:
        ImportError: If ``pyicloud`` is not installed.
        ValueError: If authentication fails or 2FA is required interactively.
    """
    from pyicloud import PyiCloudService  # noqa: S404 – unofficial third-party iCloud client

    kwargs: dict = {}
    if cookie_directory:
        kwargs["cookie_directory"] = cookie_directory

    api = PyiCloudService(username, password, **kwargs)

    # If 2SA/2FA is required the user must use an app-specific password instead.
    if api.requires_2sa or api.requires_2fa:
        raise ValueError(
            "iCloud account requires two-factor authentication.  "
            "Please generate an app-specific password at https://appleid.apple.com "
            "and use it as ICLOUD_PASSWORD."
        )

    return api


def _navigate_to_folder(drive_root, folder_path: str):
    """Navigate into (or create) the folder hierarchy described by *folder_path*.

    Args:
        drive_root: The iCloud Drive root node (``api.drive``).
        folder_path: ``/``-separated path such as ``Documents/Uploads``.

    Returns:
        The drive node representing the target folder.
    """
    node = drive_root
    if not folder_path:
        return node

    parts = [p for p in folder_path.strip("/").split("/") if p]
    for part in parts:
        children = {child.name: child for child in node.dir()}
        if part in children:
            node = children[part]
        else:
            # Create the missing folder
            node = node.mkdir(part)
    return node


@celery.task(base=UploadTaskWithRetry, bind=True)
def upload_to_icloud(self, file_path: str, file_id: int = None, folder_override: str = None):
    """Upload a file to Apple iCloud Drive.

    Args:
        file_path: Local path to the file to upload.
        file_id: Optional ``FileRecord.id`` for progress logging.
        folder_override: If provided, overrides the default ``ICLOUD_FOLDER``
            setting for this upload.
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting iCloud Drive upload: {file_path}")
    log_task_progress(
        task_id,
        "upload_to_icloud",
        "in_progress",
        f"Uploading to iCloud Drive: {os.path.basename(file_path)}",
        file_id=file_id,
    )

    # ------------------------------------------------------------------
    # Validate inputs
    # ------------------------------------------------------------------
    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_icloud", "failure", error_msg, file_id=file_id)
        raise FileNotFoundError(error_msg)

    if not settings.icloud_username or not settings.icloud_password:
        error_msg = "iCloud credentials are not configured (ICLOUD_USERNAME / ICLOUD_PASSWORD)"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_icloud", "failure", error_msg, file_id=file_id)
        raise ValueError(error_msg)

    filename = os.path.basename(file_path)
    target_folder = folder_override if folder_override is not None else (settings.icloud_folder or "")

    # ------------------------------------------------------------------
    # Authenticate & upload
    # ------------------------------------------------------------------
    try:
        api = _get_icloud_api(
            settings.icloud_username,
            settings.icloud_password,
            settings.icloud_cookie_directory,
        )

        folder_node = _navigate_to_folder(api.drive, target_folder)

        with open(file_path, "rb") as fh:
            folder_node.upload(fh)

        logger.info(f"[{task_id}] Successfully uploaded {filename} to iCloud Drive folder '{target_folder}'")
        log_task_progress(
            task_id,
            "upload_to_icloud",
            "success",
            f"Uploaded to iCloud Drive: {filename}",
            file_id=file_id,
        )
        return {
            "status": "Completed",
            "file": file_path,
            "icloud_folder": target_folder or "/",
        }

    except Exception as e:
        error_msg = f"Error uploading {filename} to iCloud Drive: {e}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_icloud", "failure", error_msg, file_id=file_id)
        raise RuntimeError(error_msg) from e
