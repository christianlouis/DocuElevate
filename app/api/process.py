"""
Document processing API endpoints
"""
from fastapi import APIRouter, HTTPException
import logging
import os

from app.auth import require_login
from app.config import settings
from app.api.common import resolve_file_path
from app.tasks.process_document import process_document
from app.tasks.upload_to_dropbox import upload_to_dropbox
from app.tasks.upload_to_paperless import upload_to_paperless
from app.tasks.upload_to_nextcloud import upload_to_nextcloud
from app.tasks.upload_to_google_drive import upload_to_google_drive
from app.tasks.upload_to_onedrive import upload_to_onedrive
from app.tasks.send_to_all import send_to_all_destinations

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/process/")
@require_login
def process(file_path: str):
    """API Endpoint to start document processing."""
    try:
        file_path = resolve_file_path(file_path)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid file path: {str(e)}"
        )

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=400, detail=f"File {file_path} not found."
        )

    task = process_document.delay(file_path)
    return {"task_id": task.id, "status": "queued"}

@router.post("/send_to_dropbox/")
@require_login
def send_to_dropbox_endpoint(file_path: str):
    """Send a document to Dropbox."""
    try:
        file_path = resolve_file_path(file_path, 'processed')
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid file path: {str(e)}"
        )
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=400, detail=f"File {file_path} not found."
        )
    task = upload_to_dropbox.delay(file_path)
    return {"task_id": task.id, "status": "queued"}

@router.post("/send_to_paperless/")
@require_login
def send_to_paperless_endpoint(file_path: str):
    """Send a document to Paperless-ngx."""
    try:
        file_path = resolve_file_path(file_path, 'processed')
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid file path: {str(e)}"
        )
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=400, detail=f"File {file_path} not found."
        )
    task = upload_to_paperless.delay(file_path)
    return {"task_id": task.id, "status": "queued"}

@router.post("/send_to_nextcloud/")
@require_login
def send_to_nextcloud_endpoint(file_path: str):
    """Send a document to NextCloud."""
    try:
        file_path = resolve_file_path(file_path, 'processed')
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid file path: {str(e)}"
        )
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=400, detail=f"File {file_path} not found."
        )
    task = upload_to_nextcloud.delay(file_path)
    return {"task_id": task.id, "status": "queued"}

@router.post("/send_to_google_drive/")
@require_login
def send_to_google_drive_endpoint(file_path: str):
    """Send a document to Google Drive."""
    try:
        file_path = resolve_file_path(file_path, 'processed')
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid file path: {str(e)}"
        )
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=400, detail=f"File {file_path} not found."
        )
    task = upload_to_google_drive.delay(file_path)
    return {"task_id": task.id, "status": "queued"}

@router.post("/send_to_onedrive/")
@require_login
def send_to_onedrive_endpoint(file_path: str):
    """Send a document to OneDrive."""
    try:
        file_path = resolve_file_path(file_path, 'processed')
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid file path: {str(e)}"
        )
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=400, detail=f"File {file_path} not found."
        )
    task = upload_to_onedrive.delay(file_path)
    return {"task_id": task.id, "status": "queued"}

@router.post("/send_to_all_destinations/")
@require_login
def send_to_all_destinations_endpoint(file_path: str):
    """Call the aggregator task that sends this file to all configured destinations."""
    try:
        file_path = resolve_file_path(file_path, 'processed')
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid file path: {str(e)}"
        )

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=400, detail=f"File {file_path} not found."
        )

    task = send_to_all_destinations.delay(file_path)
    return {"task_id": task.id, "status": "queued", "file_path": file_path}

@router.post("/processall")
@require_login
def process_all_pdfs_in_workdir():
    """Finds all .pdf files in <workdir> and enqueues them for processing."""
    target_dir = settings.workdir
    if not os.path.exists(target_dir):
        raise HTTPException(
            status_code=400, detail=f"Directory {target_dir} does not exist."
        )

    pdf_files = []
    for filename in os.listdir(target_dir):
        if filename.lower().endswith(".pdf"):
            pdf_files.append(filename)

    if not pdf_files:
        return {"message": "No PDF files found in that directory."}

    task_ids = []
    for pdf in pdf_files:
        file_path = os.path.join(target_dir, pdf)
        task = process_document.delay(file_path)
        task_ids.append(task.id)

    return {
        "message": f"Enqueued {len(pdf_files)} PDFs to upload_to_s3",
        "pdf_files": pdf_files,
        "task_ids": task_ids
    }
