"""
Tests targeting uncovered lines in:
- app/tasks/upload_to_s3.py   (lines 43-46, 49-52, 67-71, 78, 99-109)
- app/tasks/upload_to_sftp.py  (lines 39-42, 62-63, 80-88, 103, 107-111, 128-132, 146-158)
- app/utils/notification.py    (lines 74-118)
- app/tasks/send_to_all.py     (lines 50, 76, 85-105, 122-146, 210-212, 228-230)
"""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.upload_to_s3 import upload_to_s3
from app.tasks.upload_to_sftp import upload_to_sftp
from app.tasks.send_to_all import send_to_all_destinations

_TEST_CRED = "test_secret"  # noqa: S105


# ---------------------------------------------------------------------------
# S3 upload tests
# ---------------------------------------------------------------------------


class TestUploadToS3Coverage:
    """Tests for upload_to_s3 covering uncovered lines."""

    @pytest.mark.unit
    def test_no_bucket_name_raises(self, tmp_path):
        """Lines 42-46: ValueError when s3_bucket_name is empty."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        with (
            patch("app.tasks.upload_to_s3.settings") as ms,
            patch("app.tasks.upload_to_s3.log_task_progress"),
        ):
            ms.s3_bucket_name = ""
            ms.aws_access_key_id = "key"
            ms.aws_secret_access_key = _TEST_CRED

            with pytest.raises(ValueError, match="bucket name"):
                upload_to_s3.apply(args=[str(f)], kwargs={"file_id": 1}).get()

    @pytest.mark.unit
    def test_no_aws_credentials_raises(self, tmp_path):
        """Lines 48-52: ValueError when AWS credentials missing."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        with (
            patch("app.tasks.upload_to_s3.settings") as ms,
            patch("app.tasks.upload_to_s3.log_task_progress"),
        ):
            ms.s3_bucket_name = "my-bucket"
            ms.aws_access_key_id = ""
            ms.aws_secret_access_key = ""

            with pytest.raises(ValueError, match="credentials"):
                upload_to_s3.apply(args=[str(f)], kwargs={"file_id": 1}).get()

    @pytest.mark.unit
    def test_folder_prefix_appends_slash(self, tmp_path):
        """Lines 66-69: folder prefix without trailing slash gets one added."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        mock_s3 = MagicMock()
        with (
            patch("app.tasks.upload_to_s3.settings") as ms,
            patch("app.tasks.upload_to_s3.boto3") as mock_boto3,
            patch("app.tasks.upload_to_s3.log_task_progress"),
        ):
            ms.s3_bucket_name = "my-bucket"
            ms.aws_access_key_id = "key"
            ms.aws_secret_access_key = _TEST_CRED
            ms.aws_region = "us-east-1"
            ms.s3_folder_prefix = "docs"  # no trailing slash
            ms.s3_storage_class = "STANDARD"
            ms.s3_acl = ""
            mock_boto3.client.return_value = mock_s3

            result = upload_to_s3.apply(args=[str(f)], kwargs={"file_id": 1}).get()

        uploaded_key = mock_s3.upload_file.call_args[0][2]
        assert uploaded_key == "docs/test.pdf"
        assert result["status"] == "Completed"

    @pytest.mark.unit
    def test_s3_key_without_prefix(self, tmp_path):
        """Line 71: s3_key = filename when no folder prefix."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        mock_s3 = MagicMock()
        with (
            patch("app.tasks.upload_to_s3.settings") as ms,
            patch("app.tasks.upload_to_s3.boto3") as mock_boto3,
            patch("app.tasks.upload_to_s3.log_task_progress"),
        ):
            ms.s3_bucket_name = "my-bucket"
            ms.aws_access_key_id = "key"
            ms.aws_secret_access_key = _TEST_CRED
            ms.aws_region = "us-east-1"
            ms.s3_folder_prefix = ""
            ms.s3_storage_class = "STANDARD"
            ms.s3_acl = ""
            mock_boto3.client.return_value = mock_s3

            result = upload_to_s3.apply(args=[str(f)], kwargs={"file_id": 1}).get()

        assert mock_s3.upload_file.call_args[0][2] == "test.pdf"
        assert result["s3_key"] == "test.pdf"

    @pytest.mark.unit
    def test_acl_added_when_configured(self, tmp_path):
        """Line 78: ACL added to extra_args."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        mock_s3 = MagicMock()
        with (
            patch("app.tasks.upload_to_s3.settings") as ms,
            patch("app.tasks.upload_to_s3.boto3") as mock_boto3,
            patch("app.tasks.upload_to_s3.log_task_progress"),
        ):
            ms.s3_bucket_name = "my-bucket"
            ms.aws_access_key_id = "key"
            ms.aws_secret_access_key = _TEST_CRED
            ms.aws_region = "us-east-1"
            ms.s3_folder_prefix = ""
            ms.s3_storage_class = "STANDARD"
            ms.s3_acl = "public-read"
            mock_boto3.client.return_value = mock_s3

            upload_to_s3.apply(args=[str(f)], kwargs={"file_id": 1}).get()

        extra_args = mock_s3.upload_file.call_args[1]["ExtraArgs"]
        assert extra_args["ACL"] == "public-read"

    @pytest.mark.unit
    def test_client_error_handler(self, tmp_path):
        """Lines 99-103: ClientError is caught and re-raised."""
        from botocore.exceptions import ClientError

        f = tmp_path / "test.pdf"
        f.write_text("data")

        mock_s3 = MagicMock()
        error_response = {"Error": {"Code": "NoSuchBucket", "Message": "not found"}}
        mock_s3.upload_file.side_effect = ClientError(error_response, "PutObject")

        with (
            patch("app.tasks.upload_to_s3.settings") as ms,
            patch("app.tasks.upload_to_s3.boto3") as mock_boto3,
            patch("app.tasks.upload_to_s3.log_task_progress"),
        ):
            ms.s3_bucket_name = "my-bucket"
            ms.aws_access_key_id = "key"
            ms.aws_secret_access_key = _TEST_CRED
            ms.aws_region = "us-east-1"
            ms.s3_folder_prefix = ""
            ms.s3_storage_class = "STANDARD"
            ms.s3_acl = ""
            mock_boto3.client.return_value = mock_s3

            with pytest.raises(Exception, match="Failed to upload"):
                upload_to_s3.apply(args=[str(f)], kwargs={"file_id": 1}).get()

    @pytest.mark.unit
    def test_generic_exception_handler(self, tmp_path):
        """Lines 105-109: Generic exception is caught and re-raised."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        mock_s3 = MagicMock()
        mock_s3.upload_file.side_effect = RuntimeError("network timeout")

        with (
            patch("app.tasks.upload_to_s3.settings") as ms,
            patch("app.tasks.upload_to_s3.boto3") as mock_boto3,
            patch("app.tasks.upload_to_s3.log_task_progress"),
        ):
            ms.s3_bucket_name = "my-bucket"
            ms.aws_access_key_id = "key"
            ms.aws_secret_access_key = _TEST_CRED
            ms.aws_region = "us-east-1"
            ms.s3_folder_prefix = ""
            ms.s3_storage_class = "STANDARD"
            ms.s3_acl = ""
            mock_boto3.client.return_value = mock_s3

            with pytest.raises(Exception, match="Error uploading"):
                upload_to_s3.apply(args=[str(f)], kwargs={"file_id": 1}).get()


# ---------------------------------------------------------------------------
# SFTP upload tests
# ---------------------------------------------------------------------------


class TestUploadToSftpCoverage:
    """Tests for upload_to_sftp covering uncovered lines."""

    def _sftp_settings(self, ms, password="pass", key=None, passphrase=None, disable_verify=True):
        """Helper to configure common SFTP mock settings."""
        ms.sftp_host = "host"
        ms.sftp_port = 22
        ms.sftp_username = "user"
        ms.sftp_password = password
        ms.sftp_folder = "/upload"
        ms.sftp_disable_host_key_verification = disable_verify
        ms.sftp_private_key = key
        ms.sftp_private_key_passphrase = passphrase
        ms.workdir = "/workdir"

    @pytest.mark.unit
    def test_missing_config_skips(self, tmp_path):
        """Lines 39-42: Skipped when sftp config is incomplete."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        with (
            patch("app.tasks.upload_to_sftp.settings") as ms,
            patch("app.tasks.upload_to_sftp.log_task_progress"),
        ):
            ms.sftp_host = ""
            ms.sftp_port = 22
            ms.sftp_username = ""

            result = upload_to_sftp.apply(args=[str(f)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Skipped"

    @pytest.mark.unit
    def test_system_host_keys_loaded(self, tmp_path):
        """Lines 62-63: load_system_host_keys + RejectPolicy when verification enabled."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        mock_ssh = MagicMock()
        mock_sftp_client = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp_client
        mock_sftp_client.stat.return_value = MagicMock()

        with (
            patch("app.tasks.upload_to_sftp.settings") as ms,
            patch("app.tasks.upload_to_sftp.paramiko") as mock_paramiko,
            patch("app.tasks.upload_to_sftp.log_task_progress"),
            patch("app.tasks.upload_to_sftp.sanitize_filename", return_value="test.pdf"),
            patch("app.tasks.upload_to_sftp.extract_remote_path", return_value="/upload/test.pdf"),
            patch("app.tasks.upload_to_sftp.get_unique_filename", return_value="/upload/test.pdf"),
        ):
            self._sftp_settings(ms, disable_verify=False)
            mock_paramiko.SSHClient.return_value = mock_ssh

            result = upload_to_sftp.apply(args=[str(f)], kwargs={"file_id": 1}).get()

        mock_ssh.load_system_host_keys.assert_called_once()
        mock_ssh.set_missing_host_key_policy.assert_called_once_with(mock_paramiko.RejectPolicy())
        assert result["status"] == "Completed"

    @pytest.mark.unit
    def test_key_auth_with_passphrase(self, tmp_path):
        """Lines 80-81: key_filename and passphrase in connect_kwargs."""
        f = tmp_path / "test.pdf"
        f.write_text("data")
        key_file = tmp_path / "id_rsa"
        key_file.write_text("fake-key")

        mock_ssh = MagicMock()
        mock_sftp_client = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp_client
        mock_sftp_client.stat.return_value = MagicMock()

        with (
            patch("app.tasks.upload_to_sftp.settings") as ms,
            patch("app.tasks.upload_to_sftp.paramiko") as mock_paramiko,
            patch("app.tasks.upload_to_sftp.log_task_progress"),
            patch("app.tasks.upload_to_sftp.sanitize_filename", return_value="test.pdf"),
            patch("app.tasks.upload_to_sftp.extract_remote_path", return_value="/upload/test.pdf"),
            patch("app.tasks.upload_to_sftp.get_unique_filename", return_value="/upload/test.pdf"),
        ):
            self._sftp_settings(ms, password="", key=str(key_file), passphrase="my-passphrase")
            mock_paramiko.SSHClient.return_value = mock_ssh

            result = upload_to_sftp.apply(args=[str(f)], kwargs={"file_id": 1}).get()

        connect_kwargs = mock_ssh.connect.call_args[1]
        assert connect_kwargs["key_filename"] == str(key_file)
        assert connect_kwargs["passphrase"] == "my-passphrase"
        assert result["status"] == "Completed"

    @pytest.mark.unit
    def test_password_auth(self, tmp_path):
        """Lines 82-84: password authentication branch."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        mock_ssh = MagicMock()
        mock_sftp_client = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp_client
        mock_sftp_client.stat.return_value = MagicMock()

        with (
            patch("app.tasks.upload_to_sftp.settings") as ms,
            patch("app.tasks.upload_to_sftp.paramiko") as mock_paramiko,
            patch("app.tasks.upload_to_sftp.log_task_progress"),
            patch("app.tasks.upload_to_sftp.sanitize_filename", return_value="test.pdf"),
            patch("app.tasks.upload_to_sftp.extract_remote_path", return_value="/upload/test.pdf"),
            patch("app.tasks.upload_to_sftp.get_unique_filename", return_value="/upload/test.pdf"),
        ):
            self._sftp_settings(ms, password="secret-pass")
            mock_paramiko.SSHClient.return_value = mock_ssh

            result = upload_to_sftp.apply(args=[str(f)], kwargs={"file_id": 1}).get()

        connect_kwargs = mock_ssh.connect.call_args[1]
        assert connect_kwargs["password"] == "secret-pass"
        assert "key_filename" not in connect_kwargs
        assert result["status"] == "Completed"

    @pytest.mark.unit
    def test_no_auth_method_raises(self, tmp_path):
        """Lines 86-88: raises when no key or password."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        mock_ssh = MagicMock()

        with (
            patch("app.tasks.upload_to_sftp.settings") as ms,
            patch("app.tasks.upload_to_sftp.paramiko") as mock_paramiko,
            patch("app.tasks.upload_to_sftp.log_task_progress"),
            patch("app.tasks.upload_to_sftp.sanitize_filename", return_value="test.pdf"),
        ):
            self._sftp_settings(ms, password="")
            mock_paramiko.SSHClient.return_value = mock_ssh

            with pytest.raises(Exception, match="Failed to upload"):
                upload_to_sftp.apply(args=[str(f)], kwargs={"file_id": 1}).get()

    @pytest.mark.unit
    def test_remote_path_slash_prepended(self, tmp_path):
        """Line 103: slash prepended when remote_base starts with /."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        mock_ssh = MagicMock()
        mock_sftp_client = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp_client
        mock_sftp_client.stat.return_value = MagicMock()

        with (
            patch("app.tasks.upload_to_sftp.settings") as ms,
            patch("app.tasks.upload_to_sftp.paramiko") as mock_paramiko,
            patch("app.tasks.upload_to_sftp.log_task_progress"),
            patch("app.tasks.upload_to_sftp.sanitize_filename", return_value="test.pdf"),
            patch("app.tasks.upload_to_sftp.extract_remote_path", return_value="upload/test.pdf"),
            patch("app.tasks.upload_to_sftp.get_unique_filename", side_effect=lambda p, _: p),
        ):
            self._sftp_settings(ms)
            ms.sftp_folder = "/data"  # starts with /
            mock_paramiko.SSHClient.return_value = mock_ssh

            result = upload_to_sftp.apply(args=[str(f)], kwargs={"file_id": 1}).get()

        assert result["sftp_path"].startswith("/")

    @pytest.mark.unit
    def test_remote_dir_creation(self, tmp_path):
        """Lines 107-111, 118-130: creates remote directories when they don't exist."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        mock_ssh = MagicMock()
        mock_sftp_client = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp_client

        def stat_side_effect(path):
            if path in ("/upload", "/upload/sub"):
                raise FileNotFoundError()
            return MagicMock()

        mock_sftp_client.stat.side_effect = stat_side_effect

        with (
            patch("app.tasks.upload_to_sftp.settings") as ms,
            patch("app.tasks.upload_to_sftp.paramiko") as mock_paramiko,
            patch("app.tasks.upload_to_sftp.log_task_progress"),
            patch("app.tasks.upload_to_sftp.sanitize_filename", return_value="test.pdf"),
            patch("app.tasks.upload_to_sftp.extract_remote_path", return_value="/upload/sub/test.pdf"),
            patch("app.tasks.upload_to_sftp.get_unique_filename", side_effect=lambda p, _: p),
        ):
            self._sftp_settings(ms)
            ms.sftp_folder = "/"
            mock_paramiko.SSHClient.return_value = mock_ssh

            result = upload_to_sftp.apply(args=[str(f)], kwargs={"file_id": 1}).get()

        mock_sftp_client.mkdir.assert_any_call("/upload")
        mock_sftp_client.mkdir.assert_any_call("/upload/sub")
        assert result["status"] == "Completed"

    @pytest.mark.unit
    def test_mkdir_exception_logged(self, tmp_path):
        """Lines 131-132: exception during mkdir is caught as warning."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        mock_ssh = MagicMock()
        mock_sftp_client = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp_client
        mock_sftp_client.stat.side_effect = FileNotFoundError()
        mock_sftp_client.mkdir.side_effect = PermissionError("denied")

        with (
            patch("app.tasks.upload_to_sftp.settings") as ms,
            patch("app.tasks.upload_to_sftp.paramiko") as mock_paramiko,
            patch("app.tasks.upload_to_sftp.log_task_progress"),
            patch("app.tasks.upload_to_sftp.sanitize_filename", return_value="test.pdf"),
            patch("app.tasks.upload_to_sftp.extract_remote_path", return_value="/upload/test.pdf"),
            patch("app.tasks.upload_to_sftp.get_unique_filename", side_effect=lambda p, _: p),
        ):
            self._sftp_settings(ms)
            ms.sftp_folder = "/"
            mock_paramiko.SSHClient.return_value = mock_ssh

            result = upload_to_sftp.apply(args=[str(f)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"

    @pytest.mark.unit
    def test_cleanup_on_exception(self, tmp_path):
        """Lines 146-158: connections cleaned up on exception."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        mock_ssh = MagicMock()
        mock_ssh.connect.side_effect = ConnectionRefusedError("refused")

        with (
            patch("app.tasks.upload_to_sftp.settings") as ms,
            patch("app.tasks.upload_to_sftp.paramiko") as mock_paramiko,
            patch("app.tasks.upload_to_sftp.log_task_progress"),
            patch("app.tasks.upload_to_sftp.sanitize_filename", return_value="test.pdf"),
        ):
            self._sftp_settings(ms)
            mock_paramiko.SSHClient.return_value = mock_ssh

            with pytest.raises(Exception, match="Failed to upload"):
                upload_to_sftp.apply(args=[str(f)], kwargs={"file_id": 1}).get()

        mock_ssh.close.assert_called()


# ---------------------------------------------------------------------------
# Notification tests
# ---------------------------------------------------------------------------


class TestNotificationCoverage:
    """Tests for app/utils/notification covering lines 74-118."""

    def _reset_apprise(self):
        import app.utils.notification as notif_module

        notif_module._apprise = None

    @pytest.mark.unit
    def test_send_notification_success(self):
        """Lines 74-114: full body with successful server."""
        self._reset_apprise()

        mock_server = MagicMock()
        mock_server.__str__ = lambda s: "json://localhost"
        mock_server.notify.return_value = True

        mock_apprise_instance = MagicMock()
        mock_apprise_instance.servers = [mock_server]

        with (
            patch("app.utils.notification.settings") as ms,
            patch("app.utils.notification.init_apprise", return_value=mock_apprise_instance),
        ):
            ms.notification_urls = ["json://localhost"]
            from app.utils.notification import send_notification

            result = send_notification("Test Title", "Test body", notification_type="success")

        assert result is True
        mock_server.notify.assert_called_once()

    @pytest.mark.unit
    def test_send_notification_failure_type(self):
        """Lines 83-84: notification_type='failure' maps to FAILURE."""
        self._reset_apprise()

        mock_server = MagicMock()
        mock_server.__str__ = lambda s: "json://localhost"
        mock_server.notify.return_value = True

        mock_apprise_instance = MagicMock()
        mock_apprise_instance.servers = [mock_server]

        with (
            patch("app.utils.notification.settings") as ms,
            patch("app.utils.notification.init_apprise", return_value=mock_apprise_instance),
        ):
            ms.notification_urls = ["json://localhost"]
            from app.utils.notification import send_notification

            result = send_notification("Fail", "Something failed", notification_type="failure")

        assert result is True

    @pytest.mark.unit
    def test_send_notification_warning_type(self):
        """Lines 81-82: notification_type='warn' maps to WARNING."""
        self._reset_apprise()

        mock_server = MagicMock()
        mock_server.__str__ = lambda s: "json://localhost"
        mock_server.notify.return_value = True

        mock_apprise_instance = MagicMock()
        mock_apprise_instance.servers = [mock_server]

        with (
            patch("app.utils.notification.settings") as ms,
            patch("app.utils.notification.init_apprise", return_value=mock_apprise_instance),
        ):
            ms.notification_urls = ["json://localhost"]
            from app.utils.notification import send_notification

            result = send_notification("Warn", "Warning msg", notification_type="warn")

        assert result is True

    @pytest.mark.unit
    def test_send_notification_no_servers(self):
        """Lines 87-89: returns False when servers list is empty."""
        self._reset_apprise()

        mock_apprise_instance = MagicMock()
        mock_apprise_instance.servers = []

        with (
            patch("app.utils.notification.settings") as ms,
            patch("app.utils.notification.init_apprise", return_value=mock_apprise_instance),
        ):
            ms.notification_urls = ["json://localhost"]
            from app.utils.notification import send_notification

            result = send_notification("Title", "Body")

        assert result is False

    @pytest.mark.unit
    def test_send_notification_server_fails(self):
        """Lines 102-103: server.notify returns False."""
        self._reset_apprise()

        mock_server = MagicMock()
        mock_server.__str__ = lambda s: "json://localhost"
        mock_server.notify.return_value = False

        mock_apprise_instance = MagicMock()
        mock_apprise_instance.servers = [mock_server]

        with (
            patch("app.utils.notification.settings") as ms,
            patch("app.utils.notification.init_apprise", return_value=mock_apprise_instance),
        ):
            ms.notification_urls = ["json://localhost"]
            from app.utils.notification import send_notification

            result = send_notification("Title", "Body")

        assert result is False

    @pytest.mark.unit
    def test_send_notification_server_exception(self):
        """Lines 104-105: exception from server.notify is caught."""
        self._reset_apprise()

        mock_server = MagicMock()
        mock_server.__str__ = lambda s: "json://localhost"
        mock_server.notify.side_effect = RuntimeError("boom")

        mock_apprise_instance = MagicMock()
        mock_apprise_instance.servers = [mock_server]

        with (
            patch("app.utils.notification.settings") as ms,
            patch("app.utils.notification.init_apprise", return_value=mock_apprise_instance),
        ):
            ms.notification_urls = ["json://localhost"]
            from app.utils.notification import send_notification

            result = send_notification("Title", "Body")

        assert result is False

    @pytest.mark.unit
    def test_send_notification_outer_exception(self):
        """Lines 116-118: outer exception returns False."""
        self._reset_apprise()

        with (
            patch("app.utils.notification.settings") as ms,
            patch("app.utils.notification.init_apprise", side_effect=RuntimeError("init failed")),
        ):
            ms.notification_urls = ["json://localhost"]
            from app.utils.notification import send_notification

            result = send_notification("Title", "Body")

        assert result is False

    @pytest.mark.unit
    def test_send_notification_partial_success(self):
        """Lines 91-114: one server succeeds, one fails -> True."""
        self._reset_apprise()

        good = MagicMock()
        good.__str__ = lambda s: "json://good"
        good.notify.return_value = True

        bad = MagicMock()
        bad.__str__ = lambda s: "json://bad"
        bad.notify.return_value = False

        mock_apprise_instance = MagicMock()
        mock_apprise_instance.servers = [good, bad]

        with (
            patch("app.utils.notification.settings") as ms,
            patch("app.utils.notification.init_apprise", return_value=mock_apprise_instance),
        ):
            ms.notification_urls = ["json://good", "json://bad"]
            from app.utils.notification import send_notification

            result = send_notification("Title", "Body", notification_type="info")

        assert result is True


# ---------------------------------------------------------------------------
# send_to_all_destinations tests
# ---------------------------------------------------------------------------


def _all_should_upload_false():
    """Return a list of patch context managers that set all _should_upload_* to False."""
    services = [
        "dropbox", "nextcloud", "paperless", "google_drive",
        "webdav", "ftp", "sftp", "email", "onedrive", "s3",
    ]
    return [
        patch(f"app.tasks.send_to_all._should_upload_to_{s}", return_value=False)
        for s in services
    ]


class TestSendToAllCoverage:
    """Tests for send_to_all_destinations covering uncovered lines."""

    @pytest.mark.unit
    def test_should_upload_returns_false(self, tmp_path):
        """Line 50: service skipped when should_upload returns False."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        with (
            patch("app.tasks.send_to_all.os.path.exists", return_value=True),
            patch("app.tasks.send_to_all.log_task_progress"),
            patch("app.tasks.send_to_all.settings") as ms,
            patch("app.tasks.send_to_all.get_provider_status", side_effect=Exception("unavailable")),
            patch("app.tasks.send_to_all._should_upload_to_dropbox", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_nextcloud", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_paperless", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_google_drive", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_webdav", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_ftp", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_sftp", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_email", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_onedrive", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_s3", return_value=False),
            patch("app.tasks.send_to_all.SessionLocal") as mock_session_cls,
        ):
            ms.workdir = str(tmp_path)
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = send_to_all_destinations.apply(
                args=[str(f)], kwargs={"use_validator": True, "file_id": 1}
            ).get()

        assert result["status"] == "Queued"
        assert result["tasks"] == {}

    @pytest.mark.unit
    def test_get_configured_services_from_validator(self):
        """Lines 85-105: get_configured_services_from_validator maps provider status."""
        with patch("app.tasks.send_to_all.get_provider_status") as mock_prov:
            mock_prov.return_value = {
                "Dropbox": {"configured": True},
                "NextCloud": {"configured": False},
                "S3 Storage": {"configured": True},
            }
            from app.tasks.send_to_all import get_configured_services_from_validator

            result = get_configured_services_from_validator()

        assert result["dropbox"] is True
        assert result["nextcloud"] is False
        assert result["s3"] is True

    @pytest.mark.unit
    def test_file_id_lookup_from_db(self, tmp_path):
        """Lines 136-146: file_id looked up from database when not provided."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        mock_db = MagicMock()
        mock_record = MagicMock()
        mock_record.id = 42
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        mock_session_cls = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        with ExitStack() as stack:
            stack.enter_context(patch("app.tasks.send_to_all.os.path.exists", return_value=True))
            stack.enter_context(patch("app.tasks.send_to_all.log_task_progress"))
            ms = stack.enter_context(patch("app.tasks.send_to_all.settings"))
            stack.enter_context(patch("app.tasks.send_to_all.SessionLocal", mock_session_cls))
            stack.enter_context(patch("app.tasks.send_to_all.get_provider_status", return_value={}))
            for p in _all_should_upload_false():
                stack.enter_context(p)
            ms.workdir = str(tmp_path)

            result = send_to_all_destinations.apply(
                args=[str(f)], kwargs={"use_validator": True, "file_id": None}
            ).get()

        assert result["status"] == "Queued"

    @pytest.mark.unit
    def test_file_id_lookup_no_record(self, tmp_path):
        """Lines 136-146: file_id stays None when no DB record found."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_session_cls = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        with ExitStack() as stack:
            stack.enter_context(patch("app.tasks.send_to_all.os.path.exists", return_value=True))
            stack.enter_context(patch("app.tasks.send_to_all.log_task_progress"))
            ms = stack.enter_context(patch("app.tasks.send_to_all.settings"))
            stack.enter_context(patch("app.tasks.send_to_all.SessionLocal", mock_session_cls))
            stack.enter_context(patch("app.tasks.send_to_all.get_provider_status", return_value={}))
            for p in _all_should_upload_false():
                stack.enter_context(p)
            ms.workdir = str(tmp_path)

            result = send_to_all_destinations.apply(
                args=[str(f)], kwargs={"use_validator": True, "file_id": None}
            ).get()

        assert result["status"] == "Queued"

    @pytest.mark.unit
    def test_validator_exception_falls_back(self, tmp_path):
        """Lines 210-212: validator exception causes fallback to should_upload."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        with (
            patch("app.tasks.send_to_all.os.path.exists", return_value=True),
            patch("app.tasks.send_to_all.log_task_progress"),
            patch("app.tasks.send_to_all.settings") as ms,
            patch("app.tasks.send_to_all.get_provider_status", side_effect=RuntimeError("fail")),
            patch("app.tasks.send_to_all._should_upload_to_dropbox", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_nextcloud", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_paperless", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_google_drive", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_webdav", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_ftp", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_sftp", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_email", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_onedrive", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_s3", return_value=False),
            patch("app.tasks.send_to_all.SessionLocal"),
        ):
            ms.workdir = str(tmp_path)

            result = send_to_all_destinations.apply(
                args=[str(f)], kwargs={"use_validator": True, "file_id": 1}
            ).get()

        assert result["status"] == "Queued"

    @pytest.mark.unit
    def test_queue_error(self, tmp_path):
        """Lines 245-248: exception when queueing a task is caught."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        mock_upload = MagicMock()
        mock_upload.delay.side_effect = RuntimeError("broker down")

        with ExitStack() as stack:
            stack.enter_context(patch("app.tasks.send_to_all.os.path.exists", return_value=True))
            stack.enter_context(patch("app.tasks.send_to_all.log_task_progress"))
            ms = stack.enter_context(patch("app.tasks.send_to_all.settings"))
            stack.enter_context(
                patch(
                    "app.tasks.send_to_all.get_provider_status",
                    return_value={"Dropbox": {"configured": True}},
                )
            )
            stack.enter_context(patch("app.tasks.send_to_all.upload_to_dropbox", mock_upload))
            stack.enter_context(patch("app.tasks.send_to_all.SessionLocal"))
            for p in _all_should_upload_false():
                stack.enter_context(p)
            ms.workdir = str(tmp_path)

            result = send_to_all_destinations.apply(
                args=[str(f)], kwargs={"use_validator": True, "file_id": 1}
            ).get()

        assert "dropbox_error" in result["tasks"]
        assert "broker down" in result["tasks"]["dropbox_error"]

    @pytest.mark.unit
    def test_should_upload_check_exception(self, tmp_path):
        """Lines 228-230: exception in should_upload sets is_configured=False."""
        f = tmp_path / "test.pdf"
        f.write_text("data")

        with (
            patch("app.tasks.send_to_all.os.path.exists", return_value=True),
            patch("app.tasks.send_to_all.log_task_progress"),
            patch("app.tasks.send_to_all.settings") as ms,
            patch("app.tasks.send_to_all.get_provider_status", side_effect=RuntimeError("fail")),
            patch("app.tasks.send_to_all._should_upload_to_dropbox", side_effect=RuntimeError("bad")),
            patch("app.tasks.send_to_all._should_upload_to_nextcloud", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_paperless", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_google_drive", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_webdav", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_ftp", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_sftp", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_email", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_onedrive", return_value=False),
            patch("app.tasks.send_to_all._should_upload_to_s3", return_value=False),
            patch("app.tasks.send_to_all.SessionLocal"),
        ):
            ms.workdir = str(tmp_path)

            result = send_to_all_destinations.apply(
                args=[str(f)], kwargs={"use_validator": True, "file_id": 1}
            ).get()

        assert "dropbox_task_id" not in result["tasks"]
        assert result["status"] == "Queued"
