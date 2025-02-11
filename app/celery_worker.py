#!/usr/bin/env python3

from app.config import settings

# Import the shared Celery instance
from app.celery_app import celery

# Ensure tasks are loaded
from app import tasks  # <— This imports app/tasks.py so Celery can register tasks

# **Ensure all tasks are imported before Celery starts**
from app.tasks.upload_to_s3 import upload_to_s3
from app.tasks.process_with_textract import process_with_textract
from app.tasks.refine_text_with_gpt import refine_text_with_gpt
from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt
from app.tasks.embed_metadata_into_pdf import embed_metadata_into_pdf

# Import new send tasks
from app.tasks.upload_to_dropbox import upload_to_dropbox
from app.tasks.upload_to_paperless import upload_to_paperless
from app.tasks.upload_to_nextcloud import upload_to_nextcloud

celery.conf.task_routes = {
    "app.tasks.*": {"queue": "default"},
}

@celery.task
def test_task():
    return "Celery is working!"
