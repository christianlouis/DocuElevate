#!/usr/bin/env python3

from app.config import settings

# Import the shared Celery instance
from app.celery_app import celery

# Ensure tasks are loaded
from app import tasks  # <— This imports app/tasks.py so Celery can register tasks

# **Ensure all tasks are imported before Celery starts**
from app.tasks.process_document import process_document  # Updated import
from app.tasks.process_with_textract import process_with_textract
from app.tasks.refine_text_with_gpt import refine_text_with_gpt
from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt
from app.tasks.embed_metadata_into_pdf import embed_metadata_into_pdf
from app.tasks.convert_to_pdf import convert_to_pdf

# Import new send tasks
from app.tasks.upload_to_dropbox import upload_to_dropbox
from app.tasks.upload_to_paperless import upload_to_paperless
from app.tasks.upload_to_nextcloud import upload_to_nextcloud
from app.tasks.upload_to_google_drive import upload_to_google_drive
from app.tasks.upload_to_webdav import upload_to_webdav
from app.tasks.upload_to_s3 import upload_to_s3
from app.tasks.upload_to_onedrive import upload_to_onedrive
from app.tasks.upload_to_ftp import upload_to_ftp
from app.tasks.upload_to_sftp import upload_to_sftp 
from app.tasks.upload_to_email import upload_to_email

from app.tasks.imap_tasks import pull_all_inboxes
from app.tasks.send_to_all import send_to_all_destinations

celery.conf.task_routes = {
    "app.tasks.*": {"queue": "default"},
}

@celery.task
def test_task():
    return "Celery is working!"

# If you want Celery Beat to run the poll task every minute, add:
from celery.schedules import crontab

celery.conf.beat_schedule = {
    "poll-inboxes-every-minute": {
        "task": "app.tasks.imap_tasks.pull_all_inboxes",
        "schedule": crontab(minute="*/1"),  # every 1 minute
    },
}