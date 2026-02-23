#!/usr/bin/env python3

import logging
import mimetypes
import os
import shutil
import uuid

import pypdf  # Upgraded from PyPDF2 to fix CVE-2023-36464
from pypdf.errors import PdfReadError

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import FileRecord
from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt
from app.tasks.process_with_ocr import process_with_ocr
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import get_unique_filepath_with_counter, hash_file, log_task_progress

logger = logging.getLogger(__name__)


@celery.task(base=BaseTaskWithRetry, bind=True)
def process_document(
    self, original_local_file: str, original_filename: str = None, file_id: int = None, force_cloud_ocr: bool = False
):
    """
    Process a document file and trigger appropriate text extraction.

    Args:
        original_local_file: Path to the file on disk
        original_filename: Optional original filename (if different from path basename)
        file_id: Optional existing file record ID. When provided, skips duplicate
                 detection and reuses the existing record (used for reprocessing).
        force_cloud_ocr: If True, forces Azure Document Intelligence OCR processing
                        regardless of embedded text quality. Used for re-processing.

    Steps:
      1. Check if we have a FileRecord entry (via SHA-256 hash). If found, skip re-processing.
         (Skipped when file_id is provided for reprocessing.)
      2. If not found, insert a new DB row and continue with the pipeline:
         - Save immutable copy to /workdir/original
         - Copy file to /workdir/tmp for processing
         - Check for embedded text. If present, run local GPT extraction
         - Otherwise, queue Azure Document Intelligence processing
      3. If force_cloud_ocr is True, skip local text extraction and use cloud OCR
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
        log_task_progress(
            task_id,
            "process_document",
            "failure",
            "File not found",
            detail=f"File not found on disk: {original_local_file}",
        )
        return {"error": "File not found"}

    # 0. Check for duplicate files (if enabled)
    if settings.enable_deduplication:
        logger.info(f"[{task_id}] Computing file hash for deduplication check...")
        log_task_progress(task_id, "check_for_duplicates", "in_progress", "Computing file hash for deduplication")
        filehash = hash_file(original_local_file)
    else:
        logger.info(f"[{task_id}] Computing file hash (deduplication disabled)...")
        filehash = hash_file(original_local_file)

    # Use provided original_filename or fall back to basename of path
    if original_filename is None:
        original_filename = os.path.basename(original_local_file)
    file_size = os.path.getsize(original_local_file)
    mime_type, _ = mimetypes.guess_type(original_local_file)
    if not mime_type:
        mime_type = "application/octet-stream"

    logger.info(f"[{task_id}] File hash: {filehash[:10]}..., Size: {file_size} bytes, MIME: {mime_type}")

    # Log deduplication step result (only if enabled)
    if settings.enable_deduplication:
        log_task_progress(
            task_id,
            "check_for_duplicates",
            "in_progress",
            f"Hash: {filehash[:10]}..., checking for duplicates",
        )

    # Acquire DB session in the task
    with SessionLocal() as db:
        # When file_id is provided, we are reprocessing an existing file.
        # Skip the duplicate check and reuse the existing record.
        if file_id is not None:
            existing_record = db.query(FileRecord).filter_by(id=file_id).one_or_none()
            if existing_record is None:
                logger.error(f"[{task_id}] File record with ID {file_id} not found for reprocessing.")
                log_task_progress(task_id, "process_document", "failure", "File record not found", file_id=file_id)
                return {"error": "File record not found", "file_id": file_id}
            logger.info(f"[{task_id}] Reprocessing existing file record ID: {file_id}, skipping duplicate check.")
            log_task_progress(
                task_id,
                "process_document",
                "in_progress",
                f"Reprocessing file record ID: {file_id}",
                file_id=file_id,
            )
            new_record = existing_record
        else:
            # Check for duplicate only if this is a new file (not reprocessing)
            # IMPORTANT: Only consider it a duplicate if it matches a DIFFERENT file
            existing = (
                db.query(FileRecord)
                .filter(FileRecord.filehash == filehash, FileRecord.is_duplicate.is_(False))
                .order_by(FileRecord.created_at.asc())
                .first()
            )
            if existing is None:
                existing = (
                    db.query(FileRecord).filter(FileRecord.filehash == filehash).order_by(FileRecord.id.asc()).first()
                )

            # A file is only a duplicate if it matches a different file's hash
            # (not its own hash when reprocessing)
            if existing and existing.id != file_id and settings.enable_deduplication:
                logger.info(f"[{task_id}] Duplicate file detected (hash={filehash[:10]}...) Skipping processing.")
                duplicate_record = FileRecord(
                    filehash=filehash,
                    original_filename=original_filename,
                    local_filename="",
                    file_size=file_size,
                    mime_type=mime_type,
                    is_duplicate=True,
                    duplicate_of_id=existing.id,
                )
                db.add(duplicate_record)
                db.commit()
                db.refresh(duplicate_record)

                if settings.enable_deduplication and settings.show_deduplication_step:
                    log_task_progress(
                        task_id,
                        "check_for_duplicates",
                        "success",
                        f"Duplicate detected - matching file ID {existing.id}",
                        file_id=duplicate_record.id,
                        detail=(
                            f"Duplicate file detected.\n"
                            f"File hash: {filehash}\n"
                            f"Original file record ID: {existing.id}\n"
                            f"This file record ID: {duplicate_record.id}\n"
                            f"Original filename: {original_filename}"
                        ),
                    )
                log_task_progress(
                    task_id,
                    "process_document",
                    "success",
                    "Duplicate file detected, skipping",
                    file_id=duplicate_record.id,
                    detail=(
                        f"Duplicate file detected.\n"
                        f"File hash: {filehash}\n"
                        f"Original file record ID: {existing.id}\n"
                        f"Original filename: {original_filename}"
                    ),
                )
                return {
                    "status": "duplicate_file",
                    "file_id": duplicate_record.id,
                    "original_file_id": existing.id,
                    "detail": "File already processed.",
                }

            # Not a duplicate (or deduplication disabled) -> insert a new record
            logger.info(f"[{task_id}] Creating new file record in database")
            if settings.enable_deduplication and settings.show_deduplication_step:
                log_task_progress(
                    task_id,
                    "check_for_duplicates",
                    "success",
                    "New file - no duplicates found",
                )
            log_task_progress(task_id, "create_file_record", "in_progress", "Creating file record")
            new_record = FileRecord(
                filehash=filehash,
                original_filename=original_filename,
                local_filename="",  # Will fill in after we move it
                file_size=file_size,
                mime_type=mime_type,
                is_duplicate=False,
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

        # 1. Generate a UUID-based filename for storage
        file_ext = os.path.splitext(original_local_file)[1]
        file_uuid = str(uuid.uuid4())
        new_filename = f"{file_uuid}{file_ext}"

        # 2. Save immutable copy to /workdir/original (only for new files, not reprocessing)
        # For reprocessing, the original_file_path should already exist in the database
        if file_id is None:  # New file - save original copy
            # This copy serves as the permanent, untouched reference of the ingested file
            original_dir = os.path.join(settings.workdir, "original")
            os.makedirs(original_dir, exist_ok=True)

            # Use collision-resistant naming with -0001, -0002 suffixes
            base_name = os.path.splitext(new_filename)[0]
            original_file_path = get_unique_filepath_with_counter(original_dir, base_name, file_ext)

            logger.info(f"[{task_id}] Saving immutable original to: {original_file_path}")
            log_task_progress(
                task_id,
                "save_original",
                "in_progress",
                f"Saving original to {os.path.basename(original_file_path)}",
                file_id=new_record.id,
            )
            shutil.copy(original_local_file, original_file_path)
            log_task_progress(
                task_id,
                "save_original",
                "success",
                f"Original saved: {os.path.basename(original_file_path)}",
                file_id=new_record.id,
            )

            # Update the DB with original_file_path
            new_record.original_file_path = original_file_path
        else:
            # Reprocessing - original should already exist
            logger.info(f"[{task_id}] Reprocessing: original file already saved at {new_record.original_file_path}")
            log_task_progress(
                task_id,
                "save_original",
                "success",
                "Reprocessing: using existing original",
                file_id=new_record.id,
            )

        # 3. Copy to /workdir/tmp for processing
        tmp_dir = os.path.join(settings.workdir, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        new_local_path = os.path.join(tmp_dir, new_filename)

        logger.info(f"[{task_id}] Copying file to processing area: {new_local_path}")
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

        # Update the DB with local_filename
        new_record.local_filename = new_local_path
        db.commit()

        # Store file_id before session closes to avoid DetachedInstanceError
        file_id = new_record.id

    # 2. Check for embedded text (outside the DB session to avoid long open transactions)
    # Skip local text extraction if force_cloud_ocr is True
    if force_cloud_ocr:
        logger.info(f"[{task_id}] Force Cloud OCR requested, skipping embedded text check")
        log_task_progress(
            task_id,
            "check_text",
            "success",
            "Force Cloud OCR requested, queuing OCR",
            file_id=file_id,
        )
        # Mark local text extraction as skipped since force_cloud_ocr was requested
        log_task_progress(
            task_id,
            "extract_text",
            "skipped",
            "Force cloud OCR requested, skipping local extraction",
            file_id=file_id,
        )
        log_task_progress(
            task_id,
            "process_document",
            "success",
            "Queued for forced OCR processing",
            file_id=file_id,
        )
        process_with_ocr.delay(new_filename, file_id)
        return {"file": new_local_path, "status": "Queued for forced OCR", "file_id": file_id}

    # If the file is not a PDF, skip embedded text check and convert to PDF first
    is_pdf = mime_type == "application/pdf" or os.path.splitext(new_local_path)[1].lower() == ".pdf"
    if not is_pdf:
        logger.info(f"[{task_id}] Non-PDF file detected, queuing PDF conversion before OCR")
        log_task_progress(
            task_id,
            "check_text",
            "skipped",
            "Non-PDF file detected, converting to PDF",
            file_id=file_id,
        )
        log_task_progress(
            task_id,
            "process_document",
            "success",
            "Queued for PDF conversion",
            file_id=file_id,
        )
        celery.send_task(
            "app.tasks.convert_to_pdf.convert_to_pdf",
            args=[new_local_path, original_filename],
        )
        return {"file": new_local_path, "status": "Queued for PDF conversion", "file_id": file_id}

    logger.info(f"[{task_id}] Checking for embedded text in PDF")
    log_task_progress(
        task_id,
        "check_text",
        "in_progress",
        "Checking for embedded text",
        file_id=file_id,
    )
    try:
        with open(new_local_path, "rb") as file:
            pdf_reader = pypdf.PdfReader(file)
            has_text = False
            for page in pdf_reader.pages:
                if page.extract_text().strip():
                    has_text = True
                    break
    except PdfReadError as exc:
        logger.warning(f"[{task_id}] PDF read error during embedded text check: {exc}")
        log_task_progress(
            task_id,
            "check_text",
            "in_progress",
            "PDF read error, retrying embedded text check",
            file_id=file_id,
            detail=str(exc),
        )
        raise self.retry(
            exc=exc,
            countdown=10,
            kwargs={
                "original_local_file": original_local_file,
                "original_filename": original_filename,
                "file_id": file_id,
                "force_cloud_ocr": force_cloud_ocr,
            },
        )

    if has_text:
        logger.info(f"[{task_id}] PDF {original_local_file} contains embedded text. Processing locally.")
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
            pdf_reader = pypdf.PdfReader(file)
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

        # Mark OCR as skipped since we extracted text locally
        log_task_progress(
            task_id,
            "process_with_azure_document_intelligence",
            "skipped",
            "Local text extraction succeeded, OCR not needed",
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

    # 3. If no embedded text, queue OCR processing
    logger.info(f"[{task_id}] No embedded text found. Queueing OCR processing")
    log_task_progress(
        task_id,
        "check_text",
        "success",
        "No embedded text, queuing OCR",
        file_id=file_id,
    )

    # Mark local text extraction as skipped since we're using cloud OCR
    log_task_progress(
        task_id,
        "extract_text",
        "skipped",
        "No embedded text, using OCR instead",
        file_id=file_id,
    )

    log_task_progress(
        task_id,
        "process_document",
        "success",
        "Queued for OCR processing",
        file_id=file_id,
    )
    process_with_ocr.delay(new_filename, file_id)
    return {"file": new_local_path, "status": "Queued for OCR", "file_id": file_id}
