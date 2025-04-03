#!/usr/bin/env python3

from app.config import settings

# Import the shared Celery instance
from app.celery_app import celery

# Ensure tasks are loaded
from app import tasks  # <— This imports app/tasks.py so Celery can register tasks

# **Ensure all tasks are imported before Celery starts**
from app.tasks.process_document import process_document
from app.tasks.process_with_azure_document_intelligence import process_with_azure_document_intelligence
from app.tasks.rotate_pdf_pages import rotate_pdf_pages
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
from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

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
        "options": {"expires": 55},  # Ensure tasks don't pile up
    } if (settings.imap1_host or settings.imap2_host) else None,
    # Add Uptime Kuma ping task if configured
    "ping-uptime-kuma": {
        "task": "app.tasks.uptime_kuma_tasks.ping_uptime_kuma",
        "schedule": crontab(minute=f"*/{settings.uptime_kuma_ping_interval}"),
        "options": {"expires": 55},  # Ensure tasks don't pile up
    } if settings.uptime_kuma_url else None,
}

# Remove None entries from beat_schedule
celery.conf.beat_schedule = {k: v for k, v in celery.conf.beat_schedule.items() if v is not None}