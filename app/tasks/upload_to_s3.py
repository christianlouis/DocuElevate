#!/usr/bin/env python3

import logging
import os

import boto3
from botocore.exceptions import ClientError

from app.celery_app import celery
from app.config import settings
from app.tasks.retry_config import UploadTaskWithRetry
from app.utils import log_task_progress

logger = logging.getLogger(__name__)


@celery.task(base=UploadTaskWithRetry, bind=True)
def upload_to_s3(self, file_path: str, file_id: int = None):
    """
    Uploads a file to Amazon S3 in the configured bucket and folder.

    Args:
        file_path: Path to the file to upload
        file_id: Optional file ID to associate with logs
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting S3 upload: {file_path}")
    log_task_progress(
        task_id, "upload_to_s3", "in_progress", f"Uploading to S3: {os.path.basename(file_path)}", file_id=file_id
    )

    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_s3", "failure", error_msg, file_id=file_id)
        raise FileNotFoundError(error_msg)

    # Extract filename
    filename = os.path.basename(file_path)

    # Check if S3 settings are configured
    if not settings.s3_bucket_name:
        error_msg = "S3 bucket name is not configured"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_s3", "failure", error_msg, file_id=file_id)
        raise ValueError(error_msg)

    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        error_msg = "AWS credentials are not configured"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_s3", "failure", error_msg, file_id=file_id)
        raise ValueError(error_msg)

    try:
        # Create S3 client
        s3_client = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )

        # Construct the S3 key (path within the bucket)
        if settings.s3_folder_prefix:
            # Ensure folder prefix ends with a slash
            folder_prefix = settings.s3_folder_prefix
            if not folder_prefix.endswith("/"):
                folder_prefix += "/"
            s3_key = f"{folder_prefix}{filename}"
        else:
            s3_key = filename

        # Prepare extra arguments
        extra_args = {"StorageClass": settings.s3_storage_class}

        # Add ACL if configured
        if settings.s3_acl:
            extra_args["ACL"] = settings.s3_acl

        # Upload file
        s3_client.upload_file(file_path, settings.s3_bucket_name, s3_key, ExtraArgs=extra_args)

        # Generate URL to the file (useful for public files)
        # For private files, this is just a reference and won't be accessible directly
        s3_url = f"https://{settings.s3_bucket_name}.s3.{settings.aws_region}.amazonaws.com/{s3_key}"

        logger.info(
            f"[{task_id}] Successfully uploaded {filename} to S3 bucket {settings.s3_bucket_name} at path {s3_key}"
        )
        log_task_progress(task_id, "upload_to_s3", "success", f"Uploaded to S3: {filename}", file_id=file_id)
        return {
            "status": "Completed",
            "file": file_path,
            "s3_bucket": settings.s3_bucket_name,
            "s3_key": s3_key,
            "s3_url": s3_url,
        }

    except ClientError as e:
        error_msg = f"Failed to upload {filename} to S3: {str(e)}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_s3", "failure", error_msg, file_id=file_id)
        raise Exception(error_msg)

    except Exception as e:
        error_msg = f"Error uploading {filename} to S3: {str(e)}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_s3", "failure", error_msg, file_id=file_id)
        raise Exception(error_msg)
