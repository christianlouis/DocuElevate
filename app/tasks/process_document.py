#!/usr/bin/env python3

import os
import uuid
import shutil
import mimetypes
import fitz  # PyMuPDF for checking embedded text

from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.process_with_textract import process_with_textract
from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt
from app.celery_app import celery
from app.database import SessionLocal
from app.models import FileRecord
from app.utils import hash_file, log_task_progress, task_step_logging


@celery.task(base=BaseTaskWithRetry)
def process_document(original_local_file: str):
    """
    Process a document file and trigger appropriate text extraction.

    Steps:
      1. Check if we have a FileRecord entry (via SHA-256 hash). If found, skip re-processing.
      2. If not found, insert a new DB row and continue with the pipeline:
         - Copy file to /workdir/tmp
         - Check for embedded text. If present, run local GPT extraction
         - Otherwise, queue Textract-based OCR
    """
    task_id = process_document.request.id
    log_task_progress(task_id, "process_document", "pending", f"Processing {original_local_file}", file_path=original_local_file)

    if not os.path.exists(original_local_file):
        log_task_progress(task_id, "process_document", "failure", f"File {original_local_file} not found.", file_path=original_local_file)
        return {"error": "File not found"}

    # 0. Compute the file hash and check for duplicates
    with task_step_logging(task_id, "compute_hash", file_path=original_local_file):
        filehash = hash_file(original_local_file)
        original_filename = os.path.basename(original_local_file)
        file_size = os.path.getsize(original_local_file)
        mime_type, _ = mimetypes.guess_type(original_local_file)
        if not mime_type:
            mime_type = "application/octet-stream"

    # Acquire DB session in the task
    new_record = None
    with SessionLocal() as db:
        with task_step_logging(task_id, "check_duplicates", file_path=original_local_file):
            existing = db.query(FileRecord).filter_by(filehash=filehash).one_or_none()
            if existing:
                log_task_progress(task_id, "process_document", "success", 
                                f"Duplicate file detected (hash={filehash[:10]}...). Skipping processing.",
                                file_id=existing.id)
                return {
                    "status": "duplicate_file",
                    "file_id": existing.id,
                    "detail": "File already processed."
                }

        # Not a duplicate -> insert a new record
        with task_step_logging(task_id, "create_file_record", file_path=original_local_file):
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
        with task_step_logging(task_id, "copy_to_workdir", file_id=new_record.id, file_path=original_local_file):
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
    with task_step_logging(task_id, "check_embedded_text", file_id=new_record.id, file_path=new_local_path):
        pdf_doc = fitz.open(new_local_path)
        has_text = any(page.get_text() for page in pdf_doc)
        pdf_doc.close()

    if has_text:
        log_task_progress(task_id, "process_document", "in_progress", 
                        f"PDF {original_local_file} contains embedded text. Processing locally.", 
                        file_id=new_record.id)

        # Extract text locally
        extracted_text = ""
        with task_step_logging(task_id, "extract_text_locally", file_id=new_record.id, file_path=new_local_path):
            pdf_doc = fitz.open(new_local_path)
            for page in pdf_doc:
                extracted_text += page.get_text("text") + "\n"
            pdf_doc.close()

        # Call metadata extraction directly
        log_task_progress(task_id, "process_document", "success", 
                        "Text extracted locally. Queuing for metadata extraction.", 
                        file_id=new_record.id)
        extract_metadata_with_gpt.delay(new_filename, extracted_text)
        return {"file": new_local_path, "status": "Text extracted locally", "file_id": new_record.id}

    # 3. If no embedded text, queue Textract processing
    log_task_progress(task_id, "process_document", "success", 
                    "No embedded text found. Queuing for OCR.", 
                    file_id=new_record.id)
    process_with_textract.delay(new_filename)
    return {"file": new_local_path, "status": "Queued for OCR", "file_id": new_record.id}
