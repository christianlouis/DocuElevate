"""
File-related API endpoints
"""

import logging
import mimetypes
import os
import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from app.auth import require_login
from app.config import settings
from app.database import get_db
from app.models import FileRecord, ProcessingLog
from app.tasks.convert_to_pdf import convert_to_pdf
from app.tasks.process_document import process_document
from app.utils.file_queries import apply_status_filter
from app.utils.file_status import get_files_processing_status
from app.utils.filename_utils import sanitize_filename
from app.utils.input_validation import validate_search_query, validate_sort_field, validate_sort_order

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


def get_limiter():
    """Get the limiter from app state."""
    from app.main import app

    return app.state.limiter


@router.get("/files")
@require_login
def list_files_api(
    request: Request,
    db: DbSession,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
    sort_by: str = Query(
        "created_at",
        description="Sort field: id, original_filename, file_size, mime_type, created_at, status",
    ),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    search: Optional[str] = Query(None, description="Search in filename"),
    mime_type: Optional[str] = Query(None, description="Filter by MIME type"),
    status: Optional[str] = Query(None, description="Filter by processing status"),
):
    """
    Returns a paginated JSON list of FileRecord entries with processing status.
    Supports server-side sorting, filtering, and searching.

    Query Parameters:
    - page: Page number (default: 1)
    - per_page: Items per page (default: 50, max: 200)
    - sort_by: Field to sort by (default: created_at)
    - sort_order: asc or desc (default: desc)
    - search: Search in filename
    - mime_type: Filter by MIME type
    - status: Filter by processing status (pending, processing, completed, failed)

    Example response:
    {
      "files": [...],
      "pagination": {
        "page": 1,
        "per_page": 50,
        "total_items": 150,
        "total_pages": 3
      }
    }
    """
    # Validate and sanitize query parameters
    validate_sort_field(sort_by)
    validate_sort_order(sort_order)
    search = validate_search_query(search)

    # Start with base query
    query = db.query(FileRecord)

    # Apply search filter
    if search:
        query = query.filter(FileRecord.original_filename.ilike(f"%{search}%"))

    # Apply MIME type filter
    if mime_type:
        query = query.filter(FileRecord.mime_type == mime_type)

    # Apply status filter (before pagination for correct counts)
    query = apply_status_filter(query, db, status)

    # Get total count before pagination (after all filters)
    total_items = query.count()

    # Apply sorting
    sort_column = {
        "id": FileRecord.id,
        "original_filename": FileRecord.original_filename,
        "file_size": FileRecord.file_size,
        "mime_type": FileRecord.mime_type,
        "created_at": FileRecord.created_at,
    }.get(sort_by, FileRecord.created_at)

    if sort_order == "asc":
        query = query.order_by(asc(sort_column))
    else:
        query = query.order_by(desc(sort_column))

    # Apply pagination
    offset = (page - 1) * per_page
    files = query.offset(offset).limit(per_page).all()

    # Get processing status for all files efficiently
    file_ids = [f.id for f in files]
    statuses = get_files_processing_status(db, file_ids)

    # Build result with processing status
    result = []
    for f in files:
        result.append(
            {
                "id": f.id,
                "filehash": f.filehash,
                "original_filename": f.original_filename,
                "local_filename": f.local_filename,
                "file_size": f.file_size,
                "mime_type": f.mime_type,
                "created_at": f.created_at.isoformat() if f.created_at else None,
                "processing_status": statuses.get(
                    f.id,
                    {
                        "status": "pending",
                        "last_step": None,
                        "has_errors": False,
                        "total_steps": 0,
                    },
                ),
            }
        )

    # Calculate pagination info
    total_pages = (total_items + per_page - 1) // per_page

    return {
        "files": result,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_items": total_items,
            "total_pages": total_pages,
        },
    }


def _get_file_processing_status(db: Session, file_id: int) -> dict:
    """
    Deprecated: Use app.utils.file_status.get_file_processing_status instead.
    Kept for backward compatibility with file detail endpoint.
    """
    from app.utils.file_status import get_file_processing_status

    return get_file_processing_status(db, file_id)


@router.get("/files/{file_id}")
@require_login
def get_file_details(request: Request, file_id: int, db: DbSession):
    """
    Get detailed information about a specific file including processing history.
    """
    # Find the file record
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()

    if not file_record:
        raise HTTPException(status_code=404, detail=f"File record with ID {file_id} not found")

    # Get processing logs
    logs = (
        db.query(ProcessingLog).filter(ProcessingLog.file_id == file_id).order_by(ProcessingLog.timestamp.desc()).all()
    )

    # Build log list
    log_list = []
    for log in logs:
        log_list.append(
            {
                "id": log.id,
                "task_id": log.task_id,
                "step_name": log.step_name,
                "status": log.status,
                "message": log.message,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            }
        )

    # Get processing status
    processing_status = _get_file_processing_status(db, file_id)

    # Check if files exist on disk
    files_on_disk = {"original": (os.path.exists(file_record.local_filename) if file_record.local_filename else False)}

    return {
        "file": {
            "id": file_record.id,
            "filehash": file_record.filehash,
            "original_filename": file_record.original_filename,
            "local_filename": file_record.local_filename,
            "file_size": file_record.file_size,
            "mime_type": file_record.mime_type,
            "created_at": (file_record.created_at.isoformat() if file_record.created_at else None),
        },
        "processing_status": processing_status,
        "logs": log_list,
        "files_on_disk": files_on_disk,
    }


@router.delete("/files/{file_id}")
@require_login
def delete_file_record(request: Request, file_id: int, db: DbSession):
    """
    Delete a file record from the database.
    This only removes the database entry, not the actual file.
    """
    # Check if file deletion is allowed
    if not settings.allow_file_delete:
        raise HTTPException(status_code=403, detail="File deletion is disabled in the configuration")

    try:
        # Find the file record
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()

        if not file_record:
            raise HTTPException(status_code=404, detail=f"File record with ID {file_id} not found")

        # Log the deletion
        logger.info(f"Deleting file record: ID={file_id}, Filename={file_record.original_filename}")

        # Delete the record
        db.delete(file_record)
        db.commit()

        return {
            "status": "success",
            "message": f"File record {file_id} deleted successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Error deleting file record {file_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting file record: {str(e)}")


@router.post("/files/bulk-delete")
@require_login
def bulk_delete_files(request: Request, file_ids: List[int], db: DbSession):
    """
    Delete multiple file records from the database.
    This only removes the database entries, not the actual files.
    """
    # Check if file deletion is allowed
    if not settings.allow_file_delete:
        raise HTTPException(status_code=403, detail="File deletion is disabled in the configuration")

    try:
        # Find all file records
        file_records = db.query(FileRecord).filter(FileRecord.id.in_(file_ids)).all()

        if not file_records:
            raise HTTPException(status_code=404, detail="No files found with the provided IDs")

        deleted_count = len(file_records)
        deleted_ids = [f.id for f in file_records]

        # Log the deletion
        logger.info(f"Bulk deleting {deleted_count} file records: IDs={deleted_ids}")

        # Delete all records
        for file_record in file_records:
            db.delete(file_record)

        db.commit()

        return {
            "status": "success",
            "message": f"Successfully deleted {deleted_count} file records",
            "deleted_ids": deleted_ids,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Error bulk deleting file records: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error bulk deleting file records: {str(e)}")


@router.post("/files/bulk-reprocess")
@require_login
def bulk_reprocess_files(request: Request, file_ids: List[int], db: DbSession):
    """
    Reprocess multiple files by queuing them for processing.
    """
    try:
        # Find all file records
        file_records = db.query(FileRecord).filter(FileRecord.id.in_(file_ids)).all()

        if not file_records:
            raise HTTPException(status_code=404, detail="No files found with the provided IDs")

        task_ids = []
        processed_files = []
        errors = []

        for file_record in file_records:
            try:
                # Check if local file exists
                if not file_record.local_filename or not os.path.exists(file_record.local_filename):
                    errors.append(
                        {
                            "file_id": file_record.id,
                            "filename": file_record.original_filename,
                            "error": "Local file not found",
                        }
                    )
                    continue

                # Queue the file for processing, passing file_id to skip duplicate check
                task = process_document.delay(file_record.local_filename, file_id=file_record.id)
                task_ids.append(task.id)
                processed_files.append(
                    {
                        "file_id": file_record.id,
                        "filename": file_record.original_filename,
                        "task_id": task.id,
                    }
                )

                logger.info(
                    f"Reprocessing file: ID={file_record.id}, "
                    f"Filename={file_record.original_filename}, TaskID={task.id}"
                )

            except Exception as e:
                logger.exception(f"Error reprocessing file {file_record.id}: {str(e)}")
                errors.append(
                    {
                        "file_id": file_record.id,
                        "filename": file_record.original_filename,
                        "error": str(e),
                    }
                )

        return {
            "status": "success" if processed_files else "error",
            "message": f"Successfully queued {len(processed_files)} files for reprocessing",
            "processed_files": processed_files,
            "errors": errors,
            "task_ids": task_ids,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error bulk reprocessing files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error bulk reprocessing files: {str(e)}")


@router.post("/files/{file_id}/reprocess")
@require_login
def reprocess_single_file(request: Request, file_id: int, db: DbSession):
    """
    Reprocess a single file by queuing it for processing again.

    Args:
        file_id: ID of the file to reprocess

    Returns:
        Task ID and status information
    """
    try:
        # Find the file record
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()

        if not file_record:
            raise HTTPException(status_code=404, detail=f"File with ID {file_id} not found")

        # Check if local file exists
        if not file_record.local_filename or not os.path.exists(file_record.local_filename):
            raise HTTPException(
                status_code=400,
                detail="Local file not found on disk. Cannot reprocess.",
            )

        # Queue the file for processing, passing file_id to skip duplicate check
        task = process_document.delay(
            file_record.local_filename,
            original_filename=file_record.original_filename,
            file_id=file_record.id,
        )

        logger.info(
            f"Reprocessing file: ID={file_record.id}, Filename={file_record.original_filename}, TaskID={task.id}"
        )

        return {
            "status": "success",
            "message": "File queued for reprocessing",
            "file_id": file_record.id,
            "filename": file_record.original_filename,
            "task_id": task.id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error reprocessing file {file_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reprocessing file: {str(e)}")


@router.post("/files/{file_id}/reprocess-with-cloud-ocr")
@require_login
def reprocess_with_cloud_ocr(request: Request, file_id: int, db: DbSession):
    """
    Reprocess a single file with forced Cloud OCR processing.

    This endpoint forces Azure Document Intelligence OCR processing regardless
    of whether the PDF contains embedded text. Useful for documents with
    low-quality embedded text or when higher quality OCR is needed.

    Args:
        file_id: ID of the file to reprocess with Cloud OCR

    Returns:
        Task ID and status information
    """
    try:
        # Find the file record
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()

        if not file_record:
            raise HTTPException(status_code=404, detail=f"File with ID {file_id} not found")

        # Prefer using the original_file_path if available, otherwise fall back to local_filename
        source_file = None
        if file_record.original_file_path and os.path.exists(file_record.original_file_path):
            source_file = file_record.original_file_path
            logger.info(f"Using original file for Cloud OCR reprocessing: {source_file}")
        elif file_record.local_filename and os.path.exists(file_record.local_filename):
            source_file = file_record.local_filename
            logger.info(f"Using local file for Cloud OCR reprocessing: {source_file}")
        else:
            raise HTTPException(
                status_code=400,
                detail="Neither original nor local file found on disk. Cannot reprocess.",
            )

        # Queue the file for processing with force_cloud_ocr=True
        task = process_document.delay(
            source_file,
            original_filename=file_record.original_filename,
            file_id=file_record.id,
            force_cloud_ocr=True,
        )

        logger.info(
            f"Reprocessing file with Cloud OCR: ID={file_record.id}, "
            f"Filename={file_record.original_filename}, TaskID={task.id}"
        )

        return {
            "status": "success",
            "message": "File queued for Cloud OCR reprocessing",
            "file_id": file_record.id,
            "filename": file_record.original_filename,
            "task_id": task.id,
            "force_cloud_ocr": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error reprocessing file {file_id} with Cloud OCR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reprocessing file with Cloud OCR: {str(e)}")


def _extract_text_from_pdf(file_path: str) -> str:
    """
    Extract text from a PDF file using pypdf.

    Args:
        file_path: Path to the PDF file

    Returns:
        Extracted text from all pages
    """
    import pypdf  # Upgraded from PyPDF2 to fix CVE-2023-36464

    extracted_text = ""
    with open(file_path, "rb") as f:
        pdf_reader = pypdf.PdfReader(f)
        for page in pdf_reader.pages:
            extracted_text += page.extract_text() + "\n"
    return extracted_text


def _retry_pipeline_step(file_record: FileRecord, step_name: str, db: Session) -> dict:
    """
    Retry a specific pipeline processing step for a file.

    Supports restarting from intermediate pipeline steps:
    - process_document: Full reprocessing (skips duplicate check)
    - process_with_azure_document_intelligence: OCR processing
    - extract_metadata_with_gpt: Metadata extraction
    - embed_metadata_into_pdf: Metadata embedding

    Args:
        file_record: The FileRecord to reprocess
        step_name: Name of the pipeline step to retry
        db: Database session

    Returns:
        Dict with task ID and status information
    """
    file_id = file_record.id

    if step_name == "process_document":
        # Full reprocessing with duplicate check bypass
        logger.info(f"Retrying process_document for file {file_id}: local_filename={file_record.local_filename!r}")
        if not file_record.local_filename:
            logger.error(f"process_document retry failed for file {file_id}: local_filename is None")
            raise HTTPException(status_code=400, detail="Local file path is None. Cannot retry.")

        exists = os.path.exists(file_record.local_filename)
        logger.info(f"Checking local_filename: {file_record.local_filename!r}, exists={exists}")
        if not exists:
            error_message = f"Local file not found on disk. Cannot retry. Path checked: local_filename={file_record.local_filename!r} (exists=False)"
            logger.error(f"process_document retry failed for file {file_id}: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)

        logger.info(f"Found file for process_document retry at: {file_record.local_filename!r}")
        task = process_document.delay(
            file_record.local_filename,
            original_filename=file_record.original_filename,
            file_id=file_id,
        )
    elif step_name == "process_with_azure_document_intelligence":
        from app.tasks.process_with_azure_document_intelligence import (
            process_with_azure_document_intelligence,
        )

        # OCR needs the file in workdir/tmp
        logger.info(
            f"Retrying process_with_azure_document_intelligence for file {file_id}: "
            f"local_filename={file_record.local_filename!r}"
        )
        if not file_record.local_filename:
            logger.error(f"OCR retry failed for file {file_id}: local_filename is None")
            raise HTTPException(status_code=400, detail="Local file path is None. Cannot retry OCR.")

        exists = os.path.exists(file_record.local_filename)
        logger.info(f"Checking local_filename: {file_record.local_filename!r}, exists={exists}")
        if not exists:
            error_message = f"Local file not found on disk. Cannot retry OCR. Path checked: local_filename={file_record.local_filename!r} (exists=False)"
            logger.error(f"OCR retry failed for file {file_id}: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)

        logger.info(f"Found file for OCR retry at: {file_record.local_filename!r}")
        filename = os.path.basename(file_record.local_filename)
        task = process_with_azure_document_intelligence.delay(filename, file_id)
    elif step_name == "extract_metadata_with_gpt":
        from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt

        logger.info(
            f"Retrying extract_metadata_with_gpt for file {file_id}: local_filename={file_record.local_filename!r}"
        )
        if not file_record.local_filename:
            logger.error(f"Metadata extraction retry failed for file {file_id}: local_filename is None")
            raise HTTPException(
                status_code=400,
                detail="Local file path is None. Cannot retry metadata extraction.",
            )

        exists = os.path.exists(file_record.local_filename)
        logger.info(f"Checking local_filename: {file_record.local_filename!r}, exists={exists}")
        if not exists:
            error_message = f"Local file not found on disk. Cannot retry metadata extraction. Path checked: local_filename={file_record.local_filename!r} (exists=False)"
            logger.error(f"Metadata extraction retry failed for file {file_id}: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)

        logger.info(f"Found file for metadata extraction retry at: {file_record.local_filename!r}")
        extracted_text = _extract_text_from_pdf(file_record.local_filename)
        filename = os.path.basename(file_record.local_filename)
        task = extract_metadata_with_gpt.delay(filename, extracted_text, file_id)
    elif step_name == "embed_metadata_into_pdf":
        from app.tasks.extract_metadata_with_gpt import (
            extract_metadata_with_gpt as extract_metadata_task,
        )

        # Retrying embed requires re-running metadata extraction first, because
        # embed_metadata_into_pdf needs the actual metadata dict (not empty).
        # Re-trigger extract_metadata_with_gpt which will chain into embed_metadata_into_pdf.

        # Log all database path values at the start
        logger.info(
            f"Retrying embed_metadata_into_pdf for file {file_id}: "
            f"local_filename={file_record.local_filename!r}, "
            f"processed_file_path={file_record.processed_file_path!r}, "
            f"original_file_path={file_record.original_file_path!r}"
        )

        # Check for file in multiple locations:
        # 1. Original location in tmp (file_record.local_filename)
        # 2. Processed location (file_record.processed_file_path)
        # 3. Original immutable copy (file_record.original_file_path)
        # 4. Fallback to workdir/tmp/<basename>
        file_path = None
        checked_paths = []

        # Check 1: local_filename (original tmp location)
        if file_record.local_filename:
            exists = os.path.exists(file_record.local_filename)
            checked_paths.append(f"local_filename={file_record.local_filename!r} (exists={exists})")
            logger.info(f"Checking local_filename: {file_record.local_filename!r}, exists={exists}")
            if exists:
                file_path = file_record.local_filename

        # Check 2: processed_file_path
        if not file_path and file_record.processed_file_path:
            exists = os.path.exists(file_record.processed_file_path)
            checked_paths.append(f"processed_file_path={file_record.processed_file_path!r} (exists={exists})")
            logger.info(f"Checking processed_file_path: {file_record.processed_file_path!r}, exists={exists}")
            if exists:
                file_path = file_record.processed_file_path

        # Check 3: original_file_path (immutable copy in workdir/original/)
        if not file_path and file_record.original_file_path:
            exists = os.path.exists(file_record.original_file_path)
            checked_paths.append(f"original_file_path={file_record.original_file_path!r} (exists={exists})")
            logger.info(f"Checking original_file_path: {file_record.original_file_path!r}, exists={exists}")
            if exists:
                file_path = file_record.original_file_path

        # Check 4: Fallback to workdir/tmp/<basename>
        if not file_path and file_record.local_filename:
            workdir = settings.workdir
            tmp_dir = os.path.join(workdir, "tmp")
            fallback_path = os.path.join(tmp_dir, os.path.basename(file_record.local_filename))
            exists = os.path.exists(fallback_path)
            checked_paths.append(f"workdir_tmp_fallback={fallback_path!r} (exists={exists})")
            logger.info(f"Checking workdir/tmp fallback: {fallback_path!r}, exists={exists}")
            if exists:
                file_path = fallback_path

        if not file_path:
            paths_detail = "; ".join(checked_paths)
            error_message = f"File not found on disk. Cannot retry metadata embedding. Paths checked: {paths_detail}"
            logger.error(f"embed_metadata_into_pdf retry failed for file {file_id}: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)

        logger.info(f"Found file for embed_metadata_into_pdf retry at: {file_path!r}")
        extracted_text = _extract_text_from_pdf(file_path)
        # Pass the full path to the task so it can locate the file
        task = extract_metadata_task.delay(file_path, extracted_text, file_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported pipeline step: {step_name}")

    logger.info(f"Retrying pipeline step: FileID={file_record.id}, Step={step_name}, TaskID={task.id}")

    return {
        "status": "success",
        "message": f"Pipeline step {step_name} queued for retry",
        "file_id": file_record.id,
        "subtask_name": step_name,
        "task_id": task.id,
    }


@router.post("/files/{file_id}/retry-subtask")
@require_login
def retry_subtask(
    request: Request,
    file_id: int,
    db: DbSession,
    subtask_name: str = Query(
        ...,
        description="Name of the subtask to retry (e.g., 'upload_to_dropbox', 'extract_metadata_with_gpt')",
    ),
):
    """
    Retry a specific failed subtask for a file.

    Supports both upload tasks (e.g., upload_to_dropbox) and pipeline processing
    steps (e.g., process_with_azure_document_intelligence, extract_metadata_with_gpt,
    embed_metadata_into_pdf).

    Args:
        file_id: ID of the file
        subtask_name: Name of the task to retry

    Returns:
        Task ID and status information
    """
    try:
        # Find the file record
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()

        if not file_record:
            raise HTTPException(status_code=404, detail=f"File with ID {file_id} not found")

        # Pipeline processing steps that can be retried from the failed step
        pipeline_step_names = {
            "process_document",
            "process_with_azure_document_intelligence",
            "extract_metadata_with_gpt",
            "embed_metadata_into_pdf",
        }

        if subtask_name in pipeline_step_names:
            return _retry_pipeline_step(file_record, subtask_name, db)

        # Map subtask names to their corresponding Celery tasks
        from app.tasks.upload_to_dropbox import upload_to_dropbox
        from app.tasks.upload_to_email import upload_to_email
        from app.tasks.upload_to_ftp import upload_to_ftp
        from app.tasks.upload_to_google_drive import upload_to_google_drive
        from app.tasks.upload_to_nextcloud import upload_to_nextcloud
        from app.tasks.upload_to_onedrive import upload_to_onedrive
        from app.tasks.upload_to_paperless import upload_to_paperless
        from app.tasks.upload_to_s3 import upload_to_s3
        from app.tasks.upload_to_sftp import upload_to_sftp
        from app.tasks.upload_to_webdav import upload_to_webdav

        task_map = {
            "upload_to_dropbox": upload_to_dropbox,
            "upload_to_nextcloud": upload_to_nextcloud,
            "upload_to_paperless": upload_to_paperless,
            "upload_to_google_drive": upload_to_google_drive,
            "upload_to_onedrive": upload_to_onedrive,
            "upload_to_s3": upload_to_s3,
            "upload_to_webdav": upload_to_webdav,
            "upload_to_ftp": upload_to_ftp,
            "upload_to_sftp": upload_to_sftp,
            "upload_to_email": upload_to_email,
        }

        if subtask_name not in task_map:
            all_valid = sorted(list(task_map.keys()) + sorted(pipeline_step_names))
            raise HTTPException(
                status_code=400,
                detail=f"Invalid subtask name: {subtask_name}. Must be one of: {', '.join(all_valid)}",
            )

        # Check for processed file (upload tasks work with processed files)
        logger.info(
            f"Retrying upload task {subtask_name} for file {file_id}: "
            f"original_filename={file_record.original_filename!r}, "
            f"filehash={file_record.filehash!r}"
        )
        workdir = settings.workdir
        processed_dir = os.path.join(workdir, "processed")

        # Try to find the processed file
        base_filename = os.path.splitext(file_record.original_filename)[0]
        potential_paths = [
            os.path.join(processed_dir, f"{file_record.filehash}.pdf"),
            os.path.join(processed_dir, f"{base_filename}_processed.pdf"),
            os.path.join(processed_dir, file_record.original_filename),
        ]

        file_path = None
        checked_paths = []
        for path in potential_paths:
            exists = os.path.exists(path)
            checked_paths.append(f"{path!r} (exists={exists})")
            logger.info(f"Checking processed file path: {path!r}, exists={exists}")
            if exists:
                file_path = path
                break

        if not file_path:
            paths_detail = "; ".join(checked_paths)
            error_message = f"Processed file not found. Cannot retry upload. Paths checked: {paths_detail}"
            logger.error(f"Upload retry failed for file {file_id}: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)

        logger.info(f"Found processed file for upload retry at: {file_path!r}")
        # Queue the specific upload task
        upload_task = task_map[subtask_name]
        task = upload_task.delay(file_path, file_id)

        logger.info(f"Retrying upload subtask: FileID={file_record.id}, Subtask={subtask_name}, TaskID={task.id}")

        return {
            "status": "success",
            "message": f"Upload task {subtask_name} queued for retry",
            "file_id": file_record.id,
            "subtask_name": subtask_name,
            "task_id": task.id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrying subtask {subtask_name} for file {file_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrying subtask: {str(e)}")


@router.get("/files/{file_id}/preview")
@require_login
def get_file_preview(
    request: Request,
    file_id: int,
    db: DbSession,
    version: str = Query("original", description="original or processed"),
):
    """
    Get file content for preview (original or processed version).

    Args:
        file_id: ID of the file
        version: "original" for tmp file, "processed" for processed file

    Returns:
        File content for preview
    """
    from fastapi.responses import FileResponse

    try:
        # Find the file record
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()

        if not file_record:
            raise HTTPException(status_code=404, detail=f"File with ID {file_id} not found")

        if version == "original":
            # Return the original file from tmp
            if not file_record.local_filename or not os.path.exists(file_record.local_filename):
                raise HTTPException(status_code=404, detail="Original file not found on disk")

            file_path = file_record.local_filename

        elif version == "processed":
            # Look for processed file in /workdir/processed/
            workdir = settings.workdir
            processed_dir = os.path.join(workdir, "processed")

            # Try to find the processed file (same hash or UUID-based naming)
            base_filename = os.path.splitext(file_record.original_filename)[0]
            potential_paths = [
                os.path.join(processed_dir, f"{file_record.filehash}.pdf"),
                os.path.join(processed_dir, f"{base_filename}_processed.pdf"),
                os.path.join(processed_dir, file_record.original_filename),
            ]

            file_path = None
            for path in potential_paths:
                if os.path.exists(path):
                    file_path = path
                    break

            if not file_path:
                raise HTTPException(status_code=404, detail="Processed file not found")
        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid version parameter. Use 'original' or 'processed'",
            )

        # Return the file
        return FileResponse(
            path=file_path,
            media_type=file_record.mime_type or "application/pdf",
            headers={"Content-Disposition": f'inline; filename="{file_record.original_filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving file preview: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving file preview: {str(e)}")


@router.get("/files/{file_id}/download")
@require_login
def download_file(
    request: Request,
    file_id: int,
    db: DbSession,
    version: str = Query("original", description="original or processed"),
):
    """
    Download file (original or processed version) as attachment.

    Args:
        file_id: ID of the file
        version: "original" for tmp file, "processed" for processed file

    Returns:
        File content as attachment download
    """
    from fastapi.responses import FileResponse

    try:
        # Find the file record
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()

        if not file_record:
            raise HTTPException(status_code=404, detail=f"File with ID {file_id} not found")

        if version == "original":
            # Return the original file from tmp
            if not file_record.local_filename or not os.path.exists(file_record.local_filename):
                raise HTTPException(status_code=404, detail="Original file not found on disk")

            file_path = file_record.local_filename

        elif version == "processed":
            # Look for processed file in /workdir/processed/
            workdir = settings.workdir
            processed_dir = os.path.join(workdir, "processed")

            # Try to find the processed file (same hash or UUID-based naming)
            base_filename = os.path.splitext(file_record.original_filename)[0]
            potential_paths = [
                os.path.join(processed_dir, f"{file_record.filehash}.pdf"),
                os.path.join(processed_dir, f"{base_filename}_processed.pdf"),
                os.path.join(processed_dir, file_record.original_filename),
            ]

            file_path = None
            for path in potential_paths:
                if os.path.exists(path):
                    file_path = path
                    break

            if not file_path:
                raise HTTPException(status_code=404, detail="Processed file not found")
        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid version parameter. Use 'original' or 'processed'",
            )

        # Return the file with attachment disposition to trigger download
        return FileResponse(
            path=file_path,
            media_type=file_record.mime_type or "application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{file_record.original_filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error downloading file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")


@router.post("/ui-upload")
@require_login
async def ui_upload(request: Request, file: UploadFile = File(...)):
    """Endpoint to accept a user-uploaded file and enqueue it for processing."""
    workdir = settings.workdir

    # Early size check: reject before reading the body if Content-Length is known
    max_size = settings.max_upload_size
    content_length_header = request.headers.get("content-length")
    if content_length_header is not None:
        try:
            declared_size = int(content_length_header)
            if declared_size > max_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large: declared size {declared_size} bytes exceeds maximum "
                    f"{max_size} bytes. See SECURITY_AUDIT.md for configuration details.",
                )
        except ValueError:
            pass  # Malformed header; proceed and check actual size after reading

    # Extract just the filename without any path components to prevent path traversal
    # First, use basename to remove any directory components
    base_filename = os.path.basename(file.filename)
    # Then sanitize the filename to remove special characters and ensure filesystem compatibility
    safe_filename = sanitize_filename(base_filename)

    # Generate a unique filename with UUID to prevent overwriting and filename conflicts
    unique_id = str(uuid.uuid4())
    # Keep the original extension if present
    if "." in safe_filename:
        file_extension = safe_filename.rsplit(".", 1)[1]
        target_filename = f"{unique_id}.{file_extension}"
    else:
        target_filename = unique_id

    # Store both the safe original name and the unique name
    target_path = os.path.join(workdir, target_filename)

    # Read file in chunks to avoid loading the entire body into memory at once,
    # enforcing the size limit during the read so memory usage stays bounded.
    try:
        written_size = 0
        with open(target_path, "wb") as f:
            chunk_size = 65536  # 64 KB chunks
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                written_size += len(chunk)
                if written_size > max_size:
                    # Exceeded limit mid-stream; clean up and reject
                    f.close()
                    os.remove(target_path)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large: exceeded {max_size} bytes during upload. "
                        f"See SECURITY_AUDIT.md for configuration details.",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(target_path):
            os.remove(target_path)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # Log the mapping between original and safe filename
    logger.info(f"Saved uploaded file '{safe_filename}' as '{target_filename}'")
    file_size = written_size

    # Same set of allowed file types as in the IMAP task
    ALLOWED_MIME_TYPES = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/plain",
        "text/csv",
        "application/rtf",
        "text/rtf",
    }

    # Image MIME types that need conversion
    IMAGE_MIME_TYPES = {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/gif",
        "image/bmp",
        "image/tiff",
        "image/webp",
        "image/svg+xml",
    }

    # Determine if the file is a PDF or needs conversion
    mime_type, _ = mimetypes.guess_type(target_path)
    file_ext = os.path.splitext(target_path)[1].lower()

    # Check if it's a PDF by extension or MIME type
    is_pdf = file_ext == ".pdf" or mime_type == "application/pdf"

    # Check if file splitting is needed (only for PDFs)
    from app.utils.file_splitting import should_split_file

    should_split = is_pdf and should_split_file(target_path, settings.max_single_file_size)

    if should_split:
        # File needs to be split before processing
        from app.utils.file_splitting import split_pdf_by_size

        try:
            logger.info(
                f"File {target_path} ({file_size} bytes) exceeds max_single_file_size "
                f"({settings.max_single_file_size} bytes). Splitting..."
            )
            split_files = split_pdf_by_size(target_path, settings.max_single_file_size)
            logger.info(f"Split {target_path} into {len(split_files)} parts")

            # Queue each split file for processing
            task_ids = []
            for split_file in split_files:
                split_filename = os.path.basename(split_file)
                task = process_document.delay(split_file, original_filename=split_filename)
                task_ids.append(task.id)
                logger.info(f"Enqueued split PDF part for processing: {split_file}")

            # Remove the original file after successful splitting
            os.remove(target_path)

            return {
                "task_ids": task_ids,
                "status": "queued",
                "original_filename": safe_filename,
                "stored_filename": target_filename,
                "split_into_parts": len(split_files),
                "message": f"File split into {len(split_files)} parts for processing",
            }
        except Exception as e:
            logger.exception(f"Failed to split file {target_path}: {str(e)}")
            # Fall back to processing the whole file
            logger.warning(f"Falling back to processing whole file due to split error: {str(e)}")
            should_split = False

    if is_pdf and not should_split:
        # If it's a PDF, process directly
        task = process_document.delay(target_path, original_filename=safe_filename)
        logger.info(f"Enqueued PDF for processing: {target_path}")
    elif mime_type in IMAGE_MIME_TYPES or any(
        file_ext.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg"]
    ):
        # If it's an image, convert to PDF first
        task = convert_to_pdf.delay(target_path, original_filename=safe_filename)
        logger.info(f"Enqueued image for PDF conversion: {target_path}")
    elif mime_type in ALLOWED_MIME_TYPES or any(
        file_ext.endswith(ext)
        for ext in [
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".odt",
            ".ods",
            ".odp",
            ".rtf",
            ".txt",
            ".csv",
        ]
    ):
        # If it's an office document, convert to PDF first
        task = convert_to_pdf.delay(target_path, original_filename=safe_filename)
        logger.info(f"Enqueued office document for PDF conversion: {target_path}")
    else:
        # For any other file type, attempt conversion but log a warning
        logger.warning(f"Unsupported MIME type {mime_type} for {target_path}, attempting conversion")
        task = convert_to_pdf.delay(target_path, original_filename=safe_filename)

    return {
        "task_id": task.id,
        "status": "queued",
        "original_filename": safe_filename,
        "stored_filename": target_filename,
    }
