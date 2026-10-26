"""Read-only MCP adapter for DocuElevate knowledge search.

The adapter deliberately keeps the DocuElevate API token in the process
environment.  It never accepts credentials as tool arguments and delegates
document authorization to DocuElevate's existing API.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

logger = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:8000"
DEFAULT_LIMIT = 8
MAX_LIMIT = 50
DEFAULT_SCORE_THRESHOLD = 0.25
CONTRACT_VERSION = "1.0"


class DocuElevateClient:
    """Small, authenticated client for the documented knowledge API."""

    def __init__(self, base_url: str | None = None, token: str | None = None, session: Any = None):
        self.base_url = _validate_base_url(base_url or os.getenv("DOCUELEVATE_URL", DEFAULT_URL))
        self.token = token or os.getenv("DOCUELEVATE_API_TOKEN", "")
        if not self.token:
            raise ValueError("DOCUELEVATE_API_TOKEN is not configured")
        self._owns_session = session is None
        self.session = session or requests.Session()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if method == "POST":
            headers["Content-Type"] = "application/json"
        try:
            response = self.session.request(
                method,
                urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/")),
                headers=headers,
                timeout=(5, 30),
                allow_redirects=False,
                **kwargs,
            )
        except requests.RequestException:
            raise RuntimeError("DocuElevate is unavailable") from None
        finally:
            if self._owns_session:
                self.session.close()

        if response.status_code in {401, 403}:
            raise RuntimeError("DocuElevate authentication or access was rejected")
        if response.status_code == 404:
            raise RuntimeError("DocuElevate document was not found")
        if response.status_code == 429:
            raise RuntimeError("DocuElevate rate limit reached")
        if response.status_code >= 500:
            raise RuntimeError("DocuElevate returned a server error")
        if 300 <= response.status_code < 400 or response.is_redirect:
            raise RuntimeError("DocuElevate returned an unsafe redirect")
        if not 200 <= response.status_code < 300:
            raise RuntimeError("DocuElevate rejected the request")
        try:
            payload = response.json()
        except (ValueError, requests.RequestException):
            raise RuntimeError("DocuElevate returned invalid JSON") from None
        if not isinstance(payload, dict):
            raise RuntimeError("DocuElevate returned an invalid response")
        return payload

    def search(
        self,
        query: str,
        limit: int = DEFAULT_LIMIT,
        score_threshold: float | None = DEFAULT_SCORE_THRESHOLD,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/knowledge/search",
            json={"query": query, "limit": limit, "score_threshold": score_threshold},
        )

    def document(self, document_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/knowledge/documents/{document_id}")


def _validate_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("DOCUELEVATE_URL must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("DOCUELEVATE_URL must not contain credentials, query parameters, or fragments")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("DOCUELEVATE_URL must use HTTPS outside localhost")
    return value.rstrip("/")


def _client() -> DocuElevateClient:
    return DocuElevateClient()


def _validate_search(query: str, limit: int, score_threshold: float | None) -> None:
    if not isinstance(query, str) or not 1 <= len(query) <= 4000:
        raise ValueError("query must contain between 1 and 4000 characters")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    if score_threshold is not None and (
        isinstance(score_threshold, bool)
        or not isinstance(score_threshold, (int, float))
        or not 0 <= score_threshold <= 1
    ):
        raise ValueError("score_threshold must be between 0 and 1, or null")


def _normalize_sources(payload: dict[str, Any], base_url: str) -> dict[str, Any]:
    """Make API-relative citations usable without changing response fields."""
    result = dict(payload)
    items = result.get("results")
    if isinstance(items, list):
        normalized_items = []
        for item in items:
            normalized_item = item
            if isinstance(item, dict) and isinstance(item.get("source_url"), str):
                normalized_item = dict(item)
                parsed = urlparse(normalized_item["source_url"])
                if not parsed.scheme and not parsed.netloc:
                    normalized_item["source_url"] = urljoin(
                        base_url.rstrip("/") + "/", normalized_item["source_url"].lstrip("/")
                    )
            normalized_items.append(normalized_item)
        result["results"] = normalized_items
    if isinstance(result.get("source_url"), str):
        parsed = urlparse(result["source_url"])
        if not parsed.scheme and not parsed.netloc:
            result["source_url"] = urljoin(base_url.rstrip("/") + "/", result["source_url"].lstrip("/"))
    return result


def _tool_result(payload: dict[str, Any]) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        structuredContent=payload,
    )


def _tool_error(error: RuntimeError) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=str(error))],
        isError=True,
    )


def search_documents(
    query: str,
    limit: int = DEFAULT_LIMIT,
    score_threshold: float | None = DEFAULT_SCORE_THRESHOLD,
) -> CallToolResult:
    """Search accessible DocuElevate knowledge and return cited passages."""
    _validate_search(query, limit, score_threshold)
    client = _client()
    try:
        return _tool_result(_normalize_sources(client.search(query, limit, score_threshold), client.base_url))
    except RuntimeError as error:
        return _tool_error(error)


def get_document(document_id: int) -> CallToolResult:
    """Retrieve one accessible document and its authoritative OCR text."""
    if not isinstance(document_id, int) or isinstance(document_id, bool) or document_id < 1:
        raise ValueError("document_id must be a positive integer")
    client = _client()
    try:
        return _tool_result(_normalize_sources(client.document(document_id), client.base_url))
    except RuntimeError as error:
        return _tool_error(error)


mcp = MCPServer("DocuElevate", version=CONTRACT_VERSION)
_READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
mcp.tool(annotations=_READ_ONLY)(search_documents)
mcp.tool(annotations=_READ_ONLY)(get_document)


if __name__ == "__main__":
    mcp.run()
