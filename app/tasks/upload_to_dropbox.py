#!/usr/bin/env python3

import logging
import os

import dropbox
import requests
from dropbox.exceptions import ApiError, AuthError

from app.celery_app import celery
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import log_task_progress
from app.utils.filename_utils import extract_remote_path, get_unique_filename

logger = logging.getLogger(__name__)


def _validate_dropbox_settings():
    """Validate that all required Dropbox settings are available."""
    missing = []

    if not hasattr(settings, "dropbox_refresh_token") or not settings.dropbox_refresh_token:
        missing.append("refresh token")

    if not hasattr(settings, "dropbox_app_key") or not settings.dropbox_app_key:
        missing.append("app key")

    if not hasattr(settings, "dropbox_app_secret") or not settings.dropbox_app_secret:
        missing.append("app secret")

    if missing:
        logger.error(f"Cannot refresh Dropbox token: Missing {', '.join(missing)}")
        return False

    return True


def get_dropbox_access_token():
    """Refresh the Dropbox access token using the stored refresh token from ENV."""

    # Check if needed settings are available
    if not _validate_dropbox_settings():
        return None

    token_url = "https://api.dropbox.com/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "refresh_token",
        "refresh_token": settings.dropbox_refresh_token,
        "client_id": settings.dropbox_app_key,
        "client_secret": settings.dropbox_app_secret,
    }

    response = requests.post(token_url, headers=headers, data=data, timeout=settings.http_request_timeout)

    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        error_msg = f"Failed to refresh Dropbox token: {response.status_code} - {response.text}"
        logger.error(error_msg)
        raise Exception(error_msg)


def get_dropbox_client():
    """
    Create and return an authenticated Dropbox client using the configured refresh token.

    Returns:
        dropbox.Dropbox: Authenticated Dropbox client instance

    Raises:
        ValueError: If required Dropbox configuration is missing
        AuthError: If authentication with Dropbox fails
    """
    app_key = settings.dropbox_app_key
    app_secret = settings.dropbox_app_secret
    refresh_token = settings.dropbox_refresh_token

    # Validate configuration
    if not app_key or not app_secret:
        raise ValueError("Dropbox app key or app secret is not configured")

    if not refresh_token:
        raise ValueError("Dropbox refresh token is not configured")

    # Create a Dropbox client with refresh token
    try:
        dbx = dropbox.Dropbox(app_key=app_key, app_secret=app_secret, oauth2_refresh_token=refresh_token)

        # Test the connection
        dbx.users_get_current_account()
        logger.info("Successfully authenticated with Dropbox")
        return dbx

    except AuthError as auth_error:
        logger.error(f"Dropbox authentication failed: {str(auth_error)}")
        raise

    except Exception as e:
        logger.error(f"Error creating Dropbox client: {str(e)}")
        raise


@celery.task(base=BaseTaskWithRetry, bind=True)
def upload_to_dropbox(self, file_path: str, file_id: int = None):
    """
    Upload a file to Dropbox.

    Args:
        file_path: Path to the file to upload
        file_id: Optional file ID to associate with logs
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting Dropbox upload: {file_path}")
    log_task_progress(
        task_id,
        "upload_to_dropbox",
        "in_progress",
        f"Uploading to Dropbox: {os.path.basename(file_path)}",
        file_id=file_id,
    )

    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_dropbox", "failure", error_msg, file_id=file_id)
        raise FileNotFoundError(error_msg)

    # Check if Dropbox is properly configured
    if not (
        hasattr(settings, "dropbox_app_key")
        and settings.dropbox_app_key
        and hasattr(settings, "dropbox_app_secret")
        and settings.dropbox_app_secret
        and hasattr(settings, "dropbox_refresh_token")
        and settings.dropbox_refresh_token
    ):
        logger.info(f"[{task_id}] Dropbox upload skipped: Missing configuration")
        log_task_progress(task_id, "upload_to_dropbox", "success", "Skipped: Not configured", file_id=file_id)
        return {"status": "Skipped", "reason": "Dropbox settings not configured"}

    filename = os.path.basename(file_path)

    try:
        # Get the Dropbox client
        dbx = get_dropbox_client()

        # Calculate remote path based on local file structure
        remote_base = settings.dropbox_folder or ""
        remote_path = extract_remote_path(file_path, settings.workdir, remote_base)

        # Function to check if file exists in Dropbox
        def check_exists_in_dropbox(path):
            try:
                dbx.files_get_metadata(path)
                return True
            except ApiError as e:
                if e.error.is_path() and e.error.get_path().is_not_found():
                    return False
                raise

        # Get a unique path in case of collision
        remote_full_path = f"/{remote_path}"  # Dropbox paths should start with /
        remote_full_path = remote_full_path.replace("//", "/")  # Clean double slashes

        # Check for potential file collision and get a unique name if needed
        dropbox_path = get_unique_filename(remote_full_path, check_exists_in_dropbox)

        # Upload the file
        logger.info(f"[{task_id}] Uploading {filename} to Dropbox at {dropbox_path}")
        log_task_progress(task_id, "upload_file", "in_progress", f"Uploading to {dropbox_path}", file_id=file_id)
        with open(file_path, "rb") as file_data:
            # Use files_upload_session for large files to avoid timeouts
            file_size = os.path.getsize(file_path)
            if file_size > 10 * 1024 * 1024:  # 10 MB threshold for chunked upload
                cursor = None
                chunk_size = 4 * 1024 * 1024  # 4 MB chunks
                file_data.seek(0)

                # Start upload session
                session_start = dbx.files_upload_session_start(file_data.read(chunk_size))
                cursor = dropbox.files.UploadSessionCursor(session_start.session_id, file_data.tell())

                # Upload chunks until we reach the end
                while file_data.tell() < file_size:
                    if (file_size - file_data.tell()) <= chunk_size:
                        # Last chunk
                        dbx.files_upload_session_finish(
                            file_data.read(chunk_size),
                            cursor,
                            dropbox.files.CommitInfo(path=dropbox_path, mode=dropbox.files.WriteMode.overwrite),
                        )
                    else:
                        # More chunks to upload
                        dbx.files_upload_session_append_v2(file_data.read(chunk_size), cursor)
                        cursor.offset = file_data.tell()
            else:
                # Small file, direct upload
                file_data.seek(0)
                dbx.files_upload(file_data.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)

        logger.info(f"[{task_id}] Successfully uploaded {filename} to Dropbox at {dropbox_path}")
        log_task_progress(
            task_id, "upload_to_dropbox", "success", f"Uploaded to Dropbox: {dropbox_path}", file_id=file_id
        )
        return {"status": "Completed", "file_path": file_path, "dropbox_path": dropbox_path}

    except AuthError:
        error_msg = f"Authentication failed while uploading {filename} to Dropbox. Check token."
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_dropbox", "failure", error_msg, file_id=file_id)
        raise Exception(error_msg)
    except ApiError as e:
        error_msg = f"Failed to upload {filename} to Dropbox: {e}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_dropbox", "failure", error_msg, file_id=file_id)
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"Unexpected error uploading {filename} to Dropbox: {e}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_dropbox", "failure", error_msg, file_id=file_id)
        raise Exception(error_msg)
