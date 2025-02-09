#!/usr/bin/env python3

from celery import Celery
from .config import settings

celery = Celery("document_processor", broker=settings.redis_url, backend=settings.redis_url)

celery.conf.task_routes = {
    "app.tasks.*": {"queue": "default"},
}

@celery.task
def test_task():
    return "Celery is working!"
