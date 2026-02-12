#!/usr/bin/env python3

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

import pypdf  # Upgraded from PyPDF2 to fix CVE-2023-36464

# Import the shared Celery instance
from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import FileRecord
from app.tasks.finalize_document_storage import finalize_document_storage
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import get_unique_filepath_with_counter, log_task_progress
from app.utils.filename_utils import sanitize_filename

logger = logging.getLogger(__name__)

# Directory constants - defined here to avoid hardcoded strings (BAN-B108)
# Note: These are application-specific subdirectories within settings.workdir,
# not system temporary directories. The workdir is a configurable path specific
# to this application. For actual temporary file creation, tempfile module is
# used (see line 70: tempfile.NamedTemporaryFile)
TMP_SUBDIR = "tmp"
PROCESSED_SUBDIR = "processed"


def persist_metadata(metadata, final_pdf_path, original_file_path=None, processed_file_path=None):
    """
    Saves the metadata dictionary to a JSON file with the same base name as the final PDF.
    For example, if final_pdf_path is "<workdir>/processed/MyFile.pdf",
    the metadata will be saved as "<workdir>/processed/MyFile.json".

    Optionally augments the metadata with file path references for traceability.

    Args:
        metadata: Dictionary of metadata to save
        final_pdf_path: Path to the final PDF file
        original_file_path: Optional path to the immutable original file
        processed_file_path: Optional path to the processed file

    Returns:
        str: Path to the created JSON file
    """
    base, _ = os.path.splitext(final_pdf_path)
    json_path = base + ".json"

    # Augment metadata with file path references if provided
    metadata_with_paths = metadata.copy()
    if original_file_path:
        metadata_with_paths["original_file_path"] = original_file_path
    if processed_file_path:
        metadata_with_paths["processed_file_path"] = processed_file_path

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata_with_paths, f, ensure_ascii=False, indent=2)
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
    log_task_progress(
        task_id,
        "embed_metadata_into_pdf",
        "in_progress",
        f"Embedding metadata into {os.path.basename(local_file_path)}",
        file_id=file_id,
    )

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
            log_task_progress(
                task_id,
                "embed_metadata_into_pdf",
                "failure",
                "File not found",
                file_id=file_id,
                detail=(
                    f"Local file not found, cannot embed metadata.\n"
                    f"Tried path: {local_file_path}\n"
                    f"Also tried: {alt_path}"
                ),
            )
            return {"error": "File not found"}

    # Work on a safe copy in a secure temporary directory
    original_file = local_file_path
    # Create a temporary file with the same extension as the original
    _, ext = os.path.splitext(local_file_path)
    tmp_file = tempfile.NamedTemporaryFile(mode="wb", suffix=ext, prefix="processed_", delete=False)
    processed_file = tmp_file.name
    tmp_file.close()

    # Create a safe copy to work on
    shutil.copy(original_file, processed_file)

    try:
        logger.info(f"[{task_id}] Embedding metadata into {processed_file}...")
        log_task_progress(task_id, "modify_pdf", "in_progress", "Modifying PDF metadata", file_id=file_id)

        # Open the PDF and modify metadata
        with open(processed_file, "rb") as file:
            pdf_reader = pypdf.PdfReader(file)
            pdf_writer = pypdf.PdfWriter()

            # Copy all pages from the reader to the writer
            for page in pdf_reader.pages:
                pdf_writer.add_page(page)

            # Set PDF metadata
            pdf_writer.add_metadata(
                {
                    "/Title": metadata.get("filename", "Unknown Document"),
                    "/Author": metadata.get("absender", "Unknown"),
                    "/Subject": metadata.get("document_type", "Unknown"),
                    "/Keywords": ", ".join(metadata.get("tags", [])),
                }
            )

            # Write the modified PDF
            with open(processed_file, "wb") as output_file:
                pdf_writer.write(output_file)

        logger.info(f"[{task_id}] Metadata embedded successfully in {processed_file}")
        log_task_progress(task_id, "modify_pdf", "success", "PDF metadata embedded", file_id=file_id)

        # Use the suggested filename from metadata; if not provided, use the original basename.
        # SECURITY: Sanitize filename to prevent path traversal vulnerabilities
        suggested_filename = metadata.get("filename", os.path.splitext(os.path.basename(local_file_path))[0])
        # Sanitize the filename to remove path separators and dangerous characters
        suggested_filename = sanitize_filename(suggested_filename)
        # Remove any extension and then add .pdf
        suggested_filename = os.path.splitext(suggested_filename)[0]
        # Define the final directory based on settings.workdir and ensure it exists.
        final_dir = os.path.join(settings.workdir, PROCESSED_SUBDIR)
        os.makedirs(final_dir, exist_ok=True)
        # Get a unique filepath in case of collisions using -0001, -0002 suffix format
        final_file_path = get_unique_filepath_with_counter(final_dir, suggested_filename, extension=".pdf")

        logger.info(f"[{task_id}] Moving file to: {final_file_path}")
        log_task_progress(
            task_id,
            "move_to_processed",
            "in_progress",
            f"Moving to processed: {os.path.basename(final_file_path)}",
            file_id=file_id,
        )
        # Move the processed file using shutil.move to handle cross-device moves.
        shutil.move(processed_file, final_file_path)
        # Ensure the temporary file is deleted if it still exists.
        if os.path.exists(processed_file):
            os.remove(processed_file)
        log_task_progress(
            task_id, "move_to_processed", "success", f"Moved to: {os.path.basename(final_file_path)}", file_id=file_id
        )

        # Get the original_file_path from the database
        original_file_path = None
        with SessionLocal() as db:
            if file_id:
                file_record = db.query(FileRecord).filter_by(id=file_id).first()
                if file_record:
                    original_file_path = file_record.original_file_path
                    # Update the processed_file_path in the database
                    file_record.processed_file_path = final_file_path
                    db.commit()
                    logger.info(f"[{task_id}] Updated database with processed_file_path: {final_file_path}")

        # Persist the metadata into a JSON file with the same base name.
        # Include file path references for traceability
        logger.info(f"[{task_id}] Persisting metadata to JSON")
        log_task_progress(task_id, "save_metadata_json", "in_progress", "Saving metadata JSON", file_id=file_id)
        json_path = persist_metadata(
            metadata, final_file_path, original_file_path=original_file_path, processed_file_path=final_file_path
        )
        logger.info(f"[{task_id}] Metadata persisted to {json_path}")
        log_task_progress(
            task_id, "save_metadata_json", "success", f"Saved: {os.path.basename(json_path)}", file_id=file_id
        )

        # Trigger the next step: final storage.
        logger.info(f"[{task_id}] Queueing final storage task")
        log_task_progress(
            task_id,
            "embed_metadata_into_pdf",
            "success",
            "Metadata embedded, queuing finalization",
            file_id=file_id,
            detail=(
                f"Metadata embedded into PDF successfully.\n"
                f"Original file: {original_file}\n"
                f"Final file: {final_file_path}\n"
                f"Metadata JSON: {json_path}\n"
                f"Suggested filename: {suggested_filename}.pdf"
            ),
        )
        finalize_document_storage.delay(original_file, final_file_path, metadata, file_id=file_id)

        # After triggering final storage, delete the original file if it is in workdir/tmp.
        # SECURITY: Use pathlib for safe path validation to prevent path traversal
        workdir_tmp_path = Path(settings.workdir) / TMP_SUBDIR
        try:
            original_file_path = Path(original_file).resolve()
            workdir_tmp_resolved = workdir_tmp_path.resolve()

            # Check if file is within workdir/tmp and exists
            if original_file_path.is_relative_to(workdir_tmp_resolved) and original_file_path.exists():
                try:
                    original_file_path.unlink()
                    logger.info(f"[{task_id}] Deleted original file from {original_file}")
                except Exception as e:
                    logger.error(f"[{task_id}] Could not delete original file {original_file}: {e}")
        except (ValueError, OSError) as e:
            logger.error(f"[{task_id}] Error validating path for deletion {original_file}: {e}")

        return {"file": final_file_path, "metadata_file": json_path, "status": "Metadata embedded"}

    except Exception as e:
        logger.exception(f"[{task_id}] Failed to embed metadata into {processed_file}: {e}")
        log_task_progress(
            task_id,
            "embed_metadata_into_pdf",
            "failure",
            f"Exception: {str(e)}",
            file_id=file_id,
            detail=(
                f"Failed to embed metadata into {processed_file}.\n"
                f"Original file: {original_file}\nException: {str(e)}"
            ),
        )
        # Clean up temporary file in case of error
        if os.path.exists(processed_file):
            try:
                os.remove(processed_file)
                logger.info(f"[{task_id}] Cleaned up temporary file {processed_file}")
            except Exception as cleanup_error:
                logger.error(f"[{task_id}] Could not clean up temporary file {processed_file}: {cleanup_error}")
        return {"error": str(e)}
