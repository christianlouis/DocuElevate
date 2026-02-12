"""Comprehensive tests for app/tasks/upload_to_email.py to improve coverage."""

import json
import os
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest


@pytest.mark.unit
class TestGetEmailTemplate:
    """Tests for get_email_template function."""

    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.Environment")
    def test_loads_custom_template_from_workdir(self, mock_env_cls, mock_exists, mock_settings):
        """Test loading custom template from workdir."""
        from app.tasks.upload_to_email import get_email_template

        mock_settings.workdir = "/tmp/workdir"
        mock_exists.return_value = True
        mock_env = MagicMock()
        mock_template = MagicMock()
        mock_env.get_template.return_value = mock_template
        mock_env_cls.return_value = mock_env

        result = get_email_template("default.html")
        assert result == mock_template

    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.Environment")
    def test_falls_back_to_builtin_template(self, mock_env_cls, mock_exists, mock_settings):
        """Test fallback to built-in template when custom not found."""
        from app.tasks.upload_to_email import get_email_template

        mock_settings.workdir = "/tmp/workdir"
        # First call for workdir path returns False, second for app template returns True
        mock_exists.side_effect = [False, True]
        mock_env = MagicMock()
        mock_template = MagicMock()
        mock_env.get_template.return_value = mock_template
        mock_env_cls.return_value = mock_env

        result = get_email_template("default.html")
        assert result == mock_template

    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.Environment")
    def test_raises_when_no_template_found(self, mock_env_cls, mock_exists, mock_settings):
        """Test raises ValueError when no template can be loaded."""
        from app.tasks.upload_to_email import get_email_template

        mock_settings.workdir = "/tmp/workdir"
        mock_exists.return_value = False
        mock_env = MagicMock()
        mock_env.get_template.side_effect = Exception("Template not found")
        mock_env_cls.return_value = mock_env

        with pytest.raises(ValueError, match="Could not find any valid email template"):
            get_email_template("nonexistent.html")

    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.Environment")
    def test_custom_template_failure_falls_back(self, mock_env_cls, mock_exists, mock_settings):
        """Test that failure loading custom template falls back to built-in."""
        from app.tasks.upload_to_email import get_email_template

        mock_settings.workdir = "/tmp/workdir"
        mock_exists.return_value = True
        mock_env_good = MagicMock()
        mock_template = MagicMock()
        mock_env_good.get_template.return_value = mock_template

        mock_env_bad = MagicMock()
        mock_env_bad.get_template.side_effect = Exception("Bad template")

        # First Environment call (workdir) raises, second (built-in) succeeds
        mock_env_cls.side_effect = [mock_env_bad, mock_env_good]

        result = get_email_template("default.html")
        assert result == mock_template


@pytest.mark.unit
class TestExtractMetadataFromFile:
    """Tests for extract_metadata_from_file function."""

    @patch("app.tasks.upload_to_email.os.path.exists")
    def test_returns_empty_dict_when_no_metadata_file(self, mock_exists):
        """Test returns empty dict when no metadata JSON file exists."""
        from app.tasks.upload_to_email import extract_metadata_from_file

        mock_exists.return_value = False
        result = extract_metadata_from_file("/tmp/test.pdf")
        assert result == {}

    @patch("builtins.open", mock_open(read_data='{"document_type": "invoice", "amount": 100.00}'))
    @patch("app.tasks.upload_to_email.os.path.exists")
    def test_loads_metadata_from_json_file(self, mock_exists):
        """Test loads metadata from companion JSON file."""
        from app.tasks.upload_to_email import extract_metadata_from_file

        mock_exists.return_value = True
        result = extract_metadata_from_file("/tmp/test.pdf")
        assert result["document_type"] == "invoice"
        assert result["amount"] == 100.00

    @patch("builtins.open", side_effect=Exception("Read error"))
    @patch("app.tasks.upload_to_email.os.path.exists")
    def test_returns_empty_dict_on_json_read_error(self, mock_exists, mock_file):
        """Test returns empty dict when JSON file cannot be read."""
        from app.tasks.upload_to_email import extract_metadata_from_file

        mock_exists.return_value = True
        result = extract_metadata_from_file("/tmp/test.pdf")
        assert result == {}


@pytest.mark.unit
class TestAttachLogo:
    """Tests for attach_logo function."""

    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("builtins.open", mock_open(read_data=b"\x89PNG\r\n"))
    def test_attaches_custom_logo(self, mock_exists, mock_settings):
        """Test attaches custom logo from workdir."""
        from app.tasks.upload_to_email import attach_logo

        mock_settings.workdir = "/tmp/workdir"
        mock_exists.return_value = True
        msg = MIMEMultipart()

        result = attach_logo(msg)
        assert result is True

    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email.os.path.exists")
    def test_returns_false_when_no_logo_found(self, mock_exists, mock_settings):
        """Test returns False when no logo file can be found."""
        from app.tasks.upload_to_email import attach_logo

        mock_settings.workdir = "/tmp/workdir"
        mock_exists.return_value = False
        msg = MIMEMultipart()

        result = attach_logo(msg)
        assert result is False

    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("builtins.open", side_effect=Exception("Permission denied"))
    def test_returns_false_on_error(self, mock_file, mock_exists, mock_settings):
        """Test returns False when error occurs."""
        from app.tasks.upload_to_email import attach_logo

        mock_settings.workdir = "/tmp/workdir"
        mock_exists.return_value = True
        msg = MIMEMultipart()

        result = attach_logo(msg)
        assert result is False


@pytest.mark.unit
class TestPrepareRecipients:
    """Tests for _prepare_recipients function."""

    @patch("app.tasks.upload_to_email.settings")
    def test_uses_default_recipient_when_none(self, mock_settings):
        """Test uses default recipient when no recipients provided."""
        from app.tasks.upload_to_email import _prepare_recipients

        mock_settings.email_default_recipient = "default@example.com"
        recipients, error = _prepare_recipients(None)
        assert recipients == ["default@example.com"]
        assert error is None

    @patch("app.tasks.upload_to_email.settings")
    def test_returns_error_when_no_recipients_and_no_default(self, mock_settings):
        """Test returns error when no recipients and no default configured."""
        from app.tasks.upload_to_email import _prepare_recipients

        mock_settings.email_default_recipient = None
        recipients, error = _prepare_recipients(None)
        assert recipients is None
        assert "No recipients specified" in error

    def test_converts_string_to_list(self):
        """Test converts string recipient to list."""
        from app.tasks.upload_to_email import _prepare_recipients

        recipients, error = _prepare_recipients("user@example.com")
        assert recipients == ["user@example.com"]
        assert error is None

    def test_returns_list_unchanged(self):
        """Test returns list recipients unchanged."""
        from app.tasks.upload_to_email import _prepare_recipients

        input_list = ["user1@example.com", "user2@example.com"]
        recipients, error = _prepare_recipients(input_list)
        assert recipients == input_list
        assert error is None


@pytest.mark.unit
class TestSendEmailWithSmtp:
    """Tests for _send_email_with_smtp function."""

    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email.socket.gethostbyname")
    @patch("app.tasks.upload_to_email.smtplib.SMTP")
    def test_successful_send(self, mock_smtp_cls, mock_dns, mock_settings):
        """Test successful email send."""
        from app.tasks.upload_to_email import _send_email_with_smtp

        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_port = 587
        mock_settings.email_use_tls = True
        mock_settings.email_username = "user"
        mock_settings.email_password = "pass"

        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = Mock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = Mock(return_value=False)

        msg = MIMEMultipart()
        result = _send_email_with_smtp(msg, "test.pdf", ["user@example.com"])
        assert result is None

    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email.socket.gethostbyname")
    def test_dns_resolution_failure(self, mock_dns, mock_settings):
        """Test DNS resolution failure."""
        from app.tasks.upload_to_email import _send_email_with_smtp

        mock_settings.email_host = "nonexistent.example.com"
        mock_dns.side_effect = socket.gaierror("DNS resolution failed")

        msg = MIMEMultipart()
        result = _send_email_with_smtp(msg, "test.pdf", ["user@example.com"])
        assert result is not None
        assert result["status"] == "Failed"
        assert "resolve" in result["reason"].lower()

    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email.socket.gethostbyname")
    @patch("app.tasks.upload_to_email.smtplib.SMTP")
    def test_connection_refused(self, mock_smtp_cls, mock_dns, mock_settings):
        """Test connection refused error."""
        from app.tasks.upload_to_email import _send_email_with_smtp

        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_port = 587
        mock_smtp_cls.side_effect = ConnectionRefusedError("Connection refused")

        msg = MIMEMultipart()
        result = _send_email_with_smtp(msg, "test.pdf", ["user@example.com"])
        assert result is not None
        assert result["status"] == "Failed"

    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email.socket.gethostbyname")
    @patch("app.tasks.upload_to_email.smtplib.SMTP")
    def test_send_without_tls(self, mock_smtp_cls, mock_dns, mock_settings):
        """Test sending without TLS."""
        from app.tasks.upload_to_email import _send_email_with_smtp

        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_port = 25
        mock_settings.email_use_tls = False
        mock_settings.email_username = "user"
        mock_settings.email_password = "pass"

        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = Mock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = Mock(return_value=False)

        msg = MIMEMultipart()
        result = _send_email_with_smtp(msg, "test.pdf", ["user@example.com"])
        assert result is None

    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email.socket.gethostbyname")
    @patch("app.tasks.upload_to_email.smtplib.SMTP")
    def test_send_without_credentials(self, mock_smtp_cls, mock_dns, mock_settings):
        """Test sending without login credentials."""
        from app.tasks.upload_to_email import _send_email_with_smtp

        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_port = 25
        mock_settings.email_use_tls = False
        mock_settings.email_username = None
        mock_settings.email_password = None

        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = Mock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = Mock(return_value=False)

        msg = MIMEMultipart()
        result = _send_email_with_smtp(msg, "test.pdf", ["user@example.com"])
        assert result is None
        mock_server.login.assert_not_called()


@pytest.mark.unit
class TestUploadToEmailTask:
    """Tests for upload_to_email Celery task."""

    @patch("app.tasks.upload_to_email.log_task_progress")
    @patch("app.tasks.upload_to_email.os.path.exists")
    def test_file_not_found_raises(self, mock_exists, mock_log):
        """Test FileNotFoundError when file doesn't exist."""
        from app.tasks.upload_to_email import upload_to_email

        mock_exists.return_value = False
        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        with pytest.raises(FileNotFoundError):
            upload_to_email(mock_self, "/nonexistent/file.pdf")

    @patch("app.tasks.upload_to_email.log_task_progress")
    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.settings")
    def test_email_host_not_configured(self, mock_settings, mock_exists, mock_log):
        """Test returns skipped when email host not configured."""
        from app.tasks.upload_to_email import upload_to_email

        mock_exists.return_value = True
        mock_settings.email_host = None
        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        result = upload_to_email(mock_self, "/tmp/test.pdf")
        assert result["status"] == "Skipped"
        assert "not configured" in result["reason"]

    @patch("app.tasks.upload_to_email.log_task_progress")
    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email._prepare_recipients")
    def test_no_recipients_returns_skipped(self, mock_prep, mock_settings, mock_exists, mock_log):
        """Test returns skipped when no recipients available."""
        from app.tasks.upload_to_email import upload_to_email

        mock_exists.return_value = True
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_port = 587
        mock_settings.email_use_tls = True
        mock_settings.email_username = "user"
        mock_prep.return_value = (None, "No recipients specified")
        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        result = upload_to_email(mock_self, "/tmp/test.pdf")
        assert result["status"] == "Skipped"

    @patch("app.tasks.upload_to_email.log_task_progress")
    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email._prepare_recipients")
    @patch("app.tasks.upload_to_email.extract_metadata_from_file")
    @patch("app.tasks.upload_to_email.attach_logo")
    @patch("app.tasks.upload_to_email.get_email_template")
    @patch("app.tasks.upload_to_email._send_email_with_smtp")
    @patch("builtins.open", mock_open(read_data=b"%PDF-1.4"))
    def test_successful_email_send(
        self, mock_smtp, mock_template, mock_logo, mock_metadata, mock_prep, mock_settings, mock_exists, mock_log
    ):
        """Test successful email sending."""
        from app.tasks.upload_to_email import upload_to_email

        mock_exists.return_value = True
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_port = 587
        mock_settings.email_use_tls = True
        mock_settings.email_username = "user"
        mock_settings.email_sender = "sender@example.com"
        mock_settings.external_hostname = "docs.example.com"
        mock_prep.return_value = (["user@example.com"], None)
        mock_metadata.return_value = {"document_type": "invoice"}
        mock_logo.return_value = True
        mock_tmpl = MagicMock()
        mock_tmpl.render.return_value = "<html>Email content</html>"
        mock_template.return_value = mock_tmpl
        mock_smtp.return_value = None

        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        result = upload_to_email(mock_self, "/tmp/test.pdf", file_id=1)
        assert result["status"] == "Completed"
        assert result["recipients"] == ["user@example.com"]
        assert result["metadata_included"] is True
        assert result["logo_included"] is True

    @patch("app.tasks.upload_to_email.log_task_progress")
    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email._prepare_recipients")
    @patch("app.tasks.upload_to_email.extract_metadata_from_file")
    @patch("app.tasks.upload_to_email.attach_logo")
    @patch("app.tasks.upload_to_email.get_email_template")
    @patch("app.tasks.upload_to_email._send_email_with_smtp")
    @patch("builtins.open", mock_open(read_data=b"%PDF-1.4"))
    def test_smtp_failure_returns_error(
        self, mock_smtp, mock_template, mock_logo, mock_metadata, mock_prep, mock_settings, mock_exists, mock_log
    ):
        """Test SMTP failure returns error dict."""
        from app.tasks.upload_to_email import upload_to_email

        mock_exists.return_value = True
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_port = 587
        mock_settings.email_use_tls = True
        mock_settings.email_username = "user"
        mock_settings.email_sender = "sender@example.com"
        mock_settings.external_hostname = None
        mock_prep.return_value = (["user@example.com"], None)
        mock_metadata.return_value = {}
        mock_logo.return_value = False
        mock_tmpl = MagicMock()
        mock_tmpl.render.return_value = "<html>Email</html>"
        mock_template.return_value = mock_tmpl
        mock_smtp.return_value = {"status": "Failed", "reason": "Connection refused"}

        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        result = upload_to_email(mock_self, "/tmp/test.pdf")
        assert result["status"] == "Failed"

    @patch("app.tasks.upload_to_email.log_task_progress")
    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email._prepare_recipients")
    @patch("app.tasks.upload_to_email.extract_metadata_from_file")
    @patch("app.tasks.upload_to_email.attach_logo")
    @patch("app.tasks.upload_to_email.get_email_template")
    def test_general_exception_raises(
        self, mock_template, mock_logo, mock_metadata, mock_prep, mock_settings, mock_exists, mock_log
    ):
        """Test general exception is re-raised."""
        from app.tasks.upload_to_email import upload_to_email

        mock_exists.return_value = True
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_port = 587
        mock_settings.email_use_tls = True
        mock_settings.email_username = "user"
        mock_settings.email_sender = "sender@example.com"
        mock_settings.external_hostname = None
        mock_prep.return_value = (["user@example.com"], None)
        mock_metadata.return_value = {}
        mock_logo.return_value = False
        mock_template.side_effect = Exception("Template error")

        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        with pytest.raises(Exception, match="Failed to send"):
            upload_to_email(mock_self, "/tmp/test.pdf")

    @patch("app.tasks.upload_to_email.log_task_progress")
    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.settings")
    @patch("app.tasks.upload_to_email._prepare_recipients")
    @patch("app.tasks.upload_to_email.extract_metadata_from_file")
    @patch("app.tasks.upload_to_email.attach_logo")
    @patch("app.tasks.upload_to_email.get_email_template")
    @patch("app.tasks.upload_to_email._send_email_with_smtp")
    @patch("builtins.open", mock_open(read_data=b"%PDF-1.4"))
    def test_send_with_custom_subject_and_message(
        self, mock_smtp, mock_template, mock_logo, mock_metadata, mock_prep, mock_settings, mock_exists, mock_log
    ):
        """Test sending with custom subject and message."""
        from app.tasks.upload_to_email import upload_to_email

        mock_exists.return_value = True
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_port = 587
        mock_settings.email_use_tls = False
        mock_settings.email_username = "user"
        mock_settings.email_sender = None
        mock_settings.external_hostname = None
        mock_prep.return_value = (["user@example.com"], None)
        mock_metadata.return_value = {}
        mock_logo.return_value = False
        mock_tmpl = MagicMock()
        mock_tmpl.render.return_value = "<html>Custom</html>"
        mock_template.return_value = mock_tmpl
        mock_smtp.return_value = None

        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        result = upload_to_email(
            mock_self,
            "/tmp/test.pdf",
            subject="Custom Subject",
            message="Custom message",
            include_metadata=False,
        )
        assert result["status"] == "Completed"
        assert result["subject"] == "Custom Subject"
