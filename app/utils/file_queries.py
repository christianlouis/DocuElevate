"""
Shared file query utilities for filtering files by processing status.

This module contains reusable query logic for filtering FileRecord objects
based on their processing status (pending, processing, failed, completed).
"""

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.models import FileRecord, ProcessingLog


def apply_status_filter(query: Query, db: Session, status: Optional[str]) -> Query:
    """
    Apply status filter to a FileRecord query.

    This function modifies a SQLAlchemy query to filter files based on their
    processing status by examining associated ProcessingLog entries.

    Args:
        query: The base SQLAlchemy query for FileRecord objects
        db: Database session for creating subqueries
        status: Status filter to apply. Valid values:
            - "pending": Files with no ProcessingLog entries
            - "processing": Files with in_progress logs
            - "failed": Files with failure logs
            - "completed": Files with success logs but no failures or in_progress
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

    # Subquery to get file IDs matching the status
    if status == "pending":
        # Files with no logs
        subq = db.query(ProcessingLog.file_id).distinct()
        query = query.filter(~FileRecord.id.in_(subq))
    elif status == "processing":
        # Files with in_progress logs
        subq = db.query(ProcessingLog.file_id).filter(ProcessingLog.status == "in_progress").distinct()
        query = query.filter(FileRecord.id.in_(subq))
    elif status == "failed":
        # Files with failure logs
        subq = db.query(ProcessingLog.file_id).filter(ProcessingLog.status == "failure").distinct()
        query = query.filter(FileRecord.id.in_(subq))
    elif status == "completed":
        # Files with success logs but no failures or in_progress
        success_files = db.query(ProcessingLog.file_id).filter(ProcessingLog.status == "success").distinct().subquery()

        failed_files = (
            db.query(ProcessingLog.file_id)
            .filter(or_(ProcessingLog.status == "failure", ProcessingLog.status == "in_progress"))
            .distinct()
            .subquery()
        )

        query = query.filter(FileRecord.id.in_(db.query(success_files.c.file_id))).filter(
            ~FileRecord.id.in_(db.query(failed_files.c.file_id))
        )

    return query
