"""
Scheduled batch processing tasks for DocuElevate.

This module provides Celery tasks that can be scheduled via Celery Beat
and managed through the admin UI (``/admin/scheduled-jobs``):

Core batch jobs
---------------
- ``process_new_documents``      – Queue documents that have never been processed.
- ``reprocess_failed_documents`` – Re-queue documents whose processing failed.
- ``cleanup_temp_files``         – Remove stale files from the ``workdir/tmp`` directory.

Maintenance / housekeeping jobs
--------------------------------
- ``expire_shared_links``        – Auto-revoke SharedLinks whose ``expires_at`` has passed.
- ``prune_processing_logs``      – Delete old rows from ``processing_logs`` and
                                   ``settings_audit_log`` to prevent unbounded table growth.
- ``prune_old_notifications``    – Delete old read ``in_app_notifications`` rows.
- ``backfill_missing_metadata``  – Re-trigger AI metadata extraction for completed files
                                   that have OCR text but no ``ai_metadata``.
- ``sync_search_index``          – Index documents in Meilisearch that have OCR text /
                                   metadata but are not yet in the search index.

Each task records its execution result back to the ``ScheduledJob`` table so
the admin UI can display last-run times and statuses.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import (
    FileProcessingStep,
    FileRecord,
    InAppNotification,
    ProcessingLog,
    ScheduledJob,
    SettingsAuditLog,
    SharedLink,
)

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
                db.query(FileRecord.local_filename).filter(FileRecord.local_filename.like(f"{tmp_dir_str}%")).all()
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

        detail = f"Deleted {deleted} stale temp file(s); skipped {skipped} (too new or protected); {errors} error(s)."
        status = "failed" if errors and not deleted else "success"
        logger.info("[batch] cleanup_temp_files: %s", detail)
        _update_job_status(job_name, status, detail)
        return {"deleted": deleted, "skipped": skipped, "errors": errors}

    except Exception as exc:
        detail = f"Error: {exc}"
        logger.error("[batch] cleanup_temp_files failed: %s", exc, exc_info=True)
        _update_job_status(job_name, "failed", detail)
        return {"deleted": 0, "skipped": 0, "errors": 1, "error": str(exc)}


# ---------------------------------------------------------------------------
# Task: expire stale shared links
# ---------------------------------------------------------------------------


@celery.task(name="app.tasks.batch_tasks.expire_shared_links")
def expire_shared_links() -> dict:
    """
    Auto-revoke SharedLinks whose ``expires_at`` timestamp has passed.

    The ``_is_link_valid`` helper in the shared-links API already blocks
    access at request time, but the database rows remain flagged as
    ``is_active=True``.  This task sweeps those rows and sets
    ``is_active=False`` + ``revoked_at`` so the management UI reflects
    the true state and counts are accurate.

    Returns a summary dict with ``revoked`` count.
    """
    job_name = "expire-shared-links"
    logger.info("[batch] Starting expire_shared_links task")

    try:
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            stale = (
                db.query(SharedLink)
                .filter(
                    SharedLink.is_active.is_(True),
                    SharedLink.expires_at.isnot(None),
                    SharedLink.expires_at < now,
                )
                .all()
            )
            for link in stale:
                link.is_active = False
                link.revoked_at = now
            db.commit()
            revoked = len(stale)

        detail = f"Revoked {revoked} expired shared link(s)."
        logger.info("[batch] expire_shared_links: %s", detail)
        _update_job_status(job_name, "success", detail)
        return {"revoked": revoked}

    except Exception as exc:
        detail = f"Error: {exc}"
        logger.error("[batch] expire_shared_links failed: %s", exc, exc_info=True)
        _update_job_status(job_name, "failed", detail)
        return {"revoked": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Task: prune old processing logs
# ---------------------------------------------------------------------------

#: Default retention period for processing logs and audit log rows.
_LOG_RETENTION_DAYS: int = 30


@celery.task(name="app.tasks.batch_tasks.prune_processing_logs")
def prune_processing_logs(retention_days: int = _LOG_RETENTION_DAYS) -> dict:
    """
    Delete ``processing_logs`` and ``settings_audit_log`` rows older than
    *retention_days* (default 30) to prevent unbounded table growth.

    Rows for the most recent *retention_days* days are kept so that recent
    activity is still visible in the logs/audit UI.

    Args:
        retention_days: Number of days of history to keep (default 30).

    Returns:
        A summary dict with ``processing_logs_deleted`` and
        ``audit_log_deleted`` counts.
    """
    job_name = "prune-processing-logs"
    logger.info("[batch] Starting prune_processing_logs (retention_days=%s)", retention_days)

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    try:
        with SessionLocal() as db:
            pl_deleted = db.query(ProcessingLog).filter(ProcessingLog.timestamp < cutoff).delete()
            al_deleted = db.query(SettingsAuditLog).filter(SettingsAuditLog.changed_at < cutoff).delete()
            db.commit()

        detail = (
            f"Deleted {pl_deleted} processing log row(s) and "
            f"{al_deleted} settings audit log row(s) older than {retention_days} days."
        )
        logger.info("[batch] prune_processing_logs: %s", detail)
        _update_job_status(job_name, "success", detail)
        return {"processing_logs_deleted": pl_deleted, "audit_log_deleted": al_deleted}

    except Exception as exc:
        detail = f"Error: {exc}"
        logger.error("[batch] prune_processing_logs failed: %s", exc, exc_info=True)
        _update_job_status(job_name, "failed", detail)
        return {"processing_logs_deleted": 0, "audit_log_deleted": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Task: prune old in-app notifications
# ---------------------------------------------------------------------------

#: Default retention period for read notifications.
_NOTIFICATION_RETENTION_DAYS: int = 30


@celery.task(name="app.tasks.batch_tasks.prune_old_notifications")
def prune_old_notifications(retention_days: int = _NOTIFICATION_RETENTION_DAYS) -> dict:
    """
    Delete ``in_app_notifications`` rows that are already read and older than
    *retention_days* days (default 30) to prevent unbounded table growth.

    Unread notifications are always kept regardless of age so users do not
    miss important alerts.

    Args:
        retention_days: Number of days of read-notification history to keep
                        (default 30).

    Returns:
        A summary dict with ``deleted`` count.
    """
    job_name = "prune-old-notifications"
    logger.info("[batch] Starting prune_old_notifications (retention_days=%s)", retention_days)

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    try:
        with SessionLocal() as db:
            deleted = (
                db.query(InAppNotification)
                .filter(
                    InAppNotification.is_read.is_(True),
                    InAppNotification.created_at < cutoff,
                )
                .delete()
            )
            db.commit()

        detail = f"Deleted {deleted} old read notification(s) older than {retention_days} days."
        logger.info("[batch] prune_old_notifications: %s", detail)
        _update_job_status(job_name, "success", detail)
        return {"deleted": deleted}

    except Exception as exc:
        detail = f"Error: {exc}"
        logger.error("[batch] prune_old_notifications failed: %s", exc, exc_info=True)
        _update_job_status(job_name, "failed", detail)
        return {"deleted": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Task: backfill missing AI metadata
# ---------------------------------------------------------------------------

#: Maximum number of files to process per backfill run.
_METADATA_BACKFILL_BATCH_SIZE: int = 50


@celery.task(name="app.tasks.batch_tasks.backfill_missing_metadata")
def backfill_missing_metadata(batch_size: int = _METADATA_BACKFILL_BATCH_SIZE) -> dict:
    """
    Re-trigger AI metadata extraction for documents that have OCR text but
    no ``ai_metadata``.

    This handles the common case where a document was processed before the AI
    metadata extraction step was configured (e.g., before an OpenAI API key
    was added), or where the extraction previously failed.

    Only files that are **not** currently in-progress and have non-empty
    ``ocr_text`` are selected.  A configurable *batch_size* caps the number
    of tasks queued per run to avoid overwhelming the AI provider.

    Args:
        batch_size: Maximum number of files to queue per run (default 50).

    Returns:
        A summary dict with ``queued`` count.
    """
    from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt  # avoid circular import

    job_name = "backfill-missing-metadata"
    logger.info("[batch] Starting backfill_missing_metadata (batch_size=%s)", batch_size)

    try:
        with SessionLocal() as db:
            # Files currently being processed — skip them.
            in_progress_file_ids = (
                db.query(FileProcessingStep.file_id)
                .filter(FileProcessingStep.status == "in_progress")
                .distinct()
                .subquery()
            )

            candidates = (
                db.query(FileRecord)
                .filter(FileRecord.is_duplicate.is_(False))
                .filter(FileRecord.ocr_text.isnot(None))
                .filter(FileRecord.ocr_text != "")
                .filter((FileRecord.ai_metadata.is_(None)) | (FileRecord.ai_metadata == ""))
                .filter(~FileRecord.id.in_(db.query(in_progress_file_ids.c.file_id)))
                .limit(batch_size)
                .all()
            )

        queued = 0
        for record in candidates:
            filename = record.local_filename or record.original_filename or f"file_{record.id}"
            extract_metadata_with_gpt.delay(
                filename,
                record.ocr_text,
                file_id=record.id,
            )
            queued += 1

        detail = f"Queued {queued} document(s) for AI metadata backfill."
        logger.info("[batch] backfill_missing_metadata: %s", detail)
        _update_job_status(job_name, "success", detail)
        return {"queued": queued}

    except Exception as exc:
        detail = f"Error: {exc}"
        logger.error("[batch] backfill_missing_metadata failed: %s", exc, exc_info=True)
        _update_job_status(job_name, "failed", detail)
        return {"queued": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Task: sync Meilisearch search index
# ---------------------------------------------------------------------------

#: Maximum documents to index per sync run.
_SEARCH_SYNC_BATCH_SIZE: int = 100


@celery.task(name="app.tasks.batch_tasks.sync_search_index")
def sync_search_index(batch_size: int = _SEARCH_SYNC_BATCH_SIZE) -> dict:
    """
    Index documents in Meilisearch that have OCR text or AI metadata but are
    not yet present in the search index.

    This is useful after:
    - Enabling Meilisearch for the first time on an existing installation.
    - Recovering from a Meilisearch index wipe or migration.
    - Documents processed before search indexing was added to the pipeline.

    The task queries the Meilisearch index for existing document IDs, then
    finds ``FileRecord`` rows that have processable content (``ocr_text`` or
    ``ai_metadata``) but are absent from the index, and re-indexes them.

    A configurable *batch_size* caps the number of documents indexed per run.

    Args:
        batch_size: Maximum number of documents to index per run (default 100).

    Returns:
        A summary dict with ``indexed`` and ``skipped`` counts.
    """
    from app.utils.meilisearch_client import get_meilisearch_client, index_document

    job_name = "sync-search-index"
    logger.info("[batch] Starting sync_search_index (batch_size=%s)", batch_size)

    client = get_meilisearch_client()
    if client is None:
        detail = "Meilisearch is not configured; skipping search index sync."
        logger.info("[batch] sync_search_index: %s", detail)
        _update_job_status(job_name, "success", detail)
        return {"indexed": 0, "skipped": 0, "reason": "meilisearch_not_configured"}

    try:
        # Fetch the set of file_ids already in the Meilisearch index.
        index = client.get_index(settings.meilisearch_index_name)
        # Fetch up to 10 000 IDs — sufficient to determine gaps for most installs.
        existing_result = index.get_documents({"fields": ["file_id"], "limit": 10000})
        existing_ids: set[int] = {doc["file_id"] for doc in existing_result.results if "file_id" in doc}
    except Exception as exc:
        detail = f"Error fetching existing Meilisearch IDs: {exc}"
        logger.error("[batch] sync_search_index: %s", detail)
        _update_job_status(job_name, "failed", detail)
        return {"indexed": 0, "skipped": 0, "error": str(exc)}

    try:
        with SessionLocal() as db:
            # Files with indexable content that are not already in the index.
            candidates = (
                db.query(FileRecord)
                .filter(FileRecord.is_duplicate.is_(False))
                .filter(
                    (FileRecord.ocr_text.isnot(None) & (FileRecord.ocr_text != ""))
                    | (FileRecord.ai_metadata.isnot(None) & (FileRecord.ai_metadata != ""))
                )
                .filter(~FileRecord.id.in_(existing_ids) if existing_ids else True)  # type: ignore[arg-type]
                .limit(batch_size)
                .all()
            )

        indexed = 0
        skipped = 0
        for record in candidates:
            metadata: dict = {}
            if record.ai_metadata:
                try:
                    metadata = json.loads(record.ai_metadata)
                except (json.JSONDecodeError, ValueError):
                    pass

            success = index_document(record, record.ocr_text or "", metadata)
            if success:
                indexed += 1
            else:
                skipped += 1

        detail = f"Indexed {indexed} document(s) into Meilisearch; {skipped} skipped (indexing error)."
        logger.info("[batch] sync_search_index: %s", detail)
        _update_job_status(job_name, "success", detail)
        return {"indexed": indexed, "skipped": skipped}

    except Exception as exc:
        detail = f"Error: {exc}"
        logger.error("[batch] sync_search_index failed: %s", exc, exc_info=True)
        _update_job_status(job_name, "failed", detail)
        return {"indexed": 0, "skipped": 0, "error": str(exc)}
