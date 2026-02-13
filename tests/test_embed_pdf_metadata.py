"""Comprehensive unit tests for app/tasks/embed_metadata_into_pdf.py module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest

from app.tasks.embed_metadata_into_pdf import embed_metadata_into_pdf, persist_metadata


@pytest.mark.unit
class TestPersistMetadata:
    """Tests for persist_metadata function."""

    @patch("builtins.open", new_callable=mock_open)
    def test_saves_metadata_to_json_file(self, mock_file):
        """Test metadata is saved to JSON file with correct path."""
        metadata = {
            "filename": "test_document.pdf",
            "document_type": "Invoice",
            "tags": ["test", "invoice"],
        }

        result = persist_metadata(metadata, "/workdir/processed/MyFile.pdf")

        assert result == "/workdir/processed/MyFile.json"
        mock_file.assert_called_once_with("/workdir/processed/MyFile.json", "w", encoding="utf-8")

    @patch("builtins.open", new_callable=mock_open)
    @patch("app.tasks.embed_metadata_into_pdf.json.dump")
    def test_augments_metadata_with_file_paths(self, mock_json_dump, mock_file):
        """Test metadata is augmented with file path references."""
        metadata = {"filename": "test.pdf"}

        persist_metadata(
            metadata,
            "/workdir/processed/test.pdf",
            original_file_path="/workdir/original/file.pdf",
            processed_file_path="/workdir/processed/test.pdf",
        )

        # Verify json.dump was called with augmented metadata
        call_args = mock_json_dump.call_args
        augmented_metadata = call_args[0][0]
        assert augmented_metadata["original_file_path"] == "/workdir/original/file.pdf"
        assert augmented_metadata["processed_file_path"] == "/workdir/processed/test.pdf"
        assert augmented_metadata["filename"] == "test.pdf"

    @patch("builtins.open", new_callable=mock_open)
    @patch("app.tasks.embed_metadata_into_pdf.json.dump")
    def test_handles_metadata_without_optional_paths(self, mock_json_dump, mock_file):
        """Test metadata persistence works without optional file paths."""
        metadata = {"filename": "test.pdf"}

        persist_metadata(metadata, "/workdir/processed/test.pdf")

        call_args = mock_json_dump.call_args
        augmented_metadata = call_args[0][0]
        assert "original_file_path" not in augmented_metadata
        assert "processed_file_path" not in augmented_metadata


@pytest.mark.unit
class TestEmbedMetadataIntoPdf:
    """Tests for embed_metadata_into_pdf Celery task."""

    @patch("app.tasks.embed_metadata_into_pdf.finalize_document_storage")
    @patch("app.tasks.embed_metadata_into_pdf.persist_metadata")
    @patch("app.tasks.embed_metadata_into_pdf.shutil.move")
    @patch("app.tasks.embed_metadata_into_pdf.os.makedirs")
    @patch("app.tasks.embed_metadata_into_pdf.get_unique_filepath_with_counter")
    @patch("app.tasks.embed_metadata_into_pdf.sanitize_filename")
    @patch("app.tasks.embed_metadata_into_pdf.SessionLocal")
    @patch("app.tasks.embed_metadata_into_pdf.log_task_progress")
    @patch("builtins.open", new_callable=mock_open, read_data=b"%PDF-1.4 content")
    @patch("app.tasks.embed_metadata_into_pdf.pypdf.PdfReader")
    @patch("app.tasks.embed_metadata_into_pdf.pypdf.PdfWriter")
    def test_successful_metadata_embedding(
        self,
        mock_pdf_writer_class,
        mock_pdf_reader_class,
        mock_file,
        mock_log_progress,
        mock_session_local,
        mock_sanitize,
        mock_unique_path,
        mock_makedirs,
        mock_move,
        mock_persist,
        mock_finalize,
    ):
        """Test successful embedding of metadata into PDF."""
        # Mock PDF reader/writer
        mock_reader = MagicMock()
        mock_reader.pages = [MagicMock(), MagicMock()]
        mock_pdf_reader_class.return_value = mock_reader

        mock_writer = MagicMock()
        mock_pdf_writer_class.return_value = mock_writer

        # Mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_file_record = MagicMock()
        mock_file_record.id = 123
        mock_file_record.original_file_path = "/workdir/original/file.pdf"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_file_record

        # Mock other dependencies
        mock_sanitize.return_value = "2024-01-15_Invoice"
        mock_unique_path.return_value = "/workdir/processed/2024-01-15_Invoice.pdf"
        mock_persist.return_value = "/workdir/processed/2024-01-15_Invoice.json"

        # Mock tempfile
        with patch("app.tasks.embed_metadata_into_pdf.tempfile.NamedTemporaryFile") as mock_tempfile:
            mock_temp = MagicMock()
            mock_temp.name = "/tmp/processed_123.pdf"
            mock_tempfile.return_value = mock_temp

            with patch("app.tasks.embed_metadata_into_pdf.os.path.exists", return_value=True):
                with patch("app.tasks.embed_metadata_into_pdf.shutil.copy"):
                    with patch("app.tasks.embed_metadata_into_pdf.os.remove"):
                        with patch("app.tasks.embed_metadata_into_pdf.settings") as mock_settings:
                            mock_settings.workdir = "/workdir"

                            embed_metadata_into_pdf.request.id = "test-task-id"

                            metadata = {
                                "filename": "2024-01-15_Invoice.pdf",
                                "absender": "Amazon",
                                "document_type": "Invoice",
                                "tags": ["invoice", "amazon"],
                            }

                            result = embed_metadata_into_pdf.__wrapped__(
                                "/workdir/tmp/test.pdf", "Sample text", metadata, file_id=123
                            )

                            # Verify PDF metadata was set
                            mock_writer.add_metadata.assert_called_once()
                            metadata_call = mock_writer.add_metadata.call_args[0][0]
                            assert metadata_call["/Title"] == "2024-01-15_Invoice.pdf"
                            assert metadata_call["/Author"] == "Amazon"
                            assert metadata_call["/Subject"] == "Invoice"
                            assert "invoice" in metadata_call["/Keywords"]
                            assert "amazon" in metadata_call["/Keywords"]

                            # Verify file was moved
                            mock_move.assert_called_once()

                            # Verify finalize task was queued
                            mock_finalize.delay.assert_called_once()

                            # Verify result
                            assert result["file"] == "/workdir/processed/2024-01-15_Invoice.pdf"
                            assert result["metadata_file"] == "/workdir/processed/2024-01-15_Invoice.json"
                            assert result["status"] == "Metadata embedded"

    @patch("app.tasks.embed_metadata_into_pdf.log_task_progress")
    def test_handles_missing_file(self, mock_log_progress):
        """Test handling of missing file."""
        with patch("app.tasks.embed_metadata_into_pdf.os.path.exists", return_value=False):
            with patch("app.tasks.embed_metadata_into_pdf.settings") as mock_settings:
                mock_settings.workdir = "/workdir"

                embed_metadata_into_pdf.request.id = "test-task-id"

                result = embed_metadata_into_pdf.__wrapped__(
                    "/nonexistent/file.pdf", "text", {"filename": "test.pdf"}, file_id=123
                )

                assert result == {"error": "File not found"}
                # Verify failure was logged
                failure_calls = [call for call in mock_log_progress.call_args_list if "failure" in str(call)]
                assert len(failure_calls) > 0

    @patch("app.tasks.embed_metadata_into_pdf.finalize_document_storage")
    @patch("app.tasks.embed_metadata_into_pdf.persist_metadata")
    @patch("app.tasks.embed_metadata_into_pdf.shutil.move")
    @patch("app.tasks.embed_metadata_into_pdf.os.makedirs")
    @patch("app.tasks.embed_metadata_into_pdf.get_unique_filepath_with_counter")
    @patch("app.tasks.embed_metadata_into_pdf.sanitize_filename")
    @patch("app.tasks.embed_metadata_into_pdf.SessionLocal")
    @patch("app.tasks.embed_metadata_into_pdf.log_task_progress")
    def test_retrieves_file_id_from_database(
        self,
        mock_log_progress,
        mock_session_local,
        mock_sanitize,
        mock_unique_path,
        mock_makedirs,
        mock_move,
        mock_persist,
        mock_finalize,
    ):
        """Test file_id retrieval from database when not provided."""
        # Mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_file_record = MagicMock()
        mock_file_record.id = 456
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_file_record

        mock_sanitize.return_value = "test"
        mock_unique_path.return_value = "/workdir/processed/test.pdf"
        mock_persist.return_value = "/workdir/processed/test.json"

        with patch("app.tasks.embed_metadata_into_pdf.os.path.exists", return_value=True):
            with patch("app.tasks.embed_metadata_into_pdf.shutil.copy"):
                with patch("app.tasks.embed_metadata_into_pdf.os.remove"):
                    with patch("app.tasks.embed_metadata_into_pdf.settings") as mock_settings:
                        with patch("builtins.open", new_callable=mock_open, read_data=b"%PDF-1.4"):
                            with patch("app.tasks.embed_metadata_into_pdf.pypdf.PdfReader"):
                                with patch("app.tasks.embed_metadata_into_pdf.pypdf.PdfWriter"):
                                    with patch("app.tasks.embed_metadata_into_pdf.tempfile.NamedTemporaryFile"):
                                        mock_settings.workdir = "/workdir"

                                        embed_metadata_into_pdf.request.id = "test-task-id"

                                        result = embed_metadata_into_pdf.__wrapped__(
                                            "/workdir/tmp/test.pdf", "text", {"filename": "test.pdf"}
                                        )

                                        # Verify database was queried
                                        mock_db.query.assert_called()

    @patch("app.tasks.embed_metadata_into_pdf.log_task_progress")
    @patch("app.tasks.embed_metadata_into_pdf.SessionLocal")
    @patch("builtins.open", new_callable=mock_open, read_data=b"%PDF-1.4")
    @patch("app.tasks.embed_metadata_into_pdf.pypdf.PdfReader")
    def test_handles_pdf_processing_exception(self, mock_pdf_reader, mock_file, mock_session_local, mock_log_progress):
        """Test handling of PDF processing exceptions."""
        mock_pdf_reader.side_effect = Exception("Invalid PDF structure")

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        with patch("app.tasks.embed_metadata_into_pdf.os.path.exists", return_value=True):
            with patch("app.tasks.embed_metadata_into_pdf.shutil.copy"):
                with patch("app.tasks.embed_metadata_into_pdf.os.remove"):
                    with patch("app.tasks.embed_metadata_into_pdf.tempfile.NamedTemporaryFile") as mock_tempfile:
                        mock_temp = MagicMock()
                        mock_temp.name = "/tmp/temp.pdf"
                        mock_tempfile.return_value = mock_temp

                        with patch("app.tasks.embed_metadata_into_pdf.settings") as mock_settings:
                            mock_settings.workdir = "/workdir"

                            embed_metadata_into_pdf.request.id = "test-task-id"

                            result = embed_metadata_into_pdf.__wrapped__(
                                "/workdir/tmp/test.pdf", "text", {"filename": "test.pdf"}, file_id=789
                            )

                            assert "error" in result
                            # Verify failure was logged
                            failure_calls = [
                                call for call in mock_log_progress.call_args_list if "failure" in str(call)
                            ]
                            assert len(failure_calls) > 0

    @patch("app.tasks.embed_metadata_into_pdf.finalize_document_storage")
    @patch("app.tasks.embed_metadata_into_pdf.persist_metadata")
    @patch("app.tasks.embed_metadata_into_pdf.shutil.move")
    @patch("app.tasks.embed_metadata_into_pdf.os.makedirs")
    @patch("app.tasks.embed_metadata_into_pdf.get_unique_filepath_with_counter")
    @patch("app.tasks.embed_metadata_into_pdf.sanitize_filename")
    @patch("app.tasks.embed_metadata_into_pdf.SessionLocal")
    @patch("app.tasks.embed_metadata_into_pdf.log_task_progress")
    @patch("builtins.open", new_callable=mock_open, read_data=b"%PDF-1.4")
    @patch("app.tasks.embed_metadata_into_pdf.pypdf.PdfReader")
    @patch("app.tasks.embed_metadata_into_pdf.pypdf.PdfWriter")
    def test_sanitizes_malicious_filename(
        self,
        mock_pdf_writer_class,
        mock_pdf_reader_class,
        mock_file,
        mock_log_progress,
        mock_session_local,
        mock_sanitize,
        mock_unique_path,
        mock_makedirs,
        mock_move,
        mock_persist,
        mock_finalize,
    ):
        """Test filename sanitization to prevent path traversal."""
        # Mock PDF reader/writer
        mock_reader = MagicMock()
        mock_reader.pages = [MagicMock()]
        mock_pdf_reader_class.return_value = mock_reader
        mock_pdf_writer_class.return_value = MagicMock()

        # Mock database
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        # Sanitize should remove dangerous characters
        mock_sanitize.return_value = "safe_filename"
        mock_unique_path.return_value = "/workdir/processed/safe_filename.pdf"
        mock_persist.return_value = "/workdir/processed/safe_filename.json"

        with patch("app.tasks.embed_metadata_into_pdf.tempfile.NamedTemporaryFile") as mock_tempfile:
            mock_temp = MagicMock()
            mock_temp.name = "/tmp/processed.pdf"
            mock_tempfile.return_value = mock_temp

            with patch("app.tasks.embed_metadata_into_pdf.os.path.exists", return_value=True):
                with patch("app.tasks.embed_metadata_into_pdf.shutil.copy"):
                    with patch("app.tasks.embed_metadata_into_pdf.os.remove"):
                        with patch("app.tasks.embed_metadata_into_pdf.settings") as mock_settings:
                            mock_settings.workdir = "/workdir"

                            embed_metadata_into_pdf.request.id = "test-task-id"

                            # Try to embed metadata with malicious filename
                            metadata = {"filename": "../../../etc/passwd"}

                            result = embed_metadata_into_pdf.__wrapped__(
                                "/workdir/tmp/test.pdf", "text", metadata, file_id=111
                            )

                            # Verify sanitize_filename was called
                            mock_sanitize.assert_called_once()

    @patch("app.tasks.embed_metadata_into_pdf.finalize_document_storage")
    @patch("app.tasks.embed_metadata_into_pdf.persist_metadata")
    @patch("app.tasks.embed_metadata_into_pdf.shutil.move")
    @patch("app.tasks.embed_metadata_into_pdf.os.makedirs")
    @patch("app.tasks.embed_metadata_into_pdf.get_unique_filepath_with_counter")
    @patch("app.tasks.embed_metadata_into_pdf.sanitize_filename")
    @patch("app.tasks.embed_metadata_into_pdf.SessionLocal")
    @patch("app.tasks.embed_metadata_into_pdf.log_task_progress")
    @patch("builtins.open", new_callable=mock_open, read_data=b"%PDF-1.4")
    @patch("app.tasks.embed_metadata_into_pdf.pypdf.PdfReader")
    @patch("app.tasks.embed_metadata_into_pdf.pypdf.PdfWriter")
    def test_handles_missing_metadata_fields(
        self,
        mock_pdf_writer_class,
        mock_pdf_reader_class,
        mock_file,
        mock_log_progress,
        mock_session_local,
        mock_sanitize,
        mock_unique_path,
        mock_makedirs,
        mock_move,
        mock_persist,
        mock_finalize,
    ):
        """Test handling of metadata with missing fields."""
        mock_reader = MagicMock()
        mock_reader.pages = [MagicMock()]
        mock_pdf_reader_class.return_value = mock_reader

        mock_writer = MagicMock()
        mock_pdf_writer_class.return_value = mock_writer

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        mock_sanitize.return_value = "test"
        mock_unique_path.return_value = "/workdir/processed/test.pdf"
        mock_persist.return_value = "/workdir/processed/test.json"

        with patch("app.tasks.embed_metadata_into_pdf.tempfile.NamedTemporaryFile") as mock_tempfile:
            mock_temp = MagicMock()
            mock_temp.name = "/tmp/temp.pdf"
            mock_tempfile.return_value = mock_temp

            with patch("app.tasks.embed_metadata_into_pdf.os.path.exists", return_value=True):
                with patch("app.tasks.embed_metadata_into_pdf.shutil.copy"):
                    with patch("app.tasks.embed_metadata_into_pdf.os.remove"):
                        with patch("app.tasks.embed_metadata_into_pdf.settings") as mock_settings:
                            mock_settings.workdir = "/workdir"

                            embed_metadata_into_pdf.request.id = "test-task-id"

                            # Metadata with missing fields
                            metadata = {}

                            result = embed_metadata_into_pdf.__wrapped__(
                                "/workdir/tmp/test.pdf", "text", metadata, file_id=222
                            )

                            # Verify PDF metadata was set with defaults
                            mock_writer.add_metadata.assert_called_once()
                            metadata_call = mock_writer.add_metadata.call_args[0][0]
                            assert metadata_call["/Title"] == "Unknown Document"
                            assert metadata_call["/Author"] == "Unknown"
                            assert metadata_call["/Subject"] == "Unknown"
                            assert metadata_call["/Keywords"] == ""

    @patch("app.tasks.embed_metadata_into_pdf.finalize_document_storage")
    @patch("app.tasks.embed_metadata_into_pdf.persist_metadata")
    @patch("app.tasks.embed_metadata_into_pdf.shutil.move")
    @patch("app.tasks.embed_metadata_into_pdf.os.makedirs")
    @patch("app.tasks.embed_metadata_into_pdf.get_unique_filepath_with_counter")
    @patch("app.tasks.embed_metadata_into_pdf.sanitize_filename")
    @patch("app.tasks.embed_metadata_into_pdf.SessionLocal")
    @patch("app.tasks.embed_metadata_into_pdf.log_task_progress")
    @patch("builtins.open", new_callable=mock_open, read_data=b"%PDF-1.4")
    @patch("app.tasks.embed_metadata_into_pdf.pypdf.PdfReader")
    @patch("app.tasks.embed_metadata_into_pdf.pypdf.PdfWriter")
    def test_deletes_original_file_from_tmp(
        self,
        mock_pdf_writer_class,
        mock_pdf_reader_class,
        mock_file,
        mock_log_progress,
        mock_session_local,
        mock_sanitize,
        mock_unique_path,
        mock_makedirs,
        mock_move,
        mock_persist,
        mock_finalize,
    ):
        """Test that original file in tmp directory is deleted after processing."""
        mock_reader = MagicMock()
        mock_reader.pages = [MagicMock()]
        mock_pdf_reader_class.return_value = mock_reader
        mock_pdf_writer_class.return_value = MagicMock()

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        mock_sanitize.return_value = "test"
        mock_unique_path.return_value = "/workdir/processed/test.pdf"
        mock_persist.return_value = "/workdir/processed/test.json"

        with patch("app.tasks.embed_metadata_into_pdf.tempfile.NamedTemporaryFile") as mock_tempfile:
            mock_temp = MagicMock()
            mock_temp.name = "/tmp/temp.pdf"
            mock_tempfile.return_value = mock_temp

            with patch("app.tasks.embed_metadata_into_pdf.os.path.exists", return_value=True):
                with patch("app.tasks.embed_metadata_into_pdf.shutil.copy"):
                    with patch("app.tasks.embed_metadata_into_pdf.Path") as mock_path_class:
                        # Mock Path for deletion logic
                        mock_original_path = MagicMock()
                        mock_resolved_path = MagicMock()
                        mock_resolved_path.exists.return_value = True
                        mock_resolved_path.is_relative_to.return_value = True
                        mock_original_path.resolve.return_value = mock_resolved_path
                        mock_workdir_path = MagicMock()
                        mock_path_class.side_effect = [mock_workdir_path, mock_original_path]

                        with patch("app.tasks.embed_metadata_into_pdf.os.remove"):
                            with patch("app.tasks.embed_metadata_into_pdf.settings") as mock_settings:
                                mock_settings.workdir = "/workdir"

                                embed_metadata_into_pdf.request.id = "test-task-id"

                                result = embed_metadata_into_pdf.__wrapped__(
                                    "/workdir/tmp/test.pdf", "text", {"filename": "test.pdf"}, file_id=333
                                )

                                # Verify unlink (delete) was called on the resolved path
                                mock_resolved_path.unlink.assert_called_once()
