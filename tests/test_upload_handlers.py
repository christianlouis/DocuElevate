"""Unit tests for the per-type upload handler functions in upload_to_user_integration.py.

Each ``_upload_*`` helper is tested by mocking the relevant third-party library
so that tests are fast, hermetic, and free of external network calls.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

TASK_ID = "test-handler-task-id"


def _write_file(path, content: bytes = b"PDF content") -> None:
    """Write *content* to *path*, creating parent dirs as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)


# ---------------------------------------------------------------------------
# _upload_dropbox
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadDropbox:
    """Tests for _upload_dropbox handler."""

    def _call(self, file_path: str, cfg: dict, creds: dict) -> dict:
        from app.tasks.upload_to_user_integration import _upload_dropbox

        return _upload_dropbox(file_path, cfg, creds, TASK_ID)

    def test_raises_when_missing_credentials(self, tmp_path):
        """ValueError raised when app_key, app_secret, or refresh_token is missing."""
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="app_key"):
            self._call(fp, {}, {})

    def test_small_file_upload(self, tmp_path):
        """Files ≤10 MB are uploaded with files_upload."""
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp, b"x" * 100)

        mock_dbx_instance = MagicMock()
        mock_dropbox_files = MagicMock()
        mock_dropbox_files.WriteMode.overwrite = "overwrite"

        with patch.dict(
            "sys.modules",
            {
                "dropbox": MagicMock(
                    Dropbox=MagicMock(return_value=mock_dbx_instance),
                    files=mock_dropbox_files,
                )
            },
        ):
            result = self._call(
                fp,
                {"folder": "/Docs"},
                {"app_key": "key", "app_secret": "secret", "refresh_token": "rtoken"},
            )

        mock_dbx_instance.files_upload.assert_called_once()
        assert result["status"] == "Completed"
        assert result["dropbox_path"] == "/Docs/doc.pdf"

    def test_large_file_upload_uses_session(self, tmp_path):
        """Files >10 MB are uploaded with upload session (chunked)."""
        fp = str(tmp_path / "large.pdf")
        # Write 11 MB
        _write_file(fp, b"x" * (11 * 1024 * 1024))

        mock_dbx_instance = MagicMock()
        mock_session_start = MagicMock()
        mock_session_start.session_id = "session-1"
        mock_dbx_instance.files_upload_session_start.return_value = mock_session_start
        mock_dbx_instance.files_upload_session_finish.return_value = MagicMock()

        mock_files_mod = MagicMock()
        mock_files_mod.UploadSessionCursor = MagicMock(return_value=MagicMock(offset=0))
        mock_files_mod.CommitInfo = MagicMock()
        mock_files_mod.WriteMode.overwrite = "overwrite"

        with patch.dict(
            "sys.modules",
            {
                "dropbox": MagicMock(
                    Dropbox=MagicMock(return_value=mock_dbx_instance),
                    files=mock_files_mod,
                )
            },
        ):
            result = self._call(
                fp,
                {},
                {"app_key": "k", "app_secret": "s", "refresh_token": "r"},
            )

        mock_dbx_instance.files_upload_session_start.assert_called_once()
        assert result["status"] == "Completed"

    def test_default_folder_when_not_specified(self, tmp_path):
        """When no folder is configured, the default '/DocuElevate' folder is used."""
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp, b"x" * 10)

        mock_dbx_instance = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "dropbox": MagicMock(
                    Dropbox=MagicMock(return_value=mock_dbx_instance),
                    files=MagicMock(WriteMode=MagicMock(overwrite="overwrite")),
                )
            },
        ):
            result = self._call(fp, {}, {"app_key": "k", "app_secret": "s", "refresh_token": "r"})

        assert result["dropbox_path"] == "/DocuElevate/doc.pdf"


# ---------------------------------------------------------------------------
# _upload_s3
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadS3:
    """Tests for _upload_s3 handler."""

    def _call(self, file_path: str, cfg: dict, creds: dict) -> dict:
        from app.tasks.upload_to_user_integration import _upload_s3

        return _upload_s3(file_path, cfg, creds, TASK_ID)

    def test_raises_when_bucket_missing(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="bucket"):
            self._call(fp, {}, {"access_key_id": "k", "secret_access_key": "s"})

    def test_raises_when_credentials_missing(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="access_key_id"):
            self._call(fp, {"bucket": "my-bucket"}, {})

    def test_successful_upload(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_s3 = MagicMock()
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        with patch.dict("sys.modules", {"boto3": mock_boto3, "botocore.exceptions": MagicMock(ClientError=Exception)}):
            result = self._call(
                fp,
                {"bucket": "my-bucket", "region": "eu-west-1", "folder_prefix": "docs"},
                {"access_key_id": "AKIA", "secret_access_key": "secret"},
            )

        mock_s3.upload_file.assert_called_once()
        assert result["status"] == "Completed"
        assert result["s3_bucket"] == "my-bucket"
        assert result["s3_key"] == "docs/doc.pdf"

    def test_uses_endpoint_url_when_provided(self, tmp_path):
        """Custom endpoint_url is passed to boto3.client for S3-compatible stores."""
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_s3 = MagicMock()
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        with patch.dict("sys.modules", {"boto3": mock_boto3, "botocore.exceptions": MagicMock(ClientError=Exception)}):
            self._call(
                fp,
                {"bucket": "b", "endpoint_url": "https://minio.example.com"},
                {"access_key_id": "k", "secret_access_key": "s"},
            )

        call_kwargs = mock_boto3.client.call_args[1]
        assert call_kwargs.get("endpoint_url") == "https://minio.example.com"

    def test_wraps_client_error_as_runtime_error(self, tmp_path):
        """S3 ClientError is re-raised as RuntimeError."""
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        class FakeClientError(Exception):
            pass

        mock_s3 = MagicMock()
        mock_s3.upload_file.side_effect = FakeClientError("Access Denied")
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        with patch.dict(
            "sys.modules",
            {"boto3": mock_boto3, "botocore.exceptions": MagicMock(ClientError=FakeClientError)},
        ):
            with pytest.raises(RuntimeError, match="S3 upload failed"):
                self._call(fp, {"bucket": "b"}, {"access_key_id": "k", "secret_access_key": "s"})

    def test_key_without_folder_prefix(self, tmp_path):
        """When folder_prefix is empty, the S3 key is just the filename."""
        fp = str(tmp_path / "report.pdf")
        _write_file(fp)

        mock_s3 = MagicMock()
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        with patch.dict("sys.modules", {"boto3": mock_boto3, "botocore.exceptions": MagicMock(ClientError=Exception)}):
            result = self._call(fp, {"bucket": "b"}, {"access_key_id": "k", "secret_access_key": "s"})

        assert result["s3_key"] == "report.pdf"


# ---------------------------------------------------------------------------
# _upload_google_drive
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadGoogleDrive:
    """Tests for _upload_google_drive handler."""

    def _call(self, file_path: str, cfg: dict, creds: dict) -> dict:
        from app.tasks.upload_to_user_integration import _upload_google_drive

        return _upload_google_drive(file_path, cfg, creds, TASK_ID)

    def test_raises_when_no_credentials(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="OAuth credentials"):
            self._call(fp, {}, {})

    def test_oauth_upload_calls_drive_api(self, tmp_path):
        """OAuth credentials (client_id + client_secret + refresh_token) trigger OAuth flow."""
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_service = MagicMock()
        mock_service.files.return_value.create.return_value.execute.return_value = {
            "id": "gdrive-id-123",
            "webViewLink": "https://drive.google.com/file/d/gdrive-id-123",
        }

        mock_build = MagicMock(return_value=mock_service)
        mock_oauth_creds = MagicMock()

        mock_google_oauth2 = MagicMock()
        mock_google_oauth2.credentials.Credentials = MagicMock(return_value=mock_oauth_creds)
        mock_google_auth_transport = MagicMock()
        mock_google_auth_transport.requests.Request = MagicMock()
        mock_media_upload = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "googleapiclient.discovery": MagicMock(build=mock_build),
                "googleapiclient.http": MagicMock(MediaFileUpload=mock_media_upload),
                "google.oauth2.credentials": mock_google_oauth2.credentials,
                "google.auth.transport.requests": mock_google_auth_transport.requests,
                "google.oauth2.service_account": MagicMock(),
            },
        ):
            result = self._call(
                fp,
                {"folder_id": "folder-xyz"},
                {"client_id": "cid", "client_secret": "csec", "refresh_token": "rtoken"},
            )

        assert result["status"] == "Completed"
        assert result["google_drive_file_id"] == "gdrive-id-123"

    def test_service_account_upload(self, tmp_path):
        """credentials_json triggers service-account flow."""
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        sa_creds_json = json.dumps({"type": "service_account", "project_id": "myproject"})

        mock_service = MagicMock()
        mock_service.files.return_value.create.return_value.execute.return_value = {
            "id": "sa-file-id",
            "webViewLink": "https://drive.google.com/file/d/sa-file-id",
        }

        mock_sa_class = MagicMock()
        mock_sa_creds = MagicMock()
        mock_sa_class.from_service_account_info.return_value = mock_sa_creds

        mock_build = MagicMock(return_value=mock_service)
        mock_media_upload = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "googleapiclient.discovery": MagicMock(build=mock_build),
                "googleapiclient.http": MagicMock(MediaFileUpload=mock_media_upload),
                "google.oauth2.credentials": MagicMock(),
                "google.auth.transport.requests": MagicMock(),
                "google.oauth2.service_account": MagicMock(Credentials=mock_sa_class),
            },
        ):
            result = self._call(fp, {}, {"credentials_json": sa_creds_json})

        assert result["status"] == "Completed"


# ---------------------------------------------------------------------------
# _upload_webdav / _upload_nextcloud
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadWebdav:
    """Tests for _upload_webdav handler (and Nextcloud which delegates to it)."""

    def _call(self, file_path: str, cfg: dict, creds: dict) -> dict:
        from app.tasks.upload_to_user_integration import _upload_webdav

        return _upload_webdav(file_path, cfg, creds, TASK_ID)

    def test_raises_when_url_missing(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="url"):
            self._call(fp, {}, {})

    def test_successful_upload_201(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_resp = MagicMock()
        mock_resp.status_code = 201

        mock_requests = MagicMock()
        mock_requests.put.return_value = mock_resp

        with patch.dict("sys.modules", {"requests": mock_requests}):
            result = self._call(
                fp,
                {"url": "https://dav.example.com/dav/", "folder": "Files"},
                {"username": "user", "password": "pass"},
            )

        assert result["status"] == "Completed"
        mock_requests.put.assert_called_once()

    def test_raises_on_non_2xx_response(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"

        mock_requests = MagicMock()
        mock_requests.put.return_value = mock_resp

        with patch.dict("sys.modules", {"requests": mock_requests}):
            with pytest.raises(RuntimeError, match="WebDAV upload failed: 403"):
                self._call(fp, {"url": "https://dav.example.com/"}, {})

    def test_nextcloud_delegates_to_webdav(self, tmp_path):
        """_upload_nextcloud is a thin wrapper over _upload_webdav."""
        from app.tasks.upload_to_user_integration import _upload_nextcloud

        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        with patch("app.tasks.upload_to_user_integration._upload_webdav") as mock_webdav:
            mock_webdav.return_value = {"status": "Completed", "webdav_url": "https://nc.example.com/Files/doc.pdf"}
            result = _upload_nextcloud(
                fp, {"url": "https://nc.example.com"}, {"username": "u", "password": "p"}, TASK_ID
            )

        mock_webdav.assert_called_once_with(
            fp, {"url": "https://nc.example.com"}, {"username": "u", "password": "p"}, TASK_ID
        )
        assert result["status"] == "Completed"


# ---------------------------------------------------------------------------
# _upload_ftp
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadFtp:
    """Tests for _upload_ftp handler."""

    def _call(self, file_path: str, cfg: dict, creds: dict) -> dict:
        from app.tasks.upload_to_user_integration import _upload_ftp

        return _upload_ftp(file_path, cfg, creds, TASK_ID)

    def test_raises_when_host_missing(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="host"):
            self._call(fp, {}, {"password": "pass"})

    def test_tls_upload(self, tmp_path):
        """use_tls=True uses FTP_TLS."""
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_ftp_tls = MagicMock()
        mock_ftplib = MagicMock()
        mock_ftplib.FTP_TLS.return_value = mock_ftp_tls
        mock_ftplib.error_perm = Exception

        with patch.dict("sys.modules", {"ftplib": mock_ftplib}):
            with patch("app.tasks.upload_to_user_integration.ftplib", mock_ftplib):
                result = self._call(
                    fp,
                    {"host": "ftp.example.com", "port": 21, "folder": "/docs", "use_tls": True},
                    {"password": "pass"},
                )

        mock_ftplib.FTP_TLS.assert_called_once()
        assert result["status"] == "Completed"

    def test_plaintext_ftp_upload(self, tmp_path):
        """use_tls=False uses plain FTP."""
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_ftp = MagicMock()
        mock_ftplib = MagicMock()
        mock_ftplib.FTP.return_value = mock_ftp
        mock_ftplib.error_perm = Exception

        with patch("app.tasks.upload_to_user_integration.ftplib", mock_ftplib):
            result = self._call(
                fp,
                {"host": "ftp.example.com", "use_tls": False},
                {"password": "pass"},
            )

        mock_ftplib.FTP.assert_called_once()
        assert result["status"] == "Completed"

    def test_creates_folder_if_cwd_fails(self, tmp_path):
        """When cwd raises error_perm, the handler creates the directory."""
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        class FtpPermError(Exception):
            pass

        # cwd call sequence:
        # 1. ftp.cwd("uploads")          → fails (outer try, folder_stripped="uploads")
        # 2. ftp.cwd("/uploads")          → fails (inner loop, triggers mkd)
        # 3. ftp.cwd("/uploads") after mkd → succeeds
        mock_ftp = MagicMock()
        mock_ftp.cwd.side_effect = [FtpPermError("no"), FtpPermError("no"), None]
        mock_ftplib = MagicMock()
        mock_ftplib.FTP.return_value = mock_ftp
        mock_ftplib.error_perm = FtpPermError

        with patch("app.tasks.upload_to_user_integration.ftplib", mock_ftplib):
            self._call(
                fp,
                {"host": "ftp.example.com", "folder": "/uploads", "use_tls": False},
                {"password": "p"},
            )

        mock_ftp.mkd.assert_called_with("/uploads")


# ---------------------------------------------------------------------------
# _upload_sftp
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadSftp:
    """Tests for _upload_sftp handler."""

    def _call(self, file_path: str, cfg: dict, creds: dict) -> dict:
        from app.tasks.upload_to_user_integration import _upload_sftp

        return _upload_sftp(file_path, cfg, creds, TASK_ID)

    def test_raises_when_host_missing(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="host"):
            self._call(fp, {}, {"password": "p"})

    def test_raises_when_no_auth(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="password or private_key"):
            self._call(fp, {"host": "sftp.example.com"}, {})

    def test_password_auth(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp

        mock_paramiko = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_ssh
        mock_paramiko.RejectPolicy = MagicMock

        with patch.dict("sys.modules", {"paramiko": mock_paramiko}):
            result = self._call(
                fp,
                {"host": "sftp.example.com", "username": "user", "folder": "/uploads"},
                {"password": "pass"},
            )

        mock_sftp.put.assert_called_once()
        assert result["status"] == "Completed"
        assert result["sftp_host"] == "sftp.example.com"

    def test_private_key_auth(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        mock_pkey = MagicMock()

        mock_paramiko = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_ssh
        mock_paramiko.RSAKey.from_private_key.return_value = mock_pkey
        mock_paramiko.RejectPolicy = MagicMock

        with patch.dict("sys.modules", {"paramiko": mock_paramiko}):
            result = self._call(
                fp,
                {"host": "sftp.example.com", "username": "user"},
                {"private_key": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"},
            )

        mock_paramiko.RSAKey.from_private_key.assert_called_once()
        assert result["status"] == "Completed"


# ---------------------------------------------------------------------------
# _upload_paperless
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadPaperless:
    """Tests for _upload_paperless handler."""

    def _call(self, file_path: str, cfg: dict, creds: dict) -> dict:
        from app.tasks.upload_to_user_integration import _upload_paperless

        return _upload_paperless(file_path, cfg, creds, TASK_ID)

    def test_raises_when_host_missing(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="host"):
            self._call(fp, {}, {"api_token": "tok"})

    def test_raises_when_api_token_missing(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="api_token"):
            self._call(fp, {"host": "https://paperless.example.com"}, {})

    def test_successful_upload_polls_to_success(self, tmp_path):
        """Document is uploaded and task polling returns SUCCESS."""
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        # POST response
        mock_post_resp = MagicMock()
        mock_post_resp.text = '"task-uuid-123"'

        # Poll response showing SUCCESS
        mock_poll_resp = MagicMock()
        mock_poll_resp.json.return_value = [{"status": "SUCCESS", "related_document": 42}]

        mock_requests = MagicMock()
        mock_requests.post.return_value = mock_post_resp
        mock_requests.get.return_value = mock_poll_resp

        with patch.dict("sys.modules", {"requests": mock_requests}):
            with patch("time.sleep", return_value=None):
                result = self._call(
                    fp,
                    {"host": "https://paperless.example.com"},
                    {"api_token": "tok-abc"},
                )

        assert result["status"] == "Completed"
        assert result["paperless_document_id"] == 42

    def test_raises_when_paperless_task_fails(self, tmp_path):
        """RuntimeError is raised when Paperless processing status is FAILURE."""
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_post_resp = MagicMock()
        mock_post_resp.text = '"task-uuid-999"'

        mock_poll_resp = MagicMock()
        mock_poll_resp.json.return_value = [{"status": "FAILURE", "result": "OCR failed"}]

        mock_requests = MagicMock()
        mock_requests.post.return_value = mock_post_resp
        mock_requests.get.return_value = mock_poll_resp

        with patch.dict("sys.modules", {"requests": mock_requests}):
            with patch("time.sleep", return_value=None):
                with pytest.raises(RuntimeError, match="Paperless processing failed"):
                    self._call(
                        fp,
                        {"host": "https://paperless.example.com"},
                        {"api_token": "tok"},
                    )


# ---------------------------------------------------------------------------
# _upload_email
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadEmail:
    """Tests for _upload_email handler."""

    def _call(self, file_path: str, cfg: dict, creds: dict) -> dict:
        from app.tasks.upload_to_user_integration import _upload_email

        return _upload_email(file_path, cfg, creds, TASK_ID)

    def test_raises_when_host_or_recipient_missing(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="host or recipient"):
            self._call(fp, {}, {})

    def test_tls_email_sent(self, tmp_path):
        """use_tls=True invokes starttls() with ssl context."""
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_smtp_instance = MagicMock()
        mock_smtp_class = MagicMock(return_value=mock_smtp_instance)
        mock_smtp_instance.__enter__ = MagicMock(return_value=mock_smtp_instance)
        mock_smtp_instance.__exit__ = MagicMock(return_value=False)

        mock_ssl_ctx = MagicMock()
        mock_ssl = MagicMock()
        mock_ssl.create_default_context.return_value = mock_ssl_ctx

        with patch("smtplib.SMTP", mock_smtp_class):
            with patch("ssl.create_default_context", return_value=mock_ssl_ctx):
                result = self._call(
                    fp,
                    {
                        "host": "smtp.example.com",
                        "port": 587,
                        "username": "u@ex.com",
                        "recipient": "r@ex.com",
                        "use_tls": True,
                    },
                    {"password": "pass"},
                )

        mock_smtp_instance.starttls.assert_called_once_with(context=mock_ssl_ctx)
        assert result["status"] == "Completed"
        assert result["recipient"] == "r@ex.com"

    def test_plaintext_smtp_skips_starttls(self, tmp_path):
        """use_tls=False sends without starttls()."""
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_smtp_instance = MagicMock()
        mock_smtp_class = MagicMock(return_value=mock_smtp_instance)
        mock_smtp_instance.__enter__ = MagicMock(return_value=mock_smtp_instance)
        mock_smtp_instance.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", mock_smtp_class):
            result = self._call(
                fp,
                {"host": "smtp.example.com", "recipient": "r@ex.com", "use_tls": False},
                {},
            )

        mock_smtp_instance.starttls.assert_not_called()
        assert result["status"] == "Completed"


# ---------------------------------------------------------------------------
# _upload_rclone
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadRclone:
    """Tests for _upload_rclone handler."""

    def _call(self, file_path: str, cfg: dict, creds: dict) -> dict:
        from app.tasks.upload_to_user_integration import _upload_rclone

        return _upload_rclone(file_path, cfg, creds, TASK_ID)

    def test_raises_when_remote_missing(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="remote"):
            self._call(fp, {}, {"rclone_conf": "[myremote]\ntype = s3\n"})

    def test_raises_when_conf_missing(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="rclone_conf"):
            self._call(fp, {"remote": "myremote:"}, {})

    def test_raises_when_remote_unsafe(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="unsafe characters"):
            self._call(fp, {"remote": "my;remote:"}, {"rclone_conf": "[x]\ntype=s3\n"})

    def test_raises_when_folder_unsafe(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="unsafe characters"):
            self._call(fp, {"remote": "myremote:", "folder": "docs;rm -rf /"}, {"rclone_conf": "[x]\ntype=s3\n"})

    def test_successful_rclone_copy(self, tmp_path):
        """rclone process is called with correct arguments and temp config file."""
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("app.tasks.upload_to_user_integration.subprocess.run", return_value=mock_result) as mock_run:
            result = self._call(
                fp,
                {"remote": "myremote:", "folder": "docs"},
                {"rclone_conf": "[myremote]\ntype = s3\n"},
            )

        assert result["status"] == "Completed"
        # Verify subprocess.run was called with rclone command
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "rclone"
        assert cmd[1] == "copyto"
        # SECURITY: Verify `--` end-of-options separator is present and precedes
        # the file path and destination to prevent option/argument injection.
        assert "--" in cmd
        fp_index = next(i for i, v in enumerate(cmd) if v == fp)
        assert cmd.index("--") < fp_index

    def test_raises_on_rclone_nonzero_exit(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "rclone: command not found"

        with patch("app.tasks.upload_to_user_integration.subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="rclone exited 1"):
                self._call(fp, {"remote": "myremote:"}, {"rclone_conf": "[myremote]\ntype=s3\n"})


# ---------------------------------------------------------------------------
# _upload_onedrive
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadOneDrive:
    """Tests for _upload_onedrive handler."""

    def _call(self, file_path: str, cfg: dict, creds: dict) -> dict:
        from app.tasks.upload_to_user_integration import _upload_onedrive

        return _upload_onedrive(file_path, cfg, creds, TASK_ID)

    def test_raises_when_client_credentials_missing(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)
        with pytest.raises(ValueError, match="client_id or client_secret"):
            self._call(fp, {}, {})

    def test_raises_when_token_acquisition_fails(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp)

        mock_msal_app = MagicMock()
        mock_msal_app.acquire_token_for_client.return_value = {
            "error": "invalid_client",
            "error_description": "AADSTS70011",
        }
        mock_msal = MagicMock()
        mock_msal.ConfidentialClientApplication.return_value = mock_msal_app

        with patch.dict("sys.modules", {"msal": mock_msal, "requests": MagicMock()}):
            with pytest.raises(ValueError, match="token acquisition failed"):
                self._call(fp, {}, {"client_id": "cid", "client_secret": "csec"})

    def test_successful_upload_with_refresh_token(self, tmp_path):
        fp = str(tmp_path / "doc.pdf")
        _write_file(fp, b"x" * 100)

        mock_msal_app = MagicMock()
        mock_msal_app.acquire_token_by_refresh_token.return_value = {"access_token": "tok-abc"}
        mock_msal = MagicMock()
        mock_msal.ConfidentialClientApplication.return_value = mock_msal_app

        # Mock POST (create upload session) and PUT (chunk upload)
        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = {"uploadUrl": "https://upload.example.com/session"}
        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 201

        mock_requests = MagicMock()
        mock_requests.post.return_value = mock_post_resp
        mock_requests.put.return_value = mock_put_resp

        with patch.dict("sys.modules", {"msal": mock_msal, "requests": mock_requests}):
            result = self._call(
                fp,
                {"folder_path": "Documents/DocuElevate", "tenant_id": "my-tenant"},
                {"client_id": "cid", "client_secret": "csec", "refresh_token": "rtoken"},
            )

        assert result["status"] == "Completed"


# ---------------------------------------------------------------------------
# finalize_document_storage - uncovered branches
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFinalizeDocumentStorageUncoveredBranches:
    """Cover branches in finalize_document_storage not exercised by the main test class."""

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_user_destinations")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_user_destination_count", return_value=0)
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_resolves_owner_id_when_file_id_none(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_get_dest_count,
        mock_send_all,
        mock_send_user,
        mock_notify,
        tmp_path,
    ):
        """When file_id is None, the task looks up the FileRecord by local_filename."""
        from app.tasks.finalize_document_storage import finalize_document_storage

        processed_file = str(tmp_path / "processed" / "doc.pdf")
        original_file = str(tmp_path / "original" / "orig.pdf")
        os.makedirs(os.path.dirname(processed_file), exist_ok=True)
        os.makedirs(os.path.dirname(original_file), exist_ok=True)
        _write_file(processed_file)
        _write_file(original_file)

        mock_file_record = MagicMock()
        mock_file_record.id = 77
        mock_file_record.owner_id = "owner@example.com"

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file_record

        mock_get_services.return_value = {}

        finalize_document_storage.request.id = "test-task-id"
        finalize_document_storage.__wrapped__(
            original_file=original_file,
            processed_file=processed_file,
            metadata={},
            file_id=None,
        )

        # The function should have queried the DB for the file record
        mock_db.query.assert_called()

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_user_destinations")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_user_destination_count")
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_routes_to_global_when_count_query_raises(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_get_dest_count,
        mock_send_all,
        mock_send_user,
        mock_notify,
        tmp_path,
    ):
        """When get_user_destination_count raises, falls back to global routing."""
        from app.tasks.finalize_document_storage import finalize_document_storage

        processed_file = str(tmp_path / "processed2" / "doc.pdf")
        original_file = str(tmp_path / "original2" / "orig.pdf")
        os.makedirs(os.path.dirname(processed_file), exist_ok=True)
        os.makedirs(os.path.dirname(original_file), exist_ok=True)
        _write_file(processed_file)
        _write_file(original_file)

        mock_file_record = MagicMock()
        mock_file_record.id = 88
        mock_file_record.owner_id = "owner@example.com"

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file_record

        mock_get_services.return_value = {}
        mock_get_dest_count.side_effect = Exception("DB connection error")

        finalize_document_storage.request.id = "test-task-id"
        finalize_document_storage.__wrapped__(
            original_file=original_file,
            processed_file=processed_file,
            metadata={},
            file_id=88,
        )

        # Falls back to global since count raised
        mock_send_all.delay.assert_called_once()
        mock_send_user.delay.assert_not_called()
