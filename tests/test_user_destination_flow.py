"""Focused UI-flow coverage for personal destination branches."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.views.files import _compute_processing_flow


@pytest.mark.unit
def test_personal_destination_branch_uses_safe_integration_label():
    now = datetime.now(timezone.utc)
    log = SimpleNamespace(
        step_name="upload_to_user_integration_42",
        status="success",
        message="Uploaded",
        timestamp=now,
        task_id="task-42",
        detail=None,
    )

    upload_stage = next(
        stage
        for stage in _compute_processing_flow(
            [log], destination_labels={"upload_to_user_integration_42": "Alice Postmark"}
        )
        if stage["key"] == "send_to_all_destinations"
    )

    assert upload_stage["branches"][0]["label"] == "Alice Postmark"
    assert upload_stage["branches"][0]["status"] == "success"


@pytest.mark.unit
def test_personal_dispatch_sequence_keeps_parent_and_latest_retry_status():
    base = datetime(2026, 11, 1, tzinfo=timezone.utc)

    def log(step_name, status, offset, task_id):
        return SimpleNamespace(
            step_name=step_name,
            status=status,
            message=status,
            timestamp=base.replace(second=offset),
            task_id=task_id,
            detail=None,
        )

    logs = [
        log("queue_user_integration_42", "success", 1, "queue-1"),
        log("upload_to_user_integration_42", "failure", 2, "upload-1"),
        log("send_to_user_destinations", "success", 3, "dispatch-1"),
        log("queue_user_integration_42", "success", 4, "queue-2"),
        log("upload_to_user_integration_42", "success", 5, "upload-2"),
    ]

    flow = _compute_processing_flow(
        logs,
        destination_labels={"upload_to_user_integration_42": "Alice Postmark"},
    )
    upload_stage = next(stage for stage in flow if stage["key"] == "send_to_all_destinations")

    assert upload_stage["status"] == "success"
    assert upload_stage["task_id"] == "dispatch-1"
    assert upload_stage["branches"][0]["label"] == "Alice Postmark"
    assert upload_stage["branches"][0]["status"] == "success"
    assert upload_stage["branches"][0]["task_id"] == "upload-2"
