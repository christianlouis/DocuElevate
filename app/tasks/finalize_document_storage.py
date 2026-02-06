#!/usr/bin/env python3

import logging
import os
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
# Import the shared Celery instance
from app.celery_app import celery

# 1) Import the aggregator task
from app.tasks.send_to_all import send_to_all_destinations
from app.utils import log_task_progress
from app.database import SessionLocal
from app.models import FileRecord

logger = logging.getLogger(__name__)


@celery.task(base=BaseTaskWithRetry, bind=True)
def finalize_document_storage(self, original_file: str, processed_file: str, metadata: dict, file_id: int = None):
    """
    Final storage step after embedding metadata.
    We will now call 'send_to_all_destinations' to push the final PDF to Dropbox/Nextcloud/Paperless.
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Finalizing document storage for {processed_file}")
    log_task_progress(task_id, "finalize_document_storage", "in_progress", f"Finalizing: {os.path.basename(processed_file)}", file_id=file_id)
    
    # Get file_id from database if not provided (fallback only, prefer passing file_id explicitly)
    if file_id is None:
        with SessionLocal() as db:
            # Only as a last resort, try to find by exact match on local_filename
            # This should not be needed if file_id is passed correctly through the chain
            tmp_path = os.path.join(settings.workdir, "tmp", os.path.basename(original_file))
            file_record = db.query(FileRecord).filter(
                FileRecord.local_filename == tmp_path
            ).first()
            if file_record:
                file_id = file_record.id

    # 2) Enqueue uploads to all destinations (Dropbox, Nextcloud, Paperless)
    logger.info(f"[{task_id}] Queueing uploads to all destinations")
    log_task_progress(task_id, "finalize_document_storage", "success", "Queuing uploads to destinations", file_id=file_id)
    send_to_all_destinations.delay(processed_file, True, file_id)

    return {
        "status": "Completed",
        "file": processed_file
    }
