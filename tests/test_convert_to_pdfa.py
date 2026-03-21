"""Unit tests for app/tasks/convert_to_pdfa.py module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.convert_to_pdfa import (
    PDFA_ORIGINAL_SUBDIR,
    PDFA_PROCESSED_SUBDIR,
    _compute_pdfa_folder_overrides,
    _convert_pdf_to_pdfa,
    _timestamp_file,
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

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/usr/bin/ocrmypdf"
        assert "--skip-text" in cmd
        assert "--output-type" in cmd
        assert "pdfa-2" in cmd
        assert "--quiet" in cmd
        assert "--invalidate-digital-signatures" in cmd
        # "--" must be present to terminate option parsing and prevent paths
        # starting with "-" from being interpreted as flags (command injection guard)
        assert "--" in cmd
        assert cmd.index("--") < cmd.index("/input.pdf")
        assert cmd.index("--") < cmd.index("/output.pdf")
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
            assert "--" in cmd
            assert cmd.index("--") < cmd.index("/input.pdf")

    def test_invalid_pdfa_format_rejected(self):
        """Test that invalid PDF/A format values are rejected."""
        result = _convert_pdf_to_pdfa("/input.pdf", "/output.pdf", "invalid")
        assert result is False

    @patch("app.tasks.convert_to_pdfa.subprocess.run")
    @patch("app.tasks.convert_to_pdfa.shutil.which", return_value="/usr/bin/ocrmypdf")
    def test_conversion_failure_empty_stderr(self, mock_which, mock_run):
        """Test handles empty stderr on failure."""
        mock_run.return_value = MagicMock(returncode=2, stderr="")
        result = _convert_pdf_to_pdfa("/input.pdf", "/output.pdf")
        assert result is False


@pytest.mark.unit
class TestTimestampFile:
    """Tests for the _timestamp_file helper function."""

    @patch("app.tasks.convert_to_pdfa.os.path.exists", return_value=False)
    @patch("app.tasks.convert_to_pdfa.http_requests.post")
    @patch("app.tasks.convert_to_pdfa.subprocess.run")
    @patch("app.tasks.convert_to_pdfa.shutil.which", return_value="/usr/bin/openssl")
    def test_successful_timestamp(self, mock_which, mock_run, mock_post, mock_exists):
        """Test successful RFC 3161 timestamping."""
        mock_run.return_value = MagicMock(returncode=0)
        mock_post.return_value = MagicMock(status_code=200, content=b"tsr-data")

        with patch("builtins.open", MagicMock()):
            result = _timestamp_file("/test.pdf", "https://freetsa.org/tsr")

        assert result == "/test.pdf.tsr"
        mock_which.assert_called_once_with("openssl")
        mock_run.assert_called_once()
        mock_post.assert_called_once()

    @patch("app.tasks.convert_to_pdfa.shutil.which", return_value=None)
    def test_openssl_not_found(self, mock_which):
        """Test returns None when openssl is not on PATH."""
        result = _timestamp_file("/test.pdf", "https://freetsa.org/tsr")
        assert result is None

    @patch("app.tasks.convert_to_pdfa.os.path.exists", return_value=False)
    @patch("app.tasks.convert_to_pdfa.subprocess.run")
    @patch("app.tasks.convert_to_pdfa.shutil.which", return_value="/usr/bin/openssl")
    def test_openssl_ts_query_fails(self, mock_which, mock_run, mock_exists):
        """Test returns None when openssl ts -query fails."""
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        result = _timestamp_file("/test.pdf", "https://freetsa.org/tsr")
        assert result is None

    @patch("app.tasks.convert_to_pdfa.os.path.exists", return_value=False)
    @patch("app.tasks.convert_to_pdfa.http_requests.post")
    @patch("app.tasks.convert_to_pdfa.subprocess.run")
    @patch("app.tasks.convert_to_pdfa.shutil.which", return_value="/usr/bin/openssl")
    def test_tsa_returns_error(self, mock_which, mock_run, mock_post, mock_exists):
        """Test returns None when TSA returns non-200 status."""
        mock_run.return_value = MagicMock(returncode=0)
        mock_post.return_value = MagicMock(status_code=500)

        with patch("builtins.open", MagicMock()):
            result = _timestamp_file("/test.pdf", "https://freetsa.org/tsr")

        assert result is None

    @patch("app.tasks.convert_to_pdfa.os.path.exists", return_value=False)
    @patch("app.tasks.convert_to_pdfa.http_requests.post")
    @patch("app.tasks.convert_to_pdfa.subprocess.run")
    @patch("app.tasks.convert_to_pdfa.shutil.which", return_value="/usr/bin/openssl")
    def test_tsa_network_error(self, mock_which, mock_run, mock_post, mock_exists):
        """Test returns None on network error contacting TSA."""
        import requests

        mock_run.return_value = MagicMock(returncode=0)
        mock_post.side_effect = requests.ConnectionError("Network error")

        with patch("builtins.open", MagicMock()):
            result = _timestamp_file("/test.pdf", "https://freetsa.org/tsr")

        assert result is None

    @patch("app.tasks.convert_to_pdfa.os.path.exists", return_value=False)
    @patch("app.tasks.convert_to_pdfa.subprocess.run")
    @patch("app.tasks.convert_to_pdfa.shutil.which", return_value="/usr/bin/openssl")
    def test_openssl_timeout(self, mock_which, mock_run, mock_exists):
        """Test returns None when openssl times out."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="openssl", timeout=30)
        result = _timestamp_file("/test.pdf", "https://freetsa.org/tsr")
        assert result is None


@pytest.mark.unit
class TestComputePdfaFolderOverrides:
    """Tests for _compute_pdfa_folder_overrides helper."""

    @patch("app.tasks.convert_to_pdfa.settings")
    def test_appends_subfolder_to_providers(self, mock_settings):
        """Test subfolder is appended to each provider's folder."""
        mock_settings.pdfa_upload_folder = "pdfa"
        mock_settings.dropbox_folder = "/Documents"
        mock_settings.nextcloud_folder = "/Files"
        mock_settings.webdav_folder = "/webdav"
        mock_settings.ftp_folder = "/uploads"
        mock_settings.sftp_folder = "/remote"
        mock_settings.onedrive_folder_path = "Documents/Uploads"
        mock_settings.s3_folder_prefix = "docs/"
        mock_settings.google_drive_pdfa_folder_id = "gdrive-pdfa-folder-id"

        overrides = _compute_pdfa_folder_overrides()

        assert overrides["dropbox"] == "/Documents/pdfa"
        assert overrides["nextcloud"] == "/Files/pdfa"
        assert overrides["webdav"] == "/webdav/pdfa"
        assert overrides["ftp"] == "/uploads/pdfa"
        assert overrides["sftp"] == "/remote/pdfa"
        assert overrides["onedrive"] == "Documents/Uploads/pdfa"
        assert overrides["s3"] == "docs/pdfa/"
        assert overrides["google_drive"] == "gdrive-pdfa-folder-id"

    @patch("app.tasks.convert_to_pdfa.settings")
    def test_empty_subfolder_returns_empty(self, mock_settings):
        """Test empty subfolder returns empty overrides dict."""
        mock_settings.pdfa_upload_folder = ""
        overrides = _compute_pdfa_folder_overrides()
        assert overrides == {}

    @patch("app.tasks.convert_to_pdfa.settings")
    def test_no_gdrive_pdfa_id_excluded(self, mock_settings):
        """Test Google Drive excluded when no dedicated folder ID set."""
        mock_settings.pdfa_upload_folder = "archive"
        mock_settings.dropbox_folder = "/docs"
        mock_settings.nextcloud_folder = ""
        mock_settings.webdav_folder = ""
        mock_settings.ftp_folder = ""
        mock_settings.sftp_folder = ""
        mock_settings.onedrive_folder_path = ""
        mock_settings.s3_folder_prefix = ""
        mock_settings.google_drive_pdfa_folder_id = ""

        overrides = _compute_pdfa_folder_overrides()

        assert overrides["dropbox"] == "/docs/archive"
        assert "google_drive" not in overrides


@pytest.mark.unit
class TestConvertToPdfaTask:
    """Tests for the convert_to_pdfa Celery task."""

    def _mock_settings(self, mock_settings):
        """Set standard mock settings for PDF/A tests."""
        mock_settings.workdir = "/workdir"
        mock_settings.pdfa_format = "2"
        mock_settings.pdfa_upload_original = False
        mock_settings.pdfa_upload_processed = False
        mock_settings.pdfa_timestamp_enabled = False
        mock_settings.pdfa_timestamp_url = "https://freetsa.org/tsr"

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
        self._mock_settings(mock_settings)
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
        self._mock_settings(mock_settings)
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

    @patch("app.tasks.convert_to_pdfa.settings")
    @patch("app.tasks.convert_to_pdfa.log_task_progress")
    @patch("app.tasks.convert_to_pdfa.SessionLocal")
    def test_skips_missing_files(self, mock_session_local, mock_log, mock_settings):
        """Test skips conversion when original/processed files don't exist."""
        self._mock_settings(mock_settings)
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_record = MagicMock()
        mock_record.original_file_path = None
        mock_record.processed_file_path = None
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_record

        convert_to_pdfa.request.id = "test-task-id"
        result = convert_to_pdfa.__wrapped__(file_id=1)
        assert result["status"] == "failure"

    @patch("app.tasks.convert_to_pdfa._compute_pdfa_folder_overrides", return_value={"dropbox": "/docs/pdfa"})
    @patch("app.tasks.send_to_all.send_to_all_destinations")
    @patch("app.tasks.convert_to_pdfa.settings")
    @patch("app.tasks.convert_to_pdfa._convert_pdf_to_pdfa", return_value=True)
    @patch("app.tasks.convert_to_pdfa.get_unique_filepath_with_counter")
    @patch("app.tasks.convert_to_pdfa.os.makedirs")
    @patch("app.tasks.convert_to_pdfa.os.path.exists", return_value=True)
    @patch("app.tasks.convert_to_pdfa.log_task_progress")
    @patch("app.tasks.convert_to_pdfa.SessionLocal")
    def test_uploads_processed_pdfa_when_enabled(
        self,
        mock_session_local,
        mock_log,
        mock_exists,
        mock_makedirs,
        mock_unique_path,
        mock_convert,
        mock_settings,
        mock_send_all,
        mock_overrides,
    ):
        """Test uploads processed PDF/A with folder overrides when enabled."""
        self._mock_settings(mock_settings)
        mock_settings.pdfa_upload_processed = True
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
        convert_to_pdfa.__wrapped__(file_id=42)

        mock_send_all.delay.assert_called_once_with(
            "/workdir/pdfa/processed/test-PDFA.pdf",
            True,
            42,
            folder_overrides={"dropbox": "/docs/pdfa"},
        )

    @patch("app.tasks.convert_to_pdfa._compute_pdfa_folder_overrides", return_value={"s3": "docs/pdfa/"})
    @patch("app.tasks.send_to_all.send_to_all_destinations")
    @patch("app.tasks.convert_to_pdfa.settings")
    @patch("app.tasks.convert_to_pdfa._convert_pdf_to_pdfa", return_value=True)
    @patch("app.tasks.convert_to_pdfa.get_unique_filepath_with_counter")
    @patch("app.tasks.convert_to_pdfa.os.makedirs")
    @patch("app.tasks.convert_to_pdfa.os.path.exists", return_value=True)
    @patch("app.tasks.convert_to_pdfa.log_task_progress")
    @patch("app.tasks.convert_to_pdfa.SessionLocal")
    def test_uploads_original_pdfa_when_enabled(
        self,
        mock_session_local,
        mock_log,
        mock_exists,
        mock_makedirs,
        mock_unique_path,
        mock_convert,
        mock_settings,
        mock_send_all,
        mock_overrides,
    ):
        """Test uploads original PDF/A to providers when pdfa_upload_original is True."""
        self._mock_settings(mock_settings)
        mock_settings.pdfa_upload_original = True
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
        convert_to_pdfa.__wrapped__(file_id=42)

        # Only original should be uploaded
        mock_send_all.delay.assert_called_once()
        call_args = mock_send_all.delay.call_args
        assert call_args[0][0] == "/workdir/pdfa/original/test.pdf"

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
        """Test does not upload PDF/A when both upload flags are False."""
        self._mock_settings(mock_settings)
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

    @patch("app.tasks.convert_to_pdfa._timestamp_file", return_value="/workdir/pdfa/original/test.pdf.tsr")
    @patch("app.tasks.convert_to_pdfa.settings")
    @patch("app.tasks.convert_to_pdfa._convert_pdf_to_pdfa", return_value=True)
    @patch("app.tasks.convert_to_pdfa.get_unique_filepath_with_counter")
    @patch("app.tasks.convert_to_pdfa.os.makedirs")
    @patch("app.tasks.convert_to_pdfa.os.path.exists", return_value=True)
    @patch("app.tasks.convert_to_pdfa.log_task_progress")
    @patch("app.tasks.convert_to_pdfa.SessionLocal")
    def test_timestamping_when_enabled(
        self,
        mock_session_local,
        mock_log,
        mock_exists,
        mock_makedirs,
        mock_unique_path,
        mock_convert,
        mock_settings,
        mock_timestamp,
    ):
        """Test RFC 3161 timestamping is called when enabled."""
        self._mock_settings(mock_settings)
        mock_settings.pdfa_timestamp_enabled = True
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
        assert mock_timestamp.call_count == 2

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
        self._mock_settings(mock_settings)

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
