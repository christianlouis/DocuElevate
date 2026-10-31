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


def upload_file_to_s3(
    file_path: str,
    *,
    bucket: str,
    region: str | None,
    access_key: str,
    secret_key: str,
    prefix: str | None,
    storage_class: str | None,
    acl: str | None,
    endpoint_url: str | None = None,
) -> dict[str, str]:
    """Upload to an S3-compatible target using explicit, non-global settings."""
    client_kwargs = {
        "region_name": region,
        "aws_access_key_id": access_key,
        "aws_secret_access_key": secret_key,
    }
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url
    s3_client = boto3.client("s3", **client_kwargs)
    filename = os.path.basename(file_path)
    folder = prefix or ""
    folder_prefix = folder if not folder or folder.endswith("/") else f"{folder}/"
    s3_key = f"{folder_prefix}{filename}" if folder_prefix else filename
    extra_args = {"StorageClass": storage_class}
    if acl:
        extra_args["ACL"] = acl
    s3_client.upload_file(file_path, bucket, s3_key, ExtraArgs=extra_args)
    if endpoint_url:
        s3_url = f"{endpoint_url.rstrip('/')}/{s3_key}"
    else:
        s3_url = f"https://{bucket}.s3.{region}.amazonaws.com/{s3_key}"
    return {"s3_bucket": bucket, "s3_key": s3_key, "s3_url": s3_url}


@celery.task(base=UploadTaskWithRetry, bind=True)
def upload_to_s3(self, file_path: str, file_id: int = None, folder_override: str = None):
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
        s3_folder = folder_override if folder_override is not None else settings.s3_folder_prefix
        result = upload_file_to_s3(
            file_path,
            bucket=settings.s3_bucket_name,
            region=settings.aws_region,
            access_key=settings.aws_access_key_id,
            secret_key=settings.aws_secret_access_key,
            prefix=s3_folder,
            storage_class=settings.s3_storage_class,
            acl=settings.s3_acl,
        )
        s3_key = result["s3_key"]

        logger.info(
            f"[{task_id}] Successfully uploaded {filename} to S3 bucket {settings.s3_bucket_name} at path {s3_key}"
        )
        log_task_progress(task_id, "upload_to_s3", "success", f"Uploaded to S3: {filename}", file_id=file_id)
        return {
            "status": "Completed",
            "file": file_path,
            **result,
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
