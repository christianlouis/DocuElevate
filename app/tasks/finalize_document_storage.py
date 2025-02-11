#!/usr/bin/env python3

from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry

# Import the shared Celery instance
from app.celery_app import celery

@celery.task(base=BaseTaskWithRetry)
def finalize_document_storage(original_file: str, processed_file: str, metadata: dict):
    """Final storage step after embedding metadata."""
    print(f"[INFO] Finalizing document storage for {processed_file}")
    return {"status": "Completed", "file": processed_file}

