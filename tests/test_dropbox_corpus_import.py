"""Tests for resumable Dropbox corpus import and revision deduplication."""

import json
import os
from contextlib import nullcontext
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models import CorpusLlmDailyUsage, DropboxImportJob, IntegrationDirection, IntegrationType, UserIntegration
from app.utils.encryption import encrypt_value


@pytest.fixture(autouse=True)
def _owned_import_coordinator_lock():
    client = MagicMock()
    with (
        patch(
            "app.tasks.dropbox_corpus_import._acquire_import_coordinator_lock",
            return_value=(client, "corpus-lock", "owner-token"),
        ),
        patch("app.tasks.dropbox_corpus_import._release_import_coordinator_lock"),
    ):
        yield


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
def test_queue_depth_excludes_late_acked_coordinator_delivery():
    redis_client = MagicMock()
    redis_client.llen.return_value = 0
    redis_client.hlen.return_value = 1

    with patch("app.tasks.dropbox_corpus_import.redis.Redis.from_url", return_value=redis_client):
        from app.tasks.dropbox_corpus_import import _pending_queue_depth

        assert _pending_queue_depth(exclude_current_delivery=True) == 0


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
@pytest.mark.parametrize("value", [True, "true", "1", "yes", "on"])
def test_initial_backfill_index_first_can_be_enabled_live(value):
    integration = SimpleNamespace(config=json.dumps({"backfill_index_first_enabled": value}))

    with patch("app.tasks.dropbox_corpus_import.settings.vector_index_enabled", True):
        from app.tasks.dropbox_corpus_import import _index_first_enabled

        assert _index_first_enabled(integration) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("config", "index_only", "expected"),
    [
        ({"backfill_download_concurrency": 4}, True, 4),
        ({"backfill_download_concurrency": 99}, True, 8),
        ({"backfill_download_concurrency": "invalid"}, True, 1),
        ({"backfill_download_concurrency": 4}, False, 1),
    ],
)
def test_index_first_download_concurrency_is_live_bounded_and_scoped(config, index_only, expected):
    from app.tasks.dropbox_corpus_import import _index_first_download_concurrency

    with patch("app.tasks.dropbox_corpus_import.settings.corpus_backfill_download_concurrency", 1):
        assert _index_first_download_concurrency(config, index_only=index_only) == expected


@pytest.mark.unit
def test_index_first_backfill_bypasses_llm_budget_and_queues_direct_processing(db_session, tmp_path):
    integration = _integration(db_session)
    integration.config = json.dumps({"backfill_index_first_enabled": True})
    job = DropboxImportJob(
        id="job-index-first",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Documents",
        is_backfill=True,
    )
    db_session.add(job)
    db_session.commit()
    entry = SimpleNamespace(
        id="id:index-first",
        rev="rev-1",
        name="notes.docx",
        size=8,
        path_lower="/documents/notes.docx",
        path_display="/Documents/notes.docx",
    )
    client = SimpleNamespace(files_download=lambda _path: (None, SimpleNamespace(content=b"document")))

    with (
        patch("app.tasks.dropbox_corpus_import.settings.workdir", str(tmp_path)),
        patch("app.tasks.dropbox_corpus_import.settings.vector_index_enabled", True),
        patch("app.tasks.dropbox_corpus_import._reserve_job_llm_tokens") as reserve,
        patch("app.api.intake._queue_document") as queue_document,
        patch.object(db_session, "commit", wraps=db_session.commit) as commit,
    ):

        def assert_committed_before_queue(*_args, **kwargs):
            assert commit.call_count == 1
            return SimpleNamespace(id=kwargs["task_id"])

        queue_document.side_effect = assert_committed_before_queue
        from app.tasks.dropbox_corpus_import import _import_file

        assert _import_file(db_session, job, integration, client, entry) == "queued"

    reserve.assert_not_called()
    queue_document.assert_called_once()
    assert queue_document.call_args.kwargs["index_only"] is True
    assert queue_document.call_args.kwargs["task_id"]


@pytest.mark.unit
def test_index_first_import_consumes_prefetched_file_without_redownloading(db_session, tmp_path):
    integration = _integration(db_session)
    integration.config = json.dumps({"backfill_index_first_enabled": True})
    job = DropboxImportJob(
        id="job-index-first-prefetched",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Documents",
        is_backfill=True,
    )
    db_session.add(job)
    db_session.commit()
    entry = SimpleNamespace(
        id="id:prefetched",
        rev="rev-1",
        name="notes.pdf",
        size=8,
        path_lower="/documents/notes.pdf",
        path_display="/Documents/notes.pdf",
    )
    prefetched_path = tmp_path / "prefetched.pdf"
    prefetched_path.write_bytes(b"document")
    client = MagicMock()

    with (
        patch("app.tasks.dropbox_corpus_import.settings.workdir", str(tmp_path)),
        patch("app.tasks.dropbox_corpus_import.settings.vector_index_enabled", True),
        patch("app.api.intake._queue_document", return_value=SimpleNamespace(id="task-id")),
    ):
        from app.tasks.dropbox_corpus_import import _import_file

        assert (
            _import_file(
                db_session,
                job,
                integration,
                client,
                entry,
                prefetched_path=str(prefetched_path),
            )
            == "queued"
        )

    client.files_download.assert_not_called()
    assert not prefetched_path.exists()


@pytest.mark.unit
def test_prefetch_reuses_one_dropbox_client_per_worker_thread(tmp_path):
    entries = [
        SimpleNamespace(
            name=f"notes-{index}.pdf",
            path_lower=f"/documents/notes-{index}.pdf",
        )
        for index in range(2)
    ]
    client = MagicMock()
    client.files_download.return_value = (None, SimpleNamespace(content=b"document"))

    with (
        patch("app.tasks.dropbox_corpus_import.settings.workdir", str(tmp_path)),
        patch("app.tasks.dropbox_corpus_import._PREFETCH_THREAD_STATE", SimpleNamespace()),
        patch(
            "app.tasks.dropbox_corpus_import._dropbox_client_from_stored_credentials",
            return_value=client,
        ) as client_factory,
    ):
        from app.tasks.dropbox_corpus_import import _prefetch_dropbox_entry

        paths = [_prefetch_dropbox_entry(4, "encrypted", entry) for entry in entries]

    assert client_factory.call_count == 1
    assert client.files_download.call_count == 2
    for path in paths:
        os.remove(path)


@pytest.mark.unit
def test_index_first_page_prefetches_downloads_in_parallel(db_session, tmp_path):
    integration = _integration(db_session)
    integration.config = json.dumps(
        {
            "backfill_index_first_enabled": True,
            "backfill_download_concurrency": 2,
        }
    )
    job = DropboxImportJob(
        id="job-index-first-parallel",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Documents",
        is_backfill=True,
    )
    db_session.add(job)
    db_session.commit()
    entries = [
        SimpleNamespace(
            id=f"id:parallel-{index}",
            rev="rev-1",
            name=f"notes-{index}.pdf",
            size=8,
            path_lower=f"/documents/notes-{index}.pdf",
            path_display=f"/Documents/notes-{index}.pdf",
        )
        for index in range(2)
    ]
    page = SimpleNamespace(entries=entries, cursor="cursor-1", has_more=False)
    dropbox_client = MagicMock()
    dropbox_client.files_list_folder.return_value = page

    def fake_prefetch(_integration_id, _stored_credentials, entry):
        path = tmp_path / f"{entry.id.replace(':', '-')}.pdf"
        path.write_bytes(b"document")
        return str(path)

    def fake_import(_db, _job, _integration, _client, _entry, *, prefetched_path=None):
        assert prefetched_path is not None
        assert os.path.exists(prefetched_path)
        os.remove(prefetched_path)
        return "queued"

    with (
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=0),
        patch("app.tasks.dropbox_corpus_import._dropbox_client", return_value=dropbox_client),
        patch("app.tasks.dropbox_corpus_import.settings.vector_index_enabled", True),
        patch("dropbox.files.FileMetadata", SimpleNamespace),
        patch("app.tasks.dropbox_corpus_import._prefetch_dropbox_entry", side_effect=fake_prefetch) as prefetch,
        patch("app.tasks.dropbox_corpus_import._import_file", side_effect=fake_import) as import_file,
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_ocr_backlog"),
    ):
        from app.tasks.dropbox_corpus_import import run_dropbox_corpus_import

        result = run_dropbox_corpus_import.run(job.id)

    assert result["status"] == "completed"
    assert result["queued"] == 2
    assert prefetch.call_count == 2
    assert import_file.call_count == 2


@pytest.mark.unit
def test_index_first_prefetch_keeps_a_bounded_lookahead_window(db_session, tmp_path):
    from concurrent.futures import ThreadPoolExecutor as RealThreadPoolExecutor

    integration = _integration(db_session)
    integration.config = json.dumps(
        {
            "backfill_index_first_enabled": True,
            "backfill_download_concurrency": 2,
        }
    )
    job = DropboxImportJob(
        id="job-index-first-bounded-prefetch",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Documents",
        is_backfill=True,
    )
    db_session.add(job)
    db_session.commit()
    entries = [
        SimpleNamespace(
            id=f"id:bounded-{index}",
            rev="rev-1",
            name=f"notes-{index}.pdf",
            size=8,
            path_lower=f"/documents/notes-{index}.pdf",
            path_display=f"/Documents/notes-{index}.pdf",
        )
        for index in range(10)
    ]
    page = SimpleNamespace(entries=entries, cursor="cursor-1", has_more=False)
    dropbox_client = MagicMock()
    dropbox_client.files_list_folder.return_value = page
    executors = []

    class TrackingExecutor:
        def __init__(self, *, max_workers, thread_name_prefix):
            self.submit_count = 0
            self.executor = RealThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix=thread_name_prefix,
            )
            executors.append(self)

        def submit(self, *args, **kwargs):
            self.submit_count += 1
            return self.executor.submit(*args, **kwargs)

        def shutdown(self, *, wait, cancel_futures):
            return self.executor.shutdown(wait=wait, cancel_futures=cancel_futures)

    def fake_prefetch(_integration_id, _stored_credentials, entry):
        path = tmp_path / f"{entry.id.replace(':', '-')}.pdf"
        path.write_bytes(b"document")
        return str(path)

    first_import = True

    def fake_import(_db, _job, _integration, _client, _entry, *, prefetched_path=None):
        nonlocal first_import
        if first_import:
            # Two initial submissions plus one replacement after consuming the
            # first future prove that the other seven entries were not queued.
            assert executors[0].submit_count == 3
            first_import = False
        assert prefetched_path is not None
        os.remove(prefetched_path)
        return "queued"

    with (
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=0),
        patch("app.tasks.dropbox_corpus_import._dropbox_client", return_value=dropbox_client),
        patch("app.tasks.dropbox_corpus_import.settings.vector_index_enabled", True),
        patch("dropbox.files.FileMetadata", SimpleNamespace),
        patch("app.tasks.dropbox_corpus_import.ThreadPoolExecutor", TrackingExecutor),
        patch("app.tasks.dropbox_corpus_import._prefetch_dropbox_entry", side_effect=fake_prefetch) as prefetch,
        patch("app.tasks.dropbox_corpus_import._import_file", side_effect=fake_import),
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_ocr_backlog"),
    ):
        from app.tasks.dropbox_corpus_import import run_dropbox_corpus_import

        result = run_dropbox_corpus_import.run(job.id)

    assert result["status"] == "completed"
    assert result["queued"] == 10
    assert prefetch.call_count == 10


@pytest.mark.unit
def test_index_first_falls_back_to_full_pipeline_when_vector_index_is_disabled():
    integration = SimpleNamespace(config=json.dumps({"backfill_index_first_enabled": True}))

    with patch("app.tasks.dropbox_corpus_import.settings.vector_index_enabled", False):
        from app.tasks.dropbox_corpus_import import _index_first_enabled

        assert _index_first_enabled(integration) is False


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
