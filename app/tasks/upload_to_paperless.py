#!/usr/bin/env python3

from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.celery_app import celery

@celery.task(base=BaseTaskWithRetry)
def upload_to_paperless(file_path: str):
    """Simulate uploading a file to Paperless."""
    print(f"[INFO] Simulating upload to Paperless: {file_path}")
    return {"status": "Completed", "file": file_path}
