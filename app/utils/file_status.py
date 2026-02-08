"""
Utility functions for file processing status determination.
"""

from typing import Dict, List

from sqlalchemy.orm import Session

from app.models import ProcessingLog


def get_file_processing_status(db: Session, file_id: int) -> Dict:
    """
    Get the processing status for a file by checking its processing logs.

    Args:
        db: Database session
        file_id: ID of the file

    Returns:
        dict with status, last_step, and has_errors
    """
    # Get all logs for this file
    logs = (
        db.query(ProcessingLog).filter(ProcessingLog.file_id == file_id).order_by(ProcessingLog.timestamp.desc()).all()
    )

    return _compute_status_from_logs(logs)


def get_files_processing_status(db: Session, file_ids: List[int]) -> Dict[int, Dict]:
    """
    Get processing status for multiple files efficiently.

    Args:
        db: Database session
        file_ids: List of file IDs

    Returns:
        dict mapping file_id to status dict
    """
    # Get all logs for these files in one query
    logs = (
        db.query(ProcessingLog)
        .filter(ProcessingLog.file_id.in_(file_ids))
        .order_by(ProcessingLog.file_id, ProcessingLog.timestamp.desc())
        .all()
    )

    # Group logs by file_id
    logs_by_file = {}
    for log in logs:
        if log.file_id not in logs_by_file:
            logs_by_file[log.file_id] = []
        logs_by_file[log.file_id].append(log)

    # Compute status for each file
    result = {}
    for file_id in file_ids:
        file_logs = logs_by_file.get(file_id, [])
        result[file_id] = _compute_status_from_logs(file_logs)

    return result


def _compute_status_from_logs(logs: List[ProcessingLog]) -> Dict:
    """
    Compute processing status from a list of processing logs.

    Args:
        logs: List of ProcessingLog objects (should be ordered by timestamp desc)

    Returns:
        dict with status, last_step, has_errors, and total_steps
    """
    if not logs:
        return {"status": "pending", "last_step": None, "has_errors": False, "total_steps": 0}

    # Check for failures
    has_errors = any(log.status == "failure" for log in logs)

    # Check if any in progress
    in_progress = any(log.status == "in_progress" for log in logs)

    # Get the latest log
    latest_log = logs[0]

    # Determine overall status
    if has_errors:
        status = "failed"
    elif in_progress:
        status = "processing"
    elif latest_log.status == "success":
        status = "completed"
    else:
        status = "pending"

    return {"status": status, "last_step": latest_log.step_name, "has_errors": has_errors, "total_steps": len(logs)}
