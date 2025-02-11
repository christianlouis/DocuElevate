#!/usr/bin/env python3

import os
import time
import json
import requests

from typing import Optional, Dict, Any, List
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.celery_app import celery

POLL_MAX_ATTEMPTS = 10
POLL_INTERVAL_SEC = 3

def _get_headers():
    """Returns the authorization header for Paperless-ngx."""
    return {
        "Authorization": f"Token {settings.paperless_ngx_api_token}"
    }

def _paperless_api_url(path: str) -> str:
    """
    Constructs the full API URL based on the paperless_host.
    For example, '/api/correspondents/' -> 'https://paperless2.example.org/api/correspondents/'
    """
    host = settings.paperless_host.rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{host}{path}"

def get_or_create_correspondent(name: str) -> Optional[int]:
    """Look up or create a correspondent with the given name. Returns None if name is empty/Unknown."""
    if not name or name.lower() == "unknown":
        return None

    # Attempt GET
    url = _paperless_api_url("/api/correspondents/")
    params = {"name": name}
    resp = requests.get(url, headers=_get_headers(), params=params)
    resp.raise_for_status()

    data = resp.json()
    # 'results' might contain items with matching name
    existing = [c for c in data["results"] if c["name"] == name]
    if existing:
        return existing[0]["id"]

    # If not found, create
    create_resp = requests.post(
        url,
        headers={**_get_headers(), "Content-Type": "application/json"},
        json={"name": name}
    )
    create_resp.raise_for_status()
    new_corr = create_resp.json()
    return new_corr["id"]

def get_or_create_document_type(name: str) -> Optional[int]:
    """Look up or create a document type by name."""
    if not name or name.lower() == "unknown":
        return None

    url = _paperless_api_url("/api/document_types/")
    params = {"name": name}
    resp = requests.get(url, headers=_get_headers(), params=params)
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
    """Look up or create a tag by name."""
    if not tag_name or tag_name.lower() == "unknown":
        return None

    url = _paperless_api_url("/api/tags/")
    params = {"name": tag_name}
    resp = requests.get(url, headers=_get_headers(), params=params)
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
    """Look up or create a custom field by name."""
    if not field_name:
        raise ValueError("Field name must not be empty")

    url = _paperless_api_url("/api/custom_fields/")
    params = {"name": field_name}
    resp = requests.get(url, headers=_get_headers(), params=params)
    resp.raise_for_status()
    data = resp.json()

    existing = [cf for cf in data["results"] if cf["name"] == field_name]
    if existing:
        return existing[0]["id"]

    # Create custom field
    create_resp = requests.post(
        url,
        headers={**_get_headers(), "Content-Type": "application/json"},
        json={"name": field_name, "data_type": "string"}
    )
    create_resp.raise_for_status()
    return create_resp.json()["id"]

def poll_paperless_task(task_id: str) -> Optional[int]:
    """
    Polls the /api/tasks/?task_id=... endpoint until status == SUCCESS or we time out.
    Returns the newly created document_id if successful, else raises an error.
    """
    url = _paperless_api_url("/api/tasks/")
    attempts = 0
    while attempts < POLL_MAX_ATTEMPTS:
        resp = requests.get(url, headers=_get_headers(), params={"task_id": task_id})
        resp.raise_for_status()
        data = resp.json()
        results = data["results"]
        if len(results) > 0:
            task_info = results[0]
            status = task_info["status"]
            if status == "SUCCESS":
                # Typically: task_info["result"] -> {"document_id": 123, ...}
                if "result" in task_info and "document_id" in task_info["result"]:
                    return task_info["result"]["document_id"]
                else:
                    # No document_id? Possibly no doc created. Raise error.
                    raise RuntimeError(f"Task completed but no document_id. Task info: {task_info}")
            elif status == "FAILURE":
                raise RuntimeError(f"Paperless task failed: {task_info}")
        # Otherwise, keep polling
        time.sleep(POLL_INTERVAL_SEC)
        attempts += 1

    raise TimeoutError(f"Task {task_id} did not complete in time.")

def patch_document_custom_fields(document_id: int, field_values: Dict[int, str]) -> None:
    """
    Sets custom field values on a document via PATCH /api/documents/<id>/.

    field_values should be a dict of {custom_field_id: value}.
    """
    if not field_values:
        return

    custom_fields_data = []
    for field_id, val in field_values.items():
        custom_fields_data.append({"field": field_id, "value": val})

    url = _paperless_api_url(f"/api/documents/{document_id}/")
    resp = requests.patch(
        url,
        headers={**_get_headers(), "Content-Type": "application/json"},
        json={"custom_fields": custom_fields_data},
    )
    resp.raise_for_status()

@celery.task(base=BaseTaskWithRetry)
def upload_to_paperless(file_path: str):
    """
    Uploads a PDF to Paperless-ngx with the associated .json metadata.
    1. Parse metadata
    2. Create or update correspondents, doc types, tags, and custom fields
    3. Upload the PDF to /api/documents/post_document/
    4. Poll until the doc is created
    5. Patch custom fields
    """

    # Validate file existence
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Construct JSON path
    base_name, ext = os.path.splitext(file_path)
    json_path = f"{base_name}.json"
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Metadata JSON not found at {json_path}")

    # Parse JSON
    with open(json_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # Paperless metadata
    title = metadata.get("title") or os.path.basename(base_name)
    # Determine final correspondent name
    correspondent_name = metadata.get("correspondent", "") or metadata.get("absender", "")
    if correspondent_name.lower() == "unknown":
        correspondent_name = ""

    # Look up or create the needed IDs
    correspondent_id = get_or_create_correspondent(correspondent_name)
    document_type_str = metadata.get("document_type", "")
    if document_type_str.lower() == "unknown":
        document_type_str = ""
    document_type_id = get_or_create_document_type(document_type_str) if document_type_str else None

    # Process tags
    tags_list = metadata.get("tags", [])
    tag_ids = []
    for t in tags_list:
        if t and t.lower() != "unknown":
            tid = get_or_create_tag(t)
            if tid:
                tag_ids.append(tid)

    # Step 1: Upload the PDF
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

    # Paperless might require tags to be repeated or a single array. 
    # Usually, repeated form fields are used. But some versions might allow "tags": [1,2,3].
    # We'll do repeated for safety:
    for tag_id in tag_ids:
        data.setdefault("tags", [])
        data["tags"].append(str(tag_id))

    post_url = _paperless_api_url("/api/documents/post_document/")
    post_resp = requests.post(
        post_url,
        headers=_get_headers(),
        files=files,
        data=data
    )
    files["document"][1].close()  # Close the open file

    post_resp.raise_for_status()
    post_data = post_resp.json()
    task_id = post_data.get("task_id")
    if not task_id:
        raise RuntimeError(f"Paperless post_document returned no task_id. Response: {post_data}")

    # Step 2: Poll until task is consumed
    document_id = poll_paperless_task(task_id)
    print(f"[INFO] Document created with ID {document_id} after consumption.")

    # Step 3: Collect & Create Custom Fields
    # We'll skip known Paperless fields: "filename", "title", "tags", "document_type", "correspondent", ...
    # We'll create custom fields for everything else that isn't empty or 'Unknown'.
    # E.g., "absender", "empfaenger", "language", "kommunikationsart", "kommunikationskategorie", etc.

    built_in_keys = {
        "filename", "title", "tags", "document_type", "correspondent", "absender"
    }
    # We have 'absender' in built_in_keys because we might store it in correspondent if needed,
    # but user wants to store it as a custom field too. We'll keep it out if "absender" is also wanted as CF.
    # => If you want 'absender' to also become a CF, remove it from built_in_keys.

    # We'll exclude "filename" but keep "absender", "empfaenger", etc. as custom fields:
    # Just remove "absender" from built_in_keys if you want that as a CF as well
    built_in_keys = {"filename", "title", "tags", "document_type", "correspondent"}

    field_values_map = {}
    for key, val in metadata.items():
        if key in built_in_keys:
            continue
        if not val or str(val).lower() == "unknown":
            continue
        # create or get ID
        cf_id = get_or_create_custom_field(key)
        field_values_map[cf_id] = str(val)

    # Step 4: PATCH document to add custom field values
    if field_values_map:
        patch_document_custom_fields(document_id, field_values_map)

    print(f"[INFO] Successfully uploaded and patched custom fields for doc {document_id}.")
    return {
        "status": "Completed",
        "paperless_document_id": document_id,
        "file_path": file_path
    }
