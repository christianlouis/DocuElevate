#!/usr/bin/env python3

from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
# Import the shared Celery instance
from app.celery_app import celery

# 1) Import the aggregator task
from app.tasks.send_to_all import send_to_all_destinations


@celery.task(base=BaseTaskWithRetry)
def finalize_document_storage(original_file: str, processed_file: str, metadata: dict):
    """
    Final storage step after embedding metadata.
    We will now call 'send_to_all_destinations' to push the final PDF to Dropbox/Nextcloud/Paperless.
    """
    print(f"[INFO] Finalizing document storage for {processed_file}")

    # 2) Enqueue uploads to all destinations (Dropbox, Nextcloud, Paperless)
    send_to_all_destinations.delay(processed_file)

    return {
        "status": "Completed",
        "file": processed_file
    }
