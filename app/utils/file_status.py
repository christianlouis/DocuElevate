"""
Utility functions for file processing status determination.
"""

from typing import Dict, List

from sqlalchemy.orm import Session

from app.models import FileProcessingStep, FileRecord, ProcessingLog
from app.utils.step_manager import get_file_overall_status, get_step_summary


def get_file_processing_status(db: Session, file_id: int) -> Dict:
    """
    Get the processing status for a file by checking its processing steps.

    This function now queries the FileProcessingStep table instead of scanning logs.

    Args:
        db: Database session
        file_id: ID of the file

    Returns:
        dict with status, last_step, and has_errors
    """
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).one_or_none()
    if file_record and file_record.is_duplicate:
        return {
            "status": "duplicate",
            "last_step": "check_for_duplicates",
            "has_errors": False,
            "total_steps": 0,
        }

    # Use the new status table approach
    overall_status = get_file_overall_status(db, file_id)

    # Get the most recently updated step to determine last_step
    latest_step = (
        db.query(FileProcessingStep)
        .filter(FileProcessingStep.file_id == file_id)
        .order_by(FileProcessingStep.updated_at.desc())
        .first()
    )

    return {
        "status": overall_status["status"],
        "last_step": latest_step.step_name if latest_step else None,
        "has_errors": overall_status["has_errors"],
        "total_steps": overall_status["total_steps"],
    }


def get_files_processing_status(db: Session, file_ids: List[int]) -> Dict[int, Dict]:
    """
    Get processing status for multiple files efficiently.

    Only counts "real" processing steps that represent user-facing status:
    - Main steps: create_file_record, check_text, extract_text, process_with_azure_document_intelligence,
                  extract_metadata_with_gpt, embed_metadata_into_pdf, finalize_document_storage,
                  send_to_all_destinations
    - Upload steps: upload_to_*
    
    Diagnostic/internal steps (poll_task, upload_file, set_custom_fields, etc.) are ignored.

    Args:
        db: Database session
        file_ids: List of file IDs

    Returns:
        dict mapping file_id to status dict
    """
    # Preload duplicate flags for all files
    duplicate_flags = {
        record.id: record.is_duplicate
        for record in db.query(FileRecord.id, FileRecord.is_duplicate).filter(FileRecord.id.in_(file_ids)).all()
    }

    # Define which steps are "real" status-determining steps
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

    # Get all REAL steps for these files in one query
    steps = (
        db.query(FileProcessingStep)
        .filter(FileProcessingStep.file_id.in_(file_ids), FileProcessingStep.step_name.in_(REAL_STEPS))
        .all()
    )

    # Group steps by file_id
    steps_by_file = {}
    for step in steps:
        if step.file_id not in steps_by_file:
            steps_by_file[step.file_id] = []
        steps_by_file[step.file_id].append(step)

    # Compute status for each file
    result = {}
    for file_id in file_ids:
        if duplicate_flags.get(file_id):
            result[file_id] = {
                "status": "duplicate",
                "last_step": "check_for_duplicates",
                "has_errors": False,
                "total_steps": 0,
            }
            continue
        file_steps = steps_by_file.get(file_id, [])
        if not file_steps:
            result[file_id] = {"status": "pending", "last_step": None, "has_errors": False, "total_steps": 0}
        else:
            # Compute overall status from steps
            total_steps = len(file_steps)
            completed_steps = sum(1 for s in file_steps if s.status == "success")
            failed_steps = sum(1 for s in file_steps if s.status == "failure")
            in_progress_steps = sum(1 for s in file_steps if s.status == "in_progress")
            skipped_steps = sum(1 for s in file_steps if s.status == "skipped")

            has_errors = failed_steps > 0

            # Determine overall status
            if has_errors:
                status = "failed"
            elif in_progress_steps > 0:
                status = "processing"
            elif completed_steps + skipped_steps == total_steps:
                status = "completed"
            else:
                status = "pending"

            # Get last updated step
            latest_step = max(file_steps, key=lambda s: s.updated_at if s.updated_at else s.created_at)

            result[file_id] = {
                "status": status,
                "last_step": latest_step.step_name,
                "has_errors": has_errors,
                "total_steps": total_steps,
            }

    return result


def _compute_status_from_logs(logs: List[ProcessingLog]) -> Dict:
    """
    Compute processing status from a list of processing logs.

    DEPRECATED: This function is kept for backwards compatibility.
    New code should use the FileProcessingStep table instead.

    Args:
        logs: List of ProcessingLog objects (should be ordered by timestamp desc)

    Returns:
        dict with status, last_step, has_errors, and total_steps
    """
    if not logs:
        return {"status": "pending", "last_step": None, "has_errors": False, "total_steps": 0}

    # Get the latest status for each unique step
    # Since logs are ordered by timestamp desc, the first occurrence is the latest
    latest_by_step = {}
    for log in logs:
        if log.step_name not in latest_by_step:
            latest_by_step[log.step_name] = log

    # Check for failures in latest statuses
    has_errors = any(log.status == "failure" for log in latest_by_step.values())

    # Check if any step is currently in progress (based on latest status per step)
    in_progress = any(log.status == "in_progress" for log in latest_by_step.values())

    # Get the overall latest log
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
