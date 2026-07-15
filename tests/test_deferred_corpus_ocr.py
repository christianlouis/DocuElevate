"""Focused coverage for the OCR-only second pass of index-first corpus imports."""

import json
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.models import (
    DocumentIntake,
    DropboxImportJob,
    DropboxImportObject,
    FileRecord,
    IntegrationDirection,
    IntegrationType,
    ProcessingLog,
    UserIntegration,
)
from app.utils.ocr_provider import OCRResult


@pytest.fixture(autouse=True)
def _owned_import_coordinator_lock():
    client = Mock()
    with (
        patch(
            "app.tasks.dropbox_corpus_import._acquire_import_coordinator_lock",
            return_value=(client, "corpus-lock", "owner-token"),
        ),
        patch("app.tasks.dropbox_corpus_import._release_import_coordinator_lock"),
    ):
        yield


def _integration(db_session, *, config: dict | None = None) -> UserIntegration:
    integration = UserIntegration(
        owner_id="owner@example.com",
        direction=IntegrationDirection.SOURCE,
        integration_type=IntegrationType.WATCH_FOLDER,
        name="Dropbox corpus",
        config=json.dumps(
            config
            or {
                "source_type": "dropbox",
                "folder_path": "/Posteingang",
                "backfill_index_first_enabled": True,
                "backfill_deferred_ocr_enabled": True,
            }
        ),
        is_active=True,
    )
    db_session.add(integration)
    db_session.commit()
    db_session.refresh(integration)
    return integration


def _file_record(db_session, path, *, filename: str = "scan.pdf") -> FileRecord:
    record = FileRecord(
        owner_id="owner@example.com",
        filehash="hash-" + filename,
        original_filename=filename,
        local_filename=str(path),
        original_file_path=str(path),
        file_size=path.stat().st_size,
        mime_type="application/pdf",
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


@pytest.mark.unit
def test_index_only_ocr_persists_text_and_queues_vector_index(db_session, tmp_path):
    integration = _integration(db_session)
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()
    staged = tmp_dir / "scan.pdf"
    staged.write_bytes(b"scan")
    record = _file_record(db_session, staged)
    intake = DocumentIntake(
        principal_id="owner@example.com",
        idempotency_key="dropbox:scan",
        source="dropbox-corpus",
        original_filename="scan.pdf",
        task_id="source-task",
        state="needs_ocr",
    )
    db_session.add(intake)
    db_session.flush()
    imported = DropboxImportObject(
        integration_id=integration.id,
        dropbox_file_id="id:scan",
        revision="rev-1",
        remote_path="/Posteingang/scan.pdf",
        intake_id=intake.id,
        task_id="source-task",
        state="needs_ocr",
    )
    db_session.add(imported)
    db_session.commit()
    provider = Mock(name="provider")
    provider.name = "azure"
    provider.process.return_value = OCRResult("azure", "Searchable OCR text", str(staged))

    with (
        patch("app.tasks.process_with_ocr.settings.workdir", str(tmp_path)),
        patch("app.tasks.process_with_ocr.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.process_with_ocr.get_ocr_providers", return_value=[provider]),
        patch(
            "app.tasks.process_with_ocr.merge_ocr_results",
            return_value=("Searchable OCR text", str(staged), {}),
        ),
        patch("app.tasks.process_with_ocr.check_text_quality") as quality,
        patch("app.tasks.process_with_ocr.compare_text_quality") as compare,
        patch("app.tasks.process_with_ocr.embed_text_layer") as embed,
        patch("app.tasks.process_with_ocr.rotate_pdf_pages") as rotate,
        patch("app.tasks.vector_index.index_document_vectors.apply_async") as index,
    ):
        from app.tasks.process_with_ocr import process_with_ocr

        result = process_with_ocr.run(
            "scan.pdf",
            file_id=record.id,
            original_text="Existing low-quality text",
            index_only=True,
            source_task_id="source-task",
        )

    db_session.refresh(record)
    db_session.refresh(imported)
    db_session.refresh(intake)
    assert result["status"] == "queued_for_vector_index"
    assert record.ocr_text == "Searchable OCR text"
    assert imported.state == "indexing"
    assert intake.state == "indexing"
    assert not staged.exists()
    index.assert_called_once_with(
        args=[record.id],
        kwargs={"source_task_id": "source-task"},
        priority=9,
    )
    quality.assert_not_called()
    compare.assert_not_called()
    embed.assert_not_called()
    rotate.delay.assert_not_called()


@pytest.mark.unit
def test_index_only_empty_ocr_is_terminal_and_does_not_index(db_session, tmp_path):
    integration = _integration(db_session)
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()
    staged = tmp_dir / "empty.pdf"
    staged.write_bytes(b"scan")
    record = _file_record(db_session, staged, filename="empty.pdf")
    intake = DocumentIntake(
        principal_id="owner@example.com",
        idempotency_key="dropbox:empty",
        source="dropbox-corpus",
        original_filename="empty.pdf",
        task_id="empty-source-task",
        state="needs_ocr",
    )
    db_session.add(intake)
    db_session.flush()
    imported = DropboxImportObject(
        integration_id=integration.id,
        dropbox_file_id="id:empty",
        revision="rev-1",
        remote_path="/Posteingang/empty.pdf",
        intake_id=intake.id,
        task_id="empty-source-task",
        state="needs_ocr",
    )
    db_session.add(imported)
    db_session.commit()
    provider = Mock(name="provider")
    provider.name = "azure"
    provider.process.return_value = OCRResult("azure", "", str(staged))

    with (
        patch("app.tasks.process_with_ocr.settings.workdir", str(tmp_path)),
        patch("app.tasks.process_with_ocr.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.process_with_ocr.get_ocr_providers", return_value=[provider]),
        patch("app.tasks.process_with_ocr.merge_ocr_results", return_value=("", str(staged), {})),
        patch("app.tasks.vector_index.index_document_vectors.apply_async") as index,
    ):
        from app.tasks.process_with_ocr import process_with_ocr

        result = process_with_ocr.run(
            "empty.pdf",
            file_id=record.id,
            index_only=True,
            source_task_id="empty-source-task",
        )

    db_session.refresh(imported)
    db_session.refresh(intake)
    assert result == {"status": "failed", "file_id": record.id, "detail": "OCR returned no usable text"}
    assert imported.state == "failed"
    assert intake.state == "failed"
    assert intake.error == "OCR returned no usable text"
    assert not staged.exists()
    index.assert_not_called()


@pytest.mark.unit
def test_index_only_ocr_removes_separate_tmp_provider_artifact(db_session, tmp_path):
    integration = _integration(db_session)
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()
    staged = tmp_dir / "scan.pdf"
    provider_pdf = tmp_dir / "scan-searchable.pdf"
    staged.write_bytes(b"scan")
    provider_pdf.write_bytes(b"searchable")
    record = _file_record(db_session, staged)
    intake = DocumentIntake(
        principal_id="owner@example.com",
        idempotency_key="dropbox:artifact",
        source="dropbox-corpus",
        original_filename="scan.pdf",
        task_id="artifact-source-task",
        state="needs_ocr",
    )
    db_session.add(intake)
    db_session.flush()
    db_session.add(
        DropboxImportObject(
            integration_id=integration.id,
            dropbox_file_id="id:artifact",
            revision="rev-1",
            remote_path="/Posteingang/scan.pdf",
            intake_id=intake.id,
            task_id="artifact-source-task",
            state="needs_ocr",
        )
    )
    db_session.commit()
    provider = Mock(name="provider")
    provider.name = "azure"
    provider.process.return_value = OCRResult("azure", "Searchable OCR text", str(provider_pdf))

    with (
        patch("app.tasks.process_with_ocr.settings.workdir", str(tmp_path)),
        patch("app.tasks.process_with_ocr.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.process_with_ocr.get_ocr_providers", return_value=[provider]),
        patch(
            "app.tasks.process_with_ocr.merge_ocr_results",
            return_value=("Searchable OCR text", str(provider_pdf), {}),
        ),
        patch("app.tasks.vector_index.index_document_vectors.apply_async"),
    ):
        from app.tasks.process_with_ocr import process_with_ocr

        process_with_ocr.run(
            "scan.pdf",
            file_id=record.id,
            index_only=True,
            source_task_id="artifact-source-task",
        )

    assert not staged.exists()
    assert not provider_pdf.exists()


@pytest.mark.unit
def test_index_only_ocr_keeps_durable_state_when_vector_publish_fails(db_session, tmp_path):
    integration = _integration(db_session)
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()
    staged = tmp_dir / "scan.pdf"
    staged.write_bytes(b"scan")
    record = _file_record(db_session, staged)
    intake = DocumentIntake(
        principal_id="owner@example.com",
        idempotency_key="dropbox:publish-failure",
        source="dropbox-corpus",
        original_filename="scan.pdf",
        task_id="publish-failure-task",
        state="ocr_queued",
    )
    db_session.add(intake)
    db_session.flush()
    imported = DropboxImportObject(
        integration_id=integration.id,
        dropbox_file_id="id:publish-failure",
        revision="rev-1",
        remote_path="/Posteingang/scan.pdf",
        intake_id=intake.id,
        task_id="publish-failure-task",
        state="ocr_queued",
    )
    db_session.add(imported)
    db_session.commit()
    provider = Mock()
    provider.name = "azure"
    provider.process.return_value = OCRResult("azure", "Recovered later", str(staged))

    with (
        patch("app.tasks.process_with_ocr.settings.workdir", str(tmp_path)),
        patch("app.tasks.process_with_ocr.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.process_with_ocr.get_ocr_providers", return_value=[provider]),
        patch(
            "app.tasks.process_with_ocr.merge_ocr_results",
            return_value=("Recovered later", str(staged), {}),
        ),
        patch(
            "app.tasks.vector_index.index_document_vectors.apply_async",
            side_effect=RuntimeError("broker unavailable"),
        ),
    ):
        from app.tasks.process_with_ocr import process_with_ocr

        result = process_with_ocr.run(
            "scan.pdf",
            file_id=record.id,
            index_only=True,
            source_task_id="publish-failure-task",
        )

    db_session.refresh(imported)
    db_session.refresh(intake)
    db_session.refresh(record)
    assert result["status"] == "pending_vector_index"
    assert imported.state == "ocr_complete"
    assert intake.state == "ocr_complete"
    assert record.ocr_text == "Recovered later"
    assert not staged.exists()


@pytest.mark.unit
def test_completed_index_first_import_schedules_deferred_ocr(db_session):
    integration = _integration(
        db_session,
        config={
            "source_type": "dropbox",
            "folder_path": "/Posteingang",
            "backfill_index_first_enabled": True,
            "backfill_deferred_ocr_enabled": True,
        },
    )
    job = DropboxImportJob(
        id="finishing-job",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Posteingang",
        is_backfill=True,
    )
    db_session.add(job)
    db_session.commit()
    page = SimpleNamespace(entries=[], cursor="finished-cursor", has_more=False)
    dropbox_client = Mock()
    dropbox_client.files_list_folder.return_value = page

    with (
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=0),
        patch("app.tasks.dropbox_corpus_import._dropbox_client", return_value=dropbox_client),
        patch("app.tasks.dropbox_corpus_import.settings.vector_index_enabled", True),
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_ocr_backlog") as schedule,
    ):
        from app.tasks.dropbox_corpus_import import run_dropbox_corpus_import

        result = run_dropbox_corpus_import.run(job.id)

    db_session.refresh(job)
    assert result["status"] == "completed"
    assert job.state == "completed"
    schedule.assert_called_once_with(job.id)


@pytest.mark.unit
def test_completed_index_first_import_schedules_reconciliation_without_ocr(db_session):
    integration = _integration(
        db_session,
        config={
            "source_type": "dropbox",
            "folder_path": "/Posteingang",
            "backfill_index_first_enabled": True,
            "backfill_deferred_ocr_enabled": False,
        },
    )
    job = DropboxImportJob(
        id="reconciliation-only-job",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Posteingang",
        is_backfill=True,
    )
    db_session.add(job)
    db_session.commit()
    page = SimpleNamespace(entries=[], cursor="finished-cursor", has_more=False)
    dropbox_client = Mock()
    dropbox_client.files_list_folder.return_value = page

    with (
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=0),
        patch("app.tasks.dropbox_corpus_import._dropbox_client", return_value=dropbox_client),
        patch("app.tasks.dropbox_corpus_import.settings.vector_index_enabled", True),
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_ocr_backlog") as schedule,
    ):
        from app.tasks.dropbox_corpus_import import run_dropbox_corpus_import

        result = run_dropbox_corpus_import.run(job.id)

    assert result["status"] == "completed"
    schedule.assert_called_once_with(job.id)


@pytest.mark.unit
def test_deferred_ocr_backlog_stages_bounded_low_priority_work(db_session, tmp_path):
    integration = _integration(
        db_session,
        config={
            "source_type": "dropbox",
            "folder_path": "/Posteingang",
            "backfill_index_first_enabled": True,
            "backfill_deferred_ocr_enabled": True,
            "backfill_ocr_batch_size": 1,
            "backfill_ocr_recheck_seconds": 7,
        },
    )
    job = DropboxImportJob(
        id="completed-job",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Posteingang",
        state="completed",
        is_backfill=True,
    )
    original = tmp_path / "original.pdf"
    original.write_bytes(b"scan")
    record = _file_record(db_session, original)
    intake = DocumentIntake(
        principal_id=integration.owner_id,
        idempotency_key="dropbox:backlog",
        source="dropbox-corpus",
        original_filename="scan.pdf",
        task_id="backlog-source-task",
        state="needs_ocr",
    )
    db_session.add_all([job, intake])
    db_session.flush()
    imported = DropboxImportObject(
        integration_id=integration.id,
        dropbox_file_id="id:backlog",
        revision="rev-1",
        remote_path="/Posteingang/scan.pdf",
        intake_id=intake.id,
        task_id="backlog-source-task",
        state="needs_ocr",
    )
    db_session.add(imported)
    db_session.add(
        ProcessingLog(
            file_id=record.id,
            task_id="backlog-source-task",
            step_name="process_document",
            status="skipped",
        )
    )
    db_session.commit()

    with (
        patch("app.tasks.dropbox_corpus_import.settings.workdir", str(tmp_path)),
        patch("app.tasks.dropbox_corpus_import.settings.vector_index_enabled", True),
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=0),
        patch("app.tasks.process_with_ocr.process_with_ocr.apply_async") as apply_async,
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_ocr_backlog") as schedule,
    ):
        from app.tasks.dropbox_corpus_import import run_dropbox_corpus_ocr_backlog

        result = run_dropbox_corpus_ocr_backlog.run(job.id)

    db_session.refresh(imported)
    db_session.refresh(intake)
    assert result == {
        "status": "running",
        "job_id": job.id,
        "queued": 1,
        "failed": 0,
        "resume_in_seconds": 7,
    }
    assert imported.state == "ocr_queued"
    assert intake.state == "ocr_queued"
    args = apply_async.call_args.kwargs["args"]
    assert args[1] == record.id
    assert (tmp_path / "tmp" / args[0]).read_bytes() == b"scan"
    assert apply_async.call_args.kwargs["kwargs"] == {
        "index_only": True,
        "source_task_id": "backlog-source-task",
    }
    assert apply_async.call_args.kwargs["priority"] == 9
    schedule.assert_called_once_with(job.id, countdown=7)


@pytest.mark.unit
def test_deferred_ocr_backlog_leaves_office_files_for_conversion(db_session, tmp_path):
    integration = _integration(db_session)
    job = DropboxImportJob(
        id="conversion-job",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Posteingang",
        state="completed",
        is_backfill=True,
    )
    original = tmp_path / "notes.docx"
    original.write_bytes(b"office")
    record = _file_record(db_session, original, filename="notes.docx")
    intake = DocumentIntake(
        principal_id=integration.owner_id,
        idempotency_key="dropbox:conversion",
        source="dropbox-corpus",
        original_filename="notes.docx",
        task_id="conversion-source-task",
        state="needs_ocr",
        error="PDF conversion is required",
    )
    db_session.add_all([job, intake])
    db_session.flush()
    imported = DropboxImportObject(
        integration_id=integration.id,
        dropbox_file_id="id:conversion",
        revision="rev-1",
        remote_path="/Posteingang/notes.docx",
        intake_id=intake.id,
        task_id="conversion-source-task",
        state="needs_ocr",
    )
    db_session.add(imported)
    db_session.add(
        ProcessingLog(
            file_id=record.id,
            task_id="conversion-source-task",
            step_name="process_document",
            status="skipped",
        )
    )
    db_session.commit()

    with (
        patch("app.tasks.dropbox_corpus_import.settings.workdir", str(tmp_path)),
        patch("app.tasks.dropbox_corpus_import.settings.vector_index_enabled", True),
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=0),
        patch("app.tasks.process_with_ocr.process_with_ocr.apply_async") as apply_async,
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_ocr_backlog"),
    ):
        from app.tasks.dropbox_corpus_import import run_dropbox_corpus_ocr_backlog

        result = run_dropbox_corpus_ocr_backlog.run(job.id)

    db_session.refresh(imported)
    db_session.refresh(intake)
    assert result["status"] == "completed_with_gaps"
    assert result["gaps"] == 1
    assert imported.state == "needs_conversion"
    assert intake.state == "needs_conversion"
    assert intake.error == "PDF conversion is required"
    apply_async.assert_not_called()


@pytest.mark.unit
def test_stale_queued_text_record_is_reindexed_without_reingestion(db_session, tmp_path):
    integration = _integration(db_session)
    original = tmp_path / "searchable.pdf"
    original.write_bytes(b"searchable")
    record = _file_record(db_session, original, filename="searchable.pdf")
    record.ocr_text = "Useful embedded document text"
    intake = DocumentIntake(
        principal_id=integration.owner_id,
        idempotency_key="dropbox:stale-searchable",
        source="dropbox-corpus",
        original_filename="searchable.pdf",
        local_path=str(original),
        task_id="stale-searchable-task",
        state="queued",
        updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(intake)
    db_session.flush()
    imported = DropboxImportObject(
        integration_id=integration.id,
        dropbox_file_id="id:stale-searchable",
        revision="rev-1",
        remote_path="/Posteingang/searchable.pdf",
        intake_id=intake.id,
        task_id="stale-searchable-task",
        state="queued",
    )
    db_session.add_all(
        [
            imported,
            ProcessingLog(
                file_id=record.id,
                task_id="stale-searchable-task",
                step_name="process_document",
                status="success",
            ),
        ]
    )
    db_session.commit()

    with patch("app.tasks.vector_index.index_document_vectors.apply_async") as index:
        from app.tasks.dropbox_corpus_import import _reconcile_stale_queued

        queued, gaps = _reconcile_stale_queued(
            db_session,
            integration,
            stale_before=datetime.now(timezone.utc) - timedelta(minutes=15),
            limit=10,
        )

    db_session.refresh(imported)
    db_session.refresh(intake)
    assert (queued, gaps) == (1, 0)
    assert imported.state == "indexing"
    assert intake.state == "indexing"
    index.assert_called_once_with(
        args=[record.id],
        kwargs={"source_task_id": "stale-searchable-task"},
        priority=9,
    )


@pytest.mark.unit
def test_stale_queued_textless_record_moves_to_deferred_ocr(db_session, tmp_path):
    integration = _integration(db_session)
    original = tmp_path / "scan.pdf"
    original.write_bytes(b"scan")
    record = _file_record(db_session, original)
    intake = DocumentIntake(
        principal_id=integration.owner_id,
        idempotency_key="dropbox:stale-scan",
        source="dropbox-corpus",
        original_filename="scan.pdf",
        local_path=str(original),
        task_id="stale-scan-task",
        state="queued",
        updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(intake)
    db_session.flush()
    imported = DropboxImportObject(
        integration_id=integration.id,
        dropbox_file_id="id:stale-scan",
        revision="rev-1",
        remote_path="/Posteingang/scan.pdf",
        intake_id=intake.id,
        task_id="stale-scan-task",
        state="queued",
    )
    db_session.add_all(
        [
            imported,
            ProcessingLog(
                file_id=record.id,
                task_id="stale-scan-task",
                step_name="process_document",
                status="skipped",
            ),
        ]
    )
    db_session.commit()

    with patch("app.tasks.vector_index.index_document_vectors.apply_async") as index:
        from app.tasks.dropbox_corpus_import import _reconcile_stale_queued

        queued, gaps = _reconcile_stale_queued(
            db_session,
            integration,
            stale_before=datetime.now(timezone.utc) - timedelta(minutes=15),
            limit=10,
        )

    db_session.refresh(imported)
    db_session.refresh(intake)
    assert (queued, gaps) == (0, 0)
    assert imported.state == "needs_ocr"
    assert intake.state == "needs_ocr"
    index.assert_not_called()


@pytest.mark.unit
def test_stale_queue_reconciliation_runs_when_deferred_ocr_is_disabled(db_session, tmp_path):
    integration = _integration(
        db_session,
        config={
            "backfill_index_first_enabled": True,
            "backfill_deferred_ocr_enabled": False,
            "backfill_stale_queue_seconds": 60,
            "backfill_ocr_recheck_seconds": 17,
        },
    )
    job = DropboxImportJob(
        id="reconcile-without-ocr-job",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Posteingang",
        state="completed",
        is_backfill=True,
    )
    original = tmp_path / "searchable-without-ocr.pdf"
    original.write_bytes(b"searchable")
    record = _file_record(db_session, original, filename="searchable-without-ocr.pdf")
    record.ocr_text = "Existing embedded text"
    intake = DocumentIntake(
        principal_id=integration.owner_id,
        idempotency_key="dropbox:reconcile-without-ocr",
        source="dropbox-corpus",
        original_filename="searchable-without-ocr.pdf",
        local_path=str(original),
        task_id="reconcile-without-ocr-task",
        state="queued",
        updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add_all([job, intake])
    db_session.flush()
    imported = DropboxImportObject(
        integration_id=integration.id,
        dropbox_file_id="id:reconcile-without-ocr",
        revision="rev-1",
        remote_path="/Posteingang/searchable-without-ocr.pdf",
        intake_id=intake.id,
        task_id="reconcile-without-ocr-task",
        state="queued",
    )
    db_session.add_all(
        [
            imported,
            ProcessingLog(
                file_id=record.id,
                task_id="reconcile-without-ocr-task",
                step_name="process_document",
                status="success",
            ),
        ]
    )
    db_session.commit()

    with (
        patch("app.tasks.dropbox_corpus_import.settings.vector_index_enabled", True),
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=0),
        patch("app.tasks.vector_index.index_document_vectors.apply_async") as index,
        patch("app.tasks.process_with_ocr.process_with_ocr.apply_async") as ocr,
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_ocr_backlog") as schedule,
    ):
        from app.tasks.dropbox_corpus_import import run_dropbox_corpus_ocr_backlog

        result = run_dropbox_corpus_ocr_backlog.run(job.id)

    db_session.refresh(imported)
    assert result == {
        "status": "running",
        "job_id": job.id,
        "queued": 1,
        "failed": 0,
        "resume_in_seconds": 17,
    }
    assert imported.state == "indexing"
    index.assert_called_once()
    ocr.assert_not_called()
    schedule.assert_called_once_with(job.id, countdown=17)


@pytest.mark.unit
def test_stale_queued_unprocessed_file_is_requeued_once(db_session, tmp_path):
    integration = _integration(db_session)
    staged = tmp_path / "staged.pdf"
    staged.write_bytes(b"staged")
    intake = DocumentIntake(
        principal_id=integration.owner_id,
        idempotency_key="dropbox:stale-unprocessed",
        source="dropbox-corpus",
        original_filename="staged.pdf",
        local_path=str(staged),
        task_id="stale-unprocessed-task",
        state="queued",
        updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(intake)
    db_session.flush()
    imported = DropboxImportObject(
        integration_id=integration.id,
        dropbox_file_id="id:stale-unprocessed",
        revision="rev-1",
        remote_path="/Posteingang/staged.pdf",
        intake_id=intake.id,
        task_id="stale-unprocessed-task",
        state="queued",
    )
    db_session.add(imported)
    db_session.commit()

    with patch("app.api.intake._queue_document") as queue_document:
        from app.tasks.dropbox_corpus_import import _reconcile_stale_queued

        first = _reconcile_stale_queued(
            db_session,
            integration,
            stale_before=datetime.now(timezone.utc) - timedelta(minutes=15),
            limit=10,
        )
        second = _reconcile_stale_queued(
            db_session,
            integration,
            stale_before=datetime.now(timezone.utc) - timedelta(minutes=15),
            limit=10,
        )

    db_session.refresh(imported)
    db_session.refresh(intake)
    assert first == (1, 0)
    assert second == (0, 0)
    assert imported.state == "requeue_claimed"
    assert intake.state == "requeue_claimed"
    queue_document.assert_called_once_with(
        str(staged),
        "staged.pdf",
        None,
        None,
        index_only=True,
        task_id="stale-unprocessed-task",
    )


@pytest.mark.unit
def test_stale_queued_missing_staging_file_is_reported_as_gap(db_session, tmp_path):
    integration = _integration(db_session)
    intake = DocumentIntake(
        principal_id=integration.owner_id,
        idempotency_key="dropbox:stale-missing",
        source="dropbox-corpus",
        original_filename="missing.pdf",
        local_path=str(tmp_path / "missing.pdf"),
        task_id="stale-missing-task",
        state="queued",
        updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(intake)
    db_session.flush()
    imported = DropboxImportObject(
        integration_id=integration.id,
        dropbox_file_id="id:stale-missing",
        revision="rev-1",
        remote_path="/Posteingang/missing.pdf",
        intake_id=intake.id,
        task_id="stale-missing-task",
        state="queued",
    )
    db_session.add(imported)
    db_session.commit()

    from app.tasks.dropbox_corpus_import import _reconcile_stale_queued

    queued, gaps = _reconcile_stale_queued(
        db_session,
        integration,
        stale_before=datetime.now(timezone.utc) - timedelta(minutes=15),
        limit=10,
    )

    db_session.refresh(imported)
    db_session.refresh(intake)
    assert (queued, gaps) == (0, 1)
    assert imported.state == "requeue_missing"
    assert intake.state == "requeue_missing"
    assert intake.error == "Staged corpus file is unavailable"


@pytest.mark.unit
def test_fresh_queued_record_keeps_coordinator_running_without_requeue(db_session):
    integration = _integration(
        db_session,
        config={
            "backfill_index_first_enabled": True,
            "backfill_deferred_ocr_enabled": True,
            "backfill_ocr_recheck_seconds": 13,
            "backfill_stale_queue_seconds": 900,
        },
    )
    job = DropboxImportJob(
        id="fresh-queued-job",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Posteingang",
        state="completed",
        is_backfill=True,
    )
    intake = DocumentIntake(
        principal_id=integration.owner_id,
        idempotency_key="dropbox:fresh-queued",
        source="dropbox-corpus",
        original_filename="fresh.pdf",
        task_id="fresh-queued-task",
        state="queued",
    )
    db_session.add_all([job, intake])
    db_session.flush()
    imported = DropboxImportObject(
        integration_id=integration.id,
        dropbox_file_id="id:fresh-queued",
        revision="rev-1",
        remote_path="/Posteingang/fresh.pdf",
        intake_id=intake.id,
        task_id="fresh-queued-task",
        state="queued",
    )
    db_session.add(imported)
    db_session.commit()

    with (
        patch("app.tasks.dropbox_corpus_import.settings.vector_index_enabled", True),
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=0),
        patch("app.api.intake._queue_document") as queue_document,
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_ocr_backlog") as schedule,
    ):
        from app.tasks.dropbox_corpus_import import run_dropbox_corpus_ocr_backlog

        result = run_dropbox_corpus_ocr_backlog.run(job.id)

    assert result == {
        "status": "running",
        "job_id": job.id,
        "queued": 0,
        "failed": 0,
        "resume_in_seconds": 13,
    }
    queue_document.assert_not_called()
    schedule.assert_called_once_with(job.id, countdown=13)


@pytest.mark.unit
def test_deferred_ocr_backlog_respects_queue_high_watermark(db_session):
    integration = _integration(
        db_session,
        config={
            "backfill_index_first_enabled": True,
            "backfill_deferred_ocr_enabled": True,
            "backfill_queue_high_watermark": 3,
            "backfill_ocr_recheck_seconds": 11,
        },
    )
    job = DropboxImportJob(
        id="queue-limited-job",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Posteingang",
        state="completed",
        is_backfill=True,
    )
    db_session.add(job)
    db_session.commit()

    with (
        patch("app.tasks.dropbox_corpus_import.settings.vector_index_enabled", True),
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=3),
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_ocr_backlog") as schedule,
    ):
        from app.tasks.dropbox_corpus_import import run_dropbox_corpus_ocr_backlog

        result = run_dropbox_corpus_ocr_backlog.run(job.id)

    assert result == {
        "status": "paused",
        "job_id": job.id,
        "queue_depth": 3,
        "resume_in_seconds": 11,
    }
    schedule.assert_called_once_with(job.id, countdown=11)


@pytest.mark.unit
def test_deferred_ocr_backlog_waits_for_vector_index_retries(db_session):
    integration = _integration(
        db_session,
        config={
            "backfill_index_first_enabled": True,
            "backfill_deferred_ocr_enabled": True,
            "backfill_ocr_recheck_seconds": 13,
        },
    )
    job = DropboxImportJob(
        id="vector-retry-job",
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path="/Posteingang",
        state="completed",
        is_backfill=True,
    )
    imported = DropboxImportObject(
        integration_id=integration.id,
        dropbox_file_id="id:vector-retry",
        revision="rev-1",
        remote_path="/Posteingang/vector-retry.pdf",
        task_id="vector-retry-task",
        state="index_retrying",
    )
    db_session.add_all([job, imported])
    db_session.commit()

    with (
        patch("app.tasks.dropbox_corpus_import.settings.vector_index_enabled", True),
        patch("app.tasks.dropbox_corpus_import.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.dropbox_corpus_import._pending_queue_depth", return_value=0),
        patch("app.tasks.dropbox_corpus_import.schedule_dropbox_corpus_ocr_backlog") as schedule,
    ):
        from app.tasks.dropbox_corpus_import import run_dropbox_corpus_ocr_backlog

        result = run_dropbox_corpus_ocr_backlog.run(job.id)

    assert result == {
        "status": "running",
        "job_id": job.id,
        "queued": 0,
        "failed": 0,
        "resume_in_seconds": 13,
    }
    schedule.assert_called_once_with(job.id, countdown=13)
