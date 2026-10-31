"""Upload task for the optional secondary S3-compatible destination."""

import logging
import os

from app.celery_app import celery
from app.config import settings
from app.tasks.retry_config import UploadTaskWithRetry
from app.tasks.upload_to_s3 import upload_file_to_s3
from app.utils import log_task_progress
from app.utils.s3_config import is_valid_s3_endpoint

logger = logging.getLogger(__name__)


@celery.task(base=UploadTaskWithRetry, bind=True)
def upload_to_s3_secondary(self, file_path: str, file_id: int = None, folder_override: str = None):
    task_id = self.request.id
    step_name = "upload_to_s3_secondary"
    filename = os.path.basename(file_path)
    if getattr(settings, "s3_secondary_enabled", False) is not True:
        message = "Secondary S3 is disabled"
        log_task_progress(task_id, step_name, "skipped", message, file_id=file_id)
        return {"status": "Skipped", "file": file_path, "reason": message}
    log_task_progress(task_id, step_name, "in_progress", f"Uploading to secondary S3: {filename}", file_id=file_id)
    if not os.path.exists(file_path):
        log_task_progress(task_id, step_name, "failure", "File not found", file_id=file_id)
        raise FileNotFoundError(f"File not found: {file_path}")
    endpoint = getattr(settings, "s3_secondary_endpoint", None)
    required = (
        endpoint,
        getattr(settings, "s3_secondary_bucket", None),
        getattr(settings, "s3_secondary_access_key", None),
        getattr(settings, "s3_secondary_secret_key", None),
    )
    if not all(required) or not is_valid_s3_endpoint(endpoint):
        error_msg = "Secondary S3 requires an HTTPS endpoint, bucket, and credentials"
        log_task_progress(task_id, step_name, "failure", error_msg, file_id=file_id)
        raise ValueError(error_msg)
    try:
        result = upload_file_to_s3(
            file_path,
            bucket=settings.s3_secondary_bucket,
            region=settings.s3_secondary_region,
            access_key=settings.s3_secondary_access_key,
            secret_key=settings.s3_secondary_secret_key,
            prefix=folder_override if folder_override is not None else settings.s3_secondary_prefix,
            storage_class=settings.s3_secondary_storage_class,
            acl=settings.s3_secondary_acl,
            endpoint_url=endpoint,
        )
        log_task_progress(task_id, step_name, "success", f"Uploaded to secondary S3: {filename}", file_id=file_id)
        return {"status": "Completed", "file": file_path, **result}
    except Exception as exc:
        error_msg = f"Error uploading to secondary S3 ({type(exc).__name__})"
        logger.error("[%s] %s", task_id, error_msg)
        log_task_progress(task_id, step_name, "failure", error_msg, file_id=file_id)
        raise Exception(error_msg) from exc
