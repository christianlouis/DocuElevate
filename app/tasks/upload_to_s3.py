#!/usr/bin/env python3

import os
import uuid
import boto3
import shutil
import fitz  # PyMuPDF for checking embedded text
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.process_with_textract import process_with_textract
from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt

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
    Uploads a file to S3 with a UUID-based filename and triggers processing.
    - If the PDF already contains embedded text, skip Textract and extract text locally.
    - Otherwise, upload to S3 and process with Textract.
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

    # Construct the new local path using settings.workdir and a 'tmp' subdirectory
    tmp_dir = os.path.join(settings.workdir, "tmp")
    new_local_path = os.path.join(tmp_dir, new_filename)

    # Ensure the target tmp directory exists
    os.makedirs(tmp_dir, exist_ok=True)

    # Copy the file instead of moving it
    shutil.copy(original_local_file, new_local_path)

    # Check for embedded text
    pdf_doc = fitz.open(new_local_path)
    has_text = any(page.get_text() for page in pdf_doc)
    pdf_doc.close()

    if has_text:
        print(f"[INFO] PDF {original_local_file} contains embedded text. Skipping Textract.")

        # Extract text locally
        extracted_text = ""
        pdf_doc = fitz.open(new_local_path)
        for page in pdf_doc:
            extracted_text += page.get_text("text") + "\n"
        pdf_doc.close()

        # Call metadata extraction directly
        extract_metadata_with_gpt.delay(new_filename, extracted_text)

        return {"file": new_local_path, "status": "Text extracted locally"}

    try:
        print(f"[INFO] Uploading {new_local_path} to s3://{bucket_name}/{new_filename}...")
        s3_client.upload_file(new_local_path, bucket_name, new_filename)
        print(f"[INFO] File uploaded successfully: {new_filename}")

        # Trigger Textract processing if no embedded text was found
        process_with_textract.delay(new_filename)

        return {"file": new_local_path, "s3_key": new_filename, "status": "Uploaded to S3 for OCR"}

    except Exception as e:
        print(f"[ERROR] Failed to upload {new_local_path} to S3: {e}")
        return {"error": str(e)}
