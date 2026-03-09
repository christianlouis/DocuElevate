"""Tests for app/tasks/watch_folder_tasks.py module."""

import os
import stat
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestCacheHelpers:
    """Tests for the cache helper functions in watch_folder_tasks."""

    def test_evict_old_entries_removes_old(self):
        """Entries older than CACHE_RETENTION_DAYS should be removed."""
        from app.tasks.watch_folder_tasks import _evict_old_entries

        old_dt = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        recent_dt = datetime.now(timezone.utc).isoformat()
        data = {"old_key": old_dt, "new_key": recent_dt}
        result = _evict_old_entries(data)
        assert "old_key" not in result
        assert "new_key" in result

    def test_evict_old_entries_empty(self):
        """Empty cache should return empty dict."""
        from app.tasks.watch_folder_tasks import _evict_old_entries

        assert _evict_old_entries({}) == {}

    def test_evict_old_entries_skips_malformed_dates(self):
        """Entries with malformed timestamps should be silently dropped."""
        from app.tasks.watch_folder_tasks import _evict_old_entries

        data = {"bad_key": "not-a-date", "good_key": datetime.now(timezone.utc).isoformat()}
        result = _evict_old_entries(data)
        assert "bad_key" not in result
        assert "good_key" in result

    def test_mark_processed_adds_entry(self):
        """_mark_processed should add an ISO-formatted timestamp for the key."""
        from app.tasks.watch_folder_tasks import _mark_processed

        cache: dict = {}
        _mark_processed(cache, "/some/file.pdf")
        assert "/some/file.pdf" in cache
        # Timestamp should be parseable
        datetime.fromisoformat(cache["/some/file.pdf"])

    def test_load_cache_returns_empty_when_no_file(self):
        """_load_cache should return {} when the cache file does not exist."""
        from app.tasks.watch_folder_tasks import _load_cache

        result = _load_cache("/tmp/does_not_exist_xyz.json")
        assert result == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        """Saving and loading cache should preserve entries."""
        from app.tasks.watch_folder_tasks import _load_cache, _save_cache

        cache_file = str(tmp_path / "cache.json")
        data = {"key1": datetime.now(timezone.utc).isoformat()}
        _save_cache(cache_file, data)
        loaded = _load_cache(cache_file)
        assert "key1" in loaded

    def test_load_cache_handles_invalid_json(self, tmp_path):
        """_load_cache should return {} for corrupted JSON files."""
        from app.tasks.watch_folder_tasks import _load_cache

        cache_file = str(tmp_path / "bad.json")
        with open(cache_file, "w") as f:
            f.write("not valid json{{{{")
        result = _load_cache(cache_file)
        assert result == {}


@pytest.mark.unit
class TestIsAllowedFile:
    """Tests for the _is_allowed_file helper."""

    def test_pdf_is_allowed(self):
        from app.tasks.watch_folder_tasks import _is_allowed_file

        assert _is_allowed_file("document.pdf") is True
        assert _is_allowed_file("DOCUMENT.PDF") is True

    def test_docx_is_allowed(self):
        from app.tasks.watch_folder_tasks import _is_allowed_file

        assert _is_allowed_file("report.docx") is True

    def test_exe_is_not_allowed(self):
        from app.tasks.watch_folder_tasks import _is_allowed_file

        assert _is_allowed_file("malware.exe") is False

    def test_zip_is_not_allowed(self):
        from app.tasks.watch_folder_tasks import _is_allowed_file

        assert _is_allowed_file("archive.zip") is False


@pytest.mark.unit
class TestScanLocalFolder:
    """Tests for _scan_local_folder."""

    def test_nonexistent_folder_returns_zero(self):
        from app.tasks.watch_folder_tasks import _scan_local_folder

        count = _scan_local_folder("/tmp/does_not_exist_xyz_abc", {}, False)
        assert count == 0

    def test_empty_folder_returns_zero(self, tmp_path):
        from app.tasks.watch_folder_tasks import _scan_local_folder

        count = _scan_local_folder(str(tmp_path), {}, False)
        assert count == 0

    def test_new_pdf_is_enqueued(self, tmp_path):
        """A new PDF in the watch folder should be enqueued for processing."""
        from app.tasks.watch_folder_tasks import _scan_local_folder

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.process_document") as mock_proc,
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path / "workdir")
            os.makedirs(mock_settings.workdir, exist_ok=True)
            count = _scan_local_folder(str(tmp_path), cache, False)

        assert count == 1
        assert str(pdf_file) in cache

    def test_already_cached_file_is_skipped(self, tmp_path):
        """Files already in cache should not be re-processed."""
        from app.tasks.watch_folder_tasks import _scan_local_folder

        pdf_file = tmp_path / "already.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")

        cache = {str(pdf_file): datetime.now(timezone.utc).isoformat()}
        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path / "workdir")
            os.makedirs(mock_settings.workdir, exist_ok=True)
            count = _scan_local_folder(str(tmp_path), cache, False)

        assert count == 0

    def test_unsupported_file_is_skipped(self, tmp_path):
        """Unsupported file types should not be enqueued."""
        from app.tasks.watch_folder_tasks import _scan_local_folder

        exe_file = tmp_path / "bad.exe"
        exe_file.write_bytes(b"MZ malware")

        cache: dict = {}
        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path / "workdir")
            count = _scan_local_folder(str(tmp_path), cache, False)

        assert count == 0
        assert str(exe_file) not in cache

    def test_delete_after_process_removes_source(self, tmp_path):
        """When delete_after_process=True, source files should be deleted."""
        from app.tasks.watch_folder_tasks import _scan_local_folder

        pdf_file = tmp_path / "invoice.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.process_document"),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path / "workdir")
            os.makedirs(mock_settings.workdir, exist_ok=True)
            _scan_local_folder(str(tmp_path), cache, delete_after=True)

        assert not pdf_file.exists()


@pytest.mark.unit
class TestAcquireReleaseLock:
    """Tests for the Redis-based locking helpers."""

    def test_acquire_lock_succeeds(self):
        from app.tasks.watch_folder_tasks import _acquire_lock

        mock_redis = MagicMock()
        mock_redis.setnx.return_value = True
        with patch("app.tasks.watch_folder_tasks.redis_client", mock_redis):
            result = _acquire_lock("test_lock")
        assert result is True

    def test_acquire_lock_fails_when_held(self):
        from app.tasks.watch_folder_tasks import _acquire_lock

        mock_redis = MagicMock()
        mock_redis.setnx.return_value = False
        with patch("app.tasks.watch_folder_tasks.redis_client", mock_redis):
            result = _acquire_lock("test_lock")
        assert result is False

    def test_release_lock_deletes_key(self):
        from app.tasks.watch_folder_tasks import _release_lock

        mock_redis = MagicMock()
        with patch("app.tasks.watch_folder_tasks.redis_client", mock_redis):
            _release_lock("test_lock")
        mock_redis.delete.assert_called_once_with("test_lock")


@pytest.mark.unit
class TestScanLocalWatchFoldersTask:
    """Tests for the scan_local_watch_folders Celery task."""

    def test_returns_skipped_when_no_folders_configured(self):
        from app.tasks.watch_folder_tasks import scan_local_watch_folders

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.watch_folders = None
            result = scan_local_watch_folders()
        assert result["status"] == "skipped"

    def test_returns_skipped_for_empty_string(self):
        from app.tasks.watch_folder_tasks import scan_local_watch_folders

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.watch_folders = ""
            result = scan_local_watch_folders()
        assert result["status"] == "skipped"

    def test_scans_configured_folder(self, tmp_path):
        """With a valid folder configured, the task should scan it."""
        from app.tasks.watch_folder_tasks import scan_local_watch_folders

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks._load_cache", return_value={}),
            patch("app.tasks.watch_folder_tasks._save_cache"),
            patch("app.tasks.watch_folder_tasks._scan_local_folder", return_value=0) as mock_scan,
        ):
            mock_settings.watch_folders = str(tmp_path)
            mock_settings.watch_folder_delete_after_process = False
            result = scan_local_watch_folders()

        mock_scan.assert_called_once()
        assert result["status"] == "ok"
        assert result["files_enqueued"] == 0


@pytest.mark.unit
class TestScanFtpWatchFolderTask:
    """Tests for the scan_ftp_watch_folder Celery task."""

    def test_returns_skipped_when_disabled(self):
        from app.tasks.watch_folder_tasks import scan_ftp_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.ftp_ingest_enabled = False
            result = scan_ftp_watch_folder()
        assert result["status"] == "skipped"

    def test_returns_skipped_when_no_folder_configured(self):
        from app.tasks.watch_folder_tasks import scan_ftp_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.ftp_ingest_enabled = True
            mock_settings.ftp_ingest_folder = None
            result = scan_ftp_watch_folder()
        assert result["status"] == "skipped"

    def test_returns_error_when_connection_fails(self):
        from app.tasks.watch_folder_tasks import scan_ftp_watch_folder

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks._connect_ftp", return_value=None),
        ):
            mock_settings.ftp_ingest_enabled = True
            mock_settings.ftp_ingest_folder = "/inbox"
            mock_settings.ftp_ingest_delete_after_process = False
            result = scan_ftp_watch_folder()
        assert result["status"] == "error"

    def test_successful_scan(self):
        from app.tasks.watch_folder_tasks import scan_ftp_watch_folder

        mock_ftp = MagicMock()
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks._connect_ftp", return_value=mock_ftp),
            patch("app.tasks.watch_folder_tasks._load_cache", return_value={}),
            patch("app.tasks.watch_folder_tasks._save_cache"),
            patch("app.tasks.watch_folder_tasks._scan_ftp_folder", return_value=2),
        ):
            mock_settings.ftp_ingest_enabled = True
            mock_settings.ftp_ingest_folder = "/inbox"
            mock_settings.ftp_ingest_delete_after_process = False
            result = scan_ftp_watch_folder()

        assert result["status"] == "ok"
        assert result["files_enqueued"] == 2


@pytest.mark.unit
class TestScanSftpWatchFolderTask:
    """Tests for the scan_sftp_watch_folder Celery task."""

    def test_returns_skipped_when_disabled(self):
        from app.tasks.watch_folder_tasks import scan_sftp_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.sftp_ingest_enabled = False
            result = scan_sftp_watch_folder()
        assert result["status"] == "skipped"

    def test_returns_skipped_when_no_folder_configured(self):
        from app.tasks.watch_folder_tasks import scan_sftp_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.sftp_ingest_enabled = True
            mock_settings.sftp_ingest_folder = None
            result = scan_sftp_watch_folder()
        assert result["status"] == "skipped"

    def test_returns_error_when_connection_fails(self):
        from app.tasks.watch_folder_tasks import scan_sftp_watch_folder

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks._get_sftp_connection", return_value=(None, None)),
        ):
            mock_settings.sftp_ingest_enabled = True
            mock_settings.sftp_ingest_folder = "/upload"
            mock_settings.sftp_ingest_delete_after_process = False
            result = scan_sftp_watch_folder()
        assert result["status"] == "error"

    def test_successful_scan(self):
        from app.tasks.watch_folder_tasks import scan_sftp_watch_folder

        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks._get_sftp_connection", return_value=(mock_ssh, mock_sftp)),
            patch("app.tasks.watch_folder_tasks._load_cache", return_value={}),
            patch("app.tasks.watch_folder_tasks._save_cache"),
            patch("app.tasks.watch_folder_tasks._scan_sftp_folder", return_value=3),
        ):
            mock_settings.sftp_ingest_enabled = True
            mock_settings.sftp_ingest_folder = "/upload"
            mock_settings.sftp_ingest_delete_after_process = False
            result = scan_sftp_watch_folder()

        assert result["status"] == "ok"
        assert result["files_enqueued"] == 3


@pytest.mark.unit
class TestScanAllWatchFolders:
    """Tests for the scan_all_watch_folders orchestrator task."""

    def test_skips_when_lock_held(self):
        from app.tasks.watch_folder_tasks import scan_all_watch_folders

        with patch("app.tasks.watch_folder_tasks._acquire_lock", return_value=False):
            result = scan_all_watch_folders()
        assert result["status"] == "skipped"

    def test_runs_all_scans_and_releases_lock(self):
        from app.tasks.watch_folder_tasks import scan_all_watch_folders

        with (
            patch("app.tasks.watch_folder_tasks._acquire_lock", return_value=True),
            patch("app.tasks.watch_folder_tasks._release_lock") as mock_release,
            patch("app.tasks.watch_folder_tasks.scan_local_watch_folders", return_value={"status": "ok"}),
            patch("app.tasks.watch_folder_tasks.scan_ftp_watch_folder", return_value={"status": "skipped"}),
            patch("app.tasks.watch_folder_tasks.scan_sftp_watch_folder", return_value={"status": "skipped"}),
        ):
            result = scan_all_watch_folders()

        assert result["status"] == "ok"
        assert "results" in result
        mock_release.assert_called_once()

    def test_lock_released_even_on_exception(self):
        """Lock must be released even if a sub-scan raises an exception."""
        from app.tasks.watch_folder_tasks import scan_all_watch_folders

        with (
            patch("app.tasks.watch_folder_tasks._acquire_lock", return_value=True),
            patch("app.tasks.watch_folder_tasks._release_lock") as mock_release,
            patch("app.tasks.watch_folder_tasks.scan_local_watch_folders", side_effect=RuntimeError("boom")),
        ):
            with pytest.raises(RuntimeError):
                scan_all_watch_folders()

        mock_release.assert_called_once()


@pytest.mark.unit
class TestConnectFtp:
    """Tests for the _connect_ftp helper."""

    def test_returns_none_when_settings_incomplete(self):
        from app.tasks.watch_folder_tasks import _connect_ftp

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.ftp_host = None
            mock_settings.ftp_username = "user"
            mock_settings.ftp_password = "pass"  # noqa: S105
            result = _connect_ftp()
        assert result is None

    def test_returns_none_when_connection_fails(self):
        from app.tasks.watch_folder_tasks import _connect_ftp

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("ftplib.FTP_TLS") as mock_ftps_cls,
            patch("ftplib.FTP") as mock_ftp_cls,
        ):
            mock_settings.ftp_host = "ftp.example.com"
            mock_settings.ftp_port = 21
            mock_settings.ftp_username = "user"
            mock_settings.ftp_password = "pass"  # noqa: S105
            mock_settings.ftp_use_tls = False
            mock_settings.ftp_allow_plaintext = True

            mock_ftp_cls.return_value.connect.side_effect = ConnectionRefusedError("refused")
            result = _connect_ftp()
        assert result is None


@pytest.mark.unit
class TestScanFtpFolder:
    """Tests for the _scan_ftp_folder helper."""

    def test_cwd_failure_returns_zero(self):
        import ftplib  # noqa: S402

        from app.tasks.watch_folder_tasks import _scan_ftp_folder

        mock_ftp = MagicMock()
        mock_ftp.cwd.side_effect = ftplib.error_perm("550 no such directory")  # noqa: S321
        count = _scan_ftp_folder(mock_ftp, "/missing", {}, False)
        assert count == 0

    def test_skips_disallowed_files(self):
        from app.tasks.watch_folder_tasks import _scan_ftp_folder

        mock_ftp = MagicMock()
        mock_ftp.cwd.return_value = None
        mock_ftp.nlst.return_value = ["photo.exe", "virus.bat"]
        count = _scan_ftp_folder(mock_ftp, "/inbox", {}, False)
        assert count == 0

    def test_downloads_new_allowed_file(self, tmp_path):
        from app.tasks.watch_folder_tasks import _scan_ftp_folder

        mock_ftp = MagicMock()
        mock_ftp.cwd.return_value = None
        mock_ftp.nlst.return_value = ["invoice.pdf"]

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)

            # Simulate retrbinary writing bytes
            def fake_retrbinary(cmd, callback):
                callback(b"%PDF-1.4")

            mock_ftp.retrbinary.side_effect = fake_retrbinary
            count = _scan_ftp_folder(mock_ftp, "/inbox", cache, False)

        assert count == 1
        assert "ftp:/inbox/invoice.pdf" in cache

    def test_already_cached_file_is_skipped(self, tmp_path):
        from app.tasks.watch_folder_tasks import _scan_ftp_folder

        mock_ftp = MagicMock()
        mock_ftp.cwd.return_value = None
        mock_ftp.nlst.return_value = ["invoice.pdf"]

        cache = {"ftp:/inbox/invoice.pdf": datetime.now(timezone.utc).isoformat()}
        count = _scan_ftp_folder(mock_ftp, "/inbox", cache, False)
        assert count == 0


@pytest.mark.unit
class TestDropboxWatchFolderTask:
    """Tests for the scan_dropbox_watch_folder Celery task."""

    def test_returns_skipped_when_disabled(self):
        from app.tasks.watch_folder_tasks import scan_dropbox_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.dropbox_ingest_enabled = False
            result = scan_dropbox_watch_folder()
        assert result["status"] == "skipped"

    def test_returns_skipped_when_no_folder_configured(self):
        from app.tasks.watch_folder_tasks import scan_dropbox_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.dropbox_ingest_enabled = True
            mock_settings.dropbox_ingest_folder = None
            result = scan_dropbox_watch_folder()
        assert result["status"] == "skipped"

    def test_successful_scan(self):
        from app.tasks.watch_folder_tasks import scan_dropbox_watch_folder

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks._load_cache", return_value={}),
            patch("app.tasks.watch_folder_tasks._save_cache"),
            patch("app.tasks.watch_folder_tasks._scan_dropbox_folder", return_value=1),
        ):
            mock_settings.dropbox_ingest_enabled = True
            mock_settings.dropbox_ingest_folder = "/Inbox"
            mock_settings.dropbox_ingest_delete_after_process = False
            result = scan_dropbox_watch_folder()

        assert result["status"] == "ok"
        assert result["files_enqueued"] == 1


@pytest.mark.unit
class TestGoogleDriveWatchFolderTask:
    """Tests for the scan_google_drive_watch_folder Celery task."""

    def test_returns_skipped_when_disabled(self):
        from app.tasks.watch_folder_tasks import scan_google_drive_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.google_drive_ingest_enabled = False
            result = scan_google_drive_watch_folder()
        assert result["status"] == "skipped"

    def test_returns_skipped_when_no_folder_id(self):
        from app.tasks.watch_folder_tasks import scan_google_drive_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.google_drive_ingest_enabled = True
            mock_settings.google_drive_ingest_folder_id = None
            result = scan_google_drive_watch_folder()
        assert result["status"] == "skipped"

    def test_successful_scan(self):
        from app.tasks.watch_folder_tasks import scan_google_drive_watch_folder

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks._load_cache", return_value={}),
            patch("app.tasks.watch_folder_tasks._save_cache"),
            patch("app.tasks.watch_folder_tasks._scan_google_drive_folder", return_value=2),
        ):
            mock_settings.google_drive_ingest_enabled = True
            mock_settings.google_drive_ingest_folder_id = "abc123"
            mock_settings.google_drive_ingest_delete_after_process = False
            result = scan_google_drive_watch_folder()

        assert result["status"] == "ok"
        assert result["files_enqueued"] == 2


@pytest.mark.unit
class TestOnedriveWatchFolderTask:
    """Tests for the scan_onedrive_watch_folder Celery task."""

    def test_returns_skipped_when_disabled(self):
        from app.tasks.watch_folder_tasks import scan_onedrive_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.onedrive_ingest_enabled = False
            result = scan_onedrive_watch_folder()
        assert result["status"] == "skipped"

    def test_returns_skipped_when_no_folder_path(self):
        from app.tasks.watch_folder_tasks import scan_onedrive_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.onedrive_ingest_enabled = True
            mock_settings.onedrive_ingest_folder_path = None
            result = scan_onedrive_watch_folder()
        assert result["status"] == "skipped"

    def test_successful_scan(self):
        from app.tasks.watch_folder_tasks import scan_onedrive_watch_folder

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks._load_cache", return_value={}),
            patch("app.tasks.watch_folder_tasks._save_cache"),
            patch("app.tasks.watch_folder_tasks._scan_onedrive_folder", return_value=3),
        ):
            mock_settings.onedrive_ingest_enabled = True
            mock_settings.onedrive_ingest_folder_path = "/Inbox/Scanner"
            mock_settings.onedrive_ingest_delete_after_process = False
            result = scan_onedrive_watch_folder()

        assert result["status"] == "ok"
        assert result["files_enqueued"] == 3


@pytest.mark.unit
class TestNextcloudWatchFolderTask:
    """Tests for the scan_nextcloud_watch_folder Celery task."""

    def test_returns_skipped_when_disabled(self):
        from app.tasks.watch_folder_tasks import scan_nextcloud_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.nextcloud_ingest_enabled = False
            result = scan_nextcloud_watch_folder()
        assert result["status"] == "skipped"

    def test_returns_skipped_when_no_folder(self):
        from app.tasks.watch_folder_tasks import scan_nextcloud_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.nextcloud_ingest_enabled = True
            mock_settings.nextcloud_ingest_folder = None
            result = scan_nextcloud_watch_folder()
        assert result["status"] == "skipped"

    def test_successful_scan(self):
        from app.tasks.watch_folder_tasks import scan_nextcloud_watch_folder

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks._load_cache", return_value={}),
            patch("app.tasks.watch_folder_tasks._save_cache"),
            patch("app.tasks.watch_folder_tasks._scan_nextcloud_folder", return_value=1),
        ):
            mock_settings.nextcloud_ingest_enabled = True
            mock_settings.nextcloud_ingest_folder = "/Scans/Inbox"
            mock_settings.nextcloud_ingest_delete_after_process = False
            result = scan_nextcloud_watch_folder()

        assert result["status"] == "ok"
        assert result["files_enqueued"] == 1


@pytest.mark.unit
class TestS3WatchFolderTask:
    """Tests for the scan_s3_watch_folder Celery task."""

    def test_returns_skipped_when_disabled(self):
        from app.tasks.watch_folder_tasks import scan_s3_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.s3_ingest_enabled = False
            result = scan_s3_watch_folder()
        assert result["status"] == "skipped"

    def test_returns_skipped_when_no_prefix(self):
        from app.tasks.watch_folder_tasks import scan_s3_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.s3_ingest_enabled = True
            mock_settings.s3_ingest_prefix = None
            result = scan_s3_watch_folder()
        assert result["status"] == "skipped"

    def test_successful_scan(self):
        from app.tasks.watch_folder_tasks import scan_s3_watch_folder

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks._load_cache", return_value={}),
            patch("app.tasks.watch_folder_tasks._save_cache"),
            patch("app.tasks.watch_folder_tasks._scan_s3_prefix", return_value=4),
        ):
            mock_settings.s3_ingest_enabled = True
            mock_settings.s3_ingest_prefix = "inbox/scanner/"
            mock_settings.s3_ingest_delete_after_process = False
            result = scan_s3_watch_folder()

        assert result["status"] == "ok"
        assert result["files_enqueued"] == 4


@pytest.mark.unit
class TestWebdavWatchFolderTask:
    """Tests for the scan_webdav_watch_folder Celery task."""

    def test_returns_skipped_when_disabled(self):
        from app.tasks.watch_folder_tasks import scan_webdav_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.webdav_ingest_enabled = False
            result = scan_webdav_watch_folder()
        assert result["status"] == "skipped"

    def test_returns_skipped_when_no_folder(self):
        from app.tasks.watch_folder_tasks import scan_webdav_watch_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.webdav_ingest_enabled = True
            mock_settings.webdav_ingest_folder = None
            result = scan_webdav_watch_folder()
        assert result["status"] == "skipped"

    def test_successful_scan(self):
        from app.tasks.watch_folder_tasks import scan_webdav_watch_folder

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks._load_cache", return_value={}),
            patch("app.tasks.watch_folder_tasks._save_cache"),
            patch("app.tasks.watch_folder_tasks._scan_webdav_folder", return_value=2),
        ):
            mock_settings.webdav_ingest_enabled = True
            mock_settings.webdav_ingest_folder = "/remote.php/webdav/Inbox"
            mock_settings.webdav_ingest_delete_after_process = False
            result = scan_webdav_watch_folder()

        assert result["status"] == "ok"
        assert result["files_enqueued"] == 2


@pytest.mark.unit
class TestScanAllWatchFoldersCloud:
    """Tests for the extended scan_all_watch_folders with cloud providers."""

    def test_all_cloud_providers_called(self):
        """scan_all_watch_folders should call all provider-specific tasks."""
        from app.tasks.watch_folder_tasks import scan_all_watch_folders

        provider_tasks = [
            "scan_local_watch_folders",
            "scan_ftp_watch_folder",
            "scan_sftp_watch_folder",
            "scan_dropbox_watch_folder",
            "scan_google_drive_watch_folder",
            "scan_onedrive_watch_folder",
            "scan_nextcloud_watch_folder",
            "scan_s3_watch_folder",
            "scan_webdav_watch_folder",
        ]

        with (
            patch("app.tasks.watch_folder_tasks._acquire_lock", return_value=True),
            patch("app.tasks.watch_folder_tasks._release_lock"),
        ):
            mocks = {}
            patches = []
            for name in provider_tasks:
                m = MagicMock(return_value={"status": "skipped"})
                p = patch(f"app.tasks.watch_folder_tasks.{name}", m)
                patches.append(p)
                mocks[name] = m

            # Apply all patches
            for p in patches:
                p.start()
            try:
                result = scan_all_watch_folders()
            finally:
                for p in patches:
                    p.stop()

        assert result["status"] == "ok"
        for name in provider_tasks:
            mocks[name].assert_called_once()


# ===========================================================================
# Additional coverage tests
# ===========================================================================


@pytest.mark.unit
class TestSaveCacheErrors:
    """Tests for _save_cache error handling."""

    def test_save_cache_logs_error_on_os_error(self, tmp_path):
        """_save_cache should log an error when it cannot write the file."""
        from app.tasks.watch_folder_tasks import _save_cache

        # Use a path where the parent directory does not exist
        bad_path = str(tmp_path / "nonexistent_dir" / "cache.json")
        # Should not raise — just log
        _save_cache(bad_path, {"key": "val"})


@pytest.mark.unit
class TestEvictOldEntriesTimezoneNaive:
    """Additional eviction edge cases."""

    def test_evict_keeps_timezone_naive_recent_entry(self):
        """Timezone-naive timestamps should be treated as UTC and kept if recent."""
        from app.tasks.watch_folder_tasks import _evict_old_entries

        # Naive datetime string (no +00:00), recent
        naive_recent = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        result = _evict_old_entries({"recent_naive": naive_recent})
        assert "recent_naive" in result

    def test_evict_removes_timezone_naive_old_entry(self):
        """Old timezone-naive entries should be evicted."""
        from app.tasks.watch_folder_tasks import _evict_old_entries

        old_naive = (datetime.now(timezone.utc) - timedelta(days=60)).replace(tzinfo=None).isoformat()
        result = _evict_old_entries({"old_naive": old_naive})
        assert "old_naive" not in result


@pytest.mark.unit
class TestEnqueueFileNonPdf:
    """Tests for _enqueue_file with non-PDF files."""

    def test_non_pdf_triggers_convert_to_pdf(self):
        """Non-PDF files should be dispatched to convert_to_pdf."""
        from app.tasks.watch_folder_tasks import _enqueue_file

        with (
            patch("app.tasks.watch_folder_tasks.convert_to_pdf") as mock_conv,
            patch("app.tasks.watch_folder_tasks.process_document") as mock_proc,
        ):
            _enqueue_file("/tmp/doc.docx")
        mock_conv.delay.assert_called_once_with("/tmp/doc.docx", owner_id=None)
        mock_proc.delay.assert_not_called()

    def test_pdf_triggers_process_document(self):
        """PDF files should be dispatched to process_document."""
        from app.tasks.watch_folder_tasks import _enqueue_file

        with (
            patch("app.tasks.watch_folder_tasks.convert_to_pdf") as mock_conv,
            patch("app.tasks.watch_folder_tasks.process_document") as mock_proc,
        ):
            _enqueue_file("/tmp/report.pdf")
        mock_proc.delay.assert_called_once_with("/tmp/report.pdf", owner_id=None)
        mock_conv.delay.assert_not_called()

    def test_pdf_detected_via_filename_param(self):
        """When filename kwarg ends with .pdf, process_document should be called."""
        from app.tasks.watch_folder_tasks import _enqueue_file

        with (
            patch("app.tasks.watch_folder_tasks.convert_to_pdf") as mock_conv,
            patch("app.tasks.watch_folder_tasks.process_document") as mock_proc,
        ):
            _enqueue_file("/tmp/somefile", filename="renamed.pdf")
        mock_proc.delay.assert_called_once_with("/tmp/somefile", owner_id=None)
        mock_conv.delay.assert_not_called()


@pytest.mark.unit
class TestScanLocalFolderEdgeCases:
    """Additional edge cases for _scan_local_folder."""

    def test_permission_error_returns_zero(self, tmp_path):
        """PermissionError during scandir should return 0."""
        from app.tasks.watch_folder_tasks import _scan_local_folder

        with patch("os.scandir", side_effect=PermissionError("denied")):
            count = _scan_local_folder(str(tmp_path), {}, False)
        assert count == 0

    def test_copy_oserror_skips_file(self, tmp_path):
        """If shutil.copy2 raises OSError, the file should be skipped."""
        from app.tasks.watch_folder_tasks import _scan_local_folder

        pdf_file = tmp_path / "fail.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("shutil.copy2", side_effect=OSError("disk full")),
        ):
            mock_settings.workdir = str(tmp_path / "workdir")
            os.makedirs(mock_settings.workdir, exist_ok=True)
            count = _scan_local_folder(str(tmp_path), cache, False)

        assert count == 0
        assert str(pdf_file) not in cache

    def test_file_collision_generates_unique_name(self, tmp_path):
        """When dest file already exists, a timestamped name should be used."""
        from app.tasks.watch_folder_tasks import _scan_local_folder

        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        workdir = tmp_path / "workdir"
        workdir.mkdir()
        # Pre-create the destination to force the collision path
        (workdir / "wf_doc.pdf").write_bytes(b"old")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.process_document"),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(workdir)
            count = _scan_local_folder(str(tmp_path), cache, False)

        assert count == 1

    def test_delete_after_oserror_does_not_crash(self, tmp_path):
        """If os.remove raises OSError during delete_after, it should be logged but not crash."""
        from app.tasks.watch_folder_tasks import _scan_local_folder

        pdf_file = tmp_path / "todelete.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.process_document"),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("os.remove", side_effect=OSError("busy")),
        ):
            mock_settings.workdir = str(tmp_path / "workdir")
            os.makedirs(mock_settings.workdir, exist_ok=True)
            # Bypass the shutil.copy2 to avoid hitting the real copy
            with patch("shutil.copy2"):
                count = _scan_local_folder(str(tmp_path), cache, delete_after=True)

        assert count == 1


@pytest.mark.unit
class TestConnectFtpTlsFallback:
    """Tests for the FTP TLS/plaintext fallback logic in _connect_ftp."""

    def test_tls_success(self):
        """When TLS succeeds, the FTP_TLS object should be returned."""
        from app.tasks.watch_folder_tasks import _connect_ftp

        mock_ftp_tls = MagicMock()
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("ftplib.FTP_TLS", return_value=mock_ftp_tls),
        ):
            mock_settings.ftp_host = "ftp.example.com"
            mock_settings.ftp_port = 21
            mock_settings.ftp_username = "user"
            mock_settings.ftp_password = "pass"  # noqa: S105
            mock_settings.ftp_use_tls = True
            mock_settings.ftp_allow_plaintext = False
            result = _connect_ftp()
        assert result is mock_ftp_tls

    def test_tls_fails_fallback_to_plaintext(self):
        """When TLS fails and allow_plaintext=True, should fall back to plain FTP."""
        from app.tasks.watch_folder_tasks import _connect_ftp

        mock_ftp_plain = MagicMock()
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("ftplib.FTP_TLS") as mock_ftps_cls,
            patch("ftplib.FTP", return_value=mock_ftp_plain),
        ):
            mock_settings.ftp_host = "ftp.example.com"
            mock_settings.ftp_port = 21
            mock_settings.ftp_username = "user"
            mock_settings.ftp_password = "pass"  # noqa: S105
            mock_settings.ftp_use_tls = True
            mock_settings.ftp_allow_plaintext = True
            mock_ftps_cls.return_value.connect.side_effect = ConnectionRefusedError("no tls")
            result = _connect_ftp()
        assert result is mock_ftp_plain

    def test_tls_fails_no_plaintext_returns_none(self):
        """When TLS fails and allow_plaintext=False, returns None."""
        from app.tasks.watch_folder_tasks import _connect_ftp

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("ftplib.FTP_TLS") as mock_ftps_cls,
        ):
            mock_settings.ftp_host = "ftp.example.com"
            mock_settings.ftp_port = 21
            mock_settings.ftp_username = "user"
            mock_settings.ftp_password = "pass"  # noqa: S105
            mock_settings.ftp_use_tls = True
            mock_settings.ftp_allow_plaintext = False
            mock_ftps_cls.return_value.connect.side_effect = ConnectionRefusedError("no tls")
            result = _connect_ftp()
        assert result is None

    def test_plain_ftp_success(self):
        """When use_tls=False, plain FTP is used directly."""
        from app.tasks.watch_folder_tasks import _connect_ftp

        mock_ftp = MagicMock()
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("ftplib.FTP", return_value=mock_ftp),
        ):
            mock_settings.ftp_host = "ftp.example.com"
            mock_settings.ftp_port = 21
            mock_settings.ftp_username = "user"
            mock_settings.ftp_password = "pass"  # noqa: S105
            mock_settings.ftp_use_tls = False
            mock_settings.ftp_allow_plaintext = True
            result = _connect_ftp()
        assert result is mock_ftp


@pytest.mark.unit
class TestScanFtpFolderEdgeCases:
    """Additional edge cases for _scan_ftp_folder."""

    def test_nlst_failure_returns_zero(self):
        """When NLST raises an exception, return 0."""
        from app.tasks.watch_folder_tasks import _scan_ftp_folder

        mock_ftp = MagicMock()
        mock_ftp.cwd.return_value = None
        mock_ftp.nlst.side_effect = Exception("NLST failed")
        count = _scan_ftp_folder(mock_ftp, "/inbox", {}, False)
        assert count == 0

    def test_file_collision_generates_unique_name(self, tmp_path):
        """When dest path already exists, a timestamped path should be created."""
        from app.tasks.watch_folder_tasks import _scan_ftp_folder

        mock_ftp = MagicMock()
        mock_ftp.cwd.return_value = None
        mock_ftp.nlst.return_value = ["doc.pdf"]
        # Pre-create the dest file
        (tmp_path / "ftp_doc.pdf").write_bytes(b"old")

        def fake_retrbinary(cmd, callback):
            callback(b"%PDF-1.4")

        mock_ftp.retrbinary.side_effect = fake_retrbinary

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_ftp_folder(mock_ftp, "/inbox", cache, False)
        assert count == 1

    def test_download_failure_skips_file(self, tmp_path):
        """When retrbinary raises, the file should be skipped."""
        from app.tasks.watch_folder_tasks import _scan_ftp_folder

        mock_ftp = MagicMock()
        mock_ftp.cwd.return_value = None
        mock_ftp.nlst.return_value = ["broken.pdf"]
        mock_ftp.retrbinary.side_effect = Exception("transfer failed")

        cache: dict = {}
        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            count = _scan_ftp_folder(mock_ftp, "/inbox", cache, False)
        assert count == 0
        assert "ftp:/inbox/broken.pdf" not in cache

    def test_delete_after_ftp_success(self, tmp_path):
        """When delete_after=True and delete succeeds, no exception should occur."""
        from app.tasks.watch_folder_tasks import _scan_ftp_folder

        mock_ftp = MagicMock()
        mock_ftp.cwd.return_value = None
        mock_ftp.nlst.return_value = ["file.pdf"]

        def fake_retrbinary(cmd, callback):
            callback(b"%PDF-1.4")

        mock_ftp.retrbinary.side_effect = fake_retrbinary

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_ftp_folder(mock_ftp, "/inbox", cache, delete_after=True)

        assert count == 1
        mock_ftp.delete.assert_called_once_with("file.pdf")

    def test_delete_after_ftp_failure_does_not_crash(self, tmp_path):
        """When delete raises, it should log a warning but not crash."""
        from app.tasks.watch_folder_tasks import _scan_ftp_folder

        mock_ftp = MagicMock()
        mock_ftp.cwd.return_value = None
        mock_ftp.nlst.return_value = ["file.pdf"]

        def fake_retrbinary(cmd, callback):
            callback(b"%PDF-1.4")

        mock_ftp.retrbinary.side_effect = fake_retrbinary
        mock_ftp.delete.side_effect = Exception("permission denied")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_ftp_folder(mock_ftp, "/inbox", cache, delete_after=True)
        assert count == 1


@pytest.mark.unit
class TestGetSftpConnection:
    """Tests for _get_sftp_connection."""

    def test_returns_none_when_host_missing(self):
        """Returns (None, None) when host is not configured."""
        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.sftp_host = None
            mock_settings.sftp_username = "user"
            from app.tasks.watch_folder_tasks import _get_sftp_connection

            ssh, sftp = _get_sftp_connection()
        assert ssh is None
        assert sftp is None

    def test_returns_none_when_no_auth(self):
        """Returns (None, None) when neither password nor key is set."""
        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.sftp_host = "sftp.example.com"
            mock_settings.sftp_port = 22
            mock_settings.sftp_username = "user"
            mock_settings.sftp_disable_host_key_verification = False
            mock_settings.sftp_private_key = None
            mock_settings.sftp_password = None

            import paramiko

            mock_ssh = MagicMock(spec=paramiko.SSHClient)

            with patch("paramiko.SSHClient", return_value=mock_ssh):
                from app.tasks.watch_folder_tasks import _get_sftp_connection

                ssh, sftp = _get_sftp_connection()
        assert ssh is None
        assert sftp is None

    def test_connects_with_password(self):
        """Returns (ssh, sftp) when password auth succeeds."""
        import paramiko

        mock_ssh = MagicMock(spec=paramiko.SSHClient)
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("paramiko.SSHClient", return_value=mock_ssh),
        ):
            mock_settings.sftp_host = "sftp.example.com"
            mock_settings.sftp_port = 22
            mock_settings.sftp_username = "user"
            mock_settings.sftp_disable_host_key_verification = False
            mock_settings.sftp_private_key = None
            mock_settings.sftp_password = "secret"  # noqa: S105
            mock_settings.sftp_private_key_passphrase = None

            from app.tasks.watch_folder_tasks import _get_sftp_connection

            ssh, sftp = _get_sftp_connection()

        assert ssh is mock_ssh
        assert sftp is mock_sftp

    def test_connects_with_key_file(self, tmp_path):
        """Returns (ssh, sftp) when key-based auth succeeds."""
        import paramiko

        key_file = tmp_path / "id_rsa"
        key_file.write_text("fake key")

        mock_ssh = MagicMock(spec=paramiko.SSHClient)
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("paramiko.SSHClient", return_value=mock_ssh),
        ):
            mock_settings.sftp_host = "sftp.example.com"
            mock_settings.sftp_port = 22
            mock_settings.sftp_username = "user"
            mock_settings.sftp_disable_host_key_verification = False
            mock_settings.sftp_private_key = str(key_file)
            mock_settings.sftp_private_key_passphrase = "mypassphrase"
            mock_settings.sftp_password = None

            from app.tasks.watch_folder_tasks import _get_sftp_connection

            ssh, sftp = _get_sftp_connection()

        assert ssh is mock_ssh
        assert sftp is mock_sftp

    def test_connection_failure_returns_none(self):
        """Returns (None, None) when connect() raises."""
        import paramiko

        mock_ssh = MagicMock(spec=paramiko.SSHClient)
        mock_ssh.connect.side_effect = Exception("refused")

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("paramiko.SSHClient", return_value=mock_ssh),
        ):
            mock_settings.sftp_host = "sftp.example.com"
            mock_settings.sftp_port = 22
            mock_settings.sftp_username = "user"
            mock_settings.sftp_disable_host_key_verification = False
            mock_settings.sftp_private_key = None
            mock_settings.sftp_password = "secret"  # noqa: S105
            mock_settings.sftp_private_key_passphrase = None

            from app.tasks.watch_folder_tasks import _get_sftp_connection

            ssh, sftp = _get_sftp_connection()

        assert ssh is None
        assert sftp is None

    def test_disable_host_key_verification_path(self):
        """When sftp_disable_host_key_verification=True, AutoAddPolicy is set."""
        import paramiko

        mock_ssh = MagicMock(spec=paramiko.SSHClient)
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("paramiko.SSHClient", return_value=mock_ssh),
            patch("paramiko.AutoAddPolicy"),
        ):
            mock_settings.sftp_host = "sftp.example.com"
            mock_settings.sftp_port = 22
            mock_settings.sftp_username = "user"
            mock_settings.sftp_disable_host_key_verification = True
            mock_settings.sftp_private_key = None
            mock_settings.sftp_password = "secret"  # noqa: S105
            mock_settings.sftp_private_key_passphrase = None

            from app.tasks.watch_folder_tasks import _get_sftp_connection

            _get_sftp_connection()

        mock_ssh.set_missing_host_key_policy.assert_called()

    def test_connection_failure_close_raises(self):
        """When connect() fails and ssh.close() also raises, returns (None, None)."""
        import paramiko

        mock_ssh = MagicMock(spec=paramiko.SSHClient)
        mock_ssh.connect.side_effect = Exception("refused")
        mock_ssh.close.side_effect = Exception("close also failed")

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("paramiko.SSHClient", return_value=mock_ssh),
        ):
            mock_settings.sftp_host = "sftp.example.com"
            mock_settings.sftp_port = 22
            mock_settings.sftp_username = "user"
            mock_settings.sftp_disable_host_key_verification = False
            mock_settings.sftp_private_key = None
            mock_settings.sftp_password = "secret"  # noqa: S105
            mock_settings.sftp_private_key_passphrase = None

            from app.tasks.watch_folder_tasks import _get_sftp_connection

            ssh, sftp = _get_sftp_connection()

        assert ssh is None
        assert sftp is None


@pytest.mark.unit
class TestScanSftpFolderEdgeCases:
    """Additional edge cases for _scan_sftp_folder."""

    def test_listdir_failure_returns_zero(self):
        """When listdir_attr raises, return 0."""
        from app.tasks.watch_folder_tasks import _scan_sftp_folder

        mock_sftp = MagicMock()
        mock_sftp.listdir_attr.side_effect = Exception("permission denied")
        count = _scan_sftp_folder(mock_sftp, "/upload", {}, False)
        assert count == 0

    def test_directory_entry_is_skipped(self, tmp_path):
        """Directory entries should be skipped."""
        from app.tasks.watch_folder_tasks import _scan_sftp_folder

        mock_sftp = MagicMock()
        dir_attr = MagicMock()
        dir_attr.st_mode = stat.S_IFDIR | 0o755
        dir_attr.filename = "subdir"
        mock_sftp.listdir_attr.return_value = [dir_attr]

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            count = _scan_sftp_folder(mock_sftp, "/upload", {}, False)
        assert count == 0

    def test_download_new_file(self, tmp_path):
        """A new allowed file should be downloaded and enqueued."""
        from app.tasks.watch_folder_tasks import _scan_sftp_folder

        mock_sftp = MagicMock()
        file_attr = MagicMock()
        file_attr.st_mode = stat.S_IFREG | 0o644
        file_attr.filename = "scan.pdf"
        mock_sftp.listdir_attr.return_value = [file_attr]

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_sftp_folder(mock_sftp, "/upload", cache, False)

        assert count == 1
        assert "sftp:/upload/scan.pdf" in cache

    def test_file_collision_generates_unique_name(self, tmp_path):
        """When dest file already exists, a unique timestamped name is used."""
        from app.tasks.watch_folder_tasks import _scan_sftp_folder

        mock_sftp = MagicMock()
        file_attr = MagicMock()
        file_attr.st_mode = stat.S_IFREG | 0o644
        file_attr.filename = "doc.pdf"
        mock_sftp.listdir_attr.return_value = [file_attr]
        # Pre-create the collision file
        (tmp_path / "sftp_doc.pdf").write_bytes(b"old")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_sftp_folder(mock_sftp, "/upload", cache, False)
        assert count == 1

    def test_download_failure_skips_file(self, tmp_path):
        """When sftp.get raises, the file is skipped."""
        from app.tasks.watch_folder_tasks import _scan_sftp_folder

        mock_sftp = MagicMock()
        file_attr = MagicMock()
        file_attr.st_mode = stat.S_IFREG | 0o644
        file_attr.filename = "broken.pdf"
        mock_sftp.listdir_attr.return_value = [file_attr]
        mock_sftp.get.side_effect = Exception("IO error")

        cache: dict = {}
        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            count = _scan_sftp_folder(mock_sftp, "/upload", cache, False)
        assert count == 0
        assert "sftp:/upload/broken.pdf" not in cache

    def test_delete_after_success(self, tmp_path):
        """delete_after=True should call sftp.remove."""
        from app.tasks.watch_folder_tasks import _scan_sftp_folder

        mock_sftp = MagicMock()
        file_attr = MagicMock()
        file_attr.st_mode = stat.S_IFREG | 0o644
        file_attr.filename = "file.pdf"
        mock_sftp.listdir_attr.return_value = [file_attr]

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            _scan_sftp_folder(mock_sftp, "/upload", cache, delete_after=True)

        mock_sftp.remove.assert_called_once_with("/upload/file.pdf")

    def test_delete_after_failure_does_not_crash(self, tmp_path):
        """delete_after failure should be logged but not crash."""
        from app.tasks.watch_folder_tasks import _scan_sftp_folder

        mock_sftp = MagicMock()
        file_attr = MagicMock()
        file_attr.st_mode = stat.S_IFREG | 0o644
        file_attr.filename = "file.pdf"
        mock_sftp.listdir_attr.return_value = [file_attr]
        mock_sftp.remove.side_effect = Exception("permission denied")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_sftp_folder(mock_sftp, "/upload", cache, delete_after=True)
        assert count == 1

    def test_already_cached_sftp_file_skipped(self, tmp_path):
        """Files already in cache should not be re-downloaded."""
        from app.tasks.watch_folder_tasks import _scan_sftp_folder

        mock_sftp = MagicMock()
        file_attr = MagicMock()
        file_attr.st_mode = stat.S_IFREG | 0o644
        file_attr.filename = "cached.pdf"
        mock_sftp.listdir_attr.return_value = [file_attr]

        cache = {"sftp:/upload/cached.pdf": datetime.now(timezone.utc).isoformat()}
        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            count = _scan_sftp_folder(mock_sftp, "/upload", cache, False)
        assert count == 0

    def test_unsupported_type_sftp_skipped(self, tmp_path):
        """Non-allowed file types should be skipped."""
        from app.tasks.watch_folder_tasks import _scan_sftp_folder

        mock_sftp = MagicMock()
        file_attr = MagicMock()
        file_attr.st_mode = stat.S_IFREG | 0o644
        file_attr.filename = "script.sh"
        mock_sftp.listdir_attr.return_value = [file_attr]

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            count = _scan_sftp_folder(mock_sftp, "/upload", {}, False)
        assert count == 0


@pytest.mark.unit
class TestScanDropboxFolder:
    """Tests for _scan_dropbox_folder."""

    def test_auth_failure_returns_zero(self):
        """If get_dropbox_client raises, return 0."""
        from app.tasks.watch_folder_tasks import _scan_dropbox_folder

        with patch("app.tasks.upload_to_dropbox.get_dropbox_client", side_effect=Exception("auth failed")):
            result = _scan_dropbox_folder("/Inbox", {}, False)
        assert result == 0

    def test_list_folder_failure_returns_zero(self):
        """If files_list_folder raises, return 0."""
        from app.tasks.watch_folder_tasks import _scan_dropbox_folder

        mock_dbx = MagicMock()
        mock_dbx.files_list_folder.side_effect = Exception("network error")

        with patch("app.tasks.upload_to_dropbox.get_dropbox_client", return_value=mock_dbx):
            result = _scan_dropbox_folder("/Inbox", {}, False)
        assert result == 0

    def test_downloads_new_file(self, tmp_path):
        """New allowed files should be downloaded and enqueued."""
        import dropbox as dropbox_module

        from app.tasks.watch_folder_tasks import _scan_dropbox_folder

        mock_dbx = MagicMock()
        file_entry = MagicMock(spec=dropbox_module.files.FileMetadata)
        file_entry.name = "receipt.pdf"
        file_entry.id = "id:abc123"
        file_entry.path_lower = "/inbox/receipt.pdf"

        mock_result = MagicMock()
        mock_result.entries = [file_entry]
        mock_result.has_more = False
        mock_dbx.files_list_folder.return_value = mock_result

        mock_response = MagicMock()
        mock_response.content = b"%PDF-1.4"
        mock_dbx.files_download.return_value = (MagicMock(), mock_response)

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_dropbox.get_dropbox_client", return_value=mock_dbx),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_dropbox_folder("/Inbox", cache, False)

        assert count == 1
        assert "dropbox:id:abc123" in cache

    def test_skips_non_file_metadata(self, tmp_path):
        """Non-FileMetadata entries (folders) should be skipped."""
        import dropbox as dropbox_module

        from app.tasks.watch_folder_tasks import _scan_dropbox_folder

        mock_dbx = MagicMock()
        folder_entry = MagicMock(spec=dropbox_module.files.FolderMetadata)
        folder_entry.name = "subfolder"

        mock_result = MagicMock()
        mock_result.entries = [folder_entry]
        mock_result.has_more = False
        mock_dbx.files_list_folder.return_value = mock_result

        cache: dict = {}
        with patch("app.tasks.upload_to_dropbox.get_dropbox_client", return_value=mock_dbx):
            count = _scan_dropbox_folder("/Inbox", cache, False)
        assert count == 0

    def test_skips_already_cached_file(self, tmp_path):
        """Files already in cache should not be re-downloaded."""
        import dropbox as dropbox_module

        from app.tasks.watch_folder_tasks import _scan_dropbox_folder

        mock_dbx = MagicMock()
        file_entry = MagicMock(spec=dropbox_module.files.FileMetadata)
        file_entry.name = "cached.pdf"
        file_entry.id = "id:cached"
        file_entry.path_lower = "/inbox/cached.pdf"

        mock_result = MagicMock()
        mock_result.entries = [file_entry]
        mock_result.has_more = False
        mock_dbx.files_list_folder.return_value = mock_result

        cache = {"dropbox:id:cached": datetime.now(timezone.utc).isoformat()}
        with patch("app.tasks.upload_to_dropbox.get_dropbox_client", return_value=mock_dbx):
            count = _scan_dropbox_folder("/Inbox", cache, False)
        assert count == 0

    def test_skips_unsupported_file_type(self, tmp_path):
        """Non-allowed file types should be skipped."""
        import dropbox as dropbox_module

        from app.tasks.watch_folder_tasks import _scan_dropbox_folder

        mock_dbx = MagicMock()
        file_entry = MagicMock(spec=dropbox_module.files.FileMetadata)
        file_entry.name = "script.exe"
        file_entry.id = "id:exe1"
        file_entry.path_lower = "/inbox/script.exe"

        mock_result = MagicMock()
        mock_result.entries = [file_entry]
        mock_result.has_more = False
        mock_dbx.files_list_folder.return_value = mock_result

        with patch("app.tasks.upload_to_dropbox.get_dropbox_client", return_value=mock_dbx):
            count = _scan_dropbox_folder("/Inbox", {}, False)
        assert count == 0

    def test_download_failure_skips_file(self, tmp_path):
        """If files_download raises, the file should be skipped."""
        import dropbox as dropbox_module

        from app.tasks.watch_folder_tasks import _scan_dropbox_folder

        mock_dbx = MagicMock()
        file_entry = MagicMock(spec=dropbox_module.files.FileMetadata)
        file_entry.name = "fail.pdf"
        file_entry.id = "id:fail1"
        file_entry.path_lower = "/inbox/fail.pdf"

        mock_result = MagicMock()
        mock_result.entries = [file_entry]
        mock_result.has_more = False
        mock_dbx.files_list_folder.return_value = mock_result
        mock_dbx.files_download.side_effect = Exception("download failed")

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_dropbox.get_dropbox_client", return_value=mock_dbx),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_dropbox_folder("/Inbox", cache, False)
        assert count == 0
        assert "dropbox:id:fail1" not in cache

    def test_delete_after_success(self, tmp_path):
        """delete_after=True should call files_delete_v2."""
        import dropbox as dropbox_module

        from app.tasks.watch_folder_tasks import _scan_dropbox_folder

        mock_dbx = MagicMock()
        file_entry = MagicMock(spec=dropbox_module.files.FileMetadata)
        file_entry.name = "invoice.pdf"
        file_entry.id = "id:inv1"
        file_entry.path_lower = "/inbox/invoice.pdf"

        mock_result = MagicMock()
        mock_result.entries = [file_entry]
        mock_result.has_more = False
        mock_dbx.files_list_folder.return_value = mock_result

        mock_response = MagicMock()
        mock_response.content = b"%PDF-1.4"
        mock_dbx.files_download.return_value = (MagicMock(), mock_response)

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_dropbox.get_dropbox_client", return_value=mock_dbx),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            _scan_dropbox_folder("/Inbox", cache, delete_after=True)

        mock_dbx.files_delete_v2.assert_called_once_with("/inbox/invoice.pdf")

    def test_delete_after_failure_does_not_crash(self, tmp_path):
        """delete_after failure should log warning but not crash."""
        import dropbox as dropbox_module

        from app.tasks.watch_folder_tasks import _scan_dropbox_folder

        mock_dbx = MagicMock()
        file_entry = MagicMock(spec=dropbox_module.files.FileMetadata)
        file_entry.name = "doc.pdf"
        file_entry.id = "id:doc1"
        file_entry.path_lower = "/inbox/doc.pdf"

        mock_result = MagicMock()
        mock_result.entries = [file_entry]
        mock_result.has_more = False
        mock_dbx.files_list_folder.return_value = mock_result
        mock_dbx.files_delete_v2.side_effect = Exception("permission denied")

        mock_response = MagicMock()
        mock_response.content = b"%PDF-1.4"
        mock_dbx.files_download.return_value = (MagicMock(), mock_response)

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_dropbox.get_dropbox_client", return_value=mock_dbx),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_dropbox_folder("/Inbox", cache, delete_after=True)
        assert count == 1

    def test_pagination(self, tmp_path):
        """When has_more=True, should paginate to get all files."""
        import dropbox as dropbox_module

        from app.tasks.watch_folder_tasks import _scan_dropbox_folder

        mock_dbx = MagicMock()

        file1 = MagicMock(spec=dropbox_module.files.FileMetadata)
        file1.name = "page1.pdf"
        file1.id = "id:page1"
        file1.path_lower = "/inbox/page1.pdf"

        file2 = MagicMock(spec=dropbox_module.files.FileMetadata)
        file2.name = "page2.pdf"
        file2.id = "id:page2"
        file2.path_lower = "/inbox/page2.pdf"

        result1 = MagicMock()
        result1.entries = [file1]
        result1.has_more = True
        result1.cursor = "cursor1"

        result2 = MagicMock()
        result2.entries = [file2]
        result2.has_more = False

        mock_dbx.files_list_folder.return_value = result1
        mock_dbx.files_list_folder_continue.return_value = result2

        mock_response = MagicMock()
        mock_response.content = b"%PDF-1.4"
        mock_dbx.files_download.return_value = (MagicMock(), mock_response)

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_dropbox.get_dropbox_client", return_value=mock_dbx),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_dropbox_folder("/Inbox", cache, False)

        assert count == 2

    def test_file_collision_generates_unique_name(self, tmp_path):
        """When dest file already exists, a timestamped path is used."""
        import dropbox as dropbox_module

        from app.tasks.watch_folder_tasks import _scan_dropbox_folder

        mock_dbx = MagicMock()
        file_entry = MagicMock(spec=dropbox_module.files.FileMetadata)
        file_entry.name = "collision.pdf"
        file_entry.id = "id:coll1"
        file_entry.path_lower = "/inbox/collision.pdf"

        mock_result = MagicMock()
        mock_result.entries = [file_entry]
        mock_result.has_more = False
        mock_dbx.files_list_folder.return_value = mock_result

        mock_response = MagicMock()
        mock_response.content = b"%PDF-1.4"
        mock_dbx.files_download.return_value = (MagicMock(), mock_response)

        (tmp_path / "dropbox_collision.pdf").write_bytes(b"old")

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_dropbox.get_dropbox_client", return_value=mock_dbx),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_dropbox_folder("/Inbox", cache, False)
        assert count == 1


@pytest.mark.unit
class TestScanGoogleDriveFolder:
    """Tests for _scan_google_drive_folder."""

    def test_service_none_returns_zero(self):
        """If get_google_drive_service returns None, return 0."""
        from app.tasks.watch_folder_tasks import _scan_google_drive_folder

        with patch("app.tasks.upload_to_google_drive.get_google_drive_service", return_value=None):
            result = _scan_google_drive_folder("folder123", {}, False)
        assert result == 0

    def test_listing_failure_breaks_loop(self):
        """If the API listing call raises, break and return current count (0)."""
        from app.tasks.watch_folder_tasks import _scan_google_drive_folder

        mock_service = MagicMock()
        mock_service.files.return_value.list.return_value.execute.side_effect = Exception("API error")

        with patch("app.tasks.upload_to_google_drive.get_google_drive_service", return_value=mock_service):
            result = _scan_google_drive_folder("folder123", {}, False)
        assert result == 0

    def test_downloads_new_file(self, tmp_path):
        """New allowed files should be downloaded and enqueued."""
        import io

        from app.tasks.watch_folder_tasks import _scan_google_drive_folder

        mock_service = MagicMock()
        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "gid1", "name": "invoice.pdf", "mimeType": "application/pdf"}],
        }

        mock_downloader = MagicMock()
        mock_downloader.next_chunk.return_value = (None, True)

        with (
            patch("app.tasks.upload_to_google_drive.get_google_drive_service", return_value=mock_service),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
            patch("googleapiclient.http.MediaIoBaseDownload", return_value=mock_downloader),
            patch("io.BytesIO", return_value=io.BytesIO(b"%PDF-1.4")),
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_google_drive_folder("folder123", {}, False)

        assert count == 1

    def test_skips_unsupported_type(self, tmp_path):
        """Non-allowed file types should be skipped."""
        from app.tasks.watch_folder_tasks import _scan_google_drive_folder

        mock_service = MagicMock()
        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "gid2", "name": "script.exe", "mimeType": "application/octet-stream"}],
        }

        with (
            patch("app.tasks.upload_to_google_drive.get_google_drive_service", return_value=mock_service),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_google_drive_folder("folder123", {}, False)
        assert count == 0

    def test_skips_already_cached(self, tmp_path):
        """Already cached files should not be re-downloaded."""
        from app.tasks.watch_folder_tasks import _scan_google_drive_folder

        mock_service = MagicMock()
        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "gid3", "name": "cached.pdf", "mimeType": "application/pdf"}],
        }

        cache = {"gdrive:gid3": datetime.now(timezone.utc).isoformat()}
        with (
            patch("app.tasks.upload_to_google_drive.get_google_drive_service", return_value=mock_service),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_google_drive_folder("folder123", cache, False)
        assert count == 0

    def test_download_failure_skips_file(self, tmp_path):
        """Download failure should skip the file."""
        from app.tasks.watch_folder_tasks import _scan_google_drive_folder

        mock_service = MagicMock()
        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "gid4", "name": "fail.pdf", "mimeType": "application/pdf"}],
        }
        mock_service.files.return_value.get_media.side_effect = Exception("download error")

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_google_drive.get_google_drive_service", return_value=mock_service),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_google_drive_folder("folder123", cache, False)
        assert count == 0

    def test_delete_after_success(self, tmp_path):
        """delete_after=True should call service.files().delete()."""
        import io

        from app.tasks.watch_folder_tasks import _scan_google_drive_folder

        mock_service = MagicMock()
        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "gid5", "name": "todelete.pdf", "mimeType": "application/pdf"}],
        }

        mock_downloader = MagicMock()
        mock_downloader.next_chunk.return_value = (None, True)

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_google_drive.get_google_drive_service", return_value=mock_service),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
            patch("googleapiclient.http.MediaIoBaseDownload", return_value=mock_downloader),
            patch("io.BytesIO", return_value=io.BytesIO(b"%PDF-1.4")),
        ):
            mock_settings.workdir = str(tmp_path)
            _scan_google_drive_folder("folder123", cache, delete_after=True)

        mock_service.files.return_value.delete.assert_called()

    def test_pagination(self, tmp_path):
        """Should follow nextPageToken for pagination."""
        import io

        from app.tasks.watch_folder_tasks import _scan_google_drive_folder

        mock_service = MagicMock()
        mock_service.files.return_value.list.return_value.execute.side_effect = [
            {
                "files": [{"id": "gid10", "name": "page1.pdf", "mimeType": "application/pdf"}],
                "nextPageToken": "tok1",
            },
            {
                "files": [{"id": "gid11", "name": "page2.pdf", "mimeType": "application/pdf"}],
            },
        ]

        mock_downloader = MagicMock()
        mock_downloader.next_chunk.return_value = (None, True)

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_google_drive.get_google_drive_service", return_value=mock_service),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
            patch("googleapiclient.http.MediaIoBaseDownload", return_value=mock_downloader),
            patch("io.BytesIO", return_value=io.BytesIO(b"%PDF-1.4")),
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_google_drive_folder("folder123", cache, False)

        assert count == 2

    def test_delete_after_failure_does_not_crash(self, tmp_path):
        """delete_after failure is logged but does not crash."""
        import io

        from app.tasks.watch_folder_tasks import _scan_google_drive_folder

        mock_service = MagicMock()
        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "gid6", "name": "del.pdf", "mimeType": "application/pdf"}],
        }
        mock_service.files.return_value.delete.return_value.execute.side_effect = Exception("forbidden")

        mock_downloader = MagicMock()
        mock_downloader.next_chunk.return_value = (None, True)

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_google_drive.get_google_drive_service", return_value=mock_service),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
            patch("googleapiclient.http.MediaIoBaseDownload", return_value=mock_downloader),
            patch("io.BytesIO", return_value=io.BytesIO(b"%PDF-1.4")),
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_google_drive_folder("folder123", cache, delete_after=True)
        assert count == 1

    def test_file_collision_generates_unique_name(self, tmp_path):
        """When dest file already exists, a timestamped path is used."""
        import io

        from app.tasks.watch_folder_tasks import _scan_google_drive_folder

        mock_service = MagicMock()
        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "gid7", "name": "coll.pdf", "mimeType": "application/pdf"}],
        }

        (tmp_path / "gdrive_coll.pdf").write_bytes(b"old")

        mock_downloader = MagicMock()
        mock_downloader.next_chunk.return_value = (None, True)

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_google_drive.get_google_drive_service", return_value=mock_service),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
            patch("googleapiclient.http.MediaIoBaseDownload", return_value=mock_downloader),
            patch("io.BytesIO", return_value=io.BytesIO(b"%PDF-1.4")),
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_google_drive_folder("folder123", cache, False)
        assert count == 1


@pytest.mark.unit
class TestScanOneDriveFolder:
    """Tests for _scan_onedrive_folder."""

    def test_auth_failure_returns_zero(self):
        """If get_onedrive_token raises, return 0."""
        from app.tasks.watch_folder_tasks import _scan_onedrive_folder

        with patch("app.tasks.upload_to_onedrive.get_onedrive_token", side_effect=Exception("auth failed")):
            result = _scan_onedrive_folder("/Inbox", {}, False)
        assert result == 0

    def test_listing_failure_breaks_loop(self, tmp_path):
        """When the listing request raises, break and return 0."""
        from app.tasks.watch_folder_tasks import _scan_onedrive_folder

        with (
            patch("app.tasks.upload_to_onedrive.get_onedrive_token", return_value="tok"),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.get", side_effect=Exception("network error")),
        ):
            mock_settings.http_request_timeout = 30
            result = _scan_onedrive_folder("/Inbox", {}, False)
        assert result == 0

    def test_downloads_new_file(self, tmp_path):
        """New allowed files should be downloaded and enqueued."""
        from app.tasks.watch_folder_tasks import _scan_onedrive_folder

        list_resp = MagicMock()
        list_resp.json.return_value = {
            "value": [
                {
                    "name": "report.pdf",
                    "id": "item1",
                    "@microsoft.graph.downloadUrl": "https://example.com/dl/report.pdf",
                }
            ]
        }
        list_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.content = b"%PDF-1.4"
        dl_resp.raise_for_status.return_value = None

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_onedrive.get_onedrive_token", return_value="tok"),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.get", side_effect=[list_resp, dl_resp]),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_settings.http_request_timeout = 30
            count = _scan_onedrive_folder("/Inbox", cache, False)

        assert count == 1
        assert "onedrive:item1" in cache

    def test_skips_folder_items(self, tmp_path):
        """Items with 'folder' key should be skipped."""
        from app.tasks.watch_folder_tasks import _scan_onedrive_folder

        list_resp = MagicMock()
        list_resp.json.return_value = {
            "value": [
                {"name": "Subfolder", "id": "folder1", "folder": {"childCount": 2}},
            ]
        }
        list_resp.raise_for_status.return_value = None

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_onedrive.get_onedrive_token", return_value="tok"),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.get", return_value=list_resp),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_settings.http_request_timeout = 30
            count = _scan_onedrive_folder("/Inbox", cache, False)
        assert count == 0

    def test_skips_unsupported_type(self, tmp_path):
        """Non-allowed types are skipped."""
        from app.tasks.watch_folder_tasks import _scan_onedrive_folder

        list_resp = MagicMock()
        list_resp.json.return_value = {
            "value": [{"name": "script.exe", "id": "exe1", "@microsoft.graph.downloadUrl": "https://x.com/exe"}]
        }
        list_resp.raise_for_status.return_value = None

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_onedrive.get_onedrive_token", return_value="tok"),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.get", return_value=list_resp),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_settings.http_request_timeout = 30
            count = _scan_onedrive_folder("/Inbox", cache, False)
        assert count == 0

    def test_skips_already_cached(self, tmp_path):
        """Already cached files are not re-downloaded."""
        from app.tasks.watch_folder_tasks import _scan_onedrive_folder

        list_resp = MagicMock()
        list_resp.json.return_value = {
            "value": [
                {
                    "name": "cached.pdf",
                    "id": "cacheditem",
                    "@microsoft.graph.downloadUrl": "https://x.com/cached",
                }
            ]
        }
        list_resp.raise_for_status.return_value = None

        cache = {"onedrive:cacheditem": datetime.now(timezone.utc).isoformat()}
        with (
            patch("app.tasks.upload_to_onedrive.get_onedrive_token", return_value="tok"),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.get", return_value=list_resp),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_settings.http_request_timeout = 30
            count = _scan_onedrive_folder("/Inbox", cache, False)
        assert count == 0

    def test_skips_no_download_url(self, tmp_path):
        """Items without @microsoft.graph.downloadUrl are skipped."""
        from app.tasks.watch_folder_tasks import _scan_onedrive_folder

        list_resp = MagicMock()
        list_resp.json.return_value = {"value": [{"name": "nurl.pdf", "id": "nurl1"}]}
        list_resp.raise_for_status.return_value = None

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_onedrive.get_onedrive_token", return_value="tok"),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.get", return_value=list_resp),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_settings.http_request_timeout = 30
            count = _scan_onedrive_folder("/Inbox", cache, False)
        assert count == 0

    def test_download_failure_skips_file(self, tmp_path):
        """Download failure skips the file."""
        from app.tasks.watch_folder_tasks import _scan_onedrive_folder

        list_resp = MagicMock()
        list_resp.json.return_value = {
            "value": [
                {
                    "name": "fail.pdf",
                    "id": "fail1",
                    "@microsoft.graph.downloadUrl": "https://x.com/fail",
                }
            ]
        }
        list_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.raise_for_status.side_effect = Exception("dl failed")

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_onedrive.get_onedrive_token", return_value="tok"),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.get", side_effect=[list_resp, dl_resp]),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_settings.http_request_timeout = 30
            count = _scan_onedrive_folder("/Inbox", cache, False)
        assert count == 0
        assert "onedrive:fail1" not in cache

    def test_delete_after_success(self, tmp_path):
        """delete_after=True should call DELETE on the item."""
        from app.tasks.watch_folder_tasks import _scan_onedrive_folder

        list_resp = MagicMock()
        list_resp.json.return_value = {
            "value": [
                {
                    "name": "del.pdf",
                    "id": "del1",
                    "@microsoft.graph.downloadUrl": "https://x.com/del",
                }
            ]
        }
        list_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.content = b"%PDF-1.4"
        dl_resp.raise_for_status.return_value = None

        del_resp = MagicMock()
        del_resp.raise_for_status.return_value = None

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_onedrive.get_onedrive_token", return_value="tok"),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.get", side_effect=[list_resp, dl_resp]),
            patch("requests.delete", return_value=del_resp),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_settings.http_request_timeout = 30
            count = _scan_onedrive_folder("/Inbox", cache, delete_after=True)

        assert count == 1

    def test_delete_after_failure_does_not_crash(self, tmp_path):
        """delete_after failure is logged but doesn't crash."""
        from app.tasks.watch_folder_tasks import _scan_onedrive_folder

        list_resp = MagicMock()
        list_resp.json.return_value = {
            "value": [
                {
                    "name": "del2.pdf",
                    "id": "del2",
                    "@microsoft.graph.downloadUrl": "https://x.com/del2",
                }
            ]
        }
        list_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.content = b"%PDF-1.4"
        dl_resp.raise_for_status.return_value = None

        del_resp = MagicMock()
        del_resp.raise_for_status.side_effect = Exception("forbidden")

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_onedrive.get_onedrive_token", return_value="tok"),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.get", side_effect=[list_resp, dl_resp]),
            patch("requests.delete", return_value=del_resp),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_settings.http_request_timeout = 30
            count = _scan_onedrive_folder("/Inbox", cache, delete_after=True)
        assert count == 1

    def test_pagination(self, tmp_path):
        """Should follow @odata.nextLink for pagination."""
        from app.tasks.watch_folder_tasks import _scan_onedrive_folder

        page1_resp = MagicMock()
        page1_resp.json.return_value = {
            "value": [
                {
                    "name": "p1.pdf",
                    "id": "p1",
                    "@microsoft.graph.downloadUrl": "https://x.com/p1",
                }
            ],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/next",
        }
        page1_resp.raise_for_status.return_value = None

        page2_resp = MagicMock()
        page2_resp.json.return_value = {
            "value": [
                {
                    "name": "p2.pdf",
                    "id": "p2",
                    "@microsoft.graph.downloadUrl": "https://x.com/p2",
                }
            ]
        }
        page2_resp.raise_for_status.return_value = None

        dl1 = MagicMock()
        dl1.content = b"%PDF-1.4"
        dl1.raise_for_status.return_value = None

        dl2 = MagicMock()
        dl2.content = b"%PDF-1.4"
        dl2.raise_for_status.return_value = None

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_onedrive.get_onedrive_token", return_value="tok"),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.get", side_effect=[page1_resp, dl1, page2_resp, dl2]),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_settings.http_request_timeout = 30
            count = _scan_onedrive_folder("/Inbox", cache, False)

        assert count == 2

    def test_file_collision_generates_unique_name(self, tmp_path):
        """When dest file already exists, a timestamped path is used."""
        from app.tasks.watch_folder_tasks import _scan_onedrive_folder

        list_resp = MagicMock()
        list_resp.json.return_value = {
            "value": [
                {
                    "name": "coll.pdf",
                    "id": "coll1",
                    "@microsoft.graph.downloadUrl": "https://x.com/coll",
                }
            ]
        }
        list_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.content = b"%PDF-1.4"
        dl_resp.raise_for_status.return_value = None

        (tmp_path / "onedrive_coll.pdf").write_bytes(b"old")

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_onedrive.get_onedrive_token", return_value="tok"),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.get", side_effect=[list_resp, dl_resp]),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_settings.http_request_timeout = 30
            count = _scan_onedrive_folder("/Inbox", cache, False)
        assert count == 1


@pytest.mark.unit
class TestScanNextcloudFolder:
    """Tests for _scan_nextcloud_folder."""

    def test_incomplete_settings_returns_zero(self):
        """Returns 0 if Nextcloud connection settings are missing."""
        from app.tasks.watch_folder_tasks import _scan_nextcloud_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.nextcloud_upload_url = None
            mock_settings.nextcloud_username = "user"
            mock_settings.nextcloud_password = "pass"  # noqa: S105
            result = _scan_nextcloud_folder("/Scans", {}, False)
        assert result == 0

    def test_propfind_failure_returns_zero(self):
        """Returns 0 if PROPFIND request fails."""
        from app.tasks.watch_folder_tasks import _scan_nextcloud_folder

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", side_effect=Exception("connection refused")),
        ):
            mock_settings.nextcloud_upload_url = "https://cloud.example.com/remote.php/webdav"
            mock_settings.nextcloud_username = "user"
            mock_settings.nextcloud_password = "pass"  # noqa: S105
            mock_settings.http_request_timeout = 30
            result = _scan_nextcloud_folder("/Scans", {}, False)
        assert result == 0

    def test_xml_parse_failure_returns_zero(self):
        """Returns 0 if XML parsing fails."""
        from app.tasks.watch_folder_tasks import _scan_nextcloud_folder

        mock_resp = MagicMock()
        mock_resp.text = "invalid xml <<<"
        mock_resp.raise_for_status.return_value = None

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=mock_resp),
        ):
            mock_settings.nextcloud_upload_url = "https://cloud.example.com/remote.php/webdav"
            mock_settings.nextcloud_username = "user"
            mock_settings.nextcloud_password = "pass"  # noqa: S105
            mock_settings.http_request_timeout = 30
            result = _scan_nextcloud_folder("/Scans", {}, False)
        assert result == 0

    def _build_propfind_xml(self, hrefs):
        responses = "".join(
            f"<d:response><d:href>{href}</d:href><d:propstat></d:propstat></d:response>" for href in hrefs
        )
        return f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">{responses}</d:multistatus>'

    def test_downloads_new_file(self, tmp_path):
        """New allowed files should be downloaded and enqueued."""
        from app.tasks.watch_folder_tasks import _scan_nextcloud_folder

        xml = self._build_propfind_xml(["/remote.php/webdav/Scans/", "/remote.php/webdav/Scans/invoice.pdf"])
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.content = b"%PDF-1.4"
        dl_resp.raise_for_status.return_value = None

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
            patch("requests.get", return_value=dl_resp),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.nextcloud_upload_url = "https://cloud.example.com/remote.php/webdav"
            mock_settings.nextcloud_username = "user"
            mock_settings.nextcloud_password = "pass"  # noqa: S105
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_nextcloud_folder("Scans", cache, False)

        assert count == 1

    def test_skips_already_cached(self, tmp_path):
        """Cached files should not be re-downloaded."""
        from app.tasks.watch_folder_tasks import _scan_nextcloud_folder

        xml = self._build_propfind_xml(["/remote.php/webdav/Scans/cached.pdf"])
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        cache = {"nextcloud:/remote.php/webdav/Scans/cached.pdf": datetime.now(timezone.utc).isoformat()}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
        ):
            mock_settings.nextcloud_upload_url = "https://cloud.example.com/remote.php/webdav"
            mock_settings.nextcloud_username = "user"
            mock_settings.nextcloud_password = "pass"  # noqa: S105
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_nextcloud_folder("Scans", cache, False)
        assert count == 0

    def test_skips_unsupported_type(self, tmp_path):
        """Non-allowed types should be skipped."""
        from app.tasks.watch_folder_tasks import _scan_nextcloud_folder

        xml = self._build_propfind_xml(["/remote.php/webdav/Scans/script.exe"])
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
        ):
            mock_settings.nextcloud_upload_url = "https://cloud.example.com/remote.php/webdav"
            mock_settings.nextcloud_username = "user"
            mock_settings.nextcloud_password = "pass"  # noqa: S105
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_nextcloud_folder("Scans", {}, False)
        assert count == 0

    def test_download_failure_skips_file(self, tmp_path):
        """Download failure skips the file."""
        from app.tasks.watch_folder_tasks import _scan_nextcloud_folder

        xml = self._build_propfind_xml(["/remote.php/webdav/Scans/fail.pdf"])
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.raise_for_status.side_effect = Exception("download failed")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
            patch("requests.get", return_value=dl_resp),
        ):
            mock_settings.nextcloud_upload_url = "https://cloud.example.com/remote.php/webdav"
            mock_settings.nextcloud_username = "user"
            mock_settings.nextcloud_password = "pass"  # noqa: S105
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_nextcloud_folder("Scans", cache, False)
        assert count == 0

    def test_delete_after_success(self, tmp_path):
        """delete_after=True should call DELETE on the file URL."""
        from app.tasks.watch_folder_tasks import _scan_nextcloud_folder

        xml = self._build_propfind_xml(["/remote.php/webdav/Scans/del.pdf"])
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.content = b"%PDF-1.4"
        dl_resp.raise_for_status.return_value = None

        del_resp = MagicMock()
        del_resp.raise_for_status.return_value = None

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", side_effect=[propfind_resp, del_resp]),
            patch("requests.get", return_value=dl_resp),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.nextcloud_upload_url = "https://cloud.example.com/remote.php/webdav"
            mock_settings.nextcloud_username = "user"
            mock_settings.nextcloud_password = "pass"  # noqa: S105
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_nextcloud_folder("Scans", cache, delete_after=True)
        assert count == 1

    def test_delete_after_failure_does_not_crash(self, tmp_path):
        """delete_after failure is logged but doesn't crash."""
        from app.tasks.watch_folder_tasks import _scan_nextcloud_folder

        xml = self._build_propfind_xml(["/remote.php/webdav/Scans/del2.pdf"])
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.content = b"%PDF-1.4"
        dl_resp.raise_for_status.return_value = None

        del_resp = MagicMock()
        del_resp.raise_for_status.side_effect = Exception("forbidden")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", side_effect=[propfind_resp, del_resp]),
            patch("requests.get", return_value=dl_resp),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.nextcloud_upload_url = "https://cloud.example.com/remote.php/webdav"
            mock_settings.nextcloud_username = "user"
            mock_settings.nextcloud_password = "pass"  # noqa: S105
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_nextcloud_folder("Scans", cache, delete_after=True)
        assert count == 1

    def test_file_collision_generates_unique_name(self, tmp_path):
        """When dest file already exists, a timestamped path is used."""
        from app.tasks.watch_folder_tasks import _scan_nextcloud_folder

        xml = self._build_propfind_xml(["/remote.php/webdav/Scans/coll.pdf"])
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.content = b"%PDF-1.4"
        dl_resp.raise_for_status.return_value = None

        (tmp_path / "nc_coll.pdf").write_bytes(b"old")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
            patch("requests.get", return_value=dl_resp),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.nextcloud_upload_url = "https://cloud.example.com/remote.php/webdav"
            mock_settings.nextcloud_username = "user"
            mock_settings.nextcloud_password = "pass"  # noqa: S105
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_nextcloud_folder("Scans", cache, False)
        assert count == 1

    def test_absolute_href_used_directly(self, tmp_path):
        """When href is already an absolute URL, it should be used as-is."""
        from app.tasks.watch_folder_tasks import _scan_nextcloud_folder

        xml = self._build_propfind_xml(["https://cloud.example.com/remote.php/webdav/Scans/abs.pdf"])
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.content = b"%PDF-1.4"
        dl_resp.raise_for_status.return_value = None

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
            patch("requests.get", return_value=dl_resp),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.nextcloud_upload_url = "https://cloud.example.com/remote.php/webdav"
            mock_settings.nextcloud_username = "user"
            mock_settings.nextcloud_password = "pass"  # noqa: S105
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_nextcloud_folder("Scans", cache, False)
        assert count == 1


@pytest.mark.unit
class TestScanS3Prefix:
    """Tests for _scan_s3_prefix."""

    def test_missing_bucket_returns_zero(self):
        """Returns 0 when S3_BUCKET_NAME is not configured."""
        from app.tasks.watch_folder_tasks import _scan_s3_prefix

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.s3_bucket_name = None
            result = _scan_s3_prefix("inbox/", {}, False)
        assert result == 0

    def test_downloads_new_object(self, tmp_path):
        """New allowed S3 objects should be downloaded and enqueued."""
        from app.tasks.watch_folder_tasks import _scan_s3_prefix

        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"Contents": [{"Key": "inbox/invoice.pdf"}]}]

        cache: dict = {}
        with (
            patch("boto3.client", return_value=mock_s3),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.s3_bucket_name = "mybucket"
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_access_key_id = "key"
            mock_settings.aws_secret_access_key = "secret"  # noqa: S105
            mock_settings.workdir = str(tmp_path)
            count = _scan_s3_prefix("inbox/", cache, False)

        assert count == 1
        assert "s3:mybucket/inbox/invoice.pdf" in cache

    def test_skips_empty_key(self, tmp_path):
        """Objects with empty filename (folder markers) should be skipped."""
        from app.tasks.watch_folder_tasks import _scan_s3_prefix

        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"Contents": [{"Key": "inbox/"}]}]

        cache: dict = {}
        with (
            patch("boto3.client", return_value=mock_s3),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.s3_bucket_name = "mybucket"
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_access_key_id = "key"
            mock_settings.aws_secret_access_key = "secret"  # noqa: S105
            mock_settings.workdir = str(tmp_path)
            count = _scan_s3_prefix("inbox/", cache, False)
        assert count == 0

    def test_skips_unsupported_type(self, tmp_path):
        """Non-allowed types should be skipped."""
        from app.tasks.watch_folder_tasks import _scan_s3_prefix

        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"Contents": [{"Key": "inbox/script.exe"}]}]

        with (
            patch("boto3.client", return_value=mock_s3),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.s3_bucket_name = "mybucket"
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_access_key_id = "key"
            mock_settings.aws_secret_access_key = "secret"  # noqa: S105
            mock_settings.workdir = str(tmp_path)
            count = _scan_s3_prefix("inbox/", {}, False)
        assert count == 0

    def test_skips_already_cached(self, tmp_path):
        """Already cached objects should not be re-downloaded."""
        from app.tasks.watch_folder_tasks import _scan_s3_prefix

        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"Contents": [{"Key": "inbox/cached.pdf"}]}]

        cache = {"s3:mybucket/inbox/cached.pdf": datetime.now(timezone.utc).isoformat()}
        with (
            patch("boto3.client", return_value=mock_s3),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.s3_bucket_name = "mybucket"
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_access_key_id = "key"
            mock_settings.aws_secret_access_key = "secret"  # noqa: S105
            mock_settings.workdir = str(tmp_path)
            count = _scan_s3_prefix("inbox/", cache, False)
        assert count == 0

    def test_download_failure_skips_file(self, tmp_path):
        """ClientError during download should skip the file."""
        from botocore.exceptions import ClientError

        from app.tasks.watch_folder_tasks import _scan_s3_prefix

        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"Contents": [{"Key": "inbox/fail.pdf"}]}]
        mock_s3.download_file.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject"
        )

        cache: dict = {}
        with (
            patch("boto3.client", return_value=mock_s3),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.s3_bucket_name = "mybucket"
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_access_key_id = "key"
            mock_settings.aws_secret_access_key = "secret"  # noqa: S105
            mock_settings.workdir = str(tmp_path)
            count = _scan_s3_prefix("inbox/", cache, False)
        assert count == 0
        assert "s3:mybucket/inbox/fail.pdf" not in cache

    def test_delete_after_success(self, tmp_path):
        """delete_after=True should call s3.delete_object."""
        from app.tasks.watch_folder_tasks import _scan_s3_prefix

        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"Contents": [{"Key": "inbox/del.pdf"}]}]

        cache: dict = {}
        with (
            patch("boto3.client", return_value=mock_s3),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.s3_bucket_name = "mybucket"
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_access_key_id = "key"
            mock_settings.aws_secret_access_key = "secret"  # noqa: S105
            mock_settings.workdir = str(tmp_path)
            count = _scan_s3_prefix("inbox/", cache, delete_after=True)

        assert count == 1
        mock_s3.delete_object.assert_called_once_with(Bucket="mybucket", Key="inbox/del.pdf")

    def test_delete_after_failure_does_not_crash(self, tmp_path):
        """delete_after failure is logged but doesn't crash."""
        from app.tasks.watch_folder_tasks import _scan_s3_prefix

        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"Contents": [{"Key": "inbox/del2.pdf"}]}]
        mock_s3.delete_object.side_effect = Exception("access denied")

        cache: dict = {}
        with (
            patch("boto3.client", return_value=mock_s3),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.s3_bucket_name = "mybucket"
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_access_key_id = "key"
            mock_settings.aws_secret_access_key = "secret"  # noqa: S105
            mock_settings.workdir = str(tmp_path)
            count = _scan_s3_prefix("inbox/", cache, delete_after=True)
        assert count == 1

    def test_file_collision_generates_unique_name(self, tmp_path):
        """When dest file already exists, a timestamped path is used."""
        from app.tasks.watch_folder_tasks import _scan_s3_prefix

        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"Contents": [{"Key": "inbox/coll.pdf"}]}]

        (tmp_path / "s3_coll.pdf").write_bytes(b"old")

        cache: dict = {}
        with (
            patch("boto3.client", return_value=mock_s3),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.s3_bucket_name = "mybucket"
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_access_key_id = "key"
            mock_settings.aws_secret_access_key = "secret"  # noqa: S105
            mock_settings.workdir = str(tmp_path)
            count = _scan_s3_prefix("inbox/", cache, False)
        assert count == 1


@pytest.mark.unit
class TestScanWebdavFolder:
    """Tests for _scan_webdav_folder."""

    def test_missing_url_returns_zero(self):
        """Returns 0 when WEBDAV_URL is not configured."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.webdav_url = None
            mock_settings.webdav_username = None
            mock_settings.webdav_password = None  # noqa: S105
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            result = _scan_webdav_folder("/Inbox", {}, False)
        assert result == 0

    def test_propfind_failure_returns_zero(self):
        """Returns 0 if PROPFIND fails."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", side_effect=Exception("connection refused")),
        ):
            mock_settings.webdav_url = "https://dav.example.com"
            mock_settings.webdav_username = "user"
            mock_settings.webdav_password = "pass"  # noqa: S105
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            result = _scan_webdav_folder("/Inbox", {}, False)
        assert result == 0

    def test_xml_parse_failure_returns_zero(self):
        """Returns 0 if XML parsing fails."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        mock_resp = MagicMock()
        mock_resp.text = "invalid <<< xml"
        mock_resp.raise_for_status.return_value = None

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=mock_resp),
        ):
            mock_settings.webdav_url = "https://dav.example.com"
            mock_settings.webdav_username = "user"
            mock_settings.webdav_password = "pass"  # noqa: S105
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            result = _scan_webdav_folder("/Inbox", {}, False)
        assert result == 0

    def _build_webdav_xml(self, hrefs):
        responses = "".join(f"<d:response><d:href>{href}</d:href></d:response>" for href in hrefs)
        return f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">{responses}</d:multistatus>'

    def test_skips_directory_entries(self, tmp_path):
        """Entries ending with '/' should be skipped."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        xml = self._build_webdav_xml(["/dav/Inbox/"])
        mock_resp = MagicMock()
        mock_resp.text = xml
        mock_resp.raise_for_status.return_value = None

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=mock_resp),
        ):
            mock_settings.webdav_url = "https://dav.example.com"
            mock_settings.webdav_username = "user"
            mock_settings.webdav_password = "pass"  # noqa: S105
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_webdav_folder("/Inbox", {}, False)
        assert count == 0

    def test_downloads_new_file(self, tmp_path):
        """New allowed files should be downloaded and enqueued."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        xml = self._build_webdav_xml(["/dav/Inbox/invoice.pdf"])
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.content = b"%PDF-1.4"
        dl_resp.raise_for_status.return_value = None

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
            patch("requests.get", return_value=dl_resp),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.webdav_url = "https://dav.example.com"
            mock_settings.webdav_username = "user"
            mock_settings.webdav_password = "pass"  # noqa: S105
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_webdav_folder("/Inbox", cache, False)

        assert count == 1
        assert "webdav:/dav/Inbox/invoice.pdf" in cache

    def test_skips_already_cached(self, tmp_path):
        """Cached files should not be re-downloaded."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        xml = self._build_webdav_xml(["/dav/Inbox/cached.pdf"])
        mock_resp = MagicMock()
        mock_resp.text = xml
        mock_resp.raise_for_status.return_value = None

        cache = {"webdav:/dav/Inbox/cached.pdf": datetime.now(timezone.utc).isoformat()}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=mock_resp),
        ):
            mock_settings.webdav_url = "https://dav.example.com"
            mock_settings.webdav_username = "user"
            mock_settings.webdav_password = "pass"  # noqa: S105
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_webdav_folder("/Inbox", cache, False)
        assert count == 0

    def test_skips_unsupported_type(self, tmp_path):
        """Non-allowed types should be skipped."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        xml = self._build_webdav_xml(["/dav/Inbox/script.exe"])
        mock_resp = MagicMock()
        mock_resp.text = xml
        mock_resp.raise_for_status.return_value = None

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=mock_resp),
        ):
            mock_settings.webdav_url = "https://dav.example.com"
            mock_settings.webdav_username = "user"
            mock_settings.webdav_password = "pass"  # noqa: S105
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_webdav_folder("/Inbox", {}, False)
        assert count == 0

    def test_download_failure_skips_file(self, tmp_path):
        """Download failure skips the file."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        xml = self._build_webdav_xml(["/dav/Inbox/fail.pdf"])
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.raise_for_status.side_effect = Exception("dl failed")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
            patch("requests.get", return_value=dl_resp),
        ):
            mock_settings.webdav_url = "https://dav.example.com"
            mock_settings.webdav_username = "user"
            mock_settings.webdav_password = "pass"  # noqa: S105
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_webdav_folder("/Inbox", cache, False)
        assert count == 0

    def test_delete_after_success(self, tmp_path):
        """delete_after=True should issue a DELETE request."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        xml = self._build_webdav_xml(["/dav/Inbox/del.pdf"])
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.content = b"%PDF-1.4"
        dl_resp.raise_for_status.return_value = None

        del_resp = MagicMock()
        del_resp.raise_for_status.return_value = None

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", side_effect=[propfind_resp, del_resp]),
            patch("requests.get", return_value=dl_resp),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.webdav_url = "https://dav.example.com"
            mock_settings.webdav_username = "user"
            mock_settings.webdav_password = "pass"  # noqa: S105
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_webdav_folder("/Inbox", cache, delete_after=True)
        assert count == 1

    def test_delete_after_failure_does_not_crash(self, tmp_path):
        """delete_after failure is logged but doesn't crash."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        xml = self._build_webdav_xml(["/dav/Inbox/del2.pdf"])
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.content = b"%PDF-1.4"
        dl_resp.raise_for_status.return_value = None

        del_resp = MagicMock()
        del_resp.raise_for_status.side_effect = Exception("forbidden")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", side_effect=[propfind_resp, del_resp]),
            patch("requests.get", return_value=dl_resp),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.webdav_url = "https://dav.example.com"
            mock_settings.webdav_username = "user"
            mock_settings.webdav_password = "pass"  # noqa: S105
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_webdav_folder("/Inbox", cache, delete_after=True)
        assert count == 1

    def test_file_collision_generates_unique_name(self, tmp_path):
        """When dest file already exists, a timestamped path is used."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        xml = self._build_webdav_xml(["/dav/Inbox/coll.pdf"])
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.content = b"%PDF-1.4"
        dl_resp.raise_for_status.return_value = None

        (tmp_path / "webdav_coll.pdf").write_bytes(b"old")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
            patch("requests.get", return_value=dl_resp),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.webdav_url = "https://dav.example.com"
            mock_settings.webdav_username = "user"
            mock_settings.webdav_password = "pass"  # noqa: S105
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_webdav_folder("/Inbox", cache, False)
        assert count == 1

    def test_absolute_href_used_directly(self, tmp_path):
        """When href is already an absolute URL, it should be used as-is."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        xml = self._build_webdav_xml(["https://dav.example.com/dav/Inbox/abs.pdf"])
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.content = b"%PDF-1.4"
        dl_resp.raise_for_status.return_value = None

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
            patch("requests.get", return_value=dl_resp),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.webdav_url = "https://dav.example.com"
            mock_settings.webdav_username = "user"
            mock_settings.webdav_password = "pass"  # noqa: S105
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_webdav_folder("/Inbox", cache, False)
        assert count == 1

    def test_no_auth_uses_none(self, tmp_path):
        """When webdav_username is None, auth=None should be used."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        xml = self._build_webdav_xml(["/dav/Inbox/noauth.pdf"])
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.content = b"%PDF-1.4"
        dl_resp.raise_for_status.return_value = None

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
            patch("requests.get", return_value=dl_resp),
            patch("app.tasks.watch_folder_tasks.process_document"),
        ):
            mock_settings.webdav_url = "https://dav.example.com"
            mock_settings.webdav_username = None
            mock_settings.webdav_password = None  # noqa: S105
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            mock_settings.workdir = str(tmp_path)
            count = _scan_webdav_folder("/Inbox", cache, False)
        assert count == 1


@pytest.mark.unit
class TestScanFtpWatchFolderQuitError:
    """Test that FTP quit errors during scan are silently handled."""

    def test_ftp_quit_error_does_not_crash(self):
        """If ftp.quit() raises, it should be logged but not crash."""
        from app.tasks.watch_folder_tasks import scan_ftp_watch_folder

        mock_ftp = MagicMock()
        mock_ftp.quit.side_effect = Exception("quit error")

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks._connect_ftp", return_value=mock_ftp),
            patch("app.tasks.watch_folder_tasks._load_cache", return_value={}),
            patch("app.tasks.watch_folder_tasks._save_cache"),
            patch("app.tasks.watch_folder_tasks._scan_ftp_folder", return_value=0),
        ):
            mock_settings.ftp_ingest_enabled = True
            mock_settings.ftp_ingest_folder = "/inbox"
            mock_settings.ftp_ingest_delete_after_process = False
            result = scan_ftp_watch_folder()

        assert result["status"] == "ok"


@pytest.mark.unit
class TestScanSftpWatchFolderCloseErrors:
    """Test that SFTP close errors during scan are silently handled."""

    def test_sftp_close_error_does_not_crash(self):
        """If sftp.close() raises, it should be logged but not crash."""
        from app.tasks.watch_folder_tasks import scan_sftp_watch_folder

        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        mock_sftp.close.side_effect = Exception("sftp close error")
        mock_ssh.close.side_effect = Exception("ssh close error")

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks._get_sftp_connection", return_value=(mock_ssh, mock_sftp)),
            patch("app.tasks.watch_folder_tasks._load_cache", return_value={}),
            patch("app.tasks.watch_folder_tasks._save_cache"),
            patch("app.tasks.watch_folder_tasks._scan_sftp_folder", return_value=0),
        ):
            mock_settings.sftp_ingest_enabled = True
            mock_settings.sftp_ingest_folder = "/upload"
            mock_settings.sftp_ingest_delete_after_process = False
            result = scan_sftp_watch_folder()

        assert result["status"] == "ok"


@pytest.mark.unit
class TestScanLocalWatchFoldersMultipleFolders:
    """Test scan_local_watch_folders with multiple comma-separated folders."""

    def test_multiple_folders_scanned(self, tmp_path):
        """All folders in comma-separated WATCH_FOLDERS should be scanned."""
        from app.tasks.watch_folder_tasks import scan_local_watch_folders

        folder1 = str(tmp_path / "folder1")
        folder2 = str(tmp_path / "folder2")

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("app.tasks.watch_folder_tasks._load_cache", return_value={}),
            patch("app.tasks.watch_folder_tasks._save_cache"),
            patch("app.tasks.watch_folder_tasks._scan_local_folder", return_value=1) as mock_scan,
        ):
            mock_settings.watch_folders = f"{folder1},{folder2}"
            mock_settings.watch_folder_delete_after_process = False
            result = scan_local_watch_folders()

        assert result["status"] == "ok"
        assert result["folders_scanned"] == 2
        assert result["files_enqueued"] == 2
        assert mock_scan.call_count == 2

    def test_whitespace_only_entries_are_ignored(self):
        """Entries that are whitespace-only should be filtered out."""
        from app.tasks.watch_folder_tasks import scan_local_watch_folders

        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.watch_folders = "  ,  ,  "
            result = scan_local_watch_folders()

        assert result["status"] == "skipped"
        assert result["reason"] == "WATCH_FOLDERS is empty"


@pytest.mark.unit
class TestPartialFileCleanup:
    """Tests for partial file cleanup on download failures."""

    def test_ftp_download_failure_removes_partial_file(self, tmp_path):
        """When FTP download fails and partial file exists, it should be removed."""
        from app.tasks.watch_folder_tasks import _scan_ftp_folder

        mock_ftp = MagicMock()
        mock_ftp.cwd.return_value = None
        mock_ftp.nlst.return_value = ["partial.pdf"]

        # retrbinary creates a partial file then raises
        dest = tmp_path / "ftp_partial.pdf"

        def fake_retrbinary(cmd, callback):
            dest.write_bytes(b"%PDF partial")
            raise Exception("transfer interrupted")

        mock_ftp.retrbinary.side_effect = fake_retrbinary

        cache: dict = {}
        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            count = _scan_ftp_folder(mock_ftp, "/inbox", cache, False)

        assert count == 0
        assert not dest.exists()

    def test_sftp_download_failure_removes_partial_file(self, tmp_path):
        """When SFTP get fails and partial file exists, it should be removed."""
        from app.tasks.watch_folder_tasks import _scan_sftp_folder

        mock_sftp = MagicMock()
        file_attr = MagicMock()
        file_attr.st_mode = stat.S_IFREG | 0o644
        file_attr.filename = "partial.pdf"
        mock_sftp.listdir_attr.return_value = [file_attr]

        # sftp.get creates a partial file then raises
        dest = tmp_path / "sftp_partial.pdf"

        def fake_get(remote, local):
            (tmp_path / "sftp_partial.pdf").write_bytes(b"partial")
            raise Exception("connection dropped")

        mock_sftp.get.side_effect = fake_get

        cache: dict = {}
        with patch("app.tasks.watch_folder_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            count = _scan_sftp_folder(mock_sftp, "/upload", cache, False)

        assert count == 0
        assert not dest.exists()

    def test_dropbox_download_failure_removes_partial_file(self, tmp_path):
        """When Dropbox download fails and partial file exists, it should be removed."""
        import dropbox as dropbox_module

        from app.tasks.watch_folder_tasks import _scan_dropbox_folder

        mock_dbx = MagicMock()
        file_entry = MagicMock(spec=dropbox_module.files.FileMetadata)
        file_entry.name = "partial.pdf"
        file_entry.id = "id:partial"
        file_entry.path_lower = "/inbox/partial.pdf"

        mock_result = MagicMock()
        mock_result.entries = [file_entry]
        mock_result.has_more = False
        mock_dbx.files_list_folder.return_value = mock_result

        dest = tmp_path / "dropbox_partial.pdf"

        def fake_download(path):
            dest.write_bytes(b"partial")
            raise Exception("download aborted")

        mock_dbx.files_download.side_effect = fake_download

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_dropbox.get_dropbox_client", return_value=mock_dbx),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_dropbox_folder("/Inbox", cache, False)

        assert count == 0
        assert not dest.exists()

    def test_google_drive_download_failure_removes_partial_file(self, tmp_path):
        """When Google Drive download fails and partial file exists, it should be removed."""

        from app.tasks.watch_folder_tasks import _scan_google_drive_folder

        mock_service = MagicMock()
        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "gid_partial", "name": "partial.pdf", "mimeType": "application/pdf"}],
        }

        dest = tmp_path / "gdrive_partial.pdf"

        def fake_downloader(*args, **kwargs):
            dest.write_bytes(b"partial")
            raise Exception("quota exceeded")

        mock_service.files.return_value.get_media.side_effect = fake_downloader

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_google_drive.get_google_drive_service", return_value=mock_service),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            count = _scan_google_drive_folder("folder123", cache, False)

        assert count == 0
        assert not dest.exists()

    def test_onedrive_download_failure_removes_partial_file(self, tmp_path):
        """When OneDrive download fails and partial file exists, it should be removed."""
        from app.tasks.watch_folder_tasks import _scan_onedrive_folder

        list_resp = MagicMock()
        list_resp.json.return_value = {
            "value": [
                {
                    "name": "partial.pdf",
                    "id": "partial1",
                    "@microsoft.graph.downloadUrl": "https://x.com/partial",
                }
            ]
        }
        list_resp.raise_for_status.return_value = None

        dest = tmp_path / "onedrive_partial.pdf"

        dl_call_count = 0

        def fake_get(url, **kwargs):
            nonlocal dl_call_count
            dl_call_count += 1
            if dl_call_count == 1:
                # First call is the listing request
                return list_resp
            # Second call is the download — create partial file then raise
            dest.write_bytes(b"partial")
            r = MagicMock()
            r.raise_for_status.side_effect = Exception("timeout")
            return r

        cache: dict = {}
        with (
            patch("app.tasks.upload_to_onedrive.get_onedrive_token", return_value="tok"),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.get", side_effect=fake_get),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_settings.http_request_timeout = 30
            count = _scan_onedrive_folder("/Inbox", cache, False)

        assert count == 0
        assert not dest.exists()


@pytest.mark.unit
class TestSftpKeyWithoutPassphrase:
    """Test SFTP key-based auth without passphrase."""

    def test_connects_with_key_no_passphrase(self, tmp_path):
        """Key file with no passphrase should still connect successfully."""
        import paramiko

        key_file = tmp_path / "id_rsa"
        key_file.write_text("fake key")

        mock_ssh = MagicMock(spec=paramiko.SSHClient)
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("paramiko.SSHClient", return_value=mock_ssh),
        ):
            mock_settings.sftp_host = "sftp.example.com"
            mock_settings.sftp_port = 22
            mock_settings.sftp_username = "user"
            mock_settings.sftp_disable_host_key_verification = False
            mock_settings.sftp_private_key = str(key_file)
            mock_settings.sftp_private_key_passphrase = None  # No passphrase
            mock_settings.sftp_password = None

            from app.tasks.watch_folder_tasks import _get_sftp_connection

            ssh, sftp = _get_sftp_connection()

        assert ssh is mock_ssh
        assert sftp is mock_sftp
        # Verify passphrase was NOT added to connect kwargs
        call_kwargs = mock_ssh.connect.call_args[1]
        assert "passphrase" not in call_kwargs


@pytest.mark.unit
class TestS3ClientAndPaginatorFailures:
    """Tests for S3 client creation and paginator failures."""

    def test_s3_client_creation_failure_returns_zero(self, tmp_path):
        """When boto3.client() raises, return 0."""
        from app.tasks.watch_folder_tasks import _scan_s3_prefix

        with (
            patch("boto3.client", side_effect=Exception("invalid credentials")),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.s3_bucket_name = "mybucket"
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_access_key_id = "key"
            mock_settings.aws_secret_access_key = "secret"  # noqa: S105
            mock_settings.workdir = str(tmp_path)
            result = _scan_s3_prefix("inbox/", {}, False)

        assert result == 0

    def test_s3_paginate_failure_returns_zero(self, tmp_path):
        """When paginator.paginate() raises, return 0."""
        from app.tasks.watch_folder_tasks import _scan_s3_prefix

        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.side_effect = Exception("ListObjectsV2 failed")

        with (
            patch("boto3.client", return_value=mock_s3),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.s3_bucket_name = "mybucket"
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_access_key_id = "key"
            mock_settings.aws_secret_access_key = "secret"  # noqa: S105
            mock_settings.workdir = str(tmp_path)
            result = _scan_s3_prefix("inbox/", {}, False)

        assert result == 0


@pytest.mark.unit
class TestHrefNullBranches:
    """Tests for null href branches in Nextcloud and WebDAV scanning."""

    def _nc_settings(self, mock_settings):
        """Configure mock Nextcloud settings."""
        mock_settings.nextcloud_upload_url = "https://cloud.example.com/remote.php/webdav"
        mock_settings.nextcloud_username = "user"
        mock_settings.nextcloud_password = "pass"  # noqa: S105
        mock_settings.http_request_timeout = 30

    def _dav_settings(self, mock_settings, tmp_path):
        """Configure mock WebDAV settings."""
        mock_settings.webdav_url = "https://dav.example.com"
        mock_settings.webdav_username = "user"
        mock_settings.webdav_password = "pass"  # noqa: S105
        mock_settings.webdav_verify_ssl = True
        mock_settings.http_request_timeout = 30
        mock_settings.workdir = str(tmp_path)

    def test_nextcloud_response_with_no_href_element(self, tmp_path):
        """Response elements without d:href should be skipped."""
        from app.tasks.watch_folder_tasks import _scan_nextcloud_folder

        xml = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response><d:propstat></d:propstat></d:response></d:multistatus>'
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
        ):
            self._nc_settings(mock_settings)
            mock_settings.workdir = str(tmp_path)
            count = _scan_nextcloud_folder("Scans", {}, False)
        assert count == 0

    def test_nextcloud_response_with_empty_href_text(self, tmp_path):
        """Response elements with empty d:href text should be skipped."""
        from app.tasks.watch_folder_tasks import _scan_nextcloud_folder

        xml = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response><d:href></d:href></d:response></d:multistatus>'
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
        ):
            self._nc_settings(mock_settings)
            mock_settings.workdir = str(tmp_path)
            count = _scan_nextcloud_folder("Scans", {}, False)
        assert count == 0

    def test_webdav_response_with_no_href_element(self, tmp_path):
        """WebDAV response elements without d:href should be skipped."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        xml = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response><d:propstat></d:propstat></d:response></d:multistatus>'
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
        ):
            self._dav_settings(mock_settings, tmp_path)
            count = _scan_webdav_folder("/Inbox", {}, False)
        assert count == 0

    def test_webdav_response_with_empty_href_text(self, tmp_path):
        """WebDAV response elements with empty d:href text should be skipped."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        xml = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response><d:href></d:href></d:response></d:multistatus>'
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
        ):
            self._dav_settings(mock_settings, tmp_path)
            count = _scan_webdav_folder("/Inbox", {}, False)
        assert count == 0

    def test_nextcloud_download_failure_no_partial_file(self, tmp_path):
        """When Nextcloud download fails but no partial file created, skip gracefully."""
        from app.tasks.watch_folder_tasks import _scan_nextcloud_folder

        xml = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response><d:href>/remote.php/webdav/Scans/nopart.pdf</d:href></d:response></d:multistatus>'
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.raise_for_status.side_effect = Exception("network error")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
            patch("requests.get", return_value=dl_resp),
        ):
            self._nc_settings(mock_settings)
            mock_settings.workdir = str(tmp_path)
            count = _scan_nextcloud_folder("Scans", cache, False)
        assert count == 0

    def test_webdav_download_failure_no_partial_file(self, tmp_path):
        """When WebDAV download fails but no partial file exists, skip gracefully."""
        from app.tasks.watch_folder_tasks import _scan_webdav_folder

        xml = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response><d:href>/dav/Inbox/nopart.pdf</d:href></d:response></d:multistatus>'
        propfind_resp = MagicMock()
        propfind_resp.text = xml
        propfind_resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.raise_for_status.side_effect = Exception("network error")

        cache: dict = {}
        with (
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
            patch("requests.request", return_value=propfind_resp),
            patch("requests.get", return_value=dl_resp),
        ):
            self._dav_settings(mock_settings, tmp_path)
            count = _scan_webdav_folder("/Inbox", cache, False)
        assert count == 0


@pytest.mark.unit
class TestS3DownloadFailureNoPartialFile:
    """Test S3 download failure where no partial file exists."""

    def test_s3_download_failure_no_partial_file(self, tmp_path):
        """When S3 ClientError occurs before file is created, skip gracefully."""
        from botocore.exceptions import ClientError

        from app.tasks.watch_folder_tasks import _scan_s3_prefix

        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"Contents": [{"Key": "inbox/nopart.pdf"}]}]
        mock_s3.download_file.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject"
        )

        cache: dict = {}
        with (
            patch("boto3.client", return_value=mock_s3),
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.s3_bucket_name = "mybucket"
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_access_key_id = "key"
            mock_settings.aws_secret_access_key = "secret"  # noqa: S105
            mock_settings.workdir = str(tmp_path)
            count = _scan_s3_prefix("inbox/", cache, False)
        assert count == 0


# ---------------------------------------------------------------------------
# Tests for multi-tenant watch folder integration polling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIsSafeWatchPath:
    """Tests for _is_safe_watch_path path traversal security."""

    def test_absolute_path_is_safe(self):
        from app.tasks.watch_folder_tasks import _is_safe_watch_path

        assert _is_safe_watch_path("/data/watch") is True

    def test_empty_path_is_unsafe(self):
        from app.tasks.watch_folder_tasks import _is_safe_watch_path

        assert _is_safe_watch_path("") is False

    def test_relative_path_is_unsafe(self):
        from app.tasks.watch_folder_tasks import _is_safe_watch_path

        assert _is_safe_watch_path("relative/path") is False

    def test_traversal_path_is_unsafe(self):
        from app.tasks.watch_folder_tasks import _is_safe_watch_path

        assert _is_safe_watch_path("/data/../etc/passwd") is False

    def test_double_dot_component_is_unsafe(self):
        from app.tasks.watch_folder_tasks import _is_safe_watch_path

        assert _is_safe_watch_path("/data/watch/../../secret") is False

    def test_none_path_is_unsafe(self):
        from app.tasks.watch_folder_tasks import _is_safe_watch_path

        assert _is_safe_watch_path(None) is False


@pytest.mark.unit
class TestEnqueueFileOwnerIdPassthrough:
    """Test that _enqueue_file forwards owner_id to downstream tasks."""

    def test_pdf_forwards_owner_id(self):
        from app.tasks.watch_folder_tasks import _enqueue_file

        with (
            patch("app.tasks.watch_folder_tasks.convert_to_pdf") as mock_conv,
            patch("app.tasks.watch_folder_tasks.process_document") as mock_proc,
        ):
            _enqueue_file("/tmp/report.pdf", owner_id="user-123")
        mock_proc.delay.assert_called_once_with("/tmp/report.pdf", owner_id="user-123")
        mock_conv.delay.assert_not_called()

    def test_non_pdf_forwards_owner_id(self):
        from app.tasks.watch_folder_tasks import _enqueue_file

        with (
            patch("app.tasks.watch_folder_tasks.convert_to_pdf") as mock_conv,
            patch("app.tasks.watch_folder_tasks.process_document") as mock_proc,
        ):
            _enqueue_file("/tmp/doc.docx", owner_id="user-456")
        mock_conv.delay.assert_called_once_with("/tmp/doc.docx", owner_id="user-456")
        mock_proc.delay.assert_not_called()


@pytest.mark.unit
class TestScanUserWatchFolder:
    """Tests for _scan_user_watch_folder."""

    def test_scans_and_attributes_files_to_owner(self, tmp_path):
        from app.tasks.watch_folder_tasks import _scan_user_watch_folder

        # Create a test file
        (tmp_path / "test.pdf").write_bytes(b"%PDF-1.4")

        cache: dict[str, str] = {}
        with (
            patch("app.tasks.watch_folder_tasks._enqueue_file") as mock_enqueue,
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path / "workdir")
            os.makedirs(mock_settings.workdir, exist_ok=True)
            count = _scan_user_watch_folder(str(tmp_path), cache, False, "owner-77")

        assert count == 1
        mock_enqueue.assert_called_once()
        call_kwargs = mock_enqueue.call_args
        assert call_kwargs.kwargs.get("owner_id") == "owner-77"

    def test_skips_already_processed_files(self, tmp_path):
        from app.tasks.watch_folder_tasks import _scan_user_watch_folder

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4")
        cache = {str(test_file): datetime.now(timezone.utc).isoformat()}

        with (
            patch("app.tasks.watch_folder_tasks._enqueue_file") as mock_enqueue,
            patch("app.tasks.watch_folder_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path / "workdir")
            count = _scan_user_watch_folder(str(tmp_path), cache, False, "owner-77")

        assert count == 0
        mock_enqueue.assert_not_called()

    def test_returns_zero_for_nonexistent_dir(self):
        from app.tasks.watch_folder_tasks import _scan_user_watch_folder

        count = _scan_user_watch_folder("/nonexistent/path", {}, False, "owner-1")
        assert count == 0


@pytest.mark.unit
class TestPullUserIntegrationWatchFolders:
    """Tests for _pull_user_integration_watch_folders."""

    @patch("app.tasks.watch_folder_tasks._get_db_session")
    @patch("app.tasks.watch_folder_tasks._scan_user_watch_folder", return_value=2)
    @patch("app.tasks.watch_folder_tasks._load_cache", return_value={})
    @patch("app.tasks.watch_folder_tasks._save_cache")
    def test_polls_active_watch_folder_integrations(self, mock_save, mock_load, mock_scan, mock_session_factory):
        """Active WATCH_FOLDER integrations should be scanned."""
        from app.tasks.watch_folder_tasks import _pull_user_integration_watch_folders

        mock_integ = MagicMock()
        mock_integ.id = 20
        mock_integ.owner_id = "owner-wf"
        mock_integ.config = '{"folder_path": "/data/scans", "delete_after_process": false}'
        mock_integ.is_active = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_integ]
        mock_session_factory.return_value = mock_db

        with patch("app.tasks.watch_folder_tasks._is_safe_watch_path", return_value=True):
            result = _pull_user_integration_watch_folders()

        assert result["status"] == "ok"
        assert result["integrations_processed"] == 1
        assert result["files_enqueued"] == 2
        mock_scan.assert_called_once()

    @patch("app.tasks.watch_folder_tasks._get_db_session")
    def test_rejects_unsafe_paths(self, mock_session_factory):
        """Integrations with unsafe paths should be rejected."""
        from app.tasks.watch_folder_tasks import _pull_user_integration_watch_folders

        mock_integ = MagicMock()
        mock_integ.id = 21
        mock_integ.owner_id = "owner-bad"
        mock_integ.config = '{"folder_path": "/data/../etc/passwd"}'
        mock_integ.is_active = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_integ]
        mock_session_factory.return_value = mock_db

        with patch("app.tasks.watch_folder_tasks._is_safe_watch_path", return_value=False):
            result = _pull_user_integration_watch_folders()

        assert result["status"] == "ok"
        assert mock_integ.last_error is not None

    @patch("app.tasks.watch_folder_tasks._get_db_session")
    @patch("app.tasks.watch_folder_tasks._scan_user_watch_folder")
    @patch("app.tasks.watch_folder_tasks._load_cache", return_value={})
    @patch("app.tasks.watch_folder_tasks._save_cache")
    def test_handles_scan_failure_gracefully(self, mock_save, mock_load, mock_scan, mock_session_factory):
        """Scan failures should be recorded but not crash the loop."""
        from app.tasks.watch_folder_tasks import _pull_user_integration_watch_folders

        mock_integ = MagicMock()
        mock_integ.id = 22
        mock_integ.owner_id = "owner-err"
        mock_integ.config = '{"folder_path": "/data/broken"}'
        mock_integ.is_active = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_integ]
        mock_session_factory.return_value = mock_db

        mock_scan.side_effect = Exception("Disk error")

        with patch("app.tasks.watch_folder_tasks._is_safe_watch_path", return_value=True):
            result = _pull_user_integration_watch_folders()

        assert mock_integ.last_error is not None
        assert "Disk error" in mock_integ.last_error

    @patch("app.tasks.watch_folder_tasks._get_db_session")
    def test_handles_db_failure_gracefully(self, mock_session_factory):
        """Database failures should return error status without crashing."""
        from app.tasks.watch_folder_tasks import _pull_user_integration_watch_folders

        mock_session_factory.side_effect = Exception("DB unavailable")
        result = _pull_user_integration_watch_folders()
        assert result["status"] == "error"

    @patch("app.tasks.watch_folder_tasks._get_db_session")
    def test_skips_integration_without_folder_path(self, mock_session_factory):
        """Integrations without folder_path should be skipped."""
        from app.tasks.watch_folder_tasks import _pull_user_integration_watch_folders

        mock_integ = MagicMock()
        mock_integ.id = 23
        mock_integ.owner_id = "owner-empty"
        mock_integ.config = '{"delete_after_process": false}'
        mock_integ.is_active = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_integ]
        mock_session_factory.return_value = mock_db

        result = _pull_user_integration_watch_folders()
        assert result["status"] == "ok"

    @patch("app.tasks.watch_folder_tasks._get_db_session")
    @patch("app.tasks.watch_folder_tasks._load_cache", return_value={})
    @patch("app.tasks.watch_folder_tasks._save_cache")
    def test_dispatches_s3_source_type(self, mock_save, mock_load, mock_session_factory):
        """WATCH_FOLDER with source_type 's3' should dispatch to _scan_user_s3_folder."""
        from app.tasks.watch_folder_tasks import (
            _USER_WF_CLOUD_HANDLERS,
            _pull_user_integration_watch_folders,
        )

        mock_integ = MagicMock()
        mock_integ.id = 30
        mock_integ.owner_id = "owner-s3"
        mock_integ.config = (
            '{"source_type": "s3", "bucket": "test-bucket", "prefix": "inbox/", "delete_after_process": false}'
        )
        mock_integ.is_active = True
        mock_integ.credentials = "encrypted-s3-creds"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_integ]
        mock_session_factory.return_value = mock_db

        mock_s3_handler = MagicMock(return_value=3)
        original_handler = _USER_WF_CLOUD_HANDLERS.get("s3")
        _USER_WF_CLOUD_HANDLERS["s3"] = mock_s3_handler
        try:
            with patch(
                "app.utils.encryption.decrypt_value",
                return_value='{"access_key_id": "AKI", "secret_access_key": "SK"}',
            ):
                result = _pull_user_integration_watch_folders()

            assert result["status"] == "ok"
            assert result["files_enqueued"] == 3
            mock_s3_handler.assert_called_once()
            args = mock_s3_handler.call_args
            assert args[0][0]["source_type"] == "s3"
            assert args[0][4] == "owner-s3"
        finally:
            if original_handler is not None:
                _USER_WF_CLOUD_HANDLERS["s3"] = original_handler

    @patch("app.tasks.watch_folder_tasks._get_db_session")
    @patch("app.tasks.watch_folder_tasks._load_cache", return_value={})
    @patch("app.tasks.watch_folder_tasks._save_cache")
    def test_dispatches_dropbox_source_type(self, mock_save, mock_load, mock_session_factory):
        """WATCH_FOLDER with source_type 'dropbox' should dispatch to _scan_user_dropbox_folder."""
        from app.tasks.watch_folder_tasks import (
            _USER_WF_CLOUD_HANDLERS,
            _pull_user_integration_watch_folders,
        )

        mock_integ = MagicMock()
        mock_integ.id = 31
        mock_integ.owner_id = "owner-dbx"
        mock_integ.config = '{"source_type": "dropbox", "folder_path": "/Inbox", "delete_after_process": false}'
        mock_integ.is_active = True
        mock_integ.credentials = "encrypted-dbx-creds"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_integ]
        mock_session_factory.return_value = mock_db

        mock_dbx_handler = MagicMock(return_value=5)
        original_handler = _USER_WF_CLOUD_HANDLERS.get("dropbox")
        _USER_WF_CLOUD_HANDLERS["dropbox"] = mock_dbx_handler
        try:
            with patch(
                "app.utils.encryption.decrypt_value",
                return_value='{"refresh_token": "tok", "app_key": "ak", "app_secret": "as"}',
            ):
                result = _pull_user_integration_watch_folders()

            assert result["status"] == "ok"
            assert result["files_enqueued"] == 5
            mock_dbx_handler.assert_called_once()
            args = mock_dbx_handler.call_args
            assert args[0][0]["source_type"] == "dropbox"
            assert args[0][4] == "owner-dbx"
        finally:
            if original_handler is not None:
                _USER_WF_CLOUD_HANDLERS["dropbox"] = original_handler

    @patch("app.tasks.watch_folder_tasks._get_db_session")
    def test_unknown_source_type_skipped(self, mock_session_factory):
        """Unknown source_type should be skipped gracefully."""
        from app.tasks.watch_folder_tasks import _pull_user_integration_watch_folders

        mock_integ = MagicMock()
        mock_integ.id = 32
        mock_integ.owner_id = "owner-unknown"
        mock_integ.config = '{"source_type": "unknown_provider", "delete_after_process": false}'
        mock_integ.is_active = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_integ]
        mock_session_factory.return_value = mock_db

        result = _pull_user_integration_watch_folders()
        assert result["status"] == "ok"
        assert result["files_enqueued"] == 0

    @patch("app.tasks.watch_folder_tasks._get_db_session")
    @patch("app.tasks.watch_folder_tasks._scan_user_watch_folder", return_value=4)
    @patch("app.tasks.watch_folder_tasks._load_cache", return_value={})
    @patch("app.tasks.watch_folder_tasks._save_cache")
    def test_local_source_type_uses_local_scanner(self, mock_save, mock_load, mock_scan_local, mock_session_factory):
        """Explicit source_type 'local' should use the local filesystem scanner."""
        from app.tasks.watch_folder_tasks import _pull_user_integration_watch_folders

        mock_integ = MagicMock()
        mock_integ.id = 33
        mock_integ.owner_id = "owner-local"
        mock_integ.config = '{"source_type": "local", "folder_path": "/data/scans", "delete_after_process": false}'
        mock_integ.is_active = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_integ]
        mock_session_factory.return_value = mock_db

        result = _pull_user_integration_watch_folders()
        assert result["status"] == "ok"
        assert result["files_enqueued"] == 4
        mock_scan_local.assert_called_once()
        assert mock_scan_local.call_args[0][0] == "/data/scans"
        assert mock_scan_local.call_args[0][3] == "owner-local"


@pytest.mark.unit
class TestScanAllWatchFoldersIncludesUserIntegrations:
    """Test that scan_all_watch_folders calls _pull_user_integration_watch_folders."""

    def test_includes_user_watch_folders(self):
        from app.tasks.watch_folder_tasks import scan_all_watch_folders

        with (
            patch("app.tasks.watch_folder_tasks._acquire_lock", return_value=True),
            patch("app.tasks.watch_folder_tasks._release_lock"),
            patch("app.tasks.watch_folder_tasks.scan_local_watch_folders", return_value={"status": "ok"}),
            patch("app.tasks.watch_folder_tasks.scan_ftp_watch_folder", return_value={"status": "skipped"}),
            patch("app.tasks.watch_folder_tasks.scan_sftp_watch_folder", return_value={"status": "skipped"}),
            patch("app.tasks.watch_folder_tasks.scan_dropbox_watch_folder", return_value={"status": "skipped"}),
            patch("app.tasks.watch_folder_tasks.scan_google_drive_watch_folder", return_value={"status": "skipped"}),
            patch("app.tasks.watch_folder_tasks.scan_onedrive_watch_folder", return_value={"status": "skipped"}),
            patch("app.tasks.watch_folder_tasks.scan_nextcloud_watch_folder", return_value={"status": "skipped"}),
            patch("app.tasks.watch_folder_tasks.scan_s3_watch_folder", return_value={"status": "skipped"}),
            patch("app.tasks.watch_folder_tasks.scan_webdav_watch_folder", return_value={"status": "skipped"}),
            patch(
                "app.tasks.watch_folder_tasks._pull_user_integration_watch_folders",
                return_value={"status": "ok", "integrations_processed": 1, "files_enqueued": 3},
            ) as mock_pull,
        ):
            result = scan_all_watch_folders()

        mock_pull.assert_called_once()
        assert result["results"]["user_watch_folders"]["files_enqueued"] == 3
