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
