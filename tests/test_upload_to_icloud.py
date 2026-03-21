"""Unit tests for the iCloud Drive upload task and helper functions.

Tests cover the global upload task (``upload_to_icloud``) as well as the
per-user integration handler (``_upload_icloud`` in
``upload_to_user_integration``).  All external calls to ``pyicloud`` are
mocked so tests are fast, hermetic, and free of network access.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

TASK_ID = "test-icloud-task-id"


def _write_file(path, content: bytes = b"PDF content") -> None:
    """Write *content* to *path*, creating parent dirs as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)


def _mock_pyicloud_module(mock_api):
    """Return a mock ``pyicloud`` module whose ``PyiCloudService`` returns *mock_api*."""
    mock_mod = MagicMock()
    mock_mod.PyiCloudService.return_value = mock_api
    return mock_mod


# ---------------------------------------------------------------------------
# _get_icloud_api
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetIcloudApi:
    """Tests for the _get_icloud_api helper."""

    def test_returns_authenticated_api(self):
        mock_api = MagicMock()
        mock_api.requires_2sa = False
        mock_api.requires_2fa = False

        with patch.dict("sys.modules", {"pyicloud": _mock_pyicloud_module(mock_api)}):
            from app.tasks.upload_to_icloud import _get_icloud_api

            result = _get_icloud_api("user@example.com", "secret")

        assert result is mock_api

    def test_passes_cookie_directory(self):
        mock_api = MagicMock()
        mock_api.requires_2sa = False
        mock_api.requires_2fa = False
        mock_mod = _mock_pyicloud_module(mock_api)

        with patch.dict("sys.modules", {"pyicloud": mock_mod}):
            from app.tasks.upload_to_icloud import _get_icloud_api

            _get_icloud_api("user@example.com", "secret", "/tmp/cookies")

        mock_mod.PyiCloudService.assert_called_once_with("user@example.com", "secret", cookie_directory="/tmp/cookies")

    def test_raises_on_2fa_required(self):
        mock_api = MagicMock()
        mock_api.requires_2sa = False
        mock_api.requires_2fa = True

        with patch.dict("sys.modules", {"pyicloud": _mock_pyicloud_module(mock_api)}):
            from app.tasks.upload_to_icloud import _get_icloud_api

            with pytest.raises(ValueError, match="two-factor authentication"):
                _get_icloud_api("user@example.com", "secret")

    def test_raises_on_2sa_required(self):
        mock_api = MagicMock()
        mock_api.requires_2sa = True
        mock_api.requires_2fa = False

        with patch.dict("sys.modules", {"pyicloud": _mock_pyicloud_module(mock_api)}):
            from app.tasks.upload_to_icloud import _get_icloud_api

            with pytest.raises(ValueError, match="two-factor authentication"):
                _get_icloud_api("user@example.com", "secret")


# ---------------------------------------------------------------------------
# _navigate_to_folder
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNavigateToFolder:
    """Tests for the _navigate_to_folder helper."""

    def test_empty_path_returns_root(self):
        from app.tasks.upload_to_icloud import _navigate_to_folder

        root = MagicMock()
        result = _navigate_to_folder(root, "")
        assert result is root

    def test_navigates_existing_folders(self):
        from app.tasks.upload_to_icloud import _navigate_to_folder

        # Build a mock folder tree: root -> Documents -> Uploads
        uploads_node = MagicMock()
        uploads_node.name = "Uploads"

        docs_node = MagicMock()
        docs_node.name = "Documents"
        docs_node.dir.return_value = [uploads_node]

        root = MagicMock()
        root.dir.return_value = [docs_node]

        result = _navigate_to_folder(root, "Documents/Uploads")
        assert result is uploads_node

    def test_creates_missing_folder(self):
        from app.tasks.upload_to_icloud import _navigate_to_folder

        new_folder = MagicMock()
        root = MagicMock()
        root.dir.return_value = []  # No children
        root.mkdir.return_value = new_folder

        result = _navigate_to_folder(root, "NewFolder")
        root.mkdir.assert_called_once_with("NewFolder")
        assert result is new_folder


# ---------------------------------------------------------------------------
# _upload_icloud (user integration handler)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadIcloudHandler:
    """Tests for _upload_icloud handler in upload_to_user_integration."""

    def _call(self, file_path: str, cfg: dict, creds: dict) -> dict:
        from app.tasks.upload_to_user_integration import _upload_icloud

        return _upload_icloud(file_path, cfg, creds, TASK_ID)

    def test_raises_when_credentials_missing(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="username or password"):
            self._call(fp, {}, {})

    def test_raises_when_password_missing(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="username or password"):
            self._call(fp, {}, {"username": "user@example.com"})

    def test_successful_upload(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_api = MagicMock()
        mock_api.requires_2sa = False
        mock_api.requires_2fa = False

        # drive.dir() returns nothing -> mkdir will be called
        mock_folder = MagicMock()
        mock_api.drive.dir.return_value = []
        mock_api.drive.mkdir.return_value = mock_folder

        with patch.dict("sys.modules", {"pyicloud": _mock_pyicloud_module(mock_api)}):
            result = self._call(
                fp,
                {"folder": "Documents"},
                {"username": "user@example.com", "password": "secret"},
            )

        assert result["status"] == "Completed"
        assert result["icloud_folder"] == "Documents"
        mock_folder.upload.assert_called_once()

    def test_upload_to_root_when_no_folder(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_api = MagicMock()
        mock_api.requires_2sa = False
        mock_api.requires_2fa = False

        with patch.dict("sys.modules", {"pyicloud": _mock_pyicloud_module(mock_api)}):
            result = self._call(
                fp,
                {},
                {"username": "user@example.com", "password": "secret"},
            )

        assert result["status"] == "Completed"
        assert result["icloud_folder"] == "/"
        mock_api.drive.upload.assert_called_once()


# ---------------------------------------------------------------------------
# upload_to_icloud Celery task
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadToIcloudTask:
    """Tests for the upload_to_icloud Celery task."""

    @patch("app.tasks.upload_to_icloud.log_task_progress")
    def test_raises_file_not_found(self, mock_log):
        """Task raises FileNotFoundError when the file does not exist."""
        from app.tasks.upload_to_icloud import upload_to_icloud

        upload_to_icloud.request.id = TASK_ID
        with pytest.raises(FileNotFoundError, match="File not found"):
            upload_to_icloud.__wrapped__(file_path="/nonexistent/file.pdf")

    @patch("app.tasks.upload_to_icloud.log_task_progress")
    @patch("app.tasks.upload_to_icloud.settings")
    def test_raises_when_credentials_not_configured(self, mock_settings, mock_log, tmp_path):
        """Task raises ValueError when iCloud credentials are absent."""
        from app.tasks.upload_to_icloud import upload_to_icloud

        mock_settings.icloud_username = None
        mock_settings.icloud_password = None

        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        upload_to_icloud.request.id = TASK_ID
        with pytest.raises(ValueError, match="iCloud credentials are not configured"):
            upload_to_icloud.__wrapped__(file_path=fp)

    @patch("app.tasks.upload_to_icloud.log_task_progress")
    @patch("app.tasks.upload_to_icloud.settings")
    def test_raises_when_password_not_configured(self, mock_settings, mock_log, tmp_path):
        """Task raises ValueError when iCloud password is absent."""
        from app.tasks.upload_to_icloud import upload_to_icloud

        mock_settings.icloud_username = "user@example.com"
        mock_settings.icloud_password = None

        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        upload_to_icloud.request.id = TASK_ID
        with pytest.raises(ValueError, match="iCloud credentials are not configured"):
            upload_to_icloud.__wrapped__(file_path=fp)

    @patch("app.tasks.upload_to_icloud.log_task_progress")
    @patch("app.tasks.upload_to_icloud.settings")
    def test_successful_upload_with_folder(self, mock_settings, mock_log, tmp_path):
        """Task uploads to the configured folder and returns success dict."""
        from app.tasks.upload_to_icloud import upload_to_icloud

        mock_settings.icloud_username = "user@example.com"
        mock_settings.icloud_password = "secret"  # noqa: S105
        mock_settings.icloud_folder = "Documents"
        mock_settings.icloud_cookie_directory = None

        fp = str(tmp_path / "report.pdf")
        _write_file(fp)

        mock_api = MagicMock()
        mock_api.requires_2sa = False
        mock_api.requires_2fa = False

        mock_folder = MagicMock()
        mock_api.drive.dir.return_value = []
        mock_api.drive.mkdir.return_value = mock_folder

        upload_to_icloud.request.id = TASK_ID
        with patch.dict("sys.modules", {"pyicloud": _mock_pyicloud_module(mock_api)}):
            result = upload_to_icloud.__wrapped__(file_path=fp, file_id=42)

        assert result["status"] == "Completed"
        assert result["file"] == fp
        assert result["icloud_folder"] == "Documents"
        mock_folder.upload.assert_called_once()

    @patch("app.tasks.upload_to_icloud.log_task_progress")
    @patch("app.tasks.upload_to_icloud.settings")
    def test_successful_upload_to_root_when_no_folder_configured(self, mock_settings, mock_log, tmp_path):
        """Task uploads to iCloud Drive root when ICLOUD_FOLDER is empty."""
        from app.tasks.upload_to_icloud import upload_to_icloud

        mock_settings.icloud_username = "user@example.com"
        mock_settings.icloud_password = "secret"  # noqa: S105
        mock_settings.icloud_folder = ""
        mock_settings.icloud_cookie_directory = None

        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_api = MagicMock()
        mock_api.requires_2sa = False
        mock_api.requires_2fa = False

        upload_to_icloud.request.id = TASK_ID
        with patch.dict("sys.modules", {"pyicloud": _mock_pyicloud_module(mock_api)}):
            result = upload_to_icloud.__wrapped__(file_path=fp)

        assert result["status"] == "Completed"
        assert result["icloud_folder"] == "/"
        mock_api.drive.upload.assert_called_once()

    @patch("app.tasks.upload_to_icloud.log_task_progress")
    @patch("app.tasks.upload_to_icloud.settings")
    def test_folder_override_takes_precedence_over_settings(self, mock_settings, mock_log, tmp_path):
        """folder_override replaces the value from settings.icloud_folder."""
        from app.tasks.upload_to_icloud import upload_to_icloud

        mock_settings.icloud_username = "user@example.com"
        mock_settings.icloud_password = "secret"  # noqa: S105
        mock_settings.icloud_folder = "DefaultFolder"
        mock_settings.icloud_cookie_directory = None

        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_api = MagicMock()
        mock_api.requires_2sa = False
        mock_api.requires_2fa = False

        mock_folder = MagicMock()
        mock_api.drive.dir.return_value = []
        mock_api.drive.mkdir.return_value = mock_folder

        upload_to_icloud.request.id = TASK_ID
        with patch.dict("sys.modules", {"pyicloud": _mock_pyicloud_module(mock_api)}):
            result = upload_to_icloud.__wrapped__(file_path=fp, folder_override="OverrideFolder")

        assert result["icloud_folder"] == "OverrideFolder"

    @patch("app.tasks.upload_to_icloud.log_task_progress")
    @patch("app.tasks.upload_to_icloud.settings")
    def test_exception_during_upload_raises_runtime_error(self, mock_settings, mock_log, tmp_path):
        """Any exception from pyicloud is wrapped in RuntimeError."""
        from app.tasks.upload_to_icloud import upload_to_icloud

        mock_settings.icloud_username = "user@example.com"
        mock_settings.icloud_password = "secret"  # noqa: S105
        mock_settings.icloud_folder = ""
        mock_settings.icloud_cookie_directory = None

        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_api = MagicMock()
        mock_api.requires_2sa = False
        mock_api.requires_2fa = False
        mock_api.drive.upload.side_effect = OSError("disk full")

        upload_to_icloud.request.id = TASK_ID
        with patch.dict("sys.modules", {"pyicloud": _mock_pyicloud_module(mock_api)}):
            with pytest.raises(RuntimeError, match="Error uploading"):
                upload_to_icloud.__wrapped__(file_path=fp)

    @patch("app.tasks.upload_to_icloud.log_task_progress")
    @patch("app.tasks.upload_to_icloud.settings")
    def test_cookie_directory_passed_to_api(self, mock_settings, mock_log, tmp_path):
        """Task forwards icloud_cookie_directory to _get_icloud_api."""
        from app.tasks.upload_to_icloud import upload_to_icloud

        mock_settings.icloud_username = "user@example.com"
        mock_settings.icloud_password = "secret"  # noqa: S105
        mock_settings.icloud_folder = ""
        mock_settings.icloud_cookie_directory = "/tmp/icloud_cookies"

        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_api = MagicMock()
        mock_api.requires_2sa = False
        mock_api.requires_2fa = False
        mock_mod = _mock_pyicloud_module(mock_api)

        upload_to_icloud.request.id = TASK_ID
        with patch.dict("sys.modules", {"pyicloud": mock_mod}):
            upload_to_icloud.__wrapped__(file_path=fp)

        mock_mod.PyiCloudService.assert_called_once_with(
            "user@example.com",
            "secret",
            cookie_directory="/tmp/icloud_cookies",
        )
