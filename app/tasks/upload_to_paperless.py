#!/usr/bin/env python3

import os
import re
import json
import time
import requests
from typing import Optional, Dict, Any, List

from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.celery_app import celery

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

def get_or_create_correspondent(name: str) -> Optional[int]:
    """Look up or create a Paperless 'correspondent' by name. Return its ID or None if empty/unknown."""
    if not name or name.lower() == "unknown":
        return None

    url = _paperless_api_url("/api/correspondents/")
    # Attempt to find existing by name
    resp = requests.get(url, headers=_get_headers(), params={"name": name})
    resp.raise_for_status()
    data = resp.json()

    existing = [c for c in data["results"] if c["name"] == name]
    if existing:
        return existing[0]["id"]

    # If none found, create
    create_resp = requests.post(
        url,
        headers={**_get_headers(), "Content-Type": "application/json"},
        json={"name": name}
    )
    create_resp.raise_for_status()
    return create_resp.json()["id"]

def get_or_create_document_type(name: str) -> Optional[int]:
    """Look up or create a Paperless 'document_type' by name. Return its ID or None if empty/unknown."""
    if not name or name.lower() == "unknown":
        return None

    url = _paperless_api_url("/api/document_types/")
    resp = requests.get(url, headers=_get_headers(), params={"name": name})
    resp.raise_for_status()
    data = resp.json()

    existing = [dt for dt in data["results"] if dt["name"] == name]
    if existing:
        return existing[0]["id"]

    create_resp = requests.post(
        url,
        headers={**_get_headers(), "Content-Type": "application/json"},
        json={"name": name}
    )
    create_resp.raise_for_status()
    return create_resp.json()["id"]

def get_or_create_tag(tag_name: str) -> Optional[int]:
    """Look up or create a Paperless 'tag' by name. Return its ID or None if empty/unknown."""
    if not tag_name or tag_name.lower() == "unknown":
        return None

    url = _paperless_api_url("/api/tags/")
    resp = requests.get(url, headers=_get_headers(), params={"name": tag_name})
    resp.raise_for_status()
    data = resp.json()

    existing = [t for t in data["results"] if t["name"] == tag_name]
    if existing:
        return existing[0]["id"]

    create_resp = requests.post(
        url,
        headers={**_get_headers(), "Content-Type": "application/json"},
        json={"name": tag_name}
    )
    create_resp.raise_for_status()
    return create_resp.json()["id"]

def get_or_create_custom_field(field_name: str) -> int:
    """
    Look up or create a Paperless 'custom_field' by name.
    Returns its ID. Raises ValueError if field_name is empty.
    """
    if not field_name:
        raise ValueError("Field name must not be empty")

    url = _paperless_api_url("/api/custom_fields/")
    resp = requests.get(url, headers=_get_headers(), params={"name": field_name})
    resp.raise_for_status()
    data = resp.json()

    existing = [cf for cf in data["results"] if cf["name"] == field_name]
    if existing:
        return existing[0]["id"]

    create_resp = requests.post(
        url,
        headers={**_get_headers(), "Content-Type": "application/json"},
        json={"name": field_name, "data_type": "string"}
    )
    create_resp.raise_for_status()
    return create_resp.json()["id"]

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
        resp = requests.get(url, headers=_get_headers(), params={"task_id": task_id})
        resp.raise_for_status()

        # The response is typically a list of length 1, e.g.:
        # [
        #   {
        #     "task_id": "uuid",
        #     "status": "SUCCESS",
        #     "related_document": "56712",
        #     "result": "Success. New document id 56712 created",
        #     ...
        #   }
        # ]
        tasks_data = resp.json()
        if isinstance(tasks_data, dict) and "results" in tasks_data:
            # Some versions wrap tasks in { "results": [ ... ] }
            tasks_data = tasks_data["results"]

        if tasks_data:
            task_info = tasks_data[0]
            status = task_info.get("status")
            if status == "SUCCESS":
                doc_str = task_info.get("related_document")  # e.g. "56712"
                if doc_str:
                    return int(doc_str)
                # Fallback: parse from 'result' text
                match = re.search(r"New document id (\d+)", task_info.get("result", ""))
                if match:
                    return int(match.group(1))
                raise RuntimeError(
                    f"Task {task_id} completed but no doc ID found. Task info: {task_info}"
                )
            elif status == "FAILURE":
                raise RuntimeError(f"Task {task_id} failed: {task_info.get('result')}")

        attempts += 1
        time.sleep(POLL_INTERVAL_SEC)

    raise TimeoutError(f"Task {task_id} didn't reach SUCCESS within {POLL_MAX_ATTEMPTS} attempts.")

def patch_document_custom_fields(document_id: int, field_values: Dict[int, str]) -> None:
    """
    Applies custom field values to an existing document:
    PATCH /api/documents/<id>/
    JSON body: { "custom_fields": [ { "field": <id>, "value": <val> }, ... ] }
    """
    if not field_values:
        return

    url = _paperless_api_url(f"/api/documents/{document_id}/")
    payload = {
        "custom_fields": [
            {"field": cf_id, "value": cf_val}
            for cf_id, cf_val in field_values.items()
        ]
    }

    resp = requests.patch(url, headers={**_get_headers(), "Content-Type": "application/json"}, json=payload)
    resp.raise_for_status()

@celery.task(base=BaseTaskWithRetry)
def upload_to_paperless(file_path: str) -> Dict[str, Any]:
    """
    1. Reads JSON metadata from a matching .json file.
    2. Creates/fetches correspondents, doc types, tags, custom fields as needed.
    3. POSTs the PDF to Paperless => returns a quoted UUID string (task_id).
    4. Polls /api/tasks/?task_id=<uuid> until SUCCESS or FAILURE => doc_id
    5. PATCHes custom fields onto the doc if present.
    """

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    base_name, ext = os.path.splitext(file_path)
    json_path = f"{base_name}.json"
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Metadata JSON not found: {json_path}")

    # Read JSON metadata
    with open(json_path, "r", encoding="utf-8") as jf:
        metadata = json.load(jf)

    # Built-in Paperless fields
    title = metadata.get("title") or os.path.basename(base_name)
    corr_name = metadata.get("correspondent", "") or metadata.get("absender", "")
    if corr_name.lower() == "unknown":
        corr_name = ""
    correspondent_id = get_or_create_correspondent(corr_name)

    doc_type_str = metadata.get("document_type", "")
    if doc_type_str.lower() == "unknown":
        doc_type_str = ""
    document_type_id = get_or_create_document_type(doc_type_str) if doc_type_str else None

    # Tags
    tag_ids: List[int] = []
    tags_list = metadata.get("tags", [])
    for tag_item in tags_list:
        if tag_item and tag_item.lower() != "unknown":
            tid = get_or_create_tag(tag_item)
            if tid:
                tag_ids.append(tid)

    # 1) Upload PDF
    post_url = _paperless_api_url("/api/documents/post_document/")
    files = {
        "document": (os.path.basename(file_path), open(file_path, "rb"), "application/pdf"),
    }
    data = {
        "title": title
    }
    if correspondent_id:
        data["correspondent"] = correspondent_id
    if document_type_id:
        data["document_type"] = document_type_id

    # Usually Paperless expects repeated form fields for tags[] or a single tags array
    # We'll do repeated form fields for each tag
    for t_id in tag_ids:
        data.setdefault("tags", []).append(str(t_id))

    # Send the POST
    resp = requests.post(post_url, headers=_get_headers(), files=files, data=data)
    # Close file handle
    files["document"][1].close()
    resp.raise_for_status()

    # The response is typically just: "some-uuid"
    raw_task_id = resp.text.strip().strip('"').strip("'")
    print(f"[INFO] Received Paperless task ID: {raw_task_id}")

    # 2) Poll tasks until success/fail => get doc_id
    doc_id = poll_task_for_document_id(raw_task_id)
    print(f"[INFO] Document created (or found duplicate) => ID={doc_id}")

    # 3) Create custom fields for leftover JSON keys
    # Skip these built-ins to avoid storing duplicates
    built_in_keys = {"filename", "title", "tags", "document_type", "correspondent"}
    field_values_map = {}
    for key, val in metadata.items():
        if key in built_in_keys:
            continue
        if not val or str(val).lower() == "unknown":
            continue
        cf_id = get_or_create_custom_field(key)
        field_values_map[cf_id] = str(val)

    if field_values_map:
        patch_document_custom_fields(doc_id, field_values_map)
        print(f"[INFO] Patched custom fields for doc {doc_id}")

    return {
        "status": "Completed",
        "paperless_task_id": raw_task_id,
        "paperless_document_id": doc_id,
        "file_path": file_path
    }
