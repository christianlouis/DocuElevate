#!/usr/bin/env python3

import logging
import os
import time

import requests

from app.celery_app import celery
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import log_task_progress

logger = logging.getLogger(__name__)

POLL_MAX_ATTEMPTS = 10
POLL_INTERVAL_SEC = 3


def _get_headers():
    """Returns HTTP headers for Paperless-ngx API calls."""
    return {"Authorization": f"Token {settings.paperless_ngx_api_token}"}


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
            resp = requests.get(
                url, headers=_get_headers(), params={"task_id": task_id}, timeout=settings.http_request_timeout
            )
            resp.raise_for_status()
            tasks_data = resp.json()
        except requests.exceptions.RequestException as exc:
            logger.warning("Failed to poll for task_id='%s'. Attempt=%d Error=%s", task_id, attempts + 1, exc)
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
                raise RuntimeError(f"Task {task_id} completed but no doc ID found. Task info: {task_info}")
            elif status == "FAILURE":
                raise RuntimeError(f"Task {task_id} failed: {task_info.get('result')}")

        attempts += 1
        time.sleep(POLL_INTERVAL_SEC)

    raise TimeoutError(f"Task {task_id} didn't reach SUCCESS within {POLL_MAX_ATTEMPTS} attempts.")


@celery.task(base=BaseTaskWithRetry, bind=True)
def upload_to_paperless(self, file_path: str, file_id: int = None):
    """
    Uploads a file to Paperless-ngx.

    Args:
        file_path: Path to the file to upload
        file_id: Optional file ID to associate with logs
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting Paperless upload: {file_path}")
    log_task_progress(
        task_id,
        "upload_to_paperless",
        "in_progress",
        f"Uploading to Paperless: {os.path.basename(file_path)}",
        file_id=file_id,
    )

    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_paperless", "failure", error_msg, file_id=file_id)
        raise FileNotFoundError(error_msg)

    # Extract filename
    filename = os.path.basename(file_path)

    # Check if Paperless settings are configured
    if not settings.paperless_host or not settings.paperless_ngx_api_token:
        error_msg = "Paperless-ngx credentials are not fully configured"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_paperless", "failure", error_msg, file_id=file_id)
        raise ValueError(error_msg)

    # Upload the PDF
    logger.info(f"[{task_id}] Posting document to Paperless")
    log_task_progress(task_id, "post_document", "in_progress", "Posting to Paperless API", file_id=file_id)
    post_url = _paperless_api_url("/api/documents/post_document/")
    with open(file_path, "rb") as f:
        files = {
            "document": (filename, f, "application/pdf"),
        }
        data = {"title": filename}  # Title = Filename (no additional metadata)

        try:
            logger.debug("Posting document to Paperless: file=%s", filename)
            resp = requests.post(
                post_url, headers=_get_headers(), files=files, data=data, timeout=settings.http_request_timeout
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            error_msg = f"Failed to upload to Paperless: {exc}"
            logger.error(
                f"[{task_id}] Failed to upload document '%s' to Paperless. Error: %s. Response=%s",
                file_path,
                exc,
                getattr(exc.response, "text", "<no response>"),
            )
            log_task_progress(task_id, "upload_to_paperless", "failure", error_msg, file_id=file_id)
            raise

        raw_task_id = resp.text.strip().strip('"').strip("'")
        logger.info(f"[{task_id}] Received Paperless task ID: {raw_task_id}")
        log_task_progress(task_id, "post_document", "success", f"Task ID: {raw_task_id}", file_id=file_id)

    # Poll tasks until success/fail => get doc_id
    logger.info(f"[{task_id}] Polling for document ID")
    log_task_progress(task_id, "poll_task", "in_progress", "Waiting for Paperless processing", file_id=file_id)
    doc_id = poll_task_for_document_id(raw_task_id)
    logger.info(f"[{task_id}] Document {file_path} successfully ingested => ID={doc_id}")
    log_task_progress(
        task_id, "upload_to_paperless", "success", f"Uploaded to Paperless: Doc ID {doc_id}", file_id=file_id
    )

    return {
        "status": "Completed",
        "paperless_task_id": raw_task_id,
        "paperless_document_id": doc_id,
        "file_path": file_path,
    }
