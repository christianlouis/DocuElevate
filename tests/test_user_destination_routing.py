"""Focused tests for owner-aware destination dispatch."""

from unittest.mock import MagicMock, patch

import pytest

from app.tasks.send_to_all import UserDestinationRoutingError, dispatch_document_destinations


def _task_mock():
    task = MagicMock()
    task.delay.return_value.id = "queued"
    return task


@pytest.mark.unit
def test_compatibility_mode_keeps_global_fallback_and_folder_overrides():
    user_task = _task_mock()
    global_task = _task_mock()

    with patch("app.tasks.send_to_all.settings.strict_user_destination_routing", False):
        dispatch_document_destinations(
            "/tmp/document.pdf",
            owner_id="alice",
            file_id=7,
            destination_count=0,
            user_task=user_task,
            global_task=global_task,
            folder_overrides={"s3": "archive/pdfa/"},
        )

    user_task.delay.assert_not_called()
    global_task.delay.assert_called_once_with("/tmp/document.pdf", True, 7, folder_overrides={"s3": "archive/pdfa/"})


@pytest.mark.unit
def test_strict_mode_never_falls_back_when_personal_destination_is_missing():
    user_task = _task_mock()
    global_task = _task_mock()

    with patch("app.tasks.send_to_all.settings.strict_user_destination_routing", True):
        with pytest.raises(UserDestinationRoutingError, match="No active personal destinations"):
            dispatch_document_destinations(
                "/tmp/document.pdf",
                owner_id="alice",
                file_id=7,
                destination_count=0,
                user_task=user_task,
                global_task=global_task,
            )

    user_task.delay.assert_not_called()
    global_task.delay.assert_not_called()


@pytest.mark.unit
def test_strict_mode_never_falls_back_when_personal_lookup_fails():
    user_task = _task_mock()
    global_task = _task_mock()

    with (
        patch("app.tasks.send_to_all.settings.strict_user_destination_routing", True),
        patch("app.tasks.send_to_all.get_user_destination_count", side_effect=RuntimeError("db unavailable")),
    ):
        with pytest.raises(UserDestinationRoutingError, match="Could not resolve destinations"):
            dispatch_document_destinations(
                "/tmp/document.pdf",
                owner_id="alice",
                file_id=7,
                user_task=user_task,
                global_task=global_task,
            )

    user_task.delay.assert_not_called()
    global_task.delay.assert_not_called()


@pytest.mark.unit
def test_personal_destination_is_selected_when_available():
    user_task = _task_mock()
    global_task = _task_mock()

    dispatch_document_destinations(
        "/tmp/document.pdf",
        owner_id="alice",
        file_id=7,
        destination_count=1,
        user_task=user_task,
        global_task=global_task,
    )

    user_task.delay.assert_called_once_with("/tmp/document.pdf", "alice", 7)
    global_task.delay.assert_not_called()
