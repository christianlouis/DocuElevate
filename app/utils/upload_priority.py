"""Keep admitted document priorities and provenance through task fan-out."""

from datetime import datetime, timezone
from typing import Any

BULK_HEADERS = ("bulk_upload", "bulk_accepted_at", "bulk_batch_id")
IMAP_HEADERS = ("imap_backlog",)
AGE_SECONDS = 15 * 60


def inherit_upload_priority(
    headers: dict[str, Any], properties: dict[str, Any], request: Any, *, now: datetime | None = None
) -> None:
    """Copy provenance to child tasks and apply the relevant publication priority.

    Redis consumes low priority numbers first.  Ordinary mail tasks retain their
    existing priority.  A bounded outbox and prefetch=1 keep urgent arrivals from
    waiting behind an entire corpus; aging prevents fresh small batches from
    perpetually displacing older bulk documents at subsequent pipeline stages.
    Historical IMAP backlog work is deliberately not aged: its publisher assigns
    priority 6 and that priority follows the document through the pipeline.
    """
    parent_headers = getattr(request, "headers", None) or {}
    is_bulk = bool(headers.get("bulk_upload") or parent_headers.get("bulk_upload"))
    is_imap_backlog = bool(headers.get("imap_backlog") or parent_headers.get("imap_backlog"))
    if not is_bulk and not is_imap_backlog:
        return
    for key in (*BULK_HEADERS, *IMAP_HEADERS):
        if key not in headers and key in parent_headers:
            headers[key] = parent_headers[key]
    priority = properties.get("priority")
    parent_priority = (getattr(request, "delivery_info", None) or {}).get("priority")
    if parent_priority is None:
        parent_priority = 6
    # Celery supplies a default 0 even when the child publisher did not set one.
    # Bulk and historical IMAP descendants must inherit their document's priority.
    if parent_headers.get("bulk_upload"):
        priority = parent_priority
    elif parent_headers.get("imap_backlog"):
        priority = parent_priority
    if priority is None:
        priority = 6
    accepted = headers.get("bulk_accepted_at") if is_bulk else None
    if accepted:
        try:
            accepted_at = datetime.fromisoformat(str(accepted).replace("Z", "+00:00"))
            if accepted_at.tzinfo is None:
                accepted_at = accepted_at.replace(tzinfo=timezone.utc)
            if ((now or datetime.now(timezone.utc)) - accepted_at).total_seconds() >= AGE_SECONDS:
                priority = 0
        except (ValueError, TypeError):
            pass
    properties["priority"] = max(0, min(9, int(priority)))
