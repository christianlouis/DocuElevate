#!/usr/bin/env python3

import os
import json
import time
import requests
import logging
from typing import Dict, Any

from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.celery_app import celery

logger = logging.getLogger(__name__)

POLL_MAX_ATTEMPTS = 10
POLL_INTERVAL_SEC = 3

def _get_headers():
    """Returns HTTP headers for Paperless-ngx API calls."""
    return {
        "Authorization": f"Token {settings.paperless_ngx_api_token}"
    }

def _paperless_api_url(path: str) -> str:
    """
    Constructs a full Paperless-ngx API URL using `settings.paperless_host`.
    Ensures the path is appended with a leading slash if missing.
    """
    host = settings.paperless_host.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return f"{host}{path}"

def poll_task_for_document_id(task_id: str) -> int:
    """
    Polls /api/tasks/?task_id=<uuid> until we get status=SUCCESS or FAILURE,
    or until we run out of attempts.

    On SUCCESS: returns the int document_id from 'related_document'.
    On FAILURE: raises RuntimeError with the task's 'result' message.
    If times out, raises TimeoutError.
    """
    url = _paperless_api_url("/api/tasks/")
    attempts = 0

    while attempts < POLL_MAX_ATTEMPTS:
        try:
            resp = requests.get(url, headers=_get_headers(), params={"task_id": task_id})
            resp.raise_for_status()
            tasks_data = resp.json()
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "Failed to poll for task_id='%s'. Attempt=%d Error=%s",
                task_id, attempts + 1, exc
            )
            time.sleep(POLL_INTERVAL_SEC)
            attempts += 1
            continue

        if isinstance(tasks_data, dict) and "results" in tasks_data:
            tasks_data = tasks_data["results"]

        if tasks_data:
            task_info = tasks_data[0]
            status = task_info.get("status")
            if status == "SUCCESS":
                doc_str = task_info.get("related_document")
                if doc_str:
                    return int(doc_str)
                raise RuntimeError(
                    f"Task {task_id} completed but no doc ID found. Task info: {task_info}"
                )
            elif status == "FAILURE":
                raise RuntimeError(f"Task {task_id} failed: {task_info.get('result')}")

        attempts += 1
        time.sleep(POLL_INTERVAL_SEC)

    raise TimeoutError(
        f"Task {task_id} didn't reach SUCCESS within {POLL_MAX_ATTEMPTS} attempts."
    )

@celery.task(base=BaseTaskWithRetry)
def upload_to_paperless(file_path: str) -> Dict[str, Any]:
    """
    Uploads a PDF to Paperless with minimal metadata (filename and date only).
    
    1. Extracts the filename and date from the file.
    2. POSTs the PDF to Paperless => returns a quoted UUID string (task_id).
    3. Polls /api/tasks/?task_id=<uuid> until SUCCESS or FAILURE => doc_id.

    Returns a dict with status, the paperless_task_id, paperless_document_id, and file_path.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    base_name = os.path.basename(file_path)

    # Upload the PDF
    post_url = _paperless_api_url("/api/documents/post_document/")
    with open(file_path, "rb") as f:
        files = {
            "document": (base_name, f, "application/pdf"),
        }
        data = {"title": base_name}  # Title = Filename (no additional metadata)

        try:
            logger.debug("Posting document to Paperless: file=%s", base_name)
            resp = requests.post(post_url, headers=_get_headers(), files=files, data=data)
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            logger.error(
                "Failed to upload document '%s' to Paperless. Error: %s. Response=%s",
                file_path, exc, getattr(exc.response, "text", "<no response>")
            )
            raise

        raw_task_id = resp.text.strip().strip('"').strip("'")
        logger.info(f"Received Paperless task ID: {raw_task_id}")

    # Poll tasks until success/fail => get doc_id
    doc_id = poll_task_for_document_id(raw_task_id)
    logger.info(f"Document {file_path} successfully ingested => ID={doc_id}")

    return {
        "status": "Completed",
        "paperless_task_id": raw_task_id,
        "paperless_document_id": doc_id,
        "file_path": file_path
    }
