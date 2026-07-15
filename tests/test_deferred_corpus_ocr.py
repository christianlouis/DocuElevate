"""Focused coverage for the OCR-only second pass of index-first corpus imports."""

import json
from contextlib import nullcontext
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
        patch("app.tasks.process_with_ocr.rotate_pdf_pages") as rotate,
        patch("app.tasks.vector_index.index_document_vectors.delay") as index,
    ):
        from app.tasks.process_with_ocr import process_with_ocr

        result = process_with_ocr.run(
            "scan.pdf",
            file_id=record.id,
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
    index.assert_called_once_with(record.id, source_task_id="source-task")
    quality.assert_not_called()
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
        patch("app.tasks.vector_index.index_document_vectors.delay") as index,
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
        patch("app.tasks.vector_index.index_document_vectors.delay"),
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
