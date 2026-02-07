"""
File management views for displaying and managing files.
"""
from fastapi import Request, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.views.base import APIRouter, templates, require_login, get_db, logger
from app.utils.file_status import get_files_processing_status

router = APIRouter()

@router.get("/files")
@require_login
def files_page(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    search: Optional[str] = Query(None),
    mime_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None)
):
    """
    Return the 'files.html' template with server-side pagination, sorting, and filtering
    """
    try:
        # Import the model here to avoid circular imports
        from app.models import FileRecord, ProcessingLog
        from sqlalchemy import desc, asc, or_
        
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
                subq = db.query(ProcessingLog.file_id).filter(
                    ProcessingLog.status == "in_progress"
                ).distinct()
                query = query.filter(FileRecord.id.in_(subq))
            elif status == "failed":
                # Files with failure logs
                subq = db.query(ProcessingLog.file_id).filter(
                    ProcessingLog.status == "failure"
                ).distinct()
                query = query.filter(FileRecord.id.in_(subq))
            elif status == "completed":
                # Files with success logs but no failures or in_progress
                success_files = db.query(ProcessingLog.file_id).filter(
                    ProcessingLog.status == "success"
                ).distinct().subquery()
                
                failed_files = db.query(ProcessingLog.file_id).filter(
                    or_(ProcessingLog.status == "failure", ProcessingLog.status == "in_progress")
                ).distinct().subquery()
                
                query = query.filter(
                    FileRecord.id.in_(db.query(success_files.c.file_id))
                ).filter(
                    ~FileRecord.id.in_(db.query(failed_files.c.file_id))
                )
        
        # Get total count before pagination
        total_items = query.count()
        
        # Apply sorting
        sort_column = {
            "id": FileRecord.id,
            "original_filename": FileRecord.original_filename,
            "file_size": FileRecord.file_size,
            "mime_type": FileRecord.mime_type,
            "created_at": FileRecord.created_at
        }.get(sort_by, FileRecord.created_at)
        
        if sort_order == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))
        
        # Apply pagination
        offset = (page - 1) * per_page
        files = query.offset(offset).limit(per_page).all()
        
        # Get processing status for all files efficiently (avoids N+1)
        file_ids = [f.id for f in files]
        statuses = get_files_processing_status(db, file_ids)
        
        # Add status to each file
        files_with_status = []
        for file in files:
            file.processing_status = statuses.get(file.id, {}).get("status", "pending")
            files_with_status.append(file)
        
        # Calculate pagination info
        total_pages = (total_items + per_page - 1) // per_page
        
        # Get unique MIME types for filter dropdown
        mime_types = db.query(FileRecord.mime_type).distinct().filter(
            FileRecord.mime_type.isnot(None)
        ).all()
        mime_types = [mt[0] for mt in mime_types if mt[0]]
        
        # Debug output
        logger.info(f"Retrieved {len(files_with_status)} files from database (page {page}/{total_pages})")
        
        return templates.TemplateResponse("files.html", {
            "request": request,
            "files": files_with_status,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_items": total_items,
                "total_pages": total_pages
            },
            "sort_by": sort_by,
            "sort_order": sort_order,
            "search": search or "",
            "mime_type": mime_type or "",
            "status": status or "",
            "mime_types": mime_types
        })
    except Exception as e:
        # Log any errors
        logger.error(f"Error retrieving files: {str(e)}")
        # Return error message to template
        return templates.TemplateResponse("files.html", {
            "request": request,
            "files": [],
            "pagination": {
                "page": 1,
                "per_page": per_page,
                "total_items": 0,
                "total_pages": 0
            },
            "error": str(e)
        })


@router.get("/files/{file_id}/detail")
@require_login
def file_detail_page(request: Request, file_id: int, db: Session = Depends(get_db)):
    """
    Return the file detail page showing processing history and file information
    """
    try:
        from app.models import FileRecord, ProcessingLog
        import os
        
        # Find the file record
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        
        if not file_record:
            return templates.TemplateResponse("file_detail.html", {
                "request": request,
                "error": f"File with ID {file_id} not found"
            })
        
        # Get processing logs
        logs = db.query(ProcessingLog).filter(
            ProcessingLog.file_id == file_id
        ).order_by(ProcessingLog.timestamp.asc()).all()
        
        # Check if file exists on disk
        file_exists = os.path.exists(file_record.local_filename) if file_record.local_filename else False
        
        return templates.TemplateResponse("file_detail.html", {
            "request": request,
            "file": file_record,
            "logs": logs,
            "file_exists": file_exists
        })
    except Exception as e:
        logger.error(f"Error retrieving file details: {str(e)}")
        return templates.TemplateResponse("file_detail.html", {
            "request": request,
            "error": str(e)
        })
