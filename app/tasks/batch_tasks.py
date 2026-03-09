"""
Scheduled batch processing tasks for DocuElevate.

This module provides three Celery tasks that can be scheduled via Celery Beat
and managed through the admin UI (``/admin/scheduled-jobs``):

- ``process_new_documents``    – Queue any documents that have never been processed.
- ``reprocess_failed_documents`` – Re-queue documents whose processing failed.
- ``cleanup_temp_files``       – Remove stale files from the ``workdir/tmp`` directory.

Each task records its execution result back to the ``ScheduledJob`` table so
the admin UI can display last-run times and statuses.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import FileProcessingStep, FileRecord, ScheduledJob

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_PROCESSING_STEPS = {
    "create_file_record",
    "check_text",
    "extract_text",
    "process_with_ocr",
    "process_with_azure_document_intelligence",
    "extract_metadata_with_gpt",
    "embed_metadata_into_pdf",
    "finalize_document_storage",
    "send_to_all_destinations",
}


def _update_job_status(job_name: str, status: str, detail: str) -> None:
    """Persist run status back to the ScheduledJob row for display in the UI."""
    try:
        with SessionLocal() as db:
            job = db.query(ScheduledJob).filter(ScheduledJob.name == job_name).first()
            if job:
                job.last_run_at = datetime.now(timezone.utc)
                job.last_run_status = status
                job.last_run_detail = detail
                db.commit()
    except Exception as exc:  # pragma: no cover – best-effort status update
        logger.warning("Could not update ScheduledJob status for %s: %s", job_name, exc)


# ---------------------------------------------------------------------------
# Task: process new (unprocessed) documents
# ---------------------------------------------------------------------------


@celery.task(name="app.tasks.batch_tasks.process_new_documents")
def process_new_documents() -> dict:
    """
    Queue all documents that have never been processed.

    A document is considered *new* when it has no ``FileProcessingStep`` rows
    that match the core pipeline steps.  The task loads each qualifying
    ``FileRecord``, verifies that the original file still exists on disk, and
    dispatches ``process_document`` for each one.

    Returns a summary dict with ``queued`` and ``skipped`` counts.
    """
    from app.tasks.process_document import process_document  # avoid circular import

    job_name = "process-new-documents"
    logger.info("[batch] Starting process_new_documents task")

    try:
        with SessionLocal() as db:
            # Files that already have at least one processing step recorded.
            processed_file_ids = (
                db.query(FileProcessingStep.file_id)
                .filter(FileProcessingStep.step_name.in_(_PROCESSING_STEPS))
                .distinct()
                .subquery()
            )

            # Candidate files: non-duplicate records with no processing steps yet.
            candidates = (
                db.query(FileRecord)
                .filter(FileRecord.is_duplicate.is_(False))
                .filter(~FileRecord.id.in_(db.query(processed_file_ids.c.file_id)))
                .all()
            )

        queued = 0
        skipped = 0
        for record in candidates:
            if not record.local_filename or not os.path.exists(record.local_filename):
                logger.warning(
                    "[batch] Skipping file_id=%s — local file not found: %s",
                    record.id,
                    record.local_filename,
                )
                skipped += 1
                continue
            process_document.delay(
                record.local_filename,
                original_filename=record.original_filename,
                file_id=record.id,
                owner_id=record.owner_id,
            )
            queued += 1

        detail = f"Queued {queued} document(s) for processing; skipped {skipped} (file not on disk)."
        logger.info("[batch] process_new_documents: %s", detail)
        _update_job_status(job_name, "success", detail)
        return {"queued": queued, "skipped": skipped}

    except Exception as exc:
        detail = f"Error: {exc}"
        logger.error("[batch] process_new_documents failed: %s", exc, exc_info=True)
        _update_job_status(job_name, "failed", detail)
        return {"queued": 0, "skipped": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Task: reprocess failed documents
# ---------------------------------------------------------------------------


@celery.task(name="app.tasks.batch_tasks.reprocess_failed_documents")
def reprocess_failed_documents() -> dict:
    """
    Re-queue documents whose most-recent processing attempt failed.

    Only files that have at least one ``FileProcessingStep`` with
    ``status == "failure"`` **and** no currently ``in_progress`` steps are
    selected so that actively-running jobs are not interrupted.

    Returns a summary dict with ``queued`` and ``skipped`` counts.
    """
    from app.tasks.process_document import process_document  # avoid circular import

    job_name = "reprocess-failed-documents"
    logger.info("[batch] Starting reprocess_failed_documents task")

    try:
        with SessionLocal() as db:
            # Files with at least one failed step.
            failed_file_ids = (
                db.query(FileProcessingStep.file_id)
                .filter(FileProcessingStep.step_name.in_(_PROCESSING_STEPS))
                .filter(FileProcessingStep.status == "failure")
                .distinct()
                .subquery()
            )

            # Exclude files that are currently being processed.
            in_progress_file_ids = (
                db.query(FileProcessingStep.file_id)
                .filter(FileProcessingStep.status == "in_progress")
                .distinct()
                .subquery()
            )

            candidates = (
                db.query(FileRecord)
                .filter(FileRecord.is_duplicate.is_(False))
                .filter(FileRecord.id.in_(db.query(failed_file_ids.c.file_id)))
                .filter(~FileRecord.id.in_(db.query(in_progress_file_ids.c.file_id)))
                .all()
            )

        queued = 0
        skipped = 0
        for record in candidates:
            if not record.local_filename or not os.path.exists(record.local_filename):
                logger.warning(
                    "[batch] Skipping file_id=%s — local file not found: %s",
                    record.id,
                    record.local_filename,
                )
                skipped += 1
                continue
            process_document.delay(
                record.local_filename,
                original_filename=record.original_filename,
                file_id=record.id,
                owner_id=record.owner_id,
            )
            queued += 1

        detail = f"Re-queued {queued} failed document(s); skipped {skipped} (file not on disk)."
        logger.info("[batch] reprocess_failed_documents: %s", detail)
        _update_job_status(job_name, "success", detail)
        return {"queued": queued, "skipped": skipped}

    except Exception as exc:
        detail = f"Error: {exc}"
        logger.error("[batch] reprocess_failed_documents failed: %s", exc, exc_info=True)
        _update_job_status(job_name, "failed", detail)
        return {"queued": 0, "skipped": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Task: clean up temporary files
# ---------------------------------------------------------------------------

#: Files in ``workdir/tmp`` that are older than this threshold are deleted.
_TEMP_FILE_MAX_AGE_HOURS: int = 24


@celery.task(name="app.tasks.batch_tasks.cleanup_temp_files")
def cleanup_temp_files(max_age_hours: int = _TEMP_FILE_MAX_AGE_HOURS) -> dict:
    """
    Delete stale files from the ``workdir/tmp`` directory.

    A file is considered stale when **both** of the following are true:

    1. Its modification time is older than *max_age_hours* (default 24 h).
    2. No ``FileRecord.local_filename`` points to it  **or**  the file is not
       referenced by any active in-progress processing step.

    This prevents accidental deletion of files that are being actively
    processed by the pipeline.

    Args:
        max_age_hours: Minimum age (in hours) before a temp file is eligible
                       for deletion.  Defaults to 24.

    Returns:
        A summary dict with ``deleted`` and ``skipped`` counts.
    """
    job_name = "cleanup-temp-files"
    logger.info("[batch] Starting cleanup_temp_files (max_age_hours=%s)", max_age_hours)

    tmp_dir = Path(settings.workdir) / "tmp"
    if not tmp_dir.exists():
        detail = "workdir/tmp does not exist; nothing to clean."
        logger.info("[batch] cleanup_temp_files: %s", detail)
        _update_job_status(job_name, "success", detail)
        return {"deleted": 0, "skipped": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    deleted = 0
    skipped = 0
    errors = 0

    try:
        with SessionLocal() as db:
            # Collect filenames actively referenced by in-progress processing steps.
            in_progress_filenames: set[str] = set()
            in_progress_records = (
                db.query(FileRecord.local_filename)
                .join(FileProcessingStep, FileProcessingStep.file_id == FileRecord.id)
                .filter(FileProcessingStep.status == "in_progress")
                .distinct()
                .all()
            )
            for row in in_progress_records:
                if row.local_filename:
                    in_progress_filenames.add(os.path.basename(row.local_filename))

            # Also collect all filenames referenced by FileRecord.local_filename
            # that point into workdir/tmp (files still in the tmp pipeline).
            active_tmp_filenames: set[str] = set()
            tmp_dir_str = str(tmp_dir.resolve())
            active_records = (
                db.query(FileRecord.local_filename)
                .filter(FileRecord.local_filename.like(f"{tmp_dir_str}%"))
                .all()
            )
            for row in active_records:
                if row.local_filename:
                    active_tmp_filenames.add(os.path.basename(row.local_filename))

        protected_basenames = in_progress_filenames | active_tmp_filenames

        for entry in tmp_dir.iterdir():
            if not entry.is_file():
                continue

            # Check modification time.
            try:
                mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
            except OSError:
                skipped += 1
                continue

            if mtime >= cutoff:
                skipped += 1
                continue

            if entry.name in protected_basenames:
                logger.debug("[batch] cleanup_temp_files: keeping protected file %s", entry.name)
                skipped += 1
                continue

            try:
                entry.unlink()
                logger.debug("[batch] cleanup_temp_files: deleted %s", entry)
                deleted += 1
            except OSError as exc:
                logger.warning("[batch] cleanup_temp_files: could not delete %s: %s", entry, exc)
                errors += 1

        detail = (
            f"Deleted {deleted} stale temp file(s); "
            f"skipped {skipped} (too new or protected); "
            f"{errors} error(s)."
        )
        status = "failed" if errors and not deleted else "success"
        logger.info("[batch] cleanup_temp_files: %s", detail)
        _update_job_status(job_name, status, detail)
        return {"deleted": deleted, "skipped": skipped, "errors": errors}

    except Exception as exc:
        detail = f"Error: {exc}"
        logger.error("[batch] cleanup_temp_files failed: %s", exc, exc_info=True)
        _update_job_status(job_name, "failed", detail)
        return {"deleted": 0, "skipped": 0, "errors": 1, "error": str(exc)}
