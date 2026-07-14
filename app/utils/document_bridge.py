"""Secure multipart delivery from a legacy instance to document intake."""

import json
import os
import secrets
from typing import Any
from urllib.parse import urlparse

from app.config import settings
from app.utils.webhook import METADATA_ENDPOINTS, _normalise_hostname, _resolve_public_address, _send_pinned_post


class DocumentBridgeError(RuntimeError):
    """Raised for bridge configuration or delivery failures."""


def _multipart_body(fields: dict[str, str], file_path: str, filename: str, content_type: str) -> tuple[bytes, str]:
    boundary = f"docuelevate-{secrets.token_hex(16)}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")

    safe_filename = filename.replace('"', "_").replace("\r", "_").replace("\n", "_")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{safe_filename}"\r\n'.encode())
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
    with open(file_path, "rb") as source:
        body.extend(source.read())
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    return bytes(body), boundary


def deliver_document(file_record: Any, file_path: str) -> int:
    """Deliver one processed document and return the receiver HTTP status."""
    url = settings.document_bridge_url
    if not url:
        raise DocumentBridgeError("DOCUMENT_BRIDGE_URL is not configured")
    if not os.path.isfile(file_path):
        raise DocumentBridgeError("Bridge source file is missing")

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise DocumentBridgeError("Document bridge requires an HTTPS URL")
    hostname = _normalise_hostname(parsed.hostname)
    if hostname in METADATA_ENDPOINTS:
        raise DocumentBridgeError("Document bridge target is blocked")
    port = parsed.port or 443
    address = _resolve_public_address(hostname, port)
    if address is None:
        raise DocumentBridgeError("Document bridge target is private, unresolved, or blocked")

    filename = file_record.original_filename or os.path.basename(file_path)
    digest = file_record.filehash
    metadata = {
        "source_document_id": file_record.id,
        "source_file_hash": digest,
        "owner_id": file_record.owner_id,
        "title": file_record.document_title,
        "mime_type": file_record.mime_type,
        "created_at": file_record.created_at.isoformat() if file_record.created_at else None,
    }
    fields = {
        "source": settings.document_bridge_source,
        "idempotency_key": f"{settings.document_bridge_source}:{file_record.id}:{digest}",
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
    }
    body, boundary = _multipart_body(fields, file_path, filename, file_record.mime_type or "application/pdf")
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if settings.document_bridge_bearer_token:
        headers["Authorization"] = f"Bearer {settings.document_bridge_bearer_token}"
    elif settings.document_bridge_shared_secret:
        headers["X-DocuElevate-Intake-Secret"] = settings.document_bridge_shared_secret
    else:
        raise DocumentBridgeError("Document bridge authentication is not configured")

    ok, status_code = _send_pinned_post(parsed, address, body, headers)
    if not ok:
        raise DocumentBridgeError(f"Document bridge returned HTTP {status_code}")
    return status_code
