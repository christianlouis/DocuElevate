"""
Diagnostic API endpoints
"""

import datetime
import logging

import redis as redis_lib
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.auth import require_login
from app.config import settings
from app.database import engine

# Set up logging
logger = logging.getLogger(__name__)

_DEFAULT_REDIS_URL = "redis://localhost:6379/0"

router = APIRouter()


@router.get("/diagnostic/health")
@require_login
async def health_check(request: Request):
    """
    System health endpoint for monitoring tools (Grafana, Uptime Kuma, etc.).

    Checks database connectivity and Redis availability and returns a
    machine-readable summary that monitoring systems can scrape.

    **Authentication:** Required (no-op when AUTH_ENABLED=False)

    **Response (200 OK) – all subsystems healthy:**
    ```json
    {
      "status": "healthy",
      "version": "1.2.3",
      "timestamp": "2024-01-15T10:30:00+00:00",
      "checks": {
        "database": {"status": "ok"},
        "redis":    {"status": "ok"}
      }
    }
    ```

    **Response (200 OK) – one or more subsystems degraded:**
    ```json
    {
      "status": "degraded",
      "version": "1.2.3",
      "timestamp": "2024-01-15T10:30:00+00:00",
      "checks": {
        "database": {"status": "ok"},
        "redis":    {"status": "error", "detail": "Connection refused"}
      }
    }
    ```

    The outer ``status`` field is always one of:
    - ``"healthy"``  – all checks passed
    - ``"degraded"`` – at least one non-critical check failed
    - ``"unhealthy"`` – a critical check failed (currently: database)
    """
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    checks: dict[str, dict[str, str]] = {}

    # ── Database check ─────────────────────────────────────────────────────
    db_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
        db_ok = True
    except Exception as exc:
        logger.warning("Health check: database probe failed: %s", exc)
        checks["database"] = {"status": "error", "detail": str(exc)}

    # ── Redis check ────────────────────────────────────────────────────────
    try:
        redis_url = settings.redis_url or _DEFAULT_REDIS_URL
        r = redis_lib.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        r.ping()
        checks["redis"] = {"status": "ok"}
    except Exception as exc:
        logger.warning("Health check: Redis probe failed: %s", exc)
        checks["redis"] = {"status": "error", "detail": str(exc)}

    # ── Overall status ─────────────────────────────────────────────────────
    if not db_ok:
        overall = "unhealthy"
    elif any(v.get("status") != "ok" for v in checks.values()):
        overall = "degraded"
    else:
        overall = "healthy"

    http_status = 503 if overall == "unhealthy" else 200

    payload = {
        "status": overall,
        "version": settings.version,
        "timestamp": timestamp,
        "checks": checks,
    }

    return JSONResponse(content=payload, status_code=http_status)


@router.post("/diagnostic/test-notification")
@require_login
async def test_notification(request: Request):
    # Add request_time to request.state
    import datetime

    request.state.request_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    """
    Send a test notification through all configured notification channels
    """
    from app.utils.notification import send_notification

    try:
        notification_urls = getattr(settings, "notification_urls", [])
        if not notification_urls:
            return {
                "status": "warning",
                "message": "No notification services configured. Add notification URLs to your configuration.",
            }

        # Send a test notification
        hostname = settings.external_hostname or "Document Processor"
        result = send_notification(
            title=f"Test Notification from {hostname}",
            message=(
                f"This is a test notification sent at {request.state.request_time}. "
                "If you're receiving this, notifications are working!"
            ),
            notification_type="success",
            tags=["test", "notification", "diagnostic"],
        )

        if result:
            logger.info("Test notification sent successfully")
            return {
                "status": "success",
                "message": f"Test notification sent successfully to {len(notification_urls)} service(s)",
                "services_count": len(notification_urls),
            }
        else:
            logger.warning("Test notification send attempt returned False")
            return {
                "status": "error",
                "message": "Failed to send test notification. Check application logs for details.",
            }

    except Exception as e:
        logger.exception(f"Error sending test notification: {e}")
        return {"status": "error", "message": f"Error sending notification: {str(e)}"}
