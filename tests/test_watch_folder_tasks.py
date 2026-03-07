"""Tests for app/tasks/watch_folder_tasks.py module."""

import os
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
