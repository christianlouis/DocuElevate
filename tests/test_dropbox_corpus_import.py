"""Tests for resumable Dropbox corpus import and revision deduplication."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.models import DropboxImportJob, IntegrationDirection, IntegrationType, UserIntegration
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
    with patch("app.tasks.dropbox_corpus_import.run_dropbox_corpus_import.delay") as delay:
        delay.return_value.id = "import-task"
        response = client.post("/api/dropbox-imports/", json={"integration_id": integration.id})

    assert response.status_code == 202
    assert response.json()["root_path"] == "/Documents"
    assert response.json()["state"] == "queued"
    delay.assert_called_once()


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

    with patch("app.tasks.dropbox_corpus_import.run_dropbox_corpus_import.delay") as delay:
        from app.tasks.dropbox_corpus_import import queue_dropbox_watch_sync

        result = queue_dropbox_watch_sync(integration.id, db_session)

    queued = db_session.query(DropboxImportJob).filter(DropboxImportJob.id == result["job_id"]).one()
    assert result["mode"] == "incremental"
    assert queued.cursor == "cursor-after-true-up"
    delay.assert_called_once_with(queued.id)


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
