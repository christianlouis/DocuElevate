#!/usr/bin/env python3

import os
import uuid
import boto3
import shutil
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.process_with_textract import process_with_textract

# Import the shared Celery instance
from app.celery_app import celery

# Initialize S3 client
s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region,
)

@celery.task(base=BaseTaskWithRetry)
def upload_to_s3(original_local_file: str):
    """
    Uploads a file to S3 with a UUID-based filename and triggers Textract processing.
    Instead of moving the file, this version copies the file locally.
    """
    bucket_name = settings.s3_bucket_name
    if not bucket_name:
        print("[ERROR] S3 bucket name not set.")
        return {"error": "Missing S3 bucket name"}

    if not os.path.exists(original_local_file):
        print(f"[ERROR] File {original_local_file} not found.")
        return {"error": "File not found"}

    # Generate UUID and create a new filename
    file_ext = os.path.splitext(original_local_file)[1]  # Preserve original file extension
    file_uuid = str(uuid.uuid4())
    new_filename = f"{file_uuid}{file_ext}"
    new_local_path = os.path.join("/var/docparse/working/tmp", new_filename)

    # Ensure the target directory exists
    os.makedirs(os.path.dirname(new_local_path), exist_ok=True)

    # Copy the file instead of moving it
    shutil.copy(original_local_file, new_local_path)

    try:
        print(f"[INFO] Uploading {new_local_path} to s3://{bucket_name}/{new_filename}...")
        s3_client.upload_file(new_local_path, bucket_name, new_filename)
        print(f"[INFO] File uploaded successfully: {new_filename}")

        # Trigger Textract processing using the new filename (S3 key)
        process_with_textract.delay(new_filename)

        return {"file": new_local_path, "s3_key": new_filename, "status": "Uploaded"}

    except Exception as e:
        print(f"[ERROR] Failed to upload {new_local_path} to S3: {e}")
        return {"error": str(e)}

