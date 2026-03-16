#!/usr/bin/env python3

import logging

from celery.schedules import crontab

# Ensure tasks are loaded
from app import tasks  # noqa: F401 - Imports app/tasks.py so Celery can register tasks

# Import the shared Celery instance
from app.celery_app import celery
from app.config import settings
from app.tasks.backup_tasks import cleanup_old_backups, create_backup  # noqa: F401
from app.tasks.batch_tasks import (  # noqa: F401
    backfill_missing_metadata,
    cleanup_temp_files,
    expire_shared_links,
    process_new_documents,
    prune_old_notifications,
    prune_processing_logs,
    reprocess_failed_documents,
    sync_search_index,
)
from app.tasks.check_credentials import check_credentials
from app.tasks.classify_document import classify_document_task  # noqa: F401
from app.tasks.compute_embedding import backfill_missing_embeddings, compute_document_embedding  # noqa: F401
from app.tasks.convert_to_pdf import convert_to_pdf  # noqa: F401
from app.tasks.convert_to_pdfa import convert_to_pdfa  # noqa: F401
from app.tasks.embed_metadata_into_pdf import embed_metadata_into_pdf  # noqa: F401
from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt  # noqa: F401
from app.tasks.finalize_document_storage import finalize_document_storage  # noqa: F401
from app.tasks.imap_tasks import pull_all_inboxes  # noqa: F401
from app.tasks.monitor_stalled_steps import monitor_stalled_steps  # noqa: F401

# **Ensure all tasks are imported before Celery starts**
from app.tasks.process_document import process_document  # noqa: F401
from app.tasks.process_with_azure_document_intelligence import process_with_azure_document_intelligence  # noqa: F401
from app.tasks.process_with_ocr import process_with_ocr  # noqa: F401
from app.tasks.refine_text_with_gpt import refine_text_with_gpt  # noqa: F401
from app.tasks.rotate_pdf_pages import rotate_pdf_pages  # noqa: F401
from app.tasks.send_to_all import send_to_all_destinations  # noqa: F401
from app.tasks.subscription_tasks import apply_pending_subscription_changes_all  # noqa: F401
from app.tasks.translate_to_default_language import translate_to_default_language  # noqa: F401

# Import new send tasks
from app.tasks.upload_to_dropbox import upload_to_dropbox  # noqa: F401
from app.tasks.upload_to_email import upload_to_email  # noqa: F401
from app.tasks.upload_to_ftp import upload_to_ftp  # noqa: F401
from app.tasks.upload_to_google_drive import upload_to_google_drive  # noqa: F401
from app.tasks.upload_to_icloud import upload_to_icloud  # noqa: F401
from app.tasks.upload_to_nextcloud import upload_to_nextcloud  # noqa: F401
from app.tasks.upload_to_onedrive import upload_to_onedrive  # noqa: F401
from app.tasks.upload_to_paperless import upload_to_paperless  # noqa: F401
from app.tasks.upload_to_s3 import upload_to_s3  # noqa: F401
from app.tasks.upload_to_sftp import upload_to_sftp  # noqa: F401
from app.tasks.upload_to_user_integration import upload_to_user_integration  # noqa: F401
from app.tasks.upload_to_webdav import upload_to_webdav  # noqa: F401
from app.tasks.upload_with_rclone import send_to_all_rclone_destinations, upload_with_rclone  # noqa: F401
from app.tasks.uptime_kuma_tasks import ping_uptime_kuma  # noqa: F401
from app.tasks.watch_folder_tasks import scan_all_watch_folders  # noqa: F401
from app.tasks.webhook_tasks import deliver_webhook_task  # noqa: F401

# Register the settings reload signal handler so workers pick up config changes
from app.utils.settings_sync import register_settings_reload_signal

logger = logging.getLogger(__name__)

register_settings_reload_signal()

celery.conf.task_routes = {
    "app.tasks.*": {"queue": "default"},
}


@celery.task
def test_task():
    return "Celery is working!"


# Run the check_credentials task at startup
check_credentials.apply_async(countdown=10)  # Run 10 seconds after worker starts

celery.conf.beat_schedule = {
    # IMAP polling — always enabled because per-user IMAP integrations may
    # exist in the database even when no system-level IMAP hosts are configured.
    "poll-inboxes-every-minute": {
        "task": "app.tasks.imap_tasks.pull_all_inboxes",
        "schedule": crontab(minute="*/1"),  # every 1 minute
        "options": {"expires": 55},  # Ensure tasks don't pile up
    },
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
    # Monitor for stalled processing steps every minute
    "monitor-stalled-steps": {
        "task": "app.tasks.monitor_stalled_steps.monitor_stalled_steps",
        "schedule": crontab(minute="*/1"),  # Every minute
        "options": {"expires": 55},  # Must complete within 55 seconds
    },
    # Watch folder scanning — always enabled because per-user WATCH_FOLDER
    # integrations may exist in the database even when no system-level watch
    # folder settings are configured.
    # Schedule is controlled by WATCH_FOLDER_POLL_INTERVAL (default: 1 minute).
    "scan-watch-folders": {
        "task": "app.tasks.watch_folder_tasks.scan_all_watch_folders",
        "schedule": crontab(minute=f"*/{max(1, settings.watch_folder_poll_interval)}"),
        "options": {"expires": 55},
    },
    # Backfill embeddings for files that were processed before the
    # embedding pipeline was enabled, or where the embedding task failed.
    "backfill-missing-embeddings": {
        "task": "backfill_missing_embeddings",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
        "options": {"expires": 240},  # 4 minutes expiry
    },
    # Apply scheduled subscription downgrades daily at 00:05 UTC
    "apply-pending-subscription-changes": {
        "task": "app.tasks.subscription_tasks.apply_pending_subscription_changes_all",
        "schedule": crontab(hour="0", minute="5"),  # 00:05 UTC daily
        "options": {"expires": 3600},
    },
    # ── Database backup tasks ──────────────────────────────────────────────
    # Hourly backup (kept for 4 days)
    "backup-hourly": (
        {
            "task": "app.tasks.backup_tasks.create_backup",
            "schedule": crontab(minute="0"),  # top of every hour
            "kwargs": {"backup_type": "hourly"},
            "options": {"expires": 3300},
        }
        if settings.backup_enabled
        else None
    ),
    # Daily backup (kept for 3 weeks) – runs at 02:30 UTC
    "backup-daily": (
        {
            "task": "app.tasks.backup_tasks.create_backup",
            "schedule": crontab(hour="2", minute="30"),
            "kwargs": {"backup_type": "daily"},
            "options": {"expires": 3600},
        }
        if settings.backup_enabled
        else None
    ),
    # Weekly backup (kept for 13 weeks) – runs every Sunday at 03:00 UTC
    "backup-weekly": (
        {
            "task": "app.tasks.backup_tasks.create_backup",
            "schedule": crontab(hour="3", minute="0", day_of_week="0"),
            "kwargs": {"backup_type": "weekly"},
            "options": {"expires": 3600},
        }
        if settings.backup_enabled
        else None
    ),
}

# Remove None entries from beat_schedule
celery.conf.beat_schedule = {k: v for k, v in celery.conf.beat_schedule.items() if v is not None}

# ---------------------------------------------------------------------------
# Load admin-managed scheduled jobs from the database
# ---------------------------------------------------------------------------
# These jobs are defined in the ``scheduled_jobs`` table (seeded by
# ``app.api.scheduled_jobs.seed_default_scheduled_jobs``) and can be
# enabled/disabled and rescheduled via the admin UI at /admin/scheduled-jobs.
# The schedule is read once at worker startup; changes take effect after
# the worker is restarted.


def _load_db_scheduled_jobs() -> None:
    """
    Extend ``celery.conf.beat_schedule`` with entries from the ``scheduled_jobs``
    database table.

    Only rows with ``enabled=True`` are added.  Rows whose ``name`` key
    already exists in the static schedule (defined above) are skipped so
    that hardcoded entries cannot be overridden accidentally.

    Failures are logged as warnings and do not prevent the worker from
    starting.
    """
    try:
        from app.database import SessionLocal
        from app.models import ScheduledJob

        with SessionLocal() as db:
            jobs = db.query(ScheduledJob).filter(ScheduledJob.enabled.is_(True)).all()

        added = 0
        for job in jobs:
            if job.name in celery.conf.beat_schedule:
                # Static entry takes precedence; skip silently.
                continue

            if job.schedule_type == "interval" and job.interval_seconds:
                from celery.schedules import schedule as interval_schedule

                sched = interval_schedule(run_every=job.interval_seconds)
            else:
                # Default to cron.
                sched = crontab(
                    minute=job.cron_minute,
                    hour=job.cron_hour,
                    day_of_week=job.cron_day_of_week,
                    day_of_month=job.cron_day_of_month,
                    month_of_year=job.cron_month_of_year,
                )

            celery.conf.beat_schedule[job.name] = {
                "task": job.task_name,
                "schedule": sched,
                "options": {"expires": 3600},
            }
            added += 1

        logger.info("Loaded %d scheduled job(s) from database into Celery Beat.", added)
    except Exception as exc:
        logger.warning("Could not load scheduled jobs from database: %s", exc)


_load_db_scheduled_jobs()
