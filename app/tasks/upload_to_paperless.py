#!/usr/bin/env python3

import os
import re
import json
import requests
from typing import Optional, Dict, Any, List

from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.celery_app import celery

def _get_headers():
    """Returns the authorization header for Paperless-ngx."""
    return {
        "Authorization": f"Token {settings.paperless_ngx_api_token}"
    }

def _paperless_api_url(path: str) -> str:
    """Constructs the full API URL based on the paperless_host."""
    host = settings.paperless_host.rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{host}{path}"

def get_or_create_correspondent(name: str) -> Optional[int]:
    """Look up or create a correspondent with the given name. Returns None if empty/Unknown."""
    if not name or name.lower() == "unknown":
        return None

    url = _paperless_api_url("/api/correspondents/")
    # Try to find an existing one by name:
    resp = requests.get(url, headers=_get_headers(), params={"name": name})
    resp.raise_for_status()

    data = resp.json()
    existing = [c for c in data["results"] if c["name"] == name]
    if existing:
        return existing[0]["id"]

    # Create new
    create_resp = requests.post(
        url,
        headers={**_get_headers(), "Content-Type": "application/json"},
        json={"name": name}
    )
    create_resp.raise_for_status()
    return create_resp.json()["id"]

def get_or_create_document_type(name: str) -> Optional[int]:
    """Look up or create a document type by name."""
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
    """Look up or create a tag by name."""
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
    """Look up or create a custom field by name."""
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

def patch_document_custom_fields(document_id: int, field_values: Dict[int, str]) -> None:
    """
    Sets custom field values on a document via PATCH /api/documents/<id>/.
    field_values is { custom_field_id: value }.
    """
    if not field_values:
        return

    url = _paperless_api_url(f"/api/documents/{document_id}/")
    payload = {
        "custom_fields": [
            {"field": fid, "value": val} for fid, val in field_values.items()
        ]
    }
    resp = requests.patch(url, headers={**_get_headers(), "Content-Type": "application/json"}, json=payload)
    resp.raise_for_status()

@celery.task(base=BaseTaskWithRetry)
def upload_to_paperless(file_path: str):
    """
    Upload a PDF to Paperless-ngx with the associated .json metadata.
    1. Parse metadata
    2. Create/update correspondents, doc types, tags, and custom fields
    3. Upload PDF to /api/documents/post_document/
       -> parse the plain-text response to get document id
    4. PATCH custom fields
    """

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Expect a matching .json file next to the PDF
    base_name, ext = os.path.splitext(file_path)
    json_path = f"{base_name}.json"
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Metadata JSON not found at {json_path}")

    # Read JSON
    with open(json_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # Prepare fields for built-in Paperless fields
    title = metadata.get("title") or os.path.basename(base_name)

    # Determine the final "correspondent" string (fallback to "absender" if "correspondent" is unknown/empty)
    corr = metadata.get("correspondent", "") or metadata.get("absender", "")
    if corr.lower() == "unknown":
        corr = ""

    correspondent_id = get_or_create_correspondent(corr)

    doc_type_str = metadata.get("document_type", "")
    if doc_type_str.lower() == "unknown":
        doc_type_str = ""
    document_type_id = get_or_create_document_type(doc_type_str) if doc_type_str else None

    # Tags
    tags_list = metadata.get("tags", [])
    tag_ids = []
    for tag_item in tags_list:
        if tag_item and tag_item.lower() != "unknown":
            tid = get_or_create_tag(tag_item)
            if tid:
                tag_ids.append(tid)

    # Upload PDF (multipart form)
    upload_url = _paperless_api_url("/api/documents/post_document/")
    files = {
        "document": (os.path.basename(file_path), open(file_path, "rb"), "application/pdf"),
    }
    data = {"title": title}
    if correspondent_id:
        data["correspondent"] = correspondent_id
    if document_type_id:
        data["document_type"] = document_type_id

    # Paperless might require repeated form fields for each tag id or a single JSON array. 
    # We'll do repeated form fields for safety:
    for t_id in tag_ids:
        data.setdefault("tags", [])
        data["tags"].append(str(t_id))

    resp = requests.post(upload_url, headers=_get_headers(), files=files, data=data)
    # close file handle
    files["document"][1].close()

    resp.raise_for_status()

    # Paperless returns plain text like "Success. New document id 56708 created"
    response_text = resp.text.strip()
    match = re.search(r"New document id (\d+) created", response_text)
    if not match:
        # If there's no match, we can't parse the ID
        # Log the response and raise an error
        raise RuntimeError(f"Could not parse 'New document id ### created' from response: {response_text}")

    document_id = int(match.group(1))
    print(f"[INFO] Successfully uploaded doc. ID = {document_id}")

    # Create & map additional metadata to custom fields.
    # Skip known built-in keys so we don't double-store them as CF.
    built_in_keys = {"filename", "title", "tags", "document_type", "correspondent"}
    field_values_map = {}
    for key, val in metadata.items():
        if key in built_in_keys:
            continue
        if not val or str(val).lower() == "unknown":
            continue
        cf_id = get_or_create_custom_field(key)
        field_values_map[cf_id] = str(val)

    # Patch custom fields
    if field_values_map:
        patch_document_custom_fields(document_id, field_values_map)
        print(f"[INFO] Custom fields successfully patched for document {document_id}")

    return {
        "status": "Completed",
        "paperless_document_id": document_id,
        "file_path": file_path
    }
