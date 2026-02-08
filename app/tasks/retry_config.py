#!/usr/bin/env python3

from celery import Task


class BaseTaskWithRetry(Task):
    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": 3, "countdown": 10}  # 3 retries, 10s delay
    retry_backoff = True  # Exponential backoff
