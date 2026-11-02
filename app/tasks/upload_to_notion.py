"""Per-user Notion destination integration."""

import hashlib
import json
import logging
import math
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import requests

from app.celery_app import celery
from app.config import settings
from app.tasks.retry_config import UploadTaskWithRetry
from app.utils import log_task_progress

logger = logging.getLogger(__name__)
NOTION_API_URL = "https://api.notion.com"
NOTION_VERSION = "2026-03-11"
_TIMEOUT = (10, 30)
_MAX_RICH_TEXT = 1900
_MAX_SINGLE_PART_BYTES = 20 * 1024 * 1024
_NOTION_PART_BYTES = 10 * 1024 * 1024
_WORKSPACE_LIMIT_CACHE: dict[str, tuple[float, int]] = {}


class NotionTransportError(RuntimeError):
    """A Notion request did not receive a response."""


class NotionPageCreationUncertain(RuntimeError):
    """A page may have been created even though its result was not available."""


class NotionWorkspaceLimitError(ValueError):
    """The PDF exceeds the workspace upload limit."""


def _request(method: str, path: str, token: str, **kwargs: Any) -> requests.Response:
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION}
    headers.update(kwargs.pop("headers", {}))
    if "files" not in kwargs:
        headers.setdefault("Content-Type", "application/json")
    try:
        return requests.request(
            method, f"{NOTION_API_URL}{path}", headers=headers, timeout=_TIMEOUT, allow_redirects=False, **kwargs
        )
    except requests.RequestException:
        raise NotionTransportError("Notion request failed") from None


def _success(response: requests.Response) -> bool:
    return 200 <= response.status_code < 300


def _error(response: requests.Response) -> RuntimeError:
    if response.status_code in (401, 403):
        return RuntimeError("Notion rejected the token or the selected data source is not shared")
    if response.status_code == 404:
        return RuntimeError("Notion could not find the selected data source")
    if response.status_code == 429:
        return RuntimeError("Notion rate limit reached; retry later")
    if 300 <= response.status_code < 400:
        return RuntimeError("Notion returned an unexpected redirect")
    return RuntimeError(f"Notion API request failed (HTTP {response.status_code})")


def _json(response: requests.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except (ValueError, TypeError):
        raise RuntimeError("Notion returned an invalid response") from None
    if not isinstance(body, dict):
        raise RuntimeError("Notion returned an invalid response")
    return body


def _metadata(file_path: str) -> dict[str, Any]:
    try:
        with open(os.path.splitext(file_path)[0] + ".json", encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value if item is not None)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def _rich_text(value: str) -> list[dict[str, Any]]:
    value = value[:_MAX_RICH_TEXT]
    return [{"type": "text", "text": {"content": value}}] if value else []


def _uuid(value: Any, name: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"Notion {name} must be a valid UUID") from None


def _resolve_data_source(token: str, cfg: dict[str, Any]) -> str:
    data_source_id = cfg.get("data_source_id")
    database_id = cfg.get("database_id")
    if data_source_id and database_id:
        raise ValueError("Provide either a Notion data source ID or database ID, not both")
    if data_source_id:
        return _uuid(data_source_id, "data source ID")
    if not database_id:
        raise ValueError("Notion data source ID is required")
    database_uuid = _uuid(database_id, "database ID")
    response = _request("GET", f"/v1/databases/{database_uuid}", token)
    if not _success(response):
        raise _error(response)
    body = _json(response)
    sources = body.get("data_sources") or body.get("data_source_ids") or []
    if len(sources) != 1:
        raise ValueError("Notion database must resolve to exactly one data source")
    source = sources[0].get("id") if isinstance(sources[0], dict) else sources[0]
    return _uuid(source, "data source ID")


def _title_property(properties: dict[str, Any], configured: str | None) -> str:
    if configured and isinstance(properties.get(configured), dict) and properties[configured].get("type") == "title":
        return configured
    for name, value in properties.items():
        if isinstance(value, dict) and value.get("type") == "title":
            return name
    raise ValueError("The selected Notion data source has no title property")


def _document_url(cfg: dict[str, Any], file_id: int | None) -> str:
    if file_id is None:
        return ""
    base = str(cfg.get("document_url_base") or settings.public_base_url or "").rstrip("/")
    if not base:
        return ""
    parsed = urlsplit(base)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("DocuElevate base URL must use HTTPS and contain no credentials or query")
    return f"{base}/files/{file_id}"


def _workspace_upload_limit(token: str) -> int:
    """Return the bot workspace upload limit, cached per token without storing it."""
    cache_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    cached = _WORKSPACE_LIMIT_CACHE.get(cache_key)
    if cached is not None and time.monotonic() - cached[0] < 300:
        return cached[1]
    response = _request("GET", "/v1/users/me", token)
    if not _success(response):
        raise _error(response)
    limits = _json(response).get("bot", {}).get("workspace_limits")
    limit = limits.get("max_file_upload_size_in_bytes") if isinstance(limits, dict) else None
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise RuntimeError("Notion workspace upload limit was not provided")
    if len(_WORKSPACE_LIMIT_CACHE) >= 128:
        _WORKSPACE_LIMIT_CACHE.clear()
    _WORKSPACE_LIMIT_CACHE[cache_key] = (time.monotonic(), limit)
    return limit


def _upload_pdf(token: str, file_path: str, *, filename: str | None = None) -> str:
    if not file_path.lower().endswith(".pdf"):
        raise ValueError("Only PDF attachments are supported")
    file_size = os.path.getsize(file_path)
    filename = filename or os.path.basename(file_path)
    multi_part = file_size > _MAX_SINGLE_PART_BYTES
    if file_size > _workspace_upload_limit(token):
        raise NotionWorkspaceLimitError("Notion PDF attachment exceeds the workspace upload limit")
    created = _request(
        "POST",
        "/v1/file_uploads",
        token,
        json={
            "mode": "multi_part" if multi_part else "single_part",
            "filename": filename,
            "content_type": "application/pdf",
            **({"number_of_parts": math.ceil(file_size / _NOTION_PART_BYTES)} if multi_part else {}),
        },
    )
    if not _success(created):
        raise _error(created)
    upload_id = _uuid(_json(created).get("id"), "file upload ID")
    if not multi_part:
        with open(file_path, "rb") as stream:
            sent = _request(
                "POST",
                f"/v1/file_uploads/{upload_id}/send",
                token,
                files={"file": (filename, stream, "application/pdf")},
            )
        if not _success(sent):
            raise _error(sent)
        if _json(sent).get("status") != "uploaded":
            raise RuntimeError("Notion file upload was not marked uploaded")
        return upload_id

    with open(file_path, "rb") as stream:
        part_number = 1
        while chunk := stream.read(_NOTION_PART_BYTES):
            sent = _request(
                "POST",
                f"/v1/file_uploads/{upload_id}/send",
                token,
                data={"part_number": str(part_number)},
                files={"file": (filename, chunk, "application/pdf")},
            )
            if not _success(sent):
                raise _error(sent)
            part_number += 1
    completed = _request("POST", f"/v1/file_uploads/{upload_id}/complete", token)
    if not _success(completed):
        raise _error(completed)
    if _json(completed).get("status") != "uploaded":
        raise RuntimeError("Notion file upload was not marked uploaded")
    return upload_id


def test_notion_connection(config: dict[str, Any] | None, credentials: dict[str, Any] | None) -> dict[str, Any]:
    """Validate a token and data source without creating content."""
    cfg = config or {}
    token = (credentials or {}).get("api_token") or ""
    if not token:
        return {"success": False, "message": "Notion API token is required"}
    try:
        data_source_id = _resolve_data_source(token, cfg)
        response = _request("GET", f"/v1/data_sources/{data_source_id}", token)
        if not _success(response):
            raise _error(response)
        title_name = _title_property(_json(response).get("properties") or {}, cfg.get("title_property"))
        return {"success": True, "message": f"Notion connection ready ({title_name})"}
    except (requests.RequestException, ValueError, RuntimeError):
        logger.warning("Notion connection test failed")
        return {"success": False, "message": "Notion connection could not be verified"}


test_notion_connection.__test__ = False


def upload_to_notion(
    file_path: str, cfg: dict[str, Any], creds: dict[str, Any], task_id: str, *, file_id: int | None = None
) -> dict[str, Any]:
    token = creds.get("api_token") or ""
    if not token:
        raise ValueError("Notion integration is missing api_token")
    data_source_id = _resolve_data_source(token, cfg)
    metadata = _metadata(file_path)
    filename = os.path.basename(file_path)
    title = (_text(metadata.get("title")) or _text(metadata.get("filename")) or filename)[:200]
    document_url = _document_url(cfg, file_id)
    attachment_id = None
    delivery_mode = "metadata"
    policy = str(cfg.get("size_policy") or cfg.get("oversize_policy") or "stop").lower()
    if policy not in {"stop", "link"}:
        raise ValueError("Notion size policy must be stop or link")
    if cfg.get("attach_pdf"):
        upload_path = file_path
        temporary_path = None
        try:
            if cfg.get("optimize_pdf") or cfg.get("lossless_optimize"):
                from app.utils.pdf_delivery import optimize_pdf_bytes

                optimized = optimize_pdf_bytes(file_path)
                if optimized is not None:
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temporary:
                        temporary.write(optimized)
                        temporary_path = temporary.name
                    upload_path = temporary_path
                    delivery_mode = "optimized"
            attachment_id = _upload_pdf(token, upload_path, filename=filename)
            if delivery_mode != "optimized":
                delivery_mode = "multipart" if os.path.getsize(upload_path) > _MAX_SINGLE_PART_BYTES else "original"
        except NotionWorkspaceLimitError:
            if policy != "link":
                raise
            if not document_url:
                raise ValueError("Notion link fallback requires a configured HTTPS URL and file ID") from None
            delivery_mode = "link"
        finally:
            if temporary_path:
                os.unlink(temporary_path)
    schema_response = _request("GET", f"/v1/data_sources/{data_source_id}", token)
    if not _success(schema_response):
        raise _error(schema_response)
    title_name = _title_property(_json(schema_response).get("properties") or {}, cfg.get("title_property"))
    payload: dict[str, Any] = {
        "parent": {"data_source_id": data_source_id},
        "properties": {title_name: {"title": _rich_text(title)}},
        "children": [],
    }
    lines = [f"DocuElevate file: {filename}"]
    if summary := _text(metadata.get("summary")) or _text(metadata.get("description")):
        lines.append(f"Summary: {summary}")
    if tags := _text(metadata.get("tags")):
        lines.append(f"Tags: {tags}")
    document_date = _text(metadata.get("date"))
    if document_date:
        lines.append(f"Document date: {document_date}")
    else:
        lines.append(f"Processed date: {datetime.now(timezone.utc).date().isoformat()}")
    payload["children"] = [
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich_text(line)}} for line in lines
    ]
    if document_url:
        payload["children"].append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Document: "}},
                        {"type": "text", "text": {"content": "Open in DocuElevate", "link": {"url": document_url}}},
                    ]
                },
            }
        )
    if attachment_id:
        payload["children"].append(
            {"object": "block", "type": "file", "file": {"type": "file_upload", "file_upload": {"id": attachment_id}}}
        )
    try:
        response = _request("POST", "/v1/pages", token, json=payload)
    except NotionTransportError as exc:
        raise NotionPageCreationUncertain(
            "Notion page creation outcome is unknown; inspect Notion before retrying"
        ) from exc
    if 500 <= response.status_code < 600:
        raise NotionPageCreationUncertain("Notion page creation outcome is unknown; inspect Notion before retrying")
    if not _success(response):
        raise _error(response)
    try:
        body = _json(response)
        page_id = _uuid(body.get("id"), "page ID")
    except (RuntimeError, ValueError) as exc:
        raise NotionPageCreationUncertain(
            "Notion page creation outcome is unknown; inspect Notion before retrying"
        ) from exc
    return {
        "status": "Completed",
        "notion_page_id": page_id,
        "notion_url": body.get("url"),
        "delivery_mode": delivery_mode,
    }


@celery.task(
    base=UploadTaskWithRetry, bind=True, dont_autoretry_for=(NotionPageCreationUncertain, NotionWorkspaceLimitError)
)
def upload_to_notion_global(self, file_path: str, file_id: int | None = None):
    """Queue the existing provider implementation for the global destination."""
    task_id = self.request.id
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    if not getattr(settings, "notion_enabled", False) or getattr(settings, "multi_user_enabled", False):
        raise ValueError("Global Notion is disabled for this deployment")
    token = getattr(settings, "notion_api_token", None)
    if not isinstance(token, str) or not token.strip():
        raise ValueError("Notion API token is not configured")
    parent_ids = [
        value.strip()
        for value in (
            getattr(settings, "notion_data_source_id", None),
            getattr(settings, "notion_database_id", None),
        )
        if isinstance(value, str) and value.strip()
    ]
    if len(parent_ids) != 1:
        raise ValueError("Exactly one Notion data source or database must be configured")
    cfg = {
        "data_source_id": parent_ids[0]
        if isinstance(getattr(settings, "notion_data_source_id", None), str)
        and getattr(settings, "notion_data_source_id", "").strip()
        else None,
        "database_id": parent_ids[0]
        if isinstance(getattr(settings, "notion_database_id", None), str)
        and getattr(settings, "notion_database_id", "").strip()
        else None,
        "title_property": getattr(settings, "notion_title_property", None),
        "attach_pdf": getattr(settings, "notion_attach_pdf", False),
        "document_url_base": getattr(settings, "notion_document_url_base", None),
    }
    log_task_progress(
        task_id,
        "upload_to_notion",
        "in_progress",
        f"Uploading to Notion: {os.path.basename(file_path)}",
        file_id=file_id,
    )
    try:
        result = upload_to_notion(file_path, cfg, {"api_token": token}, task_id, file_id=file_id)
    except NotionPageCreationUncertain:
        log_task_progress(
            task_id,
            "upload_to_notion",
            "failure",
            "Notion page creation outcome is uncertain; inspect Notion before retrying",
            file_id=file_id,
        )
        raise
    except Exception as exc:
        logger.warning("[%s] Notion upload failed (%s)", task_id, type(exc).__name__)
        log_task_progress(task_id, "upload_to_notion", "failure", "Notion upload failed", file_id=file_id)
        raise
    log_task_progress(task_id, "upload_to_notion", "success", "Uploaded to Notion", file_id=file_id)
    return {"status": "Completed", "file_path": file_path, **result}
