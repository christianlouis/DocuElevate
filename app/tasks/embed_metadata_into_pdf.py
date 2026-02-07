#!/usr/bin/env python3

import os
import shutil
import tempfile
import logging
import PyPDF2  # Replace fitz with PyPDF2
import json
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.finalize_document_storage import finalize_document_storage

# Import the shared Celery instance
from app.celery_app import celery
from app.utils import log_task_progress
from app.database import SessionLocal
from app.models import FileRecord

logger = logging.getLogger(__name__)

# Directory constants - defined here to avoid hardcoded strings (BAN-B108)
# Note: These are application-specific subdirectories within settings.workdir,
# not system temporary directories. The workdir is a configurable path specific
# to this application. For actual temporary file creation, tempfile module is
# used (see line 70: tempfile.NamedTemporaryFile)
TMP_SUBDIR = "tmp"
PROCESSED_SUBDIR = "processed"

def unique_filepath(directory, base_filename, extension=".pdf"):
    """
    Returns a unique filepath in the specified directory.
    If 'base_filename.pdf' exists, it will append an underscore and counter.
    """
    candidate = os.path.join(directory, base_filename + extension)
    if not os.path.exists(candidate):
        return candidate
    counter = 1
    while True:
        candidate = os.path.join(directory, f"{base_filename}_{counter}{extension}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1

def persist_metadata(metadata, final_pdf_path):
    """
    Saves the metadata dictionary to a JSON file with the same base name as the final PDF.
    For example, if final_pdf_path is "<workdir>/processed/MyFile.pdf",
    the metadata will be saved as "<workdir>/processed/MyFile.json".
    """
    base, _ = os.path.splitext(final_pdf_path)
    json_path = base + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    return json_path

@celery.task(base=BaseTaskWithRetry, bind=True)
def embed_metadata_into_pdf(self, local_file_path: str, extracted_text: str, metadata: dict, file_id: int = None):
    """
    Embeds extracted metadata into the PDF's standard metadata fields.
    The mapping is as follows:
      - title: uses the extracted metadata "filename"
      - author: uses "absender" (or "Unknown" if missing)
      - subject: uses "document_type" (or "Unknown")
      - keywords: a comma‐separated list from the "tags" field

    After processing, the file is moved to
      <workdir>/processed/<suggested_filename.pdf>
    where <suggested_filename.pdf> is derived from metadata["filename"].
    Additionally, the metadata is persisted to a JSON file with the same base name.
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting metadata embedding for: {local_file_path}")
    log_task_progress(task_id, "embed_metadata_into_pdf", "in_progress", f"Embedding metadata into {os.path.basename(local_file_path)}", file_id=file_id)
    
    # Get file_id from database if not provided (fallback only, prefer passing file_id explicitly)
    if file_id is None:
        with SessionLocal() as db:
            file_record = db.query(FileRecord).filter_by(local_filename=local_file_path).first()
            if file_record:
                file_id = file_record.id
    
    # Check for file existence; if not found, try the known shared tmp directory.
    if not os.path.exists(local_file_path):
        alt_path = os.path.join(settings.workdir, TMP_SUBDIR, os.path.basename(local_file_path))
        if os.path.exists(alt_path):
            local_file_path = alt_path
        else:
            logger.error(f"[{task_id}] Local file {local_file_path} not found, cannot embed metadata.")
            log_task_progress(task_id, "embed_metadata_into_pdf", "failure", "File not found", file_id=file_id)
            return {"error": "File not found"}

    # Work on a safe copy in a secure temporary directory
    original_file = local_file_path
    # Create a temporary file with the same extension as the original
    _, ext = os.path.splitext(local_file_path)
    tmp_file = tempfile.NamedTemporaryFile(mode='wb', suffix=ext, prefix='processed_', delete=False)
    processed_file = tmp_file.name
    tmp_file.close()

    # Create a safe copy to work on
    shutil.copy(original_file, processed_file)

    try:
        logger.info(f"[{task_id}] Embedding metadata into {processed_file}...")
        log_task_progress(task_id, "modify_pdf", "in_progress", "Modifying PDF metadata", file_id=file_id)

        # Open the PDF and modify metadata
        with open(processed_file, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            pdf_writer = PyPDF2.PdfWriter()
            
            # Copy all pages from the reader to the writer
            for page in pdf_reader.pages:
                pdf_writer.add_page(page)
            
            # Set PDF metadata
            pdf_writer.add_metadata({
                "/Title": metadata.get("filename", "Unknown Document"),
                "/Author": metadata.get("absender", "Unknown"),
                "/Subject": metadata.get("document_type", "Unknown"),
                "/Keywords": ", ".join(metadata.get("tags", []))
            })
            
            # Write the modified PDF
            with open(processed_file, 'wb') as output_file:
                pdf_writer.write(output_file)

        logger.info(f"[{task_id}] Metadata embedded successfully in {processed_file}")
        log_task_progress(task_id, "modify_pdf", "success", "PDF metadata embedded", file_id=file_id)

        # Use the suggested filename from metadata; if not provided, use the original basename.
        suggested_filename = metadata.get("filename", os.path.splitext(os.path.basename(local_file_path))[0])
        # Remove any extension and then add .pdf
        suggested_filename = os.path.splitext(suggested_filename)[0]
        # Define the final directory based on settings.workdir and ensure it exists.
        final_dir = os.path.join(settings.workdir, PROCESSED_SUBDIR)
        os.makedirs(final_dir, exist_ok=True)
        # Get a unique filepath in case of collisions.
        final_file_path = unique_filepath(final_dir, suggested_filename, extension=".pdf")

        logger.info(f"[{task_id}] Moving file to: {final_file_path}")
        log_task_progress(task_id, "move_to_processed", "in_progress", f"Moving to processed: {suggested_filename}.pdf", file_id=file_id)
        # Move the processed file using shutil.move to handle cross-device moves.
        shutil.move(processed_file, final_file_path)
        # Ensure the temporary file is deleted if it still exists.
        if os.path.exists(processed_file):
            os.remove(processed_file)
        log_task_progress(task_id, "move_to_processed", "success", f"Moved to: {os.path.basename(final_file_path)}", file_id=file_id)

        # Persist the metadata into a JSON file with the same base name.
        logger.info(f"[{task_id}] Persisting metadata to JSON")
        log_task_progress(task_id, "save_metadata_json", "in_progress", "Saving metadata JSON", file_id=file_id)
        json_path = persist_metadata(metadata, final_file_path)
        logger.info(f"[{task_id}] Metadata persisted to {json_path}")
        log_task_progress(task_id, "save_metadata_json", "success", f"Saved: {os.path.basename(json_path)}", file_id=file_id)

        # Trigger the next step: final storage.
        logger.info(f"[{task_id}] Queueing final storage task")
        log_task_progress(task_id, "embed_metadata_into_pdf", "success", "Metadata embedded, queuing finalization", file_id=file_id)
        finalize_document_storage.delay(original_file, final_file_path, metadata, file_id=file_id)

        # After triggering final storage, delete the original file if it is in workdir/tmp.
        workdir_tmp = os.path.join(settings.workdir, TMP_SUBDIR)
        if original_file.startswith(workdir_tmp) and os.path.exists(original_file):
            try:
                os.remove(original_file)
                logger.info(f"[{task_id}] Deleted original file from {original_file}")
            except Exception as e:
                logger.error(f"[{task_id}] Could not delete original file {original_file}: {e}")

        return {"file": final_file_path, "metadata_file": json_path, "status": "Metadata embedded"}

    except Exception as e:
        logger.exception(f"[{task_id}] Failed to embed metadata into {processed_file}: {e}")
        log_task_progress(task_id, "embed_metadata_into_pdf", "failure", f"Exception: {str(e)}", file_id=file_id)
        # Clean up temporary file in case of error
        if os.path.exists(processed_file):
            try:
                os.remove(processed_file)
                logger.info(f"[{task_id}] Cleaned up temporary file {processed_file}")
            except Exception as cleanup_error:
                logger.error(f"[{task_id}] Could not clean up temporary file {processed_file}: {cleanup_error}")
        return {"error": str(e)}
