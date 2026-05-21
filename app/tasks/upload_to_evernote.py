#!/usr/bin/env python3

import hashlib
import json
import logging
import mimetypes
import os
from html import escape
from typing import Any

from app.celery_app import celery
from app.config import settings
from app.tasks.retry_config import UploadTaskWithRetry
from app.utils import log_task_progress

logger = logging.getLogger(__name__)

_UNKNOWN_PLACEHOLDERS = {"", "Unknown", "unknown", "N/A", "n/a", "None", "none", "null"}
_MAX_EVERNOTE_TITLE_LENGTH = 255


def _get_evernote_sdk():
    """Import the Evernote SDK lazily so the missing dependency error is actionable."""
    try:
        from evernote.edam.notestore import NoteStore
        from evernote.edam.type import ttypes as Types
        from evernote.edam.userstore import UserStore
        from thrift.protocol import TBinaryProtocol
        from thrift.transport import THttpClient
    except ImportError as exc:
        raise RuntimeError("Evernote upload requires the evernote3 package. Install requirements.txt again.") from exc
    return NoteStore, Types, UserStore, TBinaryProtocol, THttpClient


def _build_thrift_client(client_cls, url: str, binary_protocol, http_transport):
    transport = http_transport.THttpClient(url)
    protocol = binary_protocol.TBinaryProtocol(transport)
    return client_cls(protocol)


def _get_note_store(auth_token: str):
    NoteStore, Types, UserStore, TBinaryProtocol, THttpClient = _get_evernote_sdk()

    base_url = "https://sandbox.evernote.com" if getattr(settings, "evernote_sandbox", False) else "https://www.evernote.com"
    user_store = _build_thrift_client(UserStore.Client, f"{base_url}/edam/user", TBinaryProtocol, THttpClient)
    user = user_store.getUser(auth_token)
    shard_id = getattr(user, "shardId", None)
    if not shard_id:
        raise RuntimeError("Evernote user response did not include a shard ID")

    note_store_url = f"{base_url}/shard/{shard_id}/notestore"
    note_store = _build_thrift_client(NoteStore.Client, note_store_url, TBinaryProtocol, THttpClient)
    return note_store, Types


def _load_metadata(file_path: str) -> dict[str, Any]:
    """Load extracted DocuElevate metadata from the companion JSON file, when present."""
    json_path = os.path.splitext(file_path)[0] + ".json"
    if not os.path.exists(json_path):
        return {}

    try:
        with open(json_path, "r", encoding="utf-8") as metadata_file:
            data = json.load(metadata_file)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load Evernote metadata from %s: %s", json_path, exc)
        return {}

    return data if isinstance(data, dict) else {}


def _normalize_metadata_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        normalized = ", ".join(str(item) for item in value if item is not None)
    elif isinstance(value, dict):
        normalized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        normalized = str(value)

    normalized = normalized.strip()
    return "" if normalized in _UNKNOWN_PLACEHOLDERS else normalized


def _metadata_rows(metadata: dict[str, Any]) -> list[tuple[str, str]]:
    rows = []
    for key in sorted(metadata):
        value = _normalize_metadata_value(metadata[key])
        if value:
            rows.append((key, value))
    return rows


def _extract_tags(metadata: dict[str, Any]) -> list[str]:
    tags: list[str] = []

    def add_tag(value: Any) -> None:
        normalized = _normalize_metadata_value(value)
        if normalized and normalized not in tags:
            tags.append(normalized)

    default_tags = getattr(settings, "evernote_default_tags", None)
    if default_tags:
        for tag in str(default_tags).split(","):
            add_tag(tag)

    metadata_tags = metadata.get("tags")
    if isinstance(metadata_tags, str):
        for tag in metadata_tags.split(","):
            add_tag(tag)
    elif isinstance(metadata_tags, (list, tuple, set)):
        for tag in metadata_tags:
            add_tag(tag)

    return tags


def _note_title(file_path: str, metadata: dict[str, Any]) -> str:
    title = (
        _normalize_metadata_value(metadata.get("title"))
        or _normalize_metadata_value(metadata.get("filename"))
        or os.path.basename(file_path)
    )
    return title[:_MAX_EVERNOTE_TITLE_LENGTH]


def _build_enml(metadata: dict[str, Any], resource_hash: str, resource_mime: str, include_metadata: bool) -> str:
    body_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    body_parts.append('<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">')
    body_parts.append("<en-note>")

    if include_metadata:
        rows = _metadata_rows(metadata)
        if rows:
            body_parts.append("<div><b>DocuElevate metadata</b></div>")
            for key, value in rows:
                body_parts.append(f"<div><b>{escape(key)}:</b> {escape(value)}</div>")
            body_parts.append("<br/>")

    body_parts.append(f'<en-media type="{escape(resource_mime)}" hash="{resource_hash}"/>')
    body_parts.append("</en-note>")
    return "".join(body_parts)


def _create_evernote_note(file_path: str, metadata: dict[str, Any], task_id: str):
    auth_token = getattr(settings, "evernote_auth_token", None)
    if not auth_token:
        raise ValueError("Evernote auth token is not configured (EVERNOTE_AUTH_TOKEN)")

    note_store, Types = _get_note_store(auth_token)

    filename = os.path.basename(file_path)
    with open(file_path, "rb") as pdf_file:
        resource_body = pdf_file.read()

    body_hash = hashlib.md5(resource_body).digest()  # noqa: S324 - Evernote API requires MD5 resource hashes.
    body_hash_hex = hashlib.md5(resource_body).hexdigest()  # noqa: S324 - Evernote ENML references MD5 hashes.
    resource_mime = mimetypes.guess_type(filename)[0] or "application/pdf"

    data = Types.Data()
    data.size = len(resource_body)
    data.bodyHash = body_hash
    data.body = resource_body

    resource = Types.Resource()
    resource.mime = resource_mime
    resource.data = data
    resource.attributes = Types.ResourceAttributes(fileName=filename)

    note = Types.Note()
    note.title = _note_title(file_path, metadata)
    note.content = _build_enml(
        metadata,
        body_hash_hex,
        resource_mime,
        include_metadata=getattr(settings, "evernote_include_metadata", True),
    )
    note.resources = [resource]

    notebook_guid = getattr(settings, "evernote_notebook_guid", None)
    if notebook_guid:
        note.notebookGuid = notebook_guid

    tag_names = _extract_tags(metadata)
    if tag_names:
        note.tagNames = tag_names

    created_note = note_store.createNote(auth_token, note)

    logger.info("[%s] Created Evernote note %s for %s", task_id, getattr(created_note, "guid", None), file_path)
    return created_note


@celery.task(base=UploadTaskWithRetry, bind=True)
def upload_to_evernote(self, file_path: str, file_id: int = None):
    """
    Upload a document to Evernote by creating a note with metadata and a PDF attachment.

    Args:
        file_path: Path to the PDF file to upload
        file_id: Optional file ID to associate with logs
    """
    task_id = self.request.id
    filename = os.path.basename(file_path)
    logger.info("[%s] Starting Evernote upload: %s", task_id, file_path)
    log_task_progress(task_id, "upload_to_evernote", "in_progress", f"Uploading to Evernote: {filename}", file_id=file_id)

    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error("[%s] %s", task_id, error_msg)
        log_task_progress(task_id, "upload_to_evernote", "failure", error_msg, file_id=file_id)
        raise FileNotFoundError(error_msg)

    if not getattr(settings, "evernote_auth_token", None):
        error_msg = "Evernote auth token is not configured (EVERNOTE_AUTH_TOKEN)"
        logger.error("[%s] %s", task_id, error_msg)
        log_task_progress(task_id, "upload_to_evernote", "failure", error_msg, file_id=file_id)
        raise ValueError(error_msg)

    try:
        metadata = _load_metadata(file_path)
        created_note = _create_evernote_note(file_path, metadata, task_id)
    except Exception as exc:
        error_msg = f"Failed to upload to Evernote: {exc}"
        logger.error("[%s] %s", task_id, error_msg)
        log_task_progress(task_id, "upload_to_evernote", "failure", error_msg, file_id=file_id)
        raise

    note_guid = getattr(created_note, "guid", None)
    log_task_progress(task_id, "upload_to_evernote", "success", f"Uploaded to Evernote: {note_guid}", file_id=file_id)
    return {
        "status": "Completed",
        "file_path": file_path,
        "evernote_note_guid": note_guid,
        "evernote_title": getattr(created_note, "title", None),
        "evernote_notebook_guid": getattr(created_note, "notebookGuid", None),
    }
