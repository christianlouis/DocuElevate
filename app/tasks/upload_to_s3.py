#!/usr/bin/env python3

import os
import uuid
import boto3
import shutil
import mimetypes
import fitz  # PyMuPDF for checking embedded text

from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.process_with_textract import process_with_textract
from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt
from app.celery_app import celery

# NEW imports for the DB
from app.database import SessionLocal
from app.models import FileRecord
from app.utils import hash_file

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

    Steps:
      1. Check if we have a FileRecord entry (via SHA-256 hash). If found, skip re-processing.
      2. If not found, insert a new DB row and continue with the pipeline:
         - Copy file to /workdir/tmp
         - Check for embedded text. If present, skip S3 and run local GPT extraction
         - Otherwise, upload to S3 and queue Textract-based OCR
    """

    bucket_name = settings.s3_bucket_name
    if not bucket_name:
        print("[ERROR] S3 bucket name not set.")
        return {"error": "Missing S3 bucket name"}

    if not os.path.exists(original_local_file):
        print(f"[ERROR] File {original_local_file} not found.")
        return {"error": "File not found"}

    # 0. Compute the file hash and check for duplicates
    filehash = hash_file(original_local_file)
    original_filename = os.path.basename(original_local_file)
    file_size = os.path.getsize(original_local_file)
    mime_type, _ = mimetypes.guess_type(original_local_file)
    if not mime_type:
        mime_type = "application/octet-stream"

    # Acquire DB session in the task
    with SessionLocal() as db:
        existing = db.query(FileRecord).filter_by(filehash=filehash).one_or_none()
        if existing:
            print(f"[INFO] Duplicate file detected (hash={filehash[:10]}...) Skipping processing.")
            return {
                "status": "duplicate_file",
                "file_id": existing.id,
                "detail": "File already processed."
            }

        # Not a duplicate -> insert a new record
        new_record = FileRecord(
            filehash=filehash,
            original_filename=original_filename,
            local_filename="",  # Will fill in after we move it
            file_size=file_size,
            mime_type=mime_type,
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        # 1. Generate a UUID-based filename and place it in /workdir/tmp
        file_ext = os.path.splitext(original_local_file)[1]
        file_uuid = str(uuid.uuid4())
        new_filename = f"{file_uuid}{file_ext}"

        tmp_dir = os.path.join(settings.workdir, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        new_local_path = os.path.join(tmp_dir, new_filename)

        # Copy the file instead of moving it
        shutil.copy(original_local_file, new_local_path)

        # Update the DB with final local filename
        new_record.local_filename = new_local_path
        db.commit()

    # 2. Check for embedded text (outside the DB session to avoid long open transactions)
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

    # 3. If no embedded text, upload to S3 and queue Textract processing
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
