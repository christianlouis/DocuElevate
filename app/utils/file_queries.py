"""
Shared file query utilities for filtering files by processing status.

This module contains reusable query logic for filtering FileRecord objects
based on their processing status using the FileProcessingStep table.
"""

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.models import FileRecord, FileProcessingStep


def apply_status_filter(query: Query, db: Session, status: Optional[str]) -> Query:
    """
    Apply status filter to a FileRecord query using FileProcessingStep table.

    This function modifies a SQLAlchemy query to filter files based on their
    processing status by examining associated FileProcessingStep entries.
    
    Only tracks "real" processing steps that represent user-facing status:
    - Main steps: create_file_record, check_text, extract_text, process_with_azure_document_intelligence,
                  extract_metadata_with_gpt, embed_metadata_into_pdf, finalize_document_storage,
                  send_to_all_destinations
    - Upload steps: queue_*, upload_to_*
    
    Diagnostic/internal steps (poll_task, upload_file, set_custom_fields, etc.) are ignored
    as they may not complete properly and don't affect the actual status.

    Args:
        query: The base SQLAlchemy query for FileRecord objects
        db: Database session for creating subqueries
        status: Status filter to apply. Valid values:
            - "pending": Files with no real FileProcessingStep entries
            - "processing": Files with in_progress real steps
            - "failed": Files with failure real steps
            - "completed": Files with all real steps success/skipped
            - None: No filter applied (returns query unchanged)

    Returns:
        Modified query with status filter applied

    Examples:
        >>> query = db.query(FileRecord)
        >>> query = apply_status_filter(query, db, "completed")
        >>> files = query.all()
    """
    if not status:
        return query

    # Define which steps are "real" status-determining steps
    # Only high-level logical steps and actual upload destinations (not queue_* steps)
    from app.config import settings
    
    REAL_STEPS = {
        "create_file_record",
        "check_text",
        "extract_text",
        "process_with_azure_document_intelligence",
        "extract_metadata_with_gpt",
        "embed_metadata_into_pdf",
        "finalize_document_storage",
        "send_to_all_destinations",
        "upload_to_dropbox",
        "upload_to_paperless",
        "upload_to_google_drive",
        "upload_to_ftp",
        "upload_to_onedrive",
        "upload_to_webdav",
        "upload_to_sftp",
        "upload_to_nextcloud",
        "upload_to_paperless_ngx",
        "upload_to_email",
        "upload_to_s3",
    }
    
    # Add check_for_duplicates if deduplication is enabled
    if settings.enable_deduplication:
        REAL_STEPS.add("check_for_duplicates")

    # Filter to only real steps
    real_steps_subq = (
        db.query(FileProcessingStep)
        .filter(FileProcessingStep.step_name.in_(REAL_STEPS))
    )

    if status == "pending":
        # Files with no real steps (never started processing)
        subq = real_steps_subq.distinct().subquery()
        query = query.filter(~FileRecord.id.in_(db.query(subq.c.file_id)))
    elif status == "processing":
        # Files with in_progress real steps
        subq = real_steps_subq.filter(FileProcessingStep.status == "in_progress").distinct().subquery()
        query = query.filter(FileRecord.id.in_(db.query(subq.c.file_id)))
    elif status == "failed":
        # Files with failure real steps
        subq = real_steps_subq.filter(FileProcessingStep.status == "failure").distinct().subquery()
        query = query.filter(FileRecord.id.in_(db.query(subq.c.file_id)))
    elif status == "completed":
        # Files where all real steps are either success or skipped (no failures or in_progress)
        # Exclude duplicates from completed
        query = query.filter(FileRecord.is_duplicate.is_(False))
        
        # Get files that have real steps
        files_with_real_steps = real_steps_subq.distinct().subquery()

        # Get files with failures or in_progress on real steps
        files_with_issues = (
            real_steps_subq
            .filter(or_(FileProcessingStep.status == "failure", FileProcessingStep.status == "in_progress"))
            .distinct()
            .subquery()
        )

        # Select files with real steps that don't have issues
        query = query.filter(FileRecord.id.in_(db.query(files_with_real_steps.c.file_id))).filter(
            ~FileRecord.id.in_(db.query(files_with_issues.c.file_id))
        )
    elif status == "duplicate":
        # Files marked as duplicates
        query = query.filter(FileRecord.is_duplicate.is_(True))

    return query
