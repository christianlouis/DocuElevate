"""
Document processing API endpoints
"""

import logging
import os

from fastapi import APIRouter, HTTPException

from app.api.common import resolve_file_path
from app.auth import require_login
from app.config import settings
from app.tasks.process_document import process_document
from app.tasks.send_to_all import send_to_all_destinations
from app.tasks.upload_to_dropbox import upload_to_dropbox
from app.tasks.upload_to_google_drive import upload_to_google_drive
from app.tasks.upload_to_nextcloud import upload_to_nextcloud
from app.tasks.upload_to_onedrive import upload_to_onedrive
from app.tasks.upload_to_paperless import upload_to_paperless

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/process/")
@require_login
def process(file_path: str):
    """API Endpoint to start document processing."""
    file_path = resolve_file_path(file_path)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"File {file_path} not found.")

    task = process_document.delay(file_path)
    return {"task_id": task.id, "status": "queued"}


@router.post("/send_to_dropbox/")
@require_login
def send_to_dropbox_endpoint(file_path: str):
    """Send a document to Dropbox."""
    file_path = resolve_file_path(file_path, "processed")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"File {file_path} not found.")
    task = upload_to_dropbox.delay(file_path)
    return {"task_id": task.id, "status": "queued"}


@router.post("/send_to_paperless/")
@require_login
def send_to_paperless_endpoint(file_path: str):
    """Send a document to Paperless-ngx."""
    file_path = resolve_file_path(file_path, "processed")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"File {file_path} not found.")
    task = upload_to_paperless.delay(file_path)
    return {"task_id": task.id, "status": "queued"}


@router.post("/send_to_nextcloud/")
@require_login
def send_to_nextcloud_endpoint(file_path: str):
    """Send a document to NextCloud."""
    file_path = resolve_file_path(file_path, "processed")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"File {file_path} not found.")
    task = upload_to_nextcloud.delay(file_path)
    return {"task_id": task.id, "status": "queued"}


@router.post("/send_to_google_drive/")
@require_login
def send_to_google_drive_endpoint(file_path: str):
    """Send a document to Google Drive."""
    file_path = resolve_file_path(file_path, "processed")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"File {file_path} not found.")
    task = upload_to_google_drive.delay(file_path)
    return {"task_id": task.id, "status": "queued"}


@router.post("/send_to_onedrive/")
@require_login
def send_to_onedrive_endpoint(file_path: str):
    """Send a document to OneDrive."""
    file_path = resolve_file_path(file_path, "processed")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"File {file_path} not found.")
    task = upload_to_onedrive.delay(file_path)
    return {"task_id": task.id, "status": "queued"}


@router.post("/send_to_all_destinations/")
@require_login
def send_to_all_destinations_endpoint(file_path: str):
    """Call the aggregator task that sends this file to all configured destinations."""
    file_path = resolve_file_path(file_path, "processed")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"File {file_path} not found.")

    task = send_to_all_destinations.delay(file_path)
    return {"task_id": task.id, "status": "queued", "file_path": file_path}


@router.post("/processall")
@require_login
def process_all_pdfs_in_workdir():
    """
    Finds all .pdf files in <workdir> and enqueues them for processing.

    For large batches (>processall_throttle_threshold files), tasks are staggered
    to avoid overwhelming downstream APIs.
    """
    target_dir = settings.workdir
    if not os.path.exists(target_dir):
        raise HTTPException(status_code=400, detail=f"Directory {target_dir} does not exist.")

    pdf_files = []
    for filename in os.listdir(target_dir):
        if filename.lower().endswith(".pdf"):
            pdf_files.append(filename)

    if not pdf_files:
        return {"message": "No PDF files found in that directory."}

    task_ids = []
    num_files = len(pdf_files)

    # Apply throttling if we have more files than the threshold
    apply_throttle = num_files > settings.processall_throttle_threshold

    if apply_throttle:
        logger.info(
            f"Processing {num_files} files with throttling "
            f"(threshold: {settings.processall_throttle_threshold}, "
            f"delay: {settings.processall_throttle_delay}s per file)"
        )

    for index, pdf in enumerate(pdf_files):
        file_path = os.path.join(target_dir, pdf)

        if apply_throttle:
            # Stagger task submission with countdown
            # First file starts immediately (countdown=0)
            # Each subsequent file has an increasing delay
            countdown = index * settings.processall_throttle_delay
            task = process_document.apply_async(args=[file_path], countdown=countdown)
            logger.debug(f"Scheduled {pdf} with {countdown}s delay")
        else:
            # No throttling - enqueue immediately
            task = process_document.delay(file_path)

        task_ids.append(task.id)

    message = f"Enqueued {num_files} PDFs for processing"
    if apply_throttle:
        total_time = (num_files - 1) * settings.processall_throttle_delay
        message += f" (throttled over {total_time} seconds)"

    return {"message": message, "pdf_files": pdf_files, "task_ids": task_ids, "throttled": apply_throttle}
