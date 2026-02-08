"""
File-related API endpoints
"""

import logging
import mimetypes
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session

from app.api.common import get_db
from app.auth import require_login
from app.config import settings
from app.models import FileRecord, ProcessingLog
from app.tasks.convert_to_pdf import convert_to_pdf
from app.tasks.process_document import process_document
from app.utils.file_status import get_files_processing_status

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/files")
@require_login
def list_files_api(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
    sort_by: str = Query(
        "created_at", description="Sort field: id, original_filename, file_size, mime_type, created_at, status"
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
    # Start with base query
    query = db.query(FileRecord)

    # Apply search filter
    if search:
        query = query.filter(FileRecord.original_filename.ilike(f"%{search}%"))

    # Apply MIME type filter
    if mime_type:
        query = query.filter(FileRecord.mime_type == mime_type)

    # Apply status filter (before pagination for correct counts)
    if status:
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
            success_files = (
                db.query(ProcessingLog.file_id).filter(ProcessingLog.status == "success").distinct().subquery()
            )

            failed_files = (
                db.query(ProcessingLog.file_id)
                .filter(or_(ProcessingLog.status == "failure", ProcessingLog.status == "in_progress"))
                .distinct()
                .subquery()
            )

            query = query.filter(FileRecord.id.in_(db.query(success_files.c.file_id))).filter(
                ~FileRecord.id.in_(db.query(failed_files.c.file_id))
            )

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
                    f.id, {"status": "pending", "last_step": None, "has_errors": False, "total_steps": 0}
                ),
            }
        )

    # Calculate pagination info
    total_pages = (total_items + per_page - 1) // per_page

    return {
        "files": result,
        "pagination": {"page": page, "per_page": per_page, "total_items": total_items, "total_pages": total_pages},
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
def get_file_details(request: Request, file_id: int, db: Session = Depends(get_db)):
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
    files_on_disk = {"original": os.path.exists(file_record.local_filename) if file_record.local_filename else False}

    return {
        "file": {
            "id": file_record.id,
            "filehash": file_record.filehash,
            "original_filename": file_record.original_filename,
            "local_filename": file_record.local_filename,
            "file_size": file_record.file_size,
            "mime_type": file_record.mime_type,
            "created_at": file_record.created_at.isoformat() if file_record.created_at else None,
        },
        "processing_status": processing_status,
        "logs": log_list,
        "files_on_disk": files_on_disk,
    }


@router.delete("/files/{file_id}")
@require_login
def delete_file_record(request: Request, file_id: int, db: Session = Depends(get_db)):
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

        return {"status": "success", "message": f"File record {file_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Error deleting file record {file_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting file record: {str(e)}")


@router.post("/files/bulk-delete")
@require_login
def bulk_delete_files(request: Request, file_ids: List[int], db: Session = Depends(get_db)):
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
def bulk_reprocess_files(request: Request, file_ids: List[int], db: Session = Depends(get_db)):
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

                # Queue the file for processing
                task = process_document.delay(file_record.local_filename)
                task_ids.append(task.id)
                processed_files.append(
                    {"file_id": file_record.id, "filename": file_record.original_filename, "task_id": task.id}
                )

                logger.info(
                    f"Reprocessing file: ID={file_record.id}, "
                    f"Filename={file_record.original_filename}, TaskID={task.id}"
                )

            except Exception as e:
                logger.exception(f"Error reprocessing file {file_record.id}: {str(e)}")
                errors.append({"file_id": file_record.id, "filename": file_record.original_filename, "error": str(e)})

        return {
            "status": "success" if processed_files else "error",
            "message": f"Successfully queued {len(processed_files)} files for reprocessing",
            "processed_files": processed_files,
            "errors": errors if errors else None,
            "task_ids": task_ids,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error bulk reprocessing files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error bulk reprocessing files: {str(e)}")


@router.post("/files/{file_id}/reprocess")
@require_login
def reprocess_single_file(request: Request, file_id: int, db: Session = Depends(get_db)):
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
            raise HTTPException(status_code=400, detail="Local file not found on disk. Cannot reprocess.")

        # Queue the file for processing
        task = process_document.delay(file_record.local_filename, original_filename=file_record.original_filename)

        logger.info(
            f"Reprocessing file: ID={file_record.id}, " f"Filename={file_record.original_filename}, TaskID={task.id}"
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


@router.post("/files/{file_id}/retry-subtask")
@require_login
def retry_subtask(
    request: Request,
    file_id: int,
    subtask_name: str = Query(..., description="Name of the upload subtask to retry (e.g., 'upload_to_dropbox')"),
    db: Session = Depends(get_db),
):
    """
    Retry a specific failed upload subtask for a file.

    Args:
        file_id: ID of the file
        subtask_name: Name of the upload task (e.g., upload_to_dropbox, upload_to_s3)

    Returns:
        Task ID and status information
    """
    try:
        # Find the file record
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()

        if not file_record:
            raise HTTPException(status_code=404, detail=f"File with ID {file_id} not found")

        # Map subtask names to their corresponding Celery tasks
        from app.tasks.upload_to_dropbox import upload_to_dropbox
        from app.tasks.upload_to_nextcloud import upload_to_nextcloud
        from app.tasks.upload_to_paperless import upload_to_paperless
        from app.tasks.upload_to_google_drive import upload_to_google_drive
        from app.tasks.upload_to_onedrive import upload_to_onedrive
        from app.tasks.upload_to_s3 import upload_to_s3
        from app.tasks.upload_to_webdav import upload_to_webdav
        from app.tasks.upload_to_ftp import upload_to_ftp
        from app.tasks.upload_to_sftp import upload_to_sftp
        from app.tasks.upload_to_email import upload_to_email

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
            raise HTTPException(
                status_code=400,
                detail=f"Invalid subtask name: {subtask_name}. Must be one of: {', '.join(task_map.keys())}",
            )

        # Check for processed file (upload tasks work with processed files)
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
        for path in potential_paths:
            if os.path.exists(path):
                file_path = path
                break

        if not file_path:
            raise HTTPException(status_code=400, detail="Processed file not found. Cannot retry upload.")

        # Queue the specific upload task
        upload_task = task_map[subtask_name]
        task = upload_task.delay(file_path, file_id)

        logger.info(f"Retrying upload subtask: FileID={file_record.id}, " f"Subtask={subtask_name}, TaskID={task.id}")

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
    version: str = Query("original", description="original or processed"),
    db: Session = Depends(get_db),
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
            raise HTTPException(status_code=400, detail="Invalid version parameter. Use 'original' or 'processed'")

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
    version: str = Query("original", description="original or processed"),
    db: Session = Depends(get_db),
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
            raise HTTPException(status_code=400, detail="Invalid version parameter. Use 'original' or 'processed'")

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

    # Extract just the filename without any path components to prevent path traversal
    safe_filename = os.path.basename(file.filename)

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

    try:
        with open(target_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # Log the mapping between original and safe filename
    logger.info(f"Saved uploaded file '{safe_filename}' as '{target_filename}'")

    # Check file size
    file_size = os.path.getsize(target_path)
    max_size = 500 * 1024 * 1024  # 500MB
    if file_size > max_size:
        # Remove the file if it's too large
        os.remove(target_path)
        raise HTTPException(status_code=413, detail=f"File too large: {file_size} bytes (max {max_size} bytes)")

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

    if is_pdf:
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
        for ext in [".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp", ".rtf", ".txt", ".csv"]
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
