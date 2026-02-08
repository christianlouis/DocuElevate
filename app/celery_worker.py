#!/usr/bin/env python3

from celery.schedules import crontab

# Ensure tasks are loaded
from app import tasks  # noqa: F401 - Imports app/tasks.py so Celery can register tasks

# Import the shared Celery instance
from app.celery_app import celery
from app.config import settings
from app.tasks.check_credentials import check_credentials
from app.tasks.convert_to_pdf import convert_to_pdf  # noqa: F401
from app.tasks.embed_metadata_into_pdf import embed_metadata_into_pdf  # noqa: F401
from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt  # noqa: F401
from app.tasks.imap_tasks import pull_all_inboxes  # noqa: F401

# **Ensure all tasks are imported before Celery starts**
from app.tasks.process_document import process_document  # noqa: F401
from app.tasks.process_with_azure_document_intelligence import process_with_azure_document_intelligence  # noqa: F401
from app.tasks.refine_text_with_gpt import refine_text_with_gpt  # noqa: F401
from app.tasks.rotate_pdf_pages import rotate_pdf_pages  # noqa: F401
from app.tasks.send_to_all import send_to_all_destinations  # noqa: F401

# Import new send tasks
from app.tasks.upload_to_dropbox import upload_to_dropbox  # noqa: F401
from app.tasks.upload_to_email import upload_to_email  # noqa: F401
from app.tasks.upload_to_ftp import upload_to_ftp  # noqa: F401
from app.tasks.upload_to_google_drive import upload_to_google_drive  # noqa: F401
from app.tasks.upload_to_nextcloud import upload_to_nextcloud  # noqa: F401
from app.tasks.upload_to_onedrive import upload_to_onedrive  # noqa: F401
from app.tasks.upload_to_paperless import upload_to_paperless  # noqa: F401
from app.tasks.upload_to_s3 import upload_to_s3  # noqa: F401
from app.tasks.upload_to_sftp import upload_to_sftp  # noqa: F401
from app.tasks.upload_to_webdav import upload_to_webdav  # noqa: F401
from app.tasks.uptime_kuma_tasks import ping_uptime_kuma  # noqa: F401

celery.conf.task_routes = {
    "app.tasks.*": {"queue": "default"},
}


@celery.task
def test_task():
    return "Celery is working!"


# Run the check_credentials task at startup
check_credentials.apply_async(countdown=10)  # Run 10 seconds after worker starts

celery.conf.beat_schedule = {
    "poll-inboxes-every-minute": (
        {
            "task": "app.tasks.imap_tasks.pull_all_inboxes",
            "schedule": crontab(minute="*/1"),  # every 1 minute
            "options": {"expires": 55},  # Ensure tasks don't pile up
        }
        if (settings.imap1_host or settings.imap2_host)
        else None
    ),
    # Add Uptime Kuma ping task if configured
    "ping-uptime-kuma": (
        {
            "task": "app.tasks.uptime_kuma_tasks.ping_uptime_kuma",
            "schedule": crontab(minute=f"*/{settings.uptime_kuma_ping_interval}"),
            "options": {"expires": 55},  # Ensure tasks don't pile up
        }
        if settings.uptime_kuma_url
        else None
    ),
    # Check credentials every 5 minutes
    "check-credentials-regularly": {
        "task": "app.tasks.check_credentials.check_credentials",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
        "options": {"expires": 240},  # 4 minutes expiry
    },
    # Also keep daily check for logs and statistics purposes
    "check-credentials-daily": {
        "task": "app.tasks.check_credentials.check_credentials",
        "schedule": crontab(hour="0", minute="0"),  # Midnight
        "options": {"expires": 3600},  # 1 hour expiry
    },
}

# Remove None entries from beat_schedule
celery.conf.beat_schedule = {k: v for k, v in celery.conf.beat_schedule.items() if v is not None}
