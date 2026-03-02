"""Unit tests for app/tasks/convert_to_pdfa.py module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.convert_to_pdfa import (
    PDFA_ORIGINAL_SUBDIR,
    PDFA_PROCESSED_SUBDIR,
    _convert_pdf_to_pdfa,
    convert_to_pdfa,
)


@pytest.mark.unit
class TestConvertPdfToPdfa:
    """Tests for the _convert_pdf_to_pdfa helper function."""

    @patch("app.tasks.convert_to_pdfa.subprocess.run")
    @patch("app.tasks.convert_to_pdfa.shutil.which", return_value="/usr/bin/ocrmypdf")
    def test_successful_conversion(self, mock_which, mock_run):
        """Test successful PDF to PDF/A conversion."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        result = _convert_pdf_to_pdfa("/input.pdf", "/output.pdf", "2")

        assert result is True
        mock_which.assert_called_once_with("ocrmypdf")
        mock_run.assert_called_once()

        # Verify the command arguments
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/usr/bin/ocrmypdf"
        assert "--skip-text" in cmd
        assert "--output-type" in cmd
        assert "pdfa-2" in cmd
        assert "--quiet" in cmd
        assert "--invalidate-digital-signatures" in cmd
        assert "/input.pdf" in cmd
        assert "/output.pdf" in cmd

    @patch("app.tasks.convert_to_pdfa.shutil.which", return_value=None)
    def test_ocrmypdf_not_found(self, mock_which):
        """Test returns False when ocrmypdf binary is not on PATH."""
        result = _convert_pdf_to_pdfa("/input.pdf", "/output.pdf")

        assert result is False

    @patch("app.tasks.convert_to_pdfa.subprocess.run")
    @patch("app.tasks.convert_to_pdfa.shutil.which", return_value="/usr/bin/ocrmypdf")
    def test_conversion_failure(self, mock_which, mock_run):
        """Test returns False when ocrmypdf exits with non-zero code."""
        mock_run.return_value = MagicMock(returncode=1, stderr="Some error occurred")

        result = _convert_pdf_to_pdfa("/input.pdf", "/output.pdf")

        assert result is False

    @patch("app.tasks.convert_to_pdfa.subprocess.run")
    @patch("app.tasks.convert_to_pdfa.shutil.which", return_value="/usr/bin/ocrmypdf")
    def test_conversion_timeout(self, mock_which, mock_run):
        """Test returns False when ocrmypdf times out."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ocrmypdf", timeout=600)

        result = _convert_pdf_to_pdfa("/input.pdf", "/output.pdf")

        assert result is False

    @patch("app.tasks.convert_to_pdfa.subprocess.run")
    @patch("app.tasks.convert_to_pdfa.shutil.which", return_value="/usr/bin/ocrmypdf")
    def test_pdfa_format_variants(self, mock_which, mock_run):
        """Test different PDF/A format variants are passed correctly."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        for fmt in ("1", "2", "3"):
            _convert_pdf_to_pdfa("/input.pdf", "/output.pdf", fmt)
            cmd = mock_run.call_args[0][0]
            assert f"pdfa-{fmt}" in cmd

    @patch("app.tasks.convert_to_pdfa.subprocess.run")
    @patch("app.tasks.convert_to_pdfa.shutil.which", return_value="/usr/bin/ocrmypdf")
    def test_conversion_failure_empty_stderr(self, mock_which, mock_run):
        """Test handles empty stderr on failure."""
        mock_run.return_value = MagicMock(returncode=2, stderr="")

        result = _convert_pdf_to_pdfa("/input.pdf", "/output.pdf")

        assert result is False


@pytest.mark.unit
class TestConvertToPdfaTask:
    """Tests for the convert_to_pdfa Celery task."""

    @patch("app.tasks.convert_to_pdfa.settings")
    @patch("app.tasks.convert_to_pdfa._convert_pdf_to_pdfa", return_value=True)
    @patch("app.tasks.convert_to_pdfa.get_unique_filepath_with_counter")
    @patch("app.tasks.convert_to_pdfa.os.makedirs")
    @patch("app.tasks.convert_to_pdfa.os.path.exists", return_value=True)
    @patch("app.tasks.convert_to_pdfa.log_task_progress")
    @patch("app.tasks.convert_to_pdfa.SessionLocal")
    def test_successful_conversion_both_files(
        self,
        mock_session_local,
        mock_log,
        mock_exists,
        mock_makedirs,
        mock_unique_path,
        mock_convert,
        mock_settings,
    ):
        """Test successful PDF/A conversion of both original and processed files."""
        mock_settings.workdir = "/workdir"
        mock_settings.pdfa_format = "2"
        mock_settings.pdfa_upload_to_providers = False

        # Mock unique path to return predictable paths
        mock_unique_path.side_effect = [
            "/workdir/pdfa/original/test.pdf",
            "/workdir/pdfa/processed/test-PDFA.pdf",
        ]

        # Mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_record = MagicMock()
        mock_record.original_file_path = "/workdir/original/test.pdf"
        mock_record.processed_file_path = "/workdir/processed/test.pdf"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_record

        convert_to_pdfa.request.id = "test-task-id"
        result = convert_to_pdfa.__wrapped__(file_id=1)

        assert result["status"] == "success"
        assert result["file_id"] == 1
        assert "original_pdfa_path" in result
        assert "processed_pdfa_path" in result
        assert mock_convert.call_count == 2

    @patch("app.tasks.convert_to_pdfa.settings")
    @patch("app.tasks.convert_to_pdfa.log_task_progress")
    @patch("app.tasks.convert_to_pdfa.SessionLocal")
    def test_file_record_not_found(self, mock_session_local, mock_log, mock_settings):
        """Test returns error when file record is not found."""
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        convert_to_pdfa.request.id = "test-task-id"
        result = convert_to_pdfa.__wrapped__(file_id=999)

        assert "error" in result
        assert result["file_id"] == 999

    @patch("app.tasks.convert_to_pdfa.settings")
    @patch("app.tasks.convert_to_pdfa._convert_pdf_to_pdfa", return_value=False)
    @patch("app.tasks.convert_to_pdfa.get_unique_filepath_with_counter")
    @patch("app.tasks.convert_to_pdfa.os.makedirs")
    @patch("app.tasks.convert_to_pdfa.os.path.exists", return_value=True)
    @patch("app.tasks.convert_to_pdfa.log_task_progress")
    @patch("app.tasks.convert_to_pdfa.SessionLocal")
    def test_conversion_failure_both_files(
        self,
        mock_session_local,
        mock_log,
        mock_exists,
        mock_makedirs,
        mock_unique_path,
        mock_convert,
        mock_settings,
    ):
        """Test handles failure when both conversions fail."""
        mock_settings.workdir = "/workdir"
        mock_settings.pdfa_format = "2"
        mock_settings.pdfa_upload_to_providers = False

        mock_unique_path.side_effect = [
            "/workdir/pdfa/original/test.pdf",
            "/workdir/pdfa/processed/test-PDFA.pdf",
        ]

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_record = MagicMock()
        mock_record.original_file_path = "/workdir/original/test.pdf"
        mock_record.processed_file_path = "/workdir/processed/test.pdf"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_record

        convert_to_pdfa.request.id = "test-task-id"
        result = convert_to_pdfa.__wrapped__(file_id=1)

        assert result["status"] == "failure"
        assert "original_pdfa_path" not in result
        assert "processed_pdfa_path" not in result

    @patch("app.tasks.convert_to_pdfa.settings")
    @patch("app.tasks.convert_to_pdfa.log_task_progress")
    @patch("app.tasks.convert_to_pdfa.SessionLocal")
    def test_skips_missing_files(self, mock_session_local, mock_log, mock_settings):
        """Test skips conversion when original/processed files don't exist."""
        mock_settings.workdir = "/workdir"
        mock_settings.pdfa_format = "2"
        mock_settings.pdfa_upload_to_providers = False

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_record = MagicMock()
        mock_record.original_file_path = None
        mock_record.processed_file_path = None
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_record

        convert_to_pdfa.request.id = "test-task-id"
        result = convert_to_pdfa.__wrapped__(file_id=1)

        assert result["status"] == "failure"

    @patch("app.tasks.send_to_all.send_to_all_destinations")
    @patch("app.tasks.convert_to_pdfa.settings")
    @patch("app.tasks.convert_to_pdfa._convert_pdf_to_pdfa", return_value=True)
    @patch("app.tasks.convert_to_pdfa.get_unique_filepath_with_counter")
    @patch("app.tasks.convert_to_pdfa.os.makedirs")
    @patch("app.tasks.convert_to_pdfa.os.path.exists", return_value=True)
    @patch("app.tasks.convert_to_pdfa.log_task_progress")
    @patch("app.tasks.convert_to_pdfa.SessionLocal")
    def test_uploads_pdfa_when_enabled(
        self,
        mock_session_local,
        mock_log,
        mock_exists,
        mock_makedirs,
        mock_unique_path,
        mock_convert,
        mock_settings,
        mock_send_all,
    ):
        """Test uploads processed PDF/A to providers when pdfa_upload_to_providers is True."""
        mock_settings.workdir = "/workdir"
        mock_settings.pdfa_format = "2"
        mock_settings.pdfa_upload_to_providers = True

        mock_unique_path.side_effect = [
            "/workdir/pdfa/original/test.pdf",
            "/workdir/pdfa/processed/test-PDFA.pdf",
        ]

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_record = MagicMock()
        mock_record.original_file_path = "/workdir/original/test.pdf"
        mock_record.processed_file_path = "/workdir/processed/test.pdf"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_record

        convert_to_pdfa.request.id = "test-task-id"
        result = convert_to_pdfa.__wrapped__(file_id=42)

        # Verify send_to_all_destinations was called for the PDF/A file
        mock_send_all.delay.assert_called_once_with("/workdir/pdfa/processed/test-PDFA.pdf", True, 42)

    @patch("app.tasks.convert_to_pdfa.settings")
    @patch("app.tasks.convert_to_pdfa._convert_pdf_to_pdfa", return_value=True)
    @patch("app.tasks.convert_to_pdfa.get_unique_filepath_with_counter")
    @patch("app.tasks.convert_to_pdfa.os.makedirs")
    @patch("app.tasks.convert_to_pdfa.os.path.exists", return_value=True)
    @patch("app.tasks.convert_to_pdfa.log_task_progress")
    @patch("app.tasks.convert_to_pdfa.SessionLocal")
    def test_does_not_upload_when_disabled(
        self,
        mock_session_local,
        mock_log,
        mock_exists,
        mock_makedirs,
        mock_unique_path,
        mock_convert,
        mock_settings,
    ):
        """Test does not upload PDF/A when pdfa_upload_to_providers is False."""
        mock_settings.workdir = "/workdir"
        mock_settings.pdfa_format = "2"
        mock_settings.pdfa_upload_to_providers = False

        mock_unique_path.side_effect = [
            "/workdir/pdfa/original/test.pdf",
            "/workdir/pdfa/processed/test-PDFA.pdf",
        ]

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_record = MagicMock()
        mock_record.original_file_path = "/workdir/original/test.pdf"
        mock_record.processed_file_path = "/workdir/processed/test.pdf"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_record

        convert_to_pdfa.request.id = "test-task-id"
        result = convert_to_pdfa.__wrapped__(file_id=1)

        assert result["status"] == "success"

    @patch("app.tasks.convert_to_pdfa.settings")
    @patch("app.tasks.convert_to_pdfa._convert_pdf_to_pdfa")
    @patch("app.tasks.convert_to_pdfa.get_unique_filepath_with_counter")
    @patch("app.tasks.convert_to_pdfa.os.makedirs")
    @patch("app.tasks.convert_to_pdfa.os.path.exists")
    @patch("app.tasks.convert_to_pdfa.log_task_progress")
    @patch("app.tasks.convert_to_pdfa.SessionLocal")
    def test_partial_success_original_only(
        self,
        mock_session_local,
        mock_log,
        mock_exists,
        mock_makedirs,
        mock_unique_path,
        mock_convert,
        mock_settings,
    ):
        """Test partial success when only original conversion succeeds."""
        mock_settings.workdir = "/workdir"
        mock_settings.pdfa_format = "2"
        mock_settings.pdfa_upload_to_providers = False

        # Only original file exists
        def exists_side_effect(path):
            return "/original/" in path

        mock_exists.side_effect = exists_side_effect
        mock_unique_path.return_value = "/workdir/pdfa/original/test.pdf"
        mock_convert.return_value = True

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_record = MagicMock()
        mock_record.original_file_path = "/workdir/original/test.pdf"
        mock_record.processed_file_path = "/workdir/processed/test.pdf"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_record

        convert_to_pdfa.request.id = "test-task-id"
        result = convert_to_pdfa.__wrapped__(file_id=1)

        assert result["status"] == "success"
        assert "original_pdfa_path" in result
        assert "processed_pdfa_path" not in result


@pytest.mark.unit
class TestPdfaSubdirectoryConstants:
    """Tests for PDF/A subdirectory constants."""

    def test_original_subdir(self):
        """Test PDFA_ORIGINAL_SUBDIR is correct."""
        assert "pdfa" in PDFA_ORIGINAL_SUBDIR
        assert "original" in PDFA_ORIGINAL_SUBDIR

    def test_processed_subdir(self):
        """Test PDFA_PROCESSED_SUBDIR is correct."""
        assert "pdfa" in PDFA_PROCESSED_SUBDIR
        assert "processed" in PDFA_PROCESSED_SUBDIR
