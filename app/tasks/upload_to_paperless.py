#!/usr/bin/env python3

import json
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


def get_custom_field_id(field_name: str) -> int:
    """
    Retrieves the ID of a custom field by its name from Paperless-ngx.

    Args:
        field_name: The name of the custom field to look up

    Returns:
        The integer ID of the custom field

    Raises:
        ValueError: If the custom field is not found
    """
    url = _paperless_api_url("/api/custom_fields/")
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=settings.http_request_timeout)
        resp.raise_for_status()
        data = resp.json()

        # Handle paginated response
        results = data.get("results", []) if isinstance(data, dict) else data

        for field in results:
            if field.get("name") == field_name:
                return field.get("id")

        raise ValueError(f"Custom field '{field_name}' not found in Paperless-ngx")
    except requests.exceptions.RequestException as exc:
        logger.error(f"Failed to retrieve custom fields from Paperless: {exc}")
        raise


def set_document_custom_fields(doc_id: int, custom_fields: dict, task_id: str) -> None:
    """
    Updates custom fields for a document in Paperless-ngx using PATCH.

    Args:
        doc_id: The Paperless document ID
        custom_fields: Dictionary mapping field names to values
        task_id: Task ID for logging
    """
    if not custom_fields:
        return

    # Build custom_fields array for PATCH request
    custom_fields_array = []
    for field_name, value in custom_fields.items():
        if value and value != "Unknown":  # Only set non-empty, non-Unknown values
            try:
                field_id = get_custom_field_id(field_name)
                custom_fields_array.append({"field": field_id, "value": value})
                logger.info(f"[{task_id}] Mapped custom field '{field_name}' to ID {field_id} with value '{value}'")
            except ValueError as e:
                logger.warning(f"[{task_id}] {str(e)}, skipping this field")
                continue

    if not custom_fields_array:
        logger.info(f"[{task_id}] No valid custom fields to set")
        return

    # PATCH the document with custom fields
    url = _paperless_api_url(f"/api/documents/{doc_id}/")
    payload = {"custom_fields": custom_fields_array}

    try:
        logger.info(f"[{task_id}] Setting custom fields for document {doc_id}: {payload}")
        resp = requests.patch(url, headers=_get_headers(), json=payload, timeout=settings.http_request_timeout)
        resp.raise_for_status()
        logger.info(f"[{task_id}] Successfully set custom fields for document {doc_id}")
    except requests.exceptions.RequestException as exc:
        logger.error(f"[{task_id}] Failed to set custom fields for document {doc_id}: {exc}")
        # Don't raise - this is a non-critical failure, document is already uploaded
        logger.error(f"[{task_id}] Response: {getattr(exc.response, 'text', '<no response>')}")


@celery.task(base=BaseTaskWithRetry, bind=True)
def upload_to_paperless(self, file_path: str, file_id: int = None):
    """
    Uploads a file to Paperless-ngx and sets custom fields from metadata.

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

    # Try to load metadata from accompanying JSON file
    metadata = {}
    json_path = os.path.splitext(file_path)[0] + ".json"
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            logger.info(f"[{task_id}] Loaded metadata from {json_path}")
        except Exception as e:
            logger.warning(f"[{task_id}] Failed to load metadata from {json_path}: {e}")
            metadata = {}
    else:
        logger.info(f"[{task_id}] No metadata file found at {json_path}")

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

    # Set custom fields if configured and metadata available
    if settings.paperless_custom_field_absender and metadata.get("absender"):
        logger.info(f"[{task_id}] Setting custom fields for document {doc_id}")
        log_task_progress(task_id, "set_custom_fields", "in_progress", "Setting custom fields", file_id=file_id)

        # Prepare custom fields to set
        custom_fields_to_set = {}
        if settings.paperless_custom_field_absender:
            custom_fields_to_set[settings.paperless_custom_field_absender] = metadata.get("absender")

        try:
            set_document_custom_fields(doc_id, custom_fields_to_set, task_id)
            log_task_progress(task_id, "set_custom_fields", "success", "Custom fields set", file_id=file_id)
        except Exception as e:
            logger.error(f"[{task_id}] Failed to set custom fields: {e}")
            log_task_progress(task_id, "set_custom_fields", "failure", f"Failed: {str(e)}", file_id=file_id)
            # Don't fail the entire upload if custom fields fail

    return {
        "status": "Completed",
        "paperless_task_id": raw_task_id,
        "paperless_document_id": doc_id,
        "file_path": file_path,
    }
