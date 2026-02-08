#!/usr/bin/env python3

import logging
import os

import paramiko

from app.celery_app import celery
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import log_task_progress
from app.utils.filename_utils import extract_remote_path, get_unique_filename, sanitize_filename

logger = logging.getLogger(__name__)


@celery.task(base=BaseTaskWithRetry, bind=True)
def upload_to_sftp(self, file_path: str, file_id: int = None):
    """
    Upload a file to an SFTP server.

    Args:
        file_path: Path to the file to upload
        file_id: Optional file ID to associate with logs
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting SFTP upload: {file_path}")
    log_task_progress(
        task_id, "upload_to_sftp", "in_progress", f"Uploading to SFTP: {os.path.basename(file_path)}", file_id=file_id
    )

    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_sftp", "failure", error_msg, file_id=file_id)
        raise FileNotFoundError(error_msg)

    if not (settings.sftp_host and settings.sftp_port and settings.sftp_username):
        error_msg = "SFTP upload skipped: Missing configuration"
        logger.info(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_sftp", "skipped", error_msg, file_id=file_id)
        return {"status": "Skipped", "reason": "SFTP settings not configured"}

    filename = os.path.basename(file_path)
    sanitized_filename = sanitize_filename(filename)

    # SSH client for SFTP connection
    ssh = paramiko.SSHClient()

    # Security: Host key verification
    # WARNING: AutoAddPolicy automatically trusts unknown host keys (vulnerable to MITM attacks)
    # For production, use RejectPolicy and configure known_hosts, or WarningPolicy at minimum
    if getattr(settings, "sftp_disable_host_key_verification", True):
        logger.warning(
            "SFTP host key verification is DISABLED - connections are vulnerable to MITM attacks. "
            "For production, set SFTP_DISABLE_HOST_KEY_VERIFICATION=false and configure known_hosts."
        )
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # nosec B507 - Configurable, warns user
    else:
        # Use system known_hosts for host key verification (more secure)
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.RejectPolicy())

    try:
        # Setup connection parameters
        connect_kwargs = {
            "hostname": settings.sftp_host,
            "port": settings.sftp_port,
            "username": settings.sftp_username,
        }

        # Check for authentication methods - use key if available, otherwise try password
        sftp_key_path = getattr(settings, "sftp_private_key", None)
        sftp_key_passphrase = getattr(settings, "sftp_private_key_passphrase", None)

        if sftp_key_path and os.path.exists(sftp_key_path):
            logger.info(f"Using SSH key authentication with key: {sftp_key_path}")
            connect_kwargs["key_filename"] = sftp_key_path
            if sftp_key_passphrase:
                connect_kwargs["passphrase"] = sftp_key_passphrase
        elif settings.sftp_password:
            logger.info("Using password authentication for SFTP")
            connect_kwargs["password"] = settings.sftp_password
        else:
            error_msg = "No authentication method available for SFTP (no key or password)"
            logger.error(error_msg)
            raise Exception(error_msg)

        # Connect to the server
        logger.info(f"Connecting to SFTP server at {settings.sftp_host}:{settings.sftp_port}")
        ssh.connect(**connect_kwargs)

        # Open SFTP session
        sftp = ssh.open_sftp()

        # Calculate remote path based on local file structure
        remote_base = settings.sftp_folder or ""
        remote_path = extract_remote_path(file_path, settings.workdir, remote_base)

        # Ensure the remote path starts with a slash if the base folder does
        if remote_base.startswith("/") and not remote_path.startswith("/"):
            remote_path = "/" + remote_path

        # Function to check if file exists in SFTP server
        def check_exists_in_sftp(path):
            try:
                sftp.stat(path)
                return True
            except FileNotFoundError:
                return False

        # Check for potential file collision and get a unique name if needed
        remote_path = get_unique_filename(remote_path, check_exists_in_sftp)

        # Create parent directories if needed
        remote_dir = os.path.dirname(remote_path)
        if remote_dir:
            try:
                # Try to create the full directory path
                current_dir = ""
                for dir_part in remote_dir.split("/"):
                    if not dir_part:
                        continue
                    current_dir += f"/{dir_part}"
                    try:
                        sftp.stat(current_dir)
                    except FileNotFoundError:
                        logger.info(f"Creating directory on SFTP server: {current_dir}")
                        sftp.mkdir(current_dir)
            except Exception as e:
                logger.warning(f"Failed to create directory structure {remote_dir}: {str(e)}")

        # Upload the file
        logger.info(f"[{task_id}] Uploading {filename} to SFTP at {remote_path}")
        sftp.put(file_path, remote_path)
        logger.info(f"[{task_id}] Successfully uploaded {filename} to SFTP at {remote_path}")
        log_task_progress(task_id, "upload_to_sftp", "success", f"Uploaded to SFTP: {filename}", file_id=file_id)

        # Close connections
        sftp.close()
        ssh.close()

        return {"status": "Completed", "file_path": file_path, "sftp_path": remote_path}

    except Exception as e:
        # Make sure connections are closed
        try:
            if "sftp" in locals():
                sftp.close()
            ssh.close()
        except Exception:
            pass

        error_msg = f"Failed to upload {filename} to SFTP server: {str(e)}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_sftp", "failure", error_msg, file_id=file_id)
        raise Exception(error_msg)
