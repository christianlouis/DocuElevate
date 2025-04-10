# app/celery_app.py

from celery import Celery
from app.config import settings

celery = Celery(
    "document_processor",
    broker=settings.redis_url,
    backend=settings.redis_url,
)


# Optionally add this line to retain connection retry behavior at startup:
celery.conf.broker_connection_retry_on_startup = True

# Set the default queue and routing so that tasks are enqueued on "document_processor"
celery.conf.task_default_queue = 'document_processor'
celery.conf.task_routes = {
    "app.tasks.*": {"queue": "document_processor"},
}

# Task failure notification handler
from celery.signals import task_failure

@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, args=None,
                        kwargs=None, traceback=None, einfo=None, **kw):
    """Handler for Celery task failures to send notifications"""
    if getattr(settings, 'notify_on_task_failure', True):
        try:
            # Import here to avoid circular imports
            from app.utils.notification import notify_celery_failure
            notify_celery_failure(
                task_name=sender.name if sender else "Unknown", 
                task_id=task_id or "N/A",
                exc=exception, 
                args=args or [], 
                kwargs=kwargs or {}
            )
        except Exception as e:
            import logging
            logging.exception(f"Failed to send task failure notification: {e}")
