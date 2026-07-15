"""Distributed-lock coverage for the Dropbox corpus coordinator."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
def test_import_coordinator_lock_is_owner_scoped():
    from app.tasks.dropbox_corpus_import import (
        _IMPORT_COORDINATOR_LOCK_TTL_SECONDS,
        _acquire_import_coordinator_lock,
    )

    client = MagicMock()
    client.set.return_value = True
    with (
        patch("app.tasks.dropbox_corpus_import._get_import_coordinator_redis_client", return_value=client),
        patch("app.tasks.dropbox_corpus_import.uuid.uuid4", return_value="owner-token"),
    ):
        acquired = _acquire_import_coordinator_lock("job-123")

    assert acquired == (
        client,
        "docuelevate:dropbox-corpus-import:job-123:coordinator",
        "owner-token",
    )
    client.set.assert_called_once_with(
        "docuelevate:dropbox-corpus-import:job-123:coordinator",
        "owner-token",
        ex=_IMPORT_COORDINATOR_LOCK_TTL_SECONDS,
        nx=True,
    )


@pytest.mark.unit
def test_import_coordinator_lock_reports_contention():
    from app.tasks.dropbox_corpus_import import _acquire_import_coordinator_lock

    client = MagicMock()
    client.set.return_value = False
    with patch(
        "app.tasks.dropbox_corpus_import._get_import_coordinator_redis_client",
        return_value=client,
    ):
        assert _acquire_import_coordinator_lock("job-123") is None


@pytest.mark.unit
def test_import_coordinator_release_warns_if_owner_changed(caplog):
    from app.tasks.dropbox_corpus_import import _release_import_coordinator_lock

    client = MagicMock()
    client.eval.return_value = 0

    _release_import_coordinator_lock(client, "corpus-lock", "owner-token")

    assert "lock owner changed" in caplog.text


@pytest.mark.unit
def test_import_coordinator_lock_is_renewed_only_for_its_owner():
    from app.tasks.dropbox_corpus_import import (
        _IMPORT_COORDINATOR_LOCK_RENEWAL_SECONDS,
        _IMPORT_COORDINATOR_LOCK_TTL_SECONDS,
        _RENEW_IMPORT_LOCK_SCRIPT,
        _maintain_import_coordinator_lock,
    )

    client = MagicMock()
    client.eval.return_value = 1
    stop_event = MagicMock()
    stop_event.wait.side_effect = [False, True]
    lock_lost_event = MagicMock()

    _maintain_import_coordinator_lock(
        client,
        "corpus-lock",
        "owner-token",
        stop_event,
        lock_lost_event,
    )

    assert stop_event.wait.call_args_list[0].args == (_IMPORT_COORDINATOR_LOCK_RENEWAL_SECONDS,)
    client.eval.assert_called_once_with(
        _RENEW_IMPORT_LOCK_SCRIPT,
        1,
        "corpus-lock",
        "owner-token",
        _IMPORT_COORDINATOR_LOCK_TTL_SECONDS,
    )
    lock_lost_event.set.assert_not_called()


@pytest.mark.unit
def test_import_coordinator_lock_loss_aborts_page_processing():
    from app.tasks.dropbox_corpus_import import (
        CorpusCoordinatorLockLost,
        _ensure_import_coordinator_lock,
        _maintain_import_coordinator_lock,
    )

    client = MagicMock()
    client.eval.return_value = 0
    stop_event = MagicMock()
    stop_event.wait.return_value = False
    lock_lost_event = MagicMock()

    _maintain_import_coordinator_lock(
        client,
        "corpus-lock",
        "owner-token",
        stop_event,
        lock_lost_event,
    )
    lock_lost_event.set.assert_called_once_with()
    lock_lost_event.is_set.return_value = True

    with pytest.raises(CorpusCoordinatorLockLost, match="coordinator lock was lost"):
        _ensure_import_coordinator_lock(lock_lost_event)


@pytest.mark.unit
def test_import_coordinator_renewal_exception_signals_lock_loss():
    from app.tasks.dropbox_corpus_import import _maintain_import_coordinator_lock

    client = MagicMock()
    client.eval.side_effect = RuntimeError("redis unavailable")
    stop_event = MagicMock()
    stop_event.wait.return_value = False
    lock_lost_event = MagicMock()

    _maintain_import_coordinator_lock(
        client,
        "corpus-lock",
        "owner-token",
        stop_event,
        lock_lost_event,
    )

    client.eval.assert_called_once()
    lock_lost_event.set.assert_called_once_with()


@pytest.mark.unit
def test_import_coordinator_uses_late_ack_and_worker_loss_rejection():
    from app.tasks.dropbox_corpus_import import run_dropbox_corpus_import

    assert run_dropbox_corpus_import.acks_late is True
    assert run_dropbox_corpus_import.reject_on_worker_lost is True


@pytest.mark.unit
def test_duplicate_import_coordinator_returns_benign_result():
    from app.tasks.dropbox_corpus_import import run_dropbox_corpus_import

    with (
        patch("app.tasks.dropbox_corpus_import._acquire_import_coordinator_lock", return_value=None),
        patch("app.tasks.dropbox_corpus_import._run_dropbox_corpus_import") as run_import,
    ):
        result = run_dropbox_corpus_import.run("job-123")

    assert result == {"status": "already_running", "job_id": "job-123"}
    run_import.assert_not_called()


@pytest.mark.unit
def test_redelivered_import_coordinator_schedules_one_recovery_wakeup():
    from app.tasks.dropbox_corpus_import import (
        _IMPORT_COORDINATOR_RECOVERY_DELAY_SECONDS,
        run_dropbox_corpus_import,
    )

    with (
        patch("app.tasks.dropbox_corpus_import._acquire_import_coordinator_lock", return_value=None),
        patch.object(run_dropbox_corpus_import, "apply_async") as apply_async,
    ):
        result = run_dropbox_corpus_import.run("job-123", recover_lock=True)

    assert result == {"status": "waiting_for_lock", "job_id": "job-123"}
    apply_async.assert_called_once_with(
        args=["job-123"],
        kwargs={"recover_lock": True},
        countdown=_IMPORT_COORDINATOR_RECOVERY_DELAY_SECONDS,
        priority=9,
    )


@pytest.mark.unit
def test_import_coordinator_releases_only_through_owner_checked_helper():
    from app.tasks.dropbox_corpus_import import run_dropbox_corpus_import

    client = MagicMock()
    lock = (client, "corpus-lock", "owner-token")
    with (
        patch("app.tasks.dropbox_corpus_import._acquire_import_coordinator_lock", return_value=lock),
        patch("app.tasks.dropbox_corpus_import._run_dropbox_corpus_import", side_effect=RuntimeError("boom")),
        patch("app.tasks.dropbox_corpus_import._release_import_coordinator_lock") as release,
        pytest.raises(RuntimeError, match="boom"),
    ):
        run_dropbox_corpus_import.run("job-123")

    release.assert_called_once_with(client, "corpus-lock", "owner-token")


@pytest.mark.unit
def test_next_page_is_scheduled_after_coordinator_lock_release():
    from app.tasks.dropbox_corpus_import import run_dropbox_corpus_import

    client = MagicMock()
    events = []
    lock = (client, "corpus-lock", "owner-token")
    with (
        patch("app.tasks.dropbox_corpus_import._acquire_import_coordinator_lock", return_value=lock),
        patch(
            "app.tasks.dropbox_corpus_import._run_dropbox_corpus_import",
            return_value={
                "status": "running",
                "job_id": "job-123",
                "_schedule_next_page": True,
                "_schedule_ocr_backlog": False,
            },
        ),
        patch(
            "app.tasks.dropbox_corpus_import._release_import_coordinator_lock",
            side_effect=lambda *_args: events.append("release"),
        ),
        patch(
            "app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_import",
            side_effect=lambda *_args: events.append("schedule"),
        ),
    ):
        result = run_dropbox_corpus_import.run("job-123")

    assert events == ["release", "schedule"]
    assert result == {"status": "running", "job_id": "job-123"}


@pytest.mark.unit
def test_paused_resume_is_scheduled_after_coordinator_lock_release():
    from app.tasks.dropbox_corpus_import import run_dropbox_corpus_import

    client = MagicMock()
    events = []
    lock = (client, "corpus-lock", "owner-token")
    with (
        patch("app.tasks.dropbox_corpus_import._acquire_import_coordinator_lock", return_value=lock),
        patch(
            "app.tasks.dropbox_corpus_import._run_dropbox_corpus_import",
            return_value={
                "status": "paused",
                "job_id": "job-123",
                "resume_in_seconds": 30,
                "_schedule_resume_in_seconds": 30,
            },
        ),
        patch(
            "app.tasks.dropbox_corpus_import._release_import_coordinator_lock",
            side_effect=lambda *_args: events.append("release"),
        ),
        patch(
            "app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_import",
            side_effect=lambda *_args, **_kwargs: events.append("schedule"),
        ) as schedule,
    ):
        result = run_dropbox_corpus_import.run("job-123")

    assert events == ["release", "schedule"]
    schedule.assert_called_once_with("job-123", countdown=30)
    assert result == {
        "status": "paused",
        "job_id": "job-123",
        "resume_in_seconds": 30,
    }


@pytest.mark.unit
def test_ocr_backlog_is_scheduled_after_coordinator_lock_release():
    from app.tasks.dropbox_corpus_import import run_dropbox_corpus_import

    client = MagicMock()
    lock = (client, "corpus-lock", "owner-token")
    with (
        patch("app.tasks.dropbox_corpus_import._acquire_import_coordinator_lock", return_value=lock),
        patch(
            "app.tasks.dropbox_corpus_import._run_dropbox_corpus_import",
            return_value={
                "status": "completed",
                "job_id": "job-123",
                "_schedule_next_page": False,
                "_schedule_ocr_backlog": True,
            },
        ),
        patch("app.tasks.dropbox_corpus_import._release_import_coordinator_lock"),
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_ocr_backlog") as schedule,
    ):
        result = run_dropbox_corpus_import.run("job-123")

    schedule.assert_called_once_with("job-123")
    assert result == {"status": "completed", "job_id": "job-123"}


@pytest.mark.unit
def test_completed_page_without_followup_schedules_nothing():
    from app.tasks.dropbox_corpus_import import run_dropbox_corpus_import

    client = MagicMock()
    lock = (client, "corpus-lock", "owner-token")
    with (
        patch("app.tasks.dropbox_corpus_import._acquire_import_coordinator_lock", return_value=lock),
        patch(
            "app.tasks.dropbox_corpus_import._run_dropbox_corpus_import",
            return_value={"status": "completed", "job_id": "job-123"},
        ),
        patch("app.tasks.dropbox_corpus_import._release_import_coordinator_lock"),
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_import") as next_page,
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_ocr_backlog") as ocr_backlog,
    ):
        result = run_dropbox_corpus_import.run("job-123")

    next_page.assert_not_called()
    ocr_backlog.assert_not_called()
    assert result == {"status": "completed", "job_id": "job-123"}
