#!/usr/bin/env python3

import os
import uuid
import shutil
import mimetypes
import logging
import PyPDF2  # Replace fitz with PyPDF2

from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.process_with_azure_document_intelligence import (
    process_with_azure_document_intelligence,
)
from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt
from app.celery_app import celery
from app.database import SessionLocal
from app.models import FileRecord
from app.utils import hash_file, log_task_progress

logger = logging.getLogger(__name__)


@celery.task(base=BaseTaskWithRetry, bind=True)
def process_document(self, original_local_file: str):
    """
    Process a document file and trigger appropriate text extraction.

    Steps:
      1. Check if we have a FileRecord entry (via SHA-256 hash). If found, skip re-processing.
      2. If not found, insert a new DB row and continue with the pipeline:
         - Copy file to /workdir/tmp
         - Check for embedded text. If present, run local GPT extraction
         - Otherwise, queue Azure Document Intelligence processing
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting document processing: {original_local_file}")
    log_task_progress(
        task_id,
        "process_document",
        "in_progress",
        f"Processing file: {original_local_file}",
    )

    if not os.path.exists(original_local_file):
        logger.error(f"[{task_id}] File {original_local_file} not found.")
        log_task_progress(task_id, "process_document", "failure", "File not found")
        return {"error": "File not found"}

    # 0. Compute the file hash and check for duplicates
    logger.info(f"[{task_id}] Computing file hash...")
    log_task_progress(task_id, "hash_file", "in_progress", "Computing file hash")
    filehash = hash_file(original_local_file)
    original_filename = os.path.basename(original_local_file)
    file_size = os.path.getsize(original_local_file)
    mime_type, _ = mimetypes.guess_type(original_local_file)
    if not mime_type:
        mime_type = "application/octet-stream"

    logger.info(
        f"[{task_id}] File hash: {filehash[:10]}..., Size: {file_size} bytes, MIME: {mime_type}"
    )
    log_task_progress(
        task_id,
        "hash_file",
        "success",
        f"Hash: {filehash[:10]}..., Size: {file_size} bytes",
    )

    # Acquire DB session in the task
    with SessionLocal() as db:
        existing = db.query(FileRecord).filter_by(filehash=filehash).one_or_none()
        if existing:
            logger.info(
                f"[{task_id}] Duplicate file detected (hash={filehash[:10]}...) Skipping processing."
            )
            log_task_progress(
                task_id,
                "process_document",
                "success",
                "Duplicate file detected, skipping",
                file_id=existing.id,
            )
            return {
                "status": "duplicate_file",
                "file_id": existing.id,
                "detail": "File already processed.",
            }

        # Not a duplicate -> insert a new record
        logger.info(f"[{task_id}] Creating new file record in database")
        log_task_progress(
            task_id, "create_file_record", "in_progress", "Creating file record"
        )
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
        logger.info(f"[{task_id}] File record created with ID: {new_record.id}")
        log_task_progress(
            task_id,
            "create_file_record",
            "success",
            f"File record ID: {new_record.id}",
            file_id=new_record.id,
        )

        # 1. Generate a UUID-based filename and place it in /workdir/tmp
        file_ext = os.path.splitext(original_local_file)[1]
        file_uuid = str(uuid.uuid4())
        new_filename = f"{file_uuid}{file_ext}"

        tmp_dir = os.path.join(settings.workdir, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        new_local_path = os.path.join(tmp_dir, new_filename)

        logger.info(f"[{task_id}] Copying file to: {new_local_path}")
        log_task_progress(
            task_id,
            "copy_file",
            "in_progress",
            f"Copying file to {new_filename}",
            file_id=new_record.id,
        )
        # Copy the file instead of moving it
        shutil.copy(original_local_file, new_local_path)
        log_task_progress(
            task_id,
            "copy_file",
            "success",
            f"File copied to {new_filename}",
            file_id=new_record.id,
        )

        # Update the DB with final local filename
        new_record.local_filename = new_local_path
        db.commit()

        # Store file_id before session closes to avoid DetachedInstanceError
        file_id = new_record.id

    # 2. Check for embedded text (outside the DB session to avoid long open transactions)
    logger.info(f"[{task_id}] Checking for embedded text in PDF")
    log_task_progress(
        task_id,
        "check_text",
        "in_progress",
        "Checking for embedded text",
        file_id=file_id,
    )
    with open(new_local_path, "rb") as file:
        pdf_reader = PyPDF2.PdfReader(file)
        has_text = False
        for page in pdf_reader.pages:
            if page.extract_text().strip():
                has_text = True
                break

    if has_text:
        logger.info(
            f"[{task_id}] PDF {original_local_file} contains embedded text. Processing locally."
        )
        log_task_progress(
            task_id,
            "check_text",
            "success",
            "Embedded text found, extracting locally",
            file_id=file_id,
        )

        # Extract text locally
        logger.info(f"[{task_id}] Extracting text from PDF")
        log_task_progress(
            task_id,
            "extract_text",
            "in_progress",
            "Extracting text locally",
            file_id=file_id,
        )
        extracted_text = ""
        with open(new_local_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                extracted_text += page.extract_text() + "\n"

        logger.info(f"[{task_id}] Extracted {len(extracted_text)} characters")
        log_task_progress(
            task_id,
            "extract_text",
            "success",
            f"Extracted {len(extracted_text)} characters",
            file_id=file_id,
        )

        # Call metadata extraction directly
        logger.info(f"[{task_id}] Queueing metadata extraction")
        log_task_progress(
            task_id,
            "process_document",
            "success",
            "Queued for metadata extraction",
            file_id=file_id,
        )
        extract_metadata_with_gpt.delay(new_filename, extracted_text, file_id)
        return {
            "file": new_local_path,
            "status": "Text extracted locally",
            "file_id": file_id,
        }

    # 3. If no embedded text, queue Azure Document Intelligence processing
    logger.info(
        f"[{task_id}] No embedded text found. Queueing Azure Document Intelligence processing"
    )
    log_task_progress(
        task_id,
        "check_text",
        "success",
        "No embedded text, queuing OCR",
        file_id=file_id,
    )
    log_task_progress(
        task_id,
        "process_document",
        "success",
        "Queued for OCR processing",
        file_id=file_id,
    )
    process_with_azure_document_intelligence.delay(new_filename, file_id)
    return {"file": new_local_path, "status": "Queued for OCR", "file_id": file_id}
