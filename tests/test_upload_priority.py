"""Fairness must survive the fan-out from ingestion into OCR/AI/delivery."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.utils.upload_priority import inherit_upload_priority


def test_mail_priority_unchanged():
    properties = {"priority": 0}
    headers = {}
    inherit_upload_priority(headers, properties, SimpleNamespace(headers={}, delivery_info={"priority": 0}))
    assert properties == {"priority": 0}
    assert headers == {}


def test_downstream_bulk_inherits_priority_and_provenance():
    now = datetime.now(timezone.utc)
    parent = {"bulk_upload": True, "bulk_batch_id": "batch-1", "bulk_accepted_at": now.isoformat()}
    headers, properties = {}, {"priority": 0}
    inherit_upload_priority(
        headers, properties, SimpleNamespace(headers=parent, delivery_info={"priority": 6}), now=now
    )
    assert headers == parent
    assert properties["priority"] == 6


def test_small_batch_priority_survives_pipeline():
    properties = {}
    inherit_upload_priority(
        {}, properties, SimpleNamespace(headers={"bulk_upload": True}, delivery_info={"priority": 2})
    )
    assert properties["priority"] == 2


def test_aged_bulk_is_promoted_on_next_stage():
    now = datetime.now(timezone.utc)
    headers = {"bulk_upload": True, "bulk_accepted_at": (now - timedelta(minutes=16)).isoformat()}
    properties = {"priority": 6}
    inherit_upload_priority(headers, properties, None, now=now)
    assert properties["priority"] == 0


def test_malformed_timestamp_does_not_break_publication():
    headers, properties = {"bulk_upload": True, "bulk_accepted_at": "invalid"}, {"priority": 6}
    inherit_upload_priority(headers, properties, None)
    assert properties["priority"] == 6
