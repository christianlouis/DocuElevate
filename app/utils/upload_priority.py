"""Keep an admitted bulk document's priority through its entire task graph."""

from datetime import datetime, timezone
from typing import Any

BULK_HEADERS = ("bulk_upload", "bulk_accepted_at", "bulk_batch_id")
AGE_SECONDS = 15 * 60


def inherit_upload_priority(
    headers: dict[str, Any], properties: dict[str, Any], request: Any, *, now: datetime | None = None
) -> None:
    """Copy bulk provenance to child tasks and promote old work at publication.

    Redis consumes low priority numbers first.  Ordinary mail tasks retain their
    existing priority.  A bounded outbox and prefetch=1 keep urgent arrivals from
    waiting behind an entire corpus; aging prevents fresh small batches from
    perpetually displacing older bulk documents at subsequent pipeline stages.
    """
    parent_headers = getattr(request, "headers", None) or {}
    if not headers.get("bulk_upload") and not parent_headers.get("bulk_upload"):
        return
    for key in BULK_HEADERS:
        if key not in headers and key in parent_headers:
            headers[key] = parent_headers[key]
    priority = properties.get("priority")
    parent_priority = (getattr(request, "delivery_info", None) or {}).get("priority", 6)
    # Celery supplies a default 0 even when the child publisher did not set one.
    # Bulk descendants must inherit their document's priority in that case.
    if parent_headers.get("bulk_upload"):
        priority = parent_priority
    if priority is None:
        priority = 6
    accepted = headers.get("bulk_accepted_at")
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
