"""Tests for resumable Dropbox corpus import and revision deduplication."""

import json
from contextlib import nullcontext
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models import CorpusLlmDailyUsage, DropboxImportJob, IntegrationDirection, IntegrationType, UserIntegration
from app.utils.encryption import encrypt_value


def _integration(db_session) -> UserIntegration:
    integration = UserIntegration(
        owner_id="owner@example.com",
        direction=IntegrationDirection.SOURCE,
        integration_type=IntegrationType.WATCH_FOLDER,
        name="Dropbox archive",
        config=json.dumps({"source_type": "dropbox", "folder_path": "/Documents"}),
        credentials=encrypt_value(
            json.dumps({"app_key": "app-key", "app_secret": "app-secret", "refresh_token": "refresh-token"})
        ),
        is_active=True,
    )
    db_session.add(integration)
    db_session.commit()
    db_session.refresh(integration)
    return integration


def test_dropbox_import_start_queues_owned_source(client, db_session):
    integration = _integration(db_session)
    with patch("app.tasks.dropbox_corpus_import.run_dropbox_corpus_import.apply_async") as apply_async:
        apply_async.return_value.id = "task-1"
        response = client.post("/api/dropbox-imports/", json={"integration_id": integration.id})

    assert response.status_code == 202
    assert response.json()["root_path"] == "/Documents"
    assert response.json()["mode"] == "backfill"
    assert response.json()["state"] == "queued"
    assert response.json()["task_id"] == "task-1"
    apply_async.assert_called_once_with(args=[response.json()["job_id"]], countdown=0, priority=9)


def test_watch_true_up_reuses_completed_cursor(db_session):
    integration = _integration(db_session)
    integration.config = json.dumps(
        {
            "source_type": "dropbox",
            "folder_path": "/Posteingang",
            "true_up_existing": True,
            "recursive": True,
        }
    )
    previous = DropboxImportJob(
        id="completed-job",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Posteingang",
        cursor="cursor-after-true-up",
        state="completed",
    )
    db_session.add(previous)
    db_session.commit()

    with patch("app.tasks.dropbox_corpus_import.run_dropbox_corpus_import.apply_async") as apply_async:
        from app.tasks.dropbox_corpus_import import queue_dropbox_watch_sync

        result = queue_dropbox_watch_sync(integration.id, db_session)

    queued = db_session.query(DropboxImportJob).filter(DropboxImportJob.id == result["job_id"]).one()
    assert result["mode"] == "incremental"
    assert queued.cursor == "cursor-after-true-up"
    assert queued.is_backfill is False
    apply_async.assert_called_once_with(args=[queued.id], countdown=0, priority=9)


def test_watch_true_up_marks_initial_job_as_backfill(db_session):
    integration = _integration(db_session)
    integration.config = json.dumps(
        {
            "source_type": "dropbox",
            "folder_path": "/Posteingang",
            "true_up_existing": True,
            "recursive": True,
        }
    )
    db_session.commit()

    with patch("app.tasks.dropbox_corpus_import.run_dropbox_corpus_import.apply_async"):
        from app.tasks.dropbox_corpus_import import queue_dropbox_watch_sync

        result = queue_dropbox_watch_sync(integration.id, db_session)

    queued = db_session.query(DropboxImportJob).filter(DropboxImportJob.id == result["job_id"]).one()
    assert result["mode"] == "true-up"
    assert queued.cursor is None
    assert queued.is_backfill is True


def test_watch_true_up_waits_for_folder_selection(db_session):
    integration = _integration(db_session)
    integration.config = json.dumps(
        {"source_type": "dropbox", "folder_path": "", "true_up_existing": True, "recursive": True}
    )
    db_session.commit()

    with patch("app.tasks.dropbox_corpus_import.run_dropbox_corpus_import.delay") as delay:
        from app.tasks.dropbox_corpus_import import queue_dropbox_watch_sync

        result = queue_dropbox_watch_sync(integration.id, db_session)

    assert result == {"status": "skipped", "detail": "Dropbox folder has not been selected"}
    delay.assert_not_called()


def test_watch_true_up_waits_for_oauth_grant(db_session):
    integration = _integration(db_session)
    integration.config = json.dumps(
        {"source_type": "dropbox", "folder_path": "/Posteingang", "true_up_existing": True, "recursive": True}
    )
    integration.credentials = None
    db_session.commit()

    with patch("app.tasks.dropbox_corpus_import.run_dropbox_corpus_import.delay") as delay:
        from app.tasks.dropbox_corpus_import import queue_dropbox_watch_sync

        result = queue_dropbox_watch_sync(integration.id, db_session)

    assert result == {"status": "skipped", "detail": "Dropbox authorization is incomplete"}
    delay.assert_not_called()


@pytest.mark.integration
def test_dropbox_import_rejects_invalid_integration_config(client, db_session):
    integration = _integration(db_session)
    integration.config = "not-json"
    db_session.commit()

    with patch("app.tasks.dropbox_corpus_import.run_dropbox_corpus_import.delay") as delay:
        response = client.post("/api/dropbox-imports/", json={"integration_id": integration.id})

    assert response.status_code == 409
    assert response.json()["detail"] == "Integration configuration is invalid"
    delay.assert_not_called()


def test_dropbox_file_revision_is_idempotent(db_session, tmp_path):
    integration = _integration(db_session)
    job = DropboxImportJob(
        id="job-1",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Documents",
    )
    db_session.add(job)
    db_session.commit()

    entry = SimpleNamespace(
        id="id:abc",
        rev="rev-1",
        name="invoice.pdf",
        size=8,
        path_lower="/documents/invoice.pdf",
        path_display="/Documents/invoice.pdf",
    )
    client = SimpleNamespace(files_download=lambda _path: (None, SimpleNamespace(content=b"%PDF-1")))

    with (
        patch("app.tasks.dropbox_corpus_import.settings.workdir", str(tmp_path)),
        patch("app.api.intake.process_document.delay") as delay,
    ):
        delay.return_value.id = "document-task-1"
        from app.tasks.dropbox_corpus_import import _import_file

        assert _import_file(db_session, job, integration, client, entry) == "queued"
        db_session.commit()
        assert _import_file(db_session, job, integration, client, entry) == "skipped"

        entry.rev = "rev-2"
        delay.return_value.id = "document-task-2"
        assert _import_file(db_session, job, integration, client, entry) == "queued"
        db_session.commit()

    assert delay.call_count == 2


@pytest.mark.unit
def test_dropbox_import_removes_download_when_queueing_fails(db_session, tmp_path):
    integration = _integration(db_session)
    job = DropboxImportJob(
        id="job-cleanup",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Documents",
    )
    db_session.add(job)
    db_session.commit()
    entry = SimpleNamespace(
        id="id:cleanup",
        rev="rev-1",
        name="invoice.pdf",
        size=8,
        path_lower="/documents/invoice.pdf",
        path_display="/Documents/invoice.pdf",
    )
    client = SimpleNamespace(files_download=lambda _path: (None, SimpleNamespace(content=b"%PDF-1")))

    with (
        patch("app.tasks.dropbox_corpus_import.settings.workdir", str(tmp_path)),
        patch("app.api.intake._queue_document", side_effect=RuntimeError("queue unavailable")),
    ):
        from app.tasks.dropbox_corpus_import import _import_file

        with pytest.raises(RuntimeError, match="queue unavailable"):
            _import_file(db_session, job, integration, client, entry)

    assert not list(tmp_path.glob("dropbox_*"))


@pytest.mark.unit
def test_dropbox_import_pauses_at_queue_high_watermark(db_session):
    integration = _integration(db_session)
    integration.config = json.dumps({"backfill_queue_high_watermark": 25, "backfill_resume_delay_seconds": 12})
    job = DropboxImportJob(
        id="job-backpressure",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Documents",
    )
    db_session.add(job)
    db_session.commit()

    with (
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=25),
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_import") as schedule,
    ):
        from app.tasks.dropbox_corpus_import import run_dropbox_corpus_import

        result = run_dropbox_corpus_import.run(job.id)

    db_session.refresh(job)
    assert result == {
        "status": "paused",
        "job_id": job.id,
        "queue_depth": 25,
        "resume_in_seconds": 12,
    }
    assert job.state == "queued"
    assert "depth 25" in job.error
    schedule.assert_called_once_with(job.id, countdown=12)


@pytest.mark.unit
def test_queue_depth_counts_priority_queues_and_worker_reserved_tasks():
    redis_client = MagicMock()
    redis_client.llen.side_effect = lambda key: 4 if key == "document_processor\x06\x169" else 0
    redis_client.hlen.return_value = 6

    with patch("app.tasks.dropbox_corpus_import.redis.Redis.from_url", return_value=redis_client):
        from app.tasks.dropbox_corpus_import import _pending_queue_depth

        assert _pending_queue_depth() == 10

    assert redis_client.llen.call_count == 30
    redis_client.hlen.assert_called_once_with("unacked")


@pytest.mark.unit
def test_corpus_token_budget_reserves_with_prompt_headroom(db_session):
    with (
        patch("app.tasks.dropbox_corpus_import.settings.corpus_backfill_daily_llm_token_budget", 9_000_000),
        patch("app.tasks.dropbox_corpus_import.settings.corpus_backfill_llm_token_reservation_per_document", 1),
        patch("app.tasks.dropbox_corpus_import.settings.metadata_max_input_tokens", 8000),
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
    ):
        from app.tasks.dropbox_corpus_import import _reserve_corpus_llm_tokens

        usage_date, reservation = _reserve_corpus_llm_tokens()

    assert usage_date is not None
    assert reservation == 9500
    usage = db_session.query(CorpusLlmDailyUsage).filter_by(usage_date=usage_date).one()
    assert usage.reserved_tokens == 9500


@pytest.mark.unit
def test_corpus_token_budget_rejects_request_that_crosses_limit(db_session):
    frozen_now = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    db_session.add(CorpusLlmDailyUsage(usage_date=frozen_now.date(), reserved_tokens=8_995_000))
    db_session.commit()

    with (
        patch("app.tasks.dropbox_corpus_import.settings.corpus_backfill_daily_llm_token_budget", 9_000_000),
        patch("app.tasks.dropbox_corpus_import.settings.corpus_backfill_llm_token_reservation_per_document", 10_000),
        patch("app.tasks.dropbox_corpus_import.settings.metadata_max_input_tokens", 8000),
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import.datetime") as clock,
    ):
        clock.now.return_value = frozen_now
        clock.combine.side_effect = datetime.combine
        clock.min = datetime.min
        from app.tasks.dropbox_corpus_import import CorpusDailyBudgetReached, _reserve_corpus_llm_tokens

        with pytest.raises(CorpusDailyBudgetReached) as error:
            _reserve_corpus_llm_tokens()

    assert error.value.used == 8_995_000
    assert error.value.budget == 9_000_000
    assert error.value.retry_after_seconds == 43_205
    usage = db_session.query(CorpusLlmDailyUsage).filter_by(usage_date=frozen_now.date()).one()
    assert usage.reserved_tokens == 8_995_000


@pytest.mark.unit
def test_corpus_token_budget_fails_closed_when_counter_is_unavailable():
    with (
        patch("app.tasks.dropbox_corpus_import.settings.corpus_backfill_daily_llm_token_budget", 9_000_000),
        patch("app.tasks.dropbox_corpus_import.SessionLocal", side_effect=RuntimeError("database unavailable")),
    ):
        from app.tasks.dropbox_corpus_import import CorpusDailyBudgetUnavailable, _reserve_corpus_llm_tokens

        with pytest.raises(CorpusDailyBudgetUnavailable, match="Could not reserve"):
            _reserve_corpus_llm_tokens()


@pytest.mark.unit
def test_corpus_token_budget_mutations_refresh_usage_timestamp(db_session):
    # SQLite returns a naive value for DateTime(timezone=True), while
    # PostgreSQL preserves the offset. A naive sentinel remains portable.
    old_timestamp = datetime(2020, 1, 1)
    usage = CorpusLlmDailyUsage(
        usage_date=datetime.now(timezone.utc).date(),
        reserved_tokens=10_000,
        updated_at=old_timestamp,
    )
    db_session.add(usage)
    db_session.commit()

    with (
        patch("app.tasks.dropbox_corpus_import.settings.corpus_backfill_daily_llm_token_budget", 9_000_000),
        patch("app.tasks.dropbox_corpus_import.settings.corpus_backfill_llm_token_reservation_per_document", 10_000),
        patch("app.tasks.dropbox_corpus_import.settings.metadata_max_input_tokens", 8000),
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
    ):
        from app.tasks.dropbox_corpus_import import _release_corpus_llm_tokens, _reserve_corpus_llm_tokens

        reservation = _reserve_corpus_llm_tokens()
        db_session.expire_all()
        refreshed = db_session.query(CorpusLlmDailyUsage).filter_by(usage_date=usage.usage_date).one()
        assert refreshed.reserved_tokens == 20_000
        assert refreshed.updated_at.replace(tzinfo=None) > old_timestamp

        refreshed.updated_at = old_timestamp
        db_session.commit()
        _release_corpus_llm_tokens(reservation)
        db_session.expire_all()
        refreshed = db_session.query(CorpusLlmDailyUsage).filter_by(usage_date=usage.usage_date).one()
        assert refreshed.reserved_tokens == 10_000
        assert refreshed.updated_at.replace(tzinfo=None) > old_timestamp


@pytest.mark.unit
def test_corpus_token_budget_rejects_negative_global_setting():
    with patch("app.tasks.dropbox_corpus_import.settings.corpus_backfill_daily_llm_token_budget", -1):
        from app.tasks.dropbox_corpus_import import CorpusDailyBudgetUnavailable, _reserve_corpus_llm_tokens

        with pytest.raises(CorpusDailyBudgetUnavailable, match="Negative corpus backfill token budgets are invalid"):
            _reserve_corpus_llm_tokens()


@pytest.mark.unit
def test_incremental_watch_job_bypasses_backfill_token_budget():
    job = SimpleNamespace(is_backfill=False)
    integration = SimpleNamespace(config="{}")
    with patch("app.tasks.dropbox_corpus_import._reserve_corpus_llm_tokens") as reserve:
        from app.tasks.dropbox_corpus_import import _reserve_job_llm_tokens

        assert _reserve_job_llm_tokens(job, integration) == (None, 0)
    reserve.assert_not_called()


@pytest.mark.unit
def test_initial_backfill_job_uses_token_budget():
    job = SimpleNamespace(is_backfill=True)
    integration = SimpleNamespace(
        config=json.dumps({"backfill_token_budget_enabled": True, "backfill_daily_llm_token_budget": 8_500_000})
    )
    with patch(
        "app.tasks.dropbox_corpus_import._reserve_corpus_llm_tokens", return_value=(date(2026, 7, 15), 9500)
    ) as reserve:
        from app.tasks.dropbox_corpus_import import _reserve_job_llm_tokens

        assert _reserve_job_llm_tokens(job, integration) == (date(2026, 7, 15), 9500)
    reserve.assert_called_once_with(budget=8_500_000)


@pytest.mark.unit
def test_initial_backfill_negative_budget_fails_closed():
    job = SimpleNamespace(is_backfill=True)
    integration = SimpleNamespace(
        config=json.dumps({"backfill_token_budget_enabled": True, "backfill_daily_llm_token_budget": -1})
    )
    with patch("app.tasks.dropbox_corpus_import._reserve_corpus_llm_tokens") as reserve:
        from app.tasks.dropbox_corpus_import import CorpusDailyBudgetUnavailable, _reserve_job_llm_tokens

        with pytest.raises(CorpusDailyBudgetUnavailable, match="Negative corpus backfill token budgets are invalid"):
            _reserve_job_llm_tokens(job, integration)
    reserve.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    "config",
    [
        {"backfill_token_budget_enabled": False, "backfill_daily_llm_token_budget": 9_000_000},
        {"backfill_token_budget_enabled": True, "backfill_daily_llm_token_budget": 0},
    ],
)
def test_initial_backfill_budget_can_be_disabled_live(config):
    job = SimpleNamespace(is_backfill=True)
    integration = SimpleNamespace(config=json.dumps(config))
    with patch("app.tasks.dropbox_corpus_import._reserve_corpus_llm_tokens") as reserve:
        from app.tasks.dropbox_corpus_import import _reserve_job_llm_tokens

        assert _reserve_job_llm_tokens(job, integration) == (None, 0)
    reserve.assert_not_called()


@pytest.mark.unit
def test_dropbox_import_pauses_until_utc_reset_at_daily_token_budget(db_session):
    integration = _integration(db_session)
    job = DropboxImportJob(
        id="job-token-budget",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Documents",
    )
    db_session.add(job)
    db_session.commit()
    entry = SimpleNamespace(id="id:invoice", rev="rev-1", name="invoice.pdf")
    page = SimpleNamespace(entries=[entry], cursor="cursor-1", has_more=True)
    dropbox_client = MagicMock()
    dropbox_client.files_list_folder.return_value = page

    with (
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=0),
        patch("app.tasks.dropbox_corpus_import._dropbox_client", return_value=dropbox_client),
        patch("dropbox.files.FileMetadata", SimpleNamespace),
        patch("app.tasks.dropbox_corpus_import._import_file") as import_file,
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_import") as schedule,
    ):
        from app.tasks.dropbox_corpus_import import CorpusDailyBudgetReached, run_dropbox_corpus_import

        import_file.side_effect = CorpusDailyBudgetReached(used=8_990_000, budget=9_000_000, retry_after_seconds=3600)
        result = run_dropbox_corpus_import.run(job.id)

    db_session.refresh(job)
    assert result == {
        "status": "paused",
        "reason": "daily_llm_token_budget",
        "job_id": job.id,
        "tokens_reserved": 8_990_000,
        "token_budget": 9_000_000,
        "resume_in_seconds": 900,
        "budget_resets_in_seconds": 3600,
    }
    assert job.state == "queued"
    assert job.cursor is None
    assert json.loads(job.page_entry_keys) == []
    assert job.discovered == 0
    schedule.assert_called_once_with(job.id, countdown=900)


@pytest.mark.unit
def test_budget_rechecks_use_stable_entry_keys_when_page_changes(db_session):
    integration = _integration(db_session)
    job = DropboxImportJob(
        id="job-page-progress",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Documents",
    )
    db_session.add(job)
    db_session.commit()
    first = SimpleNamespace(id="id:first", rev="rev-1", name="first.pdf")
    second = SimpleNamespace(id="id:second", rev="rev-1", name="second.pdf")
    inserted = SimpleNamespace(id="id:inserted", rev="rev-1", name="inserted.pdf")
    first_page = SimpleNamespace(entries=[first, second], cursor="cursor-1", has_more=False)
    changed_page = SimpleNamespace(entries=[inserted, first, second], cursor="cursor-2", has_more=False)
    dropbox_client = MagicMock()
    dropbox_client.files_list_folder.side_effect = [first_page, changed_page, changed_page]

    with (
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=0),
        patch("app.tasks.dropbox_corpus_import._dropbox_client", return_value=dropbox_client),
        patch("dropbox.files.FileMetadata", SimpleNamespace),
        patch("app.tasks.dropbox_corpus_import._import_file") as import_file,
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_import") as schedule,
    ):
        from app.tasks.dropbox_corpus_import import CorpusDailyBudgetReached, run_dropbox_corpus_import

        budget_reached = CorpusDailyBudgetReached(
            used=9_000_000,
            budget=9_000_000,
            retry_after_seconds=3600,
        )
        import_file.side_effect = ["queued", budget_reached]
        first_pause = run_dropbox_corpus_import.run(job.id)

        db_session.refresh(job)
        assert first_pause["reason"] == "daily_llm_token_budget"
        assert set(json.loads(job.page_entry_keys)) == {"id:first:rev-1"}
        assert job.discovered == 1
        assert job.queued == 1
        assert job.skipped == 0

        import_file.side_effect = ["queued", budget_reached]
        second_pause = run_dropbox_corpus_import.run(job.id)

        db_session.refresh(job)
        assert second_pause["reason"] == "daily_llm_token_budget"
        assert set(json.loads(job.page_entry_keys)) == {"id:first:rev-1", "id:inserted:rev-1"}
        assert job.discovered == 2
        assert job.queued == 2
        assert job.skipped == 0

        import_file.side_effect = ["queued"]
        completed = run_dropbox_corpus_import.run(job.id)

    db_session.refresh(job)
    assert completed["status"] == "completed"
    assert job.cursor == "cursor-2"
    assert json.loads(job.page_entry_keys) == []
    assert job.discovered == 3
    assert job.queued == 3
    assert job.skipped == 0
    assert import_file.call_args.args[-1] is second
    assert schedule.call_count == 2


@pytest.mark.unit
def test_invalid_page_progress_fails_closed_and_persists_error(db_session):
    integration = _integration(db_session)
    job = DropboxImportJob(
        id="job-invalid-page-progress",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Documents",
    )
    db_session.add(job)
    db_session.commit()

    job.page_entry_keys = "not-json"
    db_session.commit()
    page = SimpleNamespace(entries=[], cursor="cursor-1", has_more=True)
    dropbox_client = MagicMock()
    dropbox_client.files_list_folder.return_value = page

    with (
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=0),
        patch("app.tasks.dropbox_corpus_import._dropbox_client", return_value=dropbox_client),
    ):
        from app.tasks.dropbox_corpus_import import run_dropbox_corpus_import

        with pytest.raises(RuntimeError, match="not valid JSON"):
            run_dropbox_corpus_import.run(job.id)

    db_session.refresh(job)
    assert job.state == "failed"
    assert job.error == "Saved Dropbox page progress is not valid JSON"


@pytest.mark.unit
def test_dropbox_import_uses_configured_provider_batch_size(db_session):
    integration = _integration(db_session)
    integration.config = json.dumps({"backfill_batch_size": 7})
    job = DropboxImportJob(
        id="job-small-page",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Documents",
    )
    db_session.add(job)
    db_session.commit()
    page = SimpleNamespace(entries=[], cursor="cursor-1", has_more=False)
    dropbox_client = MagicMock()
    dropbox_client.files_list_folder.return_value = page

    with (
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=0),
        patch("app.tasks.dropbox_corpus_import._dropbox_client", return_value=dropbox_client),
    ):
        from app.tasks.dropbox_corpus_import import run_dropbox_corpus_import

        result = run_dropbox_corpus_import.run(job.id)

    assert result["status"] == "completed"
    dropbox_client.files_list_folder.assert_called_once_with(
        "/Documents",
        recursive=True,
        include_deleted=False,
        limit=7,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({}, 10),
        ({"backfill_batch_size": "7"}, 7),
        ({"backfill_batch_size": "not-a-number"}, 10),
        ({"backfill_batch_size": 0}, 1),
        ({"backfill_batch_size": 5000}, 2000),
    ],
)
def test_bounded_config_int_uses_safe_fallbacks_and_limits(config, expected):
    from app.tasks.dropbox_corpus_import import _bounded_config_int

    assert (
        _bounded_config_int(
            config,
            "backfill_batch_size",
            10,
            minimum=1,
            maximum=2000,
        )
        == expected
    )


@pytest.mark.unit
@pytest.mark.parametrize("override", ["not-a-number", [], {}])
def test_dropbox_import_ignores_invalid_provider_batch_size(db_session, override):
    integration = _integration(db_session)
    integration.config = json.dumps({"backfill_batch_size": override})
    job = DropboxImportJob(
        id=f"job-invalid-page-{type(override).__name__}",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Documents",
    )
    db_session.add(job)
    db_session.commit()
    page = SimpleNamespace(entries=[], cursor="cursor-1", has_more=False)
    dropbox_client = MagicMock()
    dropbox_client.files_list_folder.return_value = page

    with (
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=0),
        patch("app.tasks.dropbox_corpus_import._dropbox_client", return_value=dropbox_client),
    ):
        from app.tasks.dropbox_corpus_import import run_dropbox_corpus_import

        result = run_dropbox_corpus_import.run(job.id)

    assert result["status"] == "completed"
    dropbox_client.files_list_folder.assert_called_once_with(
        "/Documents",
        recursive=True,
        include_deleted=False,
        limit=10,
    )
