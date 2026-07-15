"""Qdrant behaves like a first-class per-user destination."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models import DocumentIntake, FileRecord, IntegrationType


def test_vector_database_is_supported_integration_type():
    assert IntegrationType.VECTOR_DATABASE in IntegrationType.ALL


def test_vector_connection_uses_operator_qdrant(monkeypatch):
    monkeypatch.setattr("app.config.settings.vector_index_enabled", True)
    monkeypatch.setattr("app.config.settings.vector_index_collection", "DocuElevate Preprod")

    with patch("app.utils.vector_index.QdrantVectorIndex.status", return_value={"collection": "DocuElevate Preprod"}):
        from app.api.integrations import _test_vector_database_connection

        result = _test_vector_database_connection({"provider": "qdrant"}, None)

    assert result == {"success": True, "message": "Qdrant collection 'DocuElevate Preprod' is ready"}


def test_vector_upload_indexes_file_record(monkeypatch, tmp_path):
    monkeypatch.setattr("app.tasks.upload_to_user_integration.settings.vector_index_enabled", True)
    monkeypatch.setattr("app.tasks.upload_to_user_integration.settings.vector_index_collection", "DocuElevate Preprod")
    record = SimpleNamespace(id=42, ocr_text="project plan")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = record
    db_context = MagicMock()
    db_context.__enter__.return_value = db
    file_path = tmp_path / "document.pdf"
    file_path.write_bytes(b"%PDF")

    with (
        patch("app.tasks.upload_to_user_integration.SessionLocal", return_value=db_context),
        patch("app.utils.vector_index.QdrantVectorIndex.index_document", return_value=3) as index_document,
    ):
        from app.tasks.upload_to_user_integration import _upload_vector_database

        result = _upload_vector_database(str(file_path), {"provider": "qdrant"}, {}, "task-1", file_id=42)

    index_document.assert_called_once_with(record)
    assert result["status"] == "Completed"
    assert result["chunks_indexed"] == 3
    assert result["collection"] == "DocuElevate Preprod"


def test_automatic_index_defers_to_vector_destination(monkeypatch):
    monkeypatch.setattr("app.tasks.compute_embedding.settings.vector_index_enabled", True)
    record = SimpleNamespace(id=42, owner_id="owner-1")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [record, (7,)]
    db_context = MagicMock()
    db_context.__enter__.return_value = db

    with (
        patch("app.tasks.compute_embedding.SessionLocal", return_value=db_context),
        patch("app.tasks.vector_index.index_document_vectors.delay") as delay,
    ):
        from app.tasks.compute_embedding import _queue_vector_index

        _queue_vector_index(record.id)

    delay.assert_not_called()


def test_index_first_vector_task_completes_source_ledger(db_session):
    record = FileRecord(
        filehash="vector-ledger",
        original_filename="plan.pdf",
        local_filename="/workdir/original/plan.pdf",
        file_size=10,
        mime_type="application/pdf",
        ocr_text="The project milestone is next Friday.",
    )
    intake = DocumentIntake(
        principal_id="owner",
        idempotency_key="dropbox:plan",
        source="dropbox",
        original_filename="plan.pdf",
        task_id="source-task",
        state="indexing",
    )
    db_session.add_all([record, intake])
    db_session.commit()

    with (
        patch("app.tasks.vector_index.settings.vector_index_enabled", True),
        patch("app.tasks.vector_index.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.utils.vector_index.QdrantVectorIndex.index_document", return_value=2),
    ):
        from app.tasks.vector_index import index_document_vectors

        result = index_document_vectors.run(record.id, source_task_id="source-task")

    db_session.refresh(intake)
    assert result == {"status": "success", "file_id": record.id, "chunks_indexed": 2}
    assert intake.state == "indexed"
    assert intake.error is None
