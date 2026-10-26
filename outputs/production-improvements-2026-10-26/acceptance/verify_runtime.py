#!/usr/bin/env python3
"""Read-only DocuElevate acceptance verification.

The script performs GET requests only. It reports IDs, booleans, status values,
step names, and counts; it never prints document text, response bodies, tokens,
paths, notification messages, or task arguments.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterable
from typing import Any

import requests

DEFAULT_IDS = (6571, 6583, 6584)
RETRYABLE_STEPS = {
    "process_document",
    "process_with_ocr",
    "process_with_azure_document_intelligence",
    "extract_metadata_with_gpt",
    "embed_metadata_into_pdf",
}


def get_json(session: requests.Session, url: str) -> tuple[int, Any]:
    response = session.get(url, timeout=20)
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, None


def step_summary(logs: Iterable[dict[str, Any]]) -> list[dict[str, str | None]]:
    return [
        {"name": str(item.get("step_name", "")), "status": item.get("status")}
        for item in logs
        if isinstance(item, dict)
    ]


def verify_file(session: requests.Session, base: str, file_id: int, token: str) -> dict[str, Any]:
    status_code, payload = get_json(session, f"{base}/api/files/{file_id}")
    result: dict[str, Any] = {
        "file_id": file_id,
        "detail_http_status": status_code,
        "detail_reachable": status_code == 200 and isinstance(payload, dict),
        "canonical_steps": [],
        "extraction_token_present": False,
        "text_quality_present": False,
        "retry_supported_for_failed_steps": [],
    }
    if not isinstance(payload, dict):
        return result

    logs = payload.get("logs", [])
    result["canonical_steps"] = step_summary(logs)
    processing_status = payload.get("processing_status")
    if isinstance(processing_status, dict):
        quality = processing_status.get("text_quality")
        result["text_quality_present"] = quality is not None
        result["text_quality"] = quality if isinstance(quality, (str, int, float, bool)) else None

    text_response = session.get(f"{base}/api/files/{file_id}/text/processed", timeout=20)
    result["extraction_http_status"] = text_response.status_code
    result["extraction_token_present"] = text_response.status_code == 200 and token.encode() in text_response.content

    failed_steps = {
        item["name"] for item in result["canonical_steps"] if item["status"] in {"failure", "failed"} and item["name"]
    }
    result["retry_supported_for_failed_steps"] = sorted(failed_steps & RETRYABLE_STEPS)
    return result


def verify_search(session: requests.Session, base: str, token: str, file_ids: set[int]) -> dict[str, Any]:
    status_code, payload = get_json(session, f"{base}/api/search?q={token}&per_page=100")
    results = payload.get("results", []) if isinstance(payload, dict) else []
    result_ids = {
        item.get("file_id") for item in results if isinstance(item, dict) and isinstance(item.get("file_id"), int)
    }
    return {
        "search_http_status": status_code,
        "search_reachable": status_code == 200 and isinstance(payload, dict),
        "search_index_match": bool(result_ids & file_ids),
        "search_result_ids": sorted(result_ids & file_ids),
    }


def verify_export(session: requests.Session, base: str, file_id: int) -> dict[str, Any]:
    response = session.get(f"{base}/api/files/{file_id}/download", params={"version": "processed"}, timeout=30)
    return {
        "export_artifact_http_status": response.status_code,
        "export_artifact_retrievable": response.status_code == 200,
        "export_artifact_is_pdf": response.status_code == 200 and response.content.startswith(b"%PDF"),
        "export_artifact_nonempty": response.status_code == 200 and bool(response.content),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("DOCUELEVATE_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--token", required=True, help="Synthetic token; never printed")
    parser.add_argument("--file-id", type=int, action="append", default=[])
    parser.add_argument("--export-file-id", type=int)
    parser.add_argument("--bearer-token", default=os.environ.get("DOCUELEVATE_API_TOKEN"))
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    session = requests.Session()
    if args.bearer_token:
        session.headers.update({"Authorization": f"Bearer {args.bearer_token}"})
    file_ids = set(args.file_id or DEFAULT_IDS)
    report: dict[str, Any] = {
        "read_only": True,
        "file_checks": [verify_file(session, base, file_id, args.token) for file_id in sorted(file_ids)],
        "notification_acceptance": {
            "inbox_http_status": get_json(session, f"{base}/api/user-notifications/inbox?limit=1")[0],
            "provider_send_verified": False,
            "provider_send_note": "No mutating diagnostic send was performed; verify provider delivery separately.",
        },
    }
    report["search"] = verify_search(session, base, args.token, file_ids)
    if args.export_file_id is not None:
        report["export"] = verify_export(session, base, args.export_file_id)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
