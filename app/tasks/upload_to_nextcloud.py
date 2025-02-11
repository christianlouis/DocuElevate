#!/usr/bin/env python3

from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.celery_app import celery

@celery.task(base=BaseTaskWithRetry)
def upload_to_nextcloud(file_path: str):
    """Simulate uploading a file to Nextcloud."""
    print(f"[INFO] Simulating upload to Nextcloud: {file_path}")
    return {"status": "Completed", "file": file_path}
