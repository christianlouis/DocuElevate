#!/usr/bin/env python3

import logging
import os
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
# Import the shared Celery instance
from app.celery_app import celery

# Import the aggregator task and validator
from app.tasks.send_to_all import send_to_all_destinations, get_configured_services_from_validator

# Import notification utility
from app.utils.notification import notify_file_processed

# Import database and logging utils from main
from app.utils import log_task_progress
from app.database import SessionLocal
from app.models import FileRecord

logger = logging.getLogger(__name__)


@celery.task(base=BaseTaskWithRetry, bind=True)
def finalize_document_storage(self, original_file: str, processed_file: str, metadata: dict, file_id: int = None):
    """
    Final storage step after embedding metadata.
    We will now call 'send_to_all_destinations' to push the final PDF to Dropbox/Nextcloud/Paperless.
    After uploading, send a notification about the processed file.
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Finalizing document storage for {processed_file}")
    
    # 1. Update Database Status (From Main)
    log_task_progress(task_id, "finalize_document_storage", "in_progress", f"Finalizing: {os.path.basename(processed_file)}", file_id=file_id)
    
    # Get file_id from database if not provided (fallback logic from Main)
    if file_id is None:
        with SessionLocal() as db:
            # Only as a last resort, try to find by exact match on local_filename
            tmp_path = os.path.join(settings.workdir, "tmp", os.path.basename(original_file))
            file_record = db.query(FileRecord).filter(
                FileRecord.local_filename == tmp_path
            ).first()
            if file_record:
                file_id = file_record.id

    # 2. Determine Configured Destinations (From Copilot)
    # This is needed for the notification message later
    configured_destinations = []
    try:
        configured_services = get_configured_services_from_validator()
        # Get list of service names that are configured
        for service_name, is_configured in configured_services.items():
            if is_configured:
                # Format service names for display
                display_name = service_name.replace('_', ' ').title()
                configured_destinations.append(display_name)
    except Exception as e:
        logger.warning(f"[WARNING] Could not determine configured destinations: {e}")
        configured_destinations = ["configured destinations"]

    # 3. Queue Uploads (Merged)
    # Uses Main branch signature to ensure file_id is passed, but keeps logic structure
    logger.info(f"[{task_id}] Queueing uploads to all destinations")
    log_task_progress(task_id, "finalize_document_storage", "success", "Queuing uploads to destinations", file_id=file_id)
    
    # Note: send_to_all_destinations is asynchronous and queues upload tasks
    # We pass 'True' (delete_after) and 'file_id' as per Main branch requirements
    send_to_all_destinations.delay(processed_file, True, file_id)

    # 4. Send Notification (From Copilot)
    # Note: This notification is sent after processing is complete but while uploads
    # are being queued.
    try:
        # Get file information
        file_size = os.path.getsize(processed_file) if os.path.exists(processed_file) else 0
        filename = os.path.basename(processed_file)
        
        notify_file_processed(
            filename=filename,
            file_size=file_size,
            metadata=metadata,
            destinations=configured_destinations
        )
    except Exception as e:
        logger.warning(f"[WARNING] Failed to send file processed notification: {e}")

    return {
        "status": "Completed",
        "file": processed_file
    }