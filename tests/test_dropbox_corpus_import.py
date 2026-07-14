"""Tests for resumable Dropbox corpus import and revision deduplication."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from app.models import DropboxImportJob, IntegrationDirection, IntegrationType, UserIntegration


def _integration(db_session) -> UserIntegration:
    integration = UserIntegration(
        owner_id="owner@example.com",
        direction=IntegrationDirection.SOURCE,
        integration_type=IntegrationType.WATCH_FOLDER,
        name="Dropbox archive",
        config=json.dumps({"source_type": "dropbox", "folder_path": "/Documents"}),
        credentials="{}",
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
