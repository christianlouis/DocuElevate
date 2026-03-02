"""PDF/A archival conversion task.

Converts PDF files to PDF/A format using ocrmypdf (which relies on Ghostscript
internally).  Two variants are produced when enabled:

1. **Original PDF/A** – an archival copy of the ingested file, providing a
   time-stamped record of the document as it was upon ingestion.
2. **Processed PDF/A** – an archival copy of the processed file with embedded
   metadata.

Both are saved under ``workdir/pdfa/`` and referenced in the database via
``FileRecord.original_pdfa_path`` and ``FileRecord.processed_pdfa_path``.

.. note::

   PDF/A conversion may alter font rendering (especially OCR text overlays
   produced by Microsoft Azure Document Intelligence).  This is expected –
   the PDF/A copies are parallel archival variants, not replacements.
"""

import logging
import os
import shutil
import subprocess

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import FileRecord
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import get_unique_filepath_with_counter, log_task_progress

logger = logging.getLogger(__name__)

# Subdirectory structure under workdir for PDF/A copies
PDFA_ORIGINAL_SUBDIR = os.path.join("pdfa", "original")
PDFA_PROCESSED_SUBDIR = os.path.join("pdfa", "processed")


def _convert_pdf_to_pdfa(input_path: str, output_path: str, pdfa_format: str = "2") -> bool:
    """Convert a PDF file to PDF/A using ocrmypdf.

    Uses ``ocrmypdf --skip-text --output-type pdfa-N`` so that existing text
    layers are preserved (not re-OCR'd) while the output is converted to
    PDF/A via Ghostscript.

    Args:
        input_path: Absolute path to the source PDF file.
        output_path: Absolute path for the PDF/A output file.
        pdfa_format: PDF/A variant ('1', '2', or '3'). Defaults to '2' for PDF/A-2b.

    Returns:
        True if conversion succeeded, False otherwise.
    """
    ocrmypdf_bin = shutil.which("ocrmypdf")
    if not ocrmypdf_bin:
        logger.error("[convert_to_pdfa] ocrmypdf binary not found on PATH")
        return False

    output_type = f"pdfa-{pdfa_format}"

    cmd = [
        ocrmypdf_bin,
        "--skip-text",
        "--output-type",
        output_type,
        "--quiet",
        "--invalidate-digital-signatures",
        input_path,
        output_path,
    ]

    logger.info(f"[convert_to_pdfa] Running: {' '.join(cmd)}")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)  # noqa: S603
    except subprocess.TimeoutExpired:
        logger.warning("[convert_to_pdfa] ocrmypdf timed out after 600s")
        return False

    if proc.returncode != 0:
        stderr_snippet = proc.stderr.strip()[:500] if proc.stderr else ""
        logger.warning(f"[convert_to_pdfa] ocrmypdf exited with code {proc.returncode}: {stderr_snippet}")
        return False

    logger.info(f"[convert_to_pdfa] PDF/A file written to {output_path}")
    return True


@celery.task(base=BaseTaskWithRetry, bind=True)
def convert_to_pdfa(self, file_id: int) -> dict:
    """Generate PDF/A archival copies for a processed document.

    Creates PDF/A variants of both the original ingested file and the
    processed file (with embedded metadata).  Files are saved under
    ``workdir/pdfa/original/`` and ``workdir/pdfa/processed/`` respectively.

    When ``settings.pdfa_upload_to_providers`` is True, the processed PDF/A
    variant is also uploaded to all configured storage destinations.

    Args:
        file_id: ID of the FileRecord to create PDF/A copies for.

    Returns:
        Dictionary with status and file paths.
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting PDF/A conversion for file_id={file_id}")
    log_task_progress(
        task_id,
        "convert_to_pdfa",
        "in_progress",
        "Starting PDF/A archival conversion",
        file_id=file_id,
    )

    # Fetch file record
    with SessionLocal() as db:
        file_record = db.query(FileRecord).filter_by(id=file_id).first()
        if not file_record:
            logger.error(f"[{task_id}] FileRecord {file_id} not found")
            log_task_progress(task_id, "convert_to_pdfa", "failure", "File record not found", file_id=file_id)
            return {"error": "File record not found", "file_id": file_id}

        original_path = file_record.original_file_path
        processed_path = file_record.processed_file_path

    pdfa_format = settings.pdfa_format
    results = {}

    # --- Convert original file to PDF/A ---
    if original_path and os.path.exists(original_path):
        original_pdfa_dir = os.path.join(settings.workdir, PDFA_ORIGINAL_SUBDIR)
        os.makedirs(original_pdfa_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(original_path))[0]
        original_pdfa_path = get_unique_filepath_with_counter(original_pdfa_dir, base_name, ".pdf")

        logger.info(f"[{task_id}] Converting original to PDF/A: {original_path} -> {original_pdfa_path}")
        log_task_progress(
            task_id,
            "convert_original_to_pdfa",
            "in_progress",
            f"Converting original to PDF/A: {os.path.basename(original_path)}",
            file_id=file_id,
        )

        success = _convert_pdf_to_pdfa(original_path, original_pdfa_path, pdfa_format)
        if success:
            results["original_pdfa_path"] = original_pdfa_path
            log_task_progress(
                task_id,
                "convert_original_to_pdfa",
                "success",
                f"Original PDF/A saved: {os.path.basename(original_pdfa_path)}",
                file_id=file_id,
            )
        else:
            log_task_progress(
                task_id,
                "convert_original_to_pdfa",
                "failure",
                "Failed to convert original to PDF/A",
                file_id=file_id,
            )
    else:
        logger.warning(f"[{task_id}] Original file not found, skipping original PDF/A conversion")
        log_task_progress(
            task_id,
            "convert_original_to_pdfa",
            "skipped",
            "Original file not available",
            file_id=file_id,
        )

    # --- Convert processed file to PDF/A ---
    if processed_path and os.path.exists(processed_path):
        processed_pdfa_dir = os.path.join(settings.workdir, PDFA_PROCESSED_SUBDIR)
        os.makedirs(processed_pdfa_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(processed_path))[0]
        processed_pdfa_path = get_unique_filepath_with_counter(processed_pdfa_dir, f"{base_name}-PDFA", ".pdf")

        logger.info(f"[{task_id}] Converting processed to PDF/A: {processed_path} -> {processed_pdfa_path}")
        log_task_progress(
            task_id,
            "convert_processed_to_pdfa",
            "in_progress",
            f"Converting processed to PDF/A: {os.path.basename(processed_path)}",
            file_id=file_id,
        )

        success = _convert_pdf_to_pdfa(processed_path, processed_pdfa_path, pdfa_format)
        if success:
            results["processed_pdfa_path"] = processed_pdfa_path
            log_task_progress(
                task_id,
                "convert_processed_to_pdfa",
                "success",
                f"Processed PDF/A saved: {os.path.basename(processed_pdfa_path)}",
                file_id=file_id,
            )
        else:
            log_task_progress(
                task_id,
                "convert_processed_to_pdfa",
                "failure",
                "Failed to convert processed to PDF/A",
                file_id=file_id,
            )
    else:
        logger.warning(f"[{task_id}] Processed file not found, skipping processed PDF/A conversion")
        log_task_progress(
            task_id,
            "convert_processed_to_pdfa",
            "skipped",
            "Processed file not available",
            file_id=file_id,
        )

    # --- Update database with PDF/A paths ---
    with SessionLocal() as db:
        file_record = db.query(FileRecord).filter_by(id=file_id).first()
        if file_record:
            if "original_pdfa_path" in results:
                file_record.original_pdfa_path = results["original_pdfa_path"]
            if "processed_pdfa_path" in results:
                file_record.processed_pdfa_path = results["processed_pdfa_path"]
            db.commit()
            logger.info(f"[{task_id}] Updated database with PDF/A paths")

    # --- Optionally upload processed PDF/A to storage providers ---
    if settings.pdfa_upload_to_providers and "processed_pdfa_path" in results:
        from app.tasks.send_to_all import send_to_all_destinations

        logger.info(f"[{task_id}] Uploading processed PDF/A to storage providers")
        log_task_progress(
            task_id,
            "upload_pdfa_to_providers",
            "in_progress",
            "Uploading PDF/A variant to storage providers",
            file_id=file_id,
        )
        send_to_all_destinations.delay(results["processed_pdfa_path"], True, file_id)
        log_task_progress(
            task_id,
            "upload_pdfa_to_providers",
            "success",
            "PDF/A variant queued for upload",
            file_id=file_id,
        )

    # --- Final status ---
    has_any = bool(results)
    status = "success" if has_any else "failure"
    message = (
        f"PDF/A conversion complete ({len(results)} variant(s) created)" if has_any else "No PDF/A variants created"
    )
    log_task_progress(task_id, "convert_to_pdfa", status, message, file_id=file_id)

    return {"status": status, "file_id": file_id, **results}
