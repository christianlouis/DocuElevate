# app/celery_app.py

import logging
import os

from celery import Celery
from celery.signals import task_failure, worker_ready

from app.config import settings

logger = logging.getLogger(__name__)

celery = Celery(
    "document_processor",
    broker=settings.redis_url,
    backend=settings.redis_url,
)


# Optionally add this line to retain connection retry behavior at startup:
celery.conf.broker_connection_retry_on_startup = True

# Set the default queue and routing so that tasks are enqueued on "document_processor"
celery.conf.task_default_queue = "document_processor"
celery.conf.task_routes = {
    "app.tasks.*": {"queue": "document_processor"},
}

# Mapping of document pipeline task names to the positional index of ``file_id``
# in their ``args`` tuple.  These indices correspond to the task signatures:
#   process_with_ocr(filename, file_id, ...)          → index 1
#   extract_metadata_with_gpt(filename, text, file_id) → index 2
#   embed_metadata_into_pdf(path, text, metadata, file_id) → index 3
# Tasks that always pass ``file_id`` as a keyword argument
# (e.g. ``process_document``, ``finalize_document_storage``) are not listed
# here — their ``file_id`` is found via ``kwargs`` instead.
_FILE_ID_ARG_INDEX: dict[str, int] = {
    "app.tasks.process_with_ocr.process_with_ocr": 1,
    "app.tasks.extract_metadata_with_gpt.extract_metadata_with_gpt": 2,
    "app.tasks.embed_metadata_into_pdf.embed_metadata_into_pdf": 3,
}


def _dispatch_user_failure_notification(sender, exception, args: list | None, kwargs: dict | None) -> None:
    """Best-effort per-user failure notification for document pipeline tasks.

    Extracts ``file_id`` from the failed task's arguments, looks up the owning
    user from the database, and dispatches a ``document.failed`` notification.
    """
    from app.database import SessionLocal
    from app.models import FileRecord
    from app.utils.user_notification import notify_user_document_failed

    task_name = sender.name if sender else ""
    if not task_name.startswith("app.tasks."):
        return

    # 1. Resolve file_id from kwargs or positional args
    file_id = (kwargs or {}).get("file_id")
    if file_id is None:
        idx = _FILE_ID_ARG_INDEX.get(task_name)
        if idx is not None and args and len(args) > idx:
            val = args[idx]
            if isinstance(val, int):
                file_id = val

    if file_id is None:
        return

    # 2. Look up owner from the database
    with SessionLocal() as db:
        record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not record or not record.owner_id:
            return
        owner_id = record.owner_id
        filename = record.original_filename or record.local_filename or "unknown"

    # 3. Dispatch per-user notification
    error_msg = f"{type(exception).__name__}: {exception}" if exception else "Unknown error"
    notify_user_document_failed(
        owner_id=owner_id,
        filename=os.path.basename(filename),
        error=error_msg,
        file_id=file_id,
    )


@worker_ready.connect
def init_sentry_on_worker_ready(**kwargs):
    """Initialise Sentry SDK in the Celery worker process."""
    from app.utils.sentry import init_sentry

    init_sentry(integrations_extra=["celery"])


@task_failure.connect
def task_failure_handler(
    sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, **kw
):
    """Handler for Celery task failures to send notifications"""
    if getattr(settings, "notify_on_task_failure", True):
        try:
            # Import here to avoid circular imports
            from app.utils.notification import notify_celery_failure

            notify_celery_failure(
                task_name=sender.name if sender else "Unknown",
                task_id=task_id or "N/A",
                exc=exception,
                args=args or [],
                kwargs=kwargs or {},
            )
        except Exception as e:
            logger.exception(f"Failed to send task failure notification: {e}")

    # Also dispatch a per-user failure notification for document pipeline tasks
    try:
        _dispatch_user_failure_notification(sender, exception, args, kwargs)
    except Exception:
        logger.warning("Could not dispatch per-user failure notification", exc_info=True)
