#!/usr/bin/env python3

import logging
import os
import subprocess

from app.celery_app import celery
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import log_task_progress

logger = logging.getLogger(__name__)


@celery.task(base=BaseTaskWithRetry, bind=True)
def upload_with_rclone(self, file_path: str, destination: str):
    """
    Uploads a file using rclone to the specified destination.

    Args:
        file_path: Path to the file to upload
        destination: Rclone destination in format "remote:path/to/folder"
                     e.g. "gdrive:Uploads" or "dropbox:Documents/Uploads"
    """
    task_id = self.request.id

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Extract filename
    filename = os.path.basename(file_path)

    log_task_progress(task_id, "upload_with_rclone", "in_progress", f"Uploading {filename} to {destination}")

    # Validate destination format to prevent command injection
    if ":" not in destination:
        raise ValueError(f"Invalid destination format: {destination}. Expected format: remote:path")

    # Split and validate destination components
    remote, remote_path = destination.split(":", 1)

    # Validate remote name to prevent command injection
    # Must start with alphanumeric, can contain alphanumeric, underscore, hyphen
    if not remote or not remote[0].isalnum() or not all(c.isalnum() or c in ("_", "-") for c in remote):
        raise ValueError(f"Invalid remote name: {remote}")

    # Check if rclone is installed and config exists
    rclone_config_path = os.path.join(settings.workdir, "rclone.conf")
    if not os.path.exists(rclone_config_path):
        error_msg = f"Rclone configuration not found at {rclone_config_path}"
        logger.error(f"[{task_id}] {error_msg}")
        raise ValueError(error_msg)

    log_task_progress(task_id, "validate_rclone", "success", f"Validated rclone config for {remote}")

    try:
        # Ensure the remote path exists (create folders if needed)
        mkdir_cmd = ["rclone", "mkdir", "--config", rclone_config_path, destination]

        subprocess.run(mkdir_cmd, check=True, capture_output=True)

        # Construct the upload command
        upload_cmd = ["rclone", "copy", "--config", rclone_config_path, file_path, destination, "--progress"]

        log_task_progress(task_id, "rclone_upload", "in_progress", f"Executing rclone copy to {destination}")

        # Execute the upload command
        result = subprocess.run(upload_cmd, check=True, capture_output=True, text=True)

        # Check if upload was successful
        if result.returncode == 0:
            # Try to get a public link if possible
            try:
                link_cmd = ["rclone", "link", "--config", rclone_config_path, f"{destination}/{filename}"]
                link_result = subprocess.run(link_cmd, capture_output=True, text=True)
                public_url = link_result.stdout.strip() if link_result.returncode == 0 else None
            except (subprocess.SubprocessError, OSError) as e:
                logger.warning(f"[{task_id}] Failed to get public link for {filename}: {str(e)}")
                public_url = None

            logger.info(f"[{task_id}] Successfully uploaded {filename} to {destination}")
            log_task_progress(
                task_id,
                "upload_with_rclone",
                "success",
                f"Uploaded {filename} to {destination}",
                detail=f"public_url={public_url}",
            )
            return {"status": "Completed", "file": file_path, "destination": destination, "public_url": public_url}
        else:
            error_msg = f"Failed to upload {filename} to {destination}: {result.stderr}"
            logger.error(f"[{task_id}] {error_msg}")
            raise RuntimeError(error_msg)

    except subprocess.CalledProcessError as e:
        error_msg = f"Rclone error: {e.stderr.decode('utf-8') if hasattr(e.stderr, 'decode') else e.stderr}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(
            task_id, "upload_with_rclone", "failure", f"Rclone command failed for {filename}", detail=error_msg
        )
        raise RuntimeError(error_msg) from e

    except (OSError, ValueError) as e:
        error_msg = f"Error uploading {filename} to {destination}: {str(e)}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(
            task_id, "upload_with_rclone", "failure", f"Upload failed for {filename}", detail=error_msg
        )
        raise RuntimeError(error_msg) from e


@celery.task(base=BaseTaskWithRetry, bind=True)
def send_to_all_rclone_destinations(self, file_path: str):
    """
    Uploads a file to all configured rclone destinations.
    Destinations are loaded from the rclone configuration file.
    """
    task_id = self.request.id

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Extract filename
    filename = os.path.basename(file_path)

    log_task_progress(
        task_id, "send_to_all_rclone_destinations", "in_progress", f"Queueing rclone uploads for {filename}"
    )

    # Path to rclone config
    rclone_config_path = os.path.join(settings.workdir, "rclone.conf")
    if not os.path.exists(rclone_config_path):
        error_msg = f"Rclone configuration not found at {rclone_config_path}"
        logger.error(f"[{task_id}] {error_msg}")
        raise ValueError(error_msg)

    # Get list of configured destinations from rclone
    try:
        remotes_cmd = ["rclone", "listremotes", "--config", rclone_config_path]
        result = subprocess.run(remotes_cmd, check=True, capture_output=True, text=True)

        if result.returncode == 0:
            # Process the list of remotes
            remotes = [r.strip() for r in result.stdout.splitlines() if r.strip()]

            # Target directories for each remote (from settings)
            remote_paths = {}
            for remote in remotes:
                remote_name = remote.rstrip(":")
                path_setting_name = f"rclone_{remote_name}_path"
                if hasattr(settings, path_setting_name) and getattr(settings, path_setting_name):
                    remote_paths[remote] = getattr(settings, path_setting_name)
                else:
                    # Default to root of remote if not specified
                    remote_paths[remote] = ""

            # Queue upload tasks for each configured destination
            results = {}
            for remote, path in remote_paths.items():
                full_destination = f"{remote}{path}"
                if path and not path.endswith("/"):
                    full_destination += "/"

                logger.info(f"[{task_id}] Queueing {file_path} for upload to {full_destination}")
                task = upload_with_rclone.delay(file_path, full_destination)
                results[f"rclone_{remote.rstrip(':')}_task_id"] = task.id

            log_task_progress(
                task_id,
                "send_to_all_rclone_destinations",
                "success",
                f"Queued {len(results)} rclone upload(s)",
            )
            return {"status": "Queued", "file_path": file_path, "tasks": results}
        else:
            error_msg = f"Failed to list rclone remotes: {result.stderr}"
            logger.error(f"[{task_id}] {error_msg}")
            raise RuntimeError(error_msg)

    except (subprocess.SubprocessError, OSError) as e:
        error_msg = f"Error setting up rclone uploads for {filename}: {str(e)}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(
            task_id,
            "send_to_all_rclone_destinations",
            "failure",
            f"Failed to set up rclone uploads for {filename}",
            detail=error_msg,
        )
        raise RuntimeError(error_msg) from e
