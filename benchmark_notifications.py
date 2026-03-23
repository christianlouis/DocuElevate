import json
import time
import pytest
from app.database import get_db
from app.models import UserNotificationTarget, UserNotificationPreference
from app.main import app
from tests.test_notifications_api import _make_client, _OWNER, _cleanup
import statistics

def run_benchmark(notif_engine, notif_session, client, items_count, iterations=5):
    # Setup
    target = UserNotificationTarget(
        owner_id=_OWNER,
        channel_type="webhook",
        name="My Webhook",
        config=json.dumps({"url": "https://x.com"}),
    )
    notif_session.add(target)
    notif_session.commit()
    notif_session.refresh(target)

    # Generate big payload
    preferences = []
    for i in range(items_count):
        preferences.append({
            "event_type": f"event.type.{i}",
            "channel_type": "webhook",
            "is_enabled": True,
            "target_id": target.id,
        })

    payload = {"preferences": preferences}

    # Warm up
    client.put("/api/user-notifications/preferences", json=payload)

    times = []
    for _ in range(iterations):
        # Alter the values a bit so it's a real update
        for p in payload["preferences"]:
            p["is_enabled"] = not p["is_enabled"]

        start = time.time()
        resp = client.put("/api/user-notifications/preferences", json=payload)
        end = time.time()

        assert resp.status_code == 200
        times.append(end - start)

    return statistics.mean(times)
