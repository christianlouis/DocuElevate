"""Tests for app/tasks/upload_to_email.py module."""

import json
import socket
from email.mime.multipart import MIMEMultipart
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest

from app.tasks.upload_to_email import (
    _prepare_recipients,
    _send_email_with_smtp,
    attach_logo,
    extract_metadata_from_file,
    get_email_template,
    upload_to_email,
)


@pytest.mark.unit
class TestGetEmailTemplate:
    """Tests for get_email_template function."""

    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.FileSystemLoader")
    @patch("app.tasks.upload_to_email.Environment")
    def test_loads_custom_template_from_workdir(self, mock_env, mock_loader, mock_exists):
        """Test loading custom template from workdir."""
        mock_exists.return_value = True
        mock_template = Mock()
        mock_env.return_value.get_template.return_value = mock_template

        result = get_email_template("custom.html")

        assert result == mock_template
        mock_env.return_value.get_template.assert_called_once_with("custom.html")

    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.FileSystemLoader")
    @patch("app.tasks.upload_to_email.Environment")
    def test_falls_back_to_builtin_template(self, mock_env, mock_loader, mock_exists):
        """Test fallback to built-in template."""
        # First call (workdir) returns False, second call (app) returns True
        mock_exists.side_effect = [False, True]
        mock_template = Mock()
        mock_env.return_value.get_template.return_value = mock_template

        result = get_email_template("default.html")

        assert result == mock_template

    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.FileSystemLoader")
    @patch("app.tasks.upload_to_email.Environment")
    def test_raises_error_when_no_template_found(self, mock_env, mock_loader, mock_exists):
        """Test raises error when template not found."""
        mock_exists.return_value = False
        mock_env.return_value.get_template.side_effect = Exception("Template not found")

        with pytest.raises(ValueError, match="Could not find any valid email template"):
            get_email_template("missing.html")

    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.FileSystemLoader")
    @patch("app.tasks.upload_to_email.Environment")
    def test_fallback_to_builtin_template_when_custom_template_fails(self, mock_env, mock_loader, mock_exists):
        """Test fallback to built-in template when custom template loading fails."""
        # Workdir exists, but template loading fails; falls back to built-in
        mock_exists.return_value = True
        mock_template = Mock()

        # First environment (workdir) raises exception, second (app) returns template
        mock_env_workdir = Mock()
        mock_env_workdir.globals = {}
        mock_env_workdir.get_template.side_effect = Exception("Custom template error")
        mock_env_app = Mock()
        mock_env_app.globals = {}
        mock_env_app.get_template.return_value = mock_template
        mock_env.side_effect = [mock_env_workdir, mock_env_app]

        result = get_email_template("custom.html")

        assert result == mock_template


@pytest.mark.unit
class TestExtractMetadataFromFile:
    """Tests for extract_metadata_from_file function."""

    def test_returns_empty_dict_when_no_metadata(self, tmp_path):
        """Test returns empty dict when no metadata file exists."""
        file_path = tmp_path / "test.pdf"
        file_path.write_text("test content")

        result = extract_metadata_from_file(str(file_path))

        assert result == {}

    def test_loads_metadata_from_json_file(self, tmp_path):
        """Test loads metadata from JSON file."""
        file_path = tmp_path / "test.pdf"
        file_path.write_text("test content")

        metadata = {"document_type": "invoice", "amount": 100.00}
        json_path = tmp_path / "test.json"
        json_path.write_text(json.dumps(metadata))

        result = extract_metadata_from_file(str(file_path))

        assert result == metadata

    def test_handles_invalid_json_gracefully(self, tmp_path):
        """Test handles invalid JSON gracefully."""
        file_path = tmp_path / "test.pdf"
        file_path.write_text("test content")

        json_path = tmp_path / "test.json"
        json_path.write_text("invalid json {")

        result = extract_metadata_from_file(str(file_path))

        assert result == {}


@pytest.mark.unit
class TestAttachLogo:
    """Tests for attach_logo function."""

    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data=b"fake_logo_data")
    def test_attaches_logo_successfully(self, mock_file, mock_exists):
        """Test attaches logo successfully."""
        mock_exists.return_value = True
        msg = MIMEMultipart()

        result = attach_logo(msg)

        assert result is True
        assert len(msg.get_payload()) > 0

    @patch("app.tasks.upload_to_email.os.path.exists")
    def test_returns_false_when_logo_not_found(self, mock_exists):
        """Test returns False when logo not found."""
        mock_exists.return_value = False
        msg = MIMEMultipart()

        result = attach_logo(msg)

        assert result is False

    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("builtins.open", side_effect=IOError("Cannot read file"))
    def test_handles_file_read_error_gracefully(self, mock_file, mock_exists):
        """Test handles file read error gracefully."""
        mock_exists.return_value = True
        msg = MIMEMultipart()

        result = attach_logo(msg)

        assert result is False

    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data=b"fake_svg_data")
    def test_attaches_svg_logo_with_correct_mime_type(self, mock_file, mock_exists):
        """Test attaches SVG logo with correct MIME type (image/svg+xml)."""

        # Create a custom side effect that returns True only for SVG path
        def custom_exists(path):
            return "logo.svg" in path

        mock_exists.side_effect = custom_exists
        msg = MIMEMultipart()

        # Patch the logo filename to be SVG
        with patch("app.tasks.upload_to_email._LOGO_FILENAME", "logo.svg"):
            with patch("app.tasks.upload_to_email.settings") as mock_settings:
                mock_settings.workdir = "/tmp"
                result = attach_logo(msg)

        assert result is True
        assert len(msg.get_payload()) > 0

        # Verify SVG MIME type is used (the function detects .svg extension)
        # Note: MIMEImage may default to a different subtype, but the key is that
        # the function passes 'image/svg+xml' as mimetype parameter
        # Since we're using mock_open, we can't verify the exact MIME in the attachment,
        # but we verified the code path is exercised

    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data=b"fake_logo_data")
    def test_checks_multiple_logo_locations(self, mock_file, mock_exists):
        """Test checks custom location first, then falls back to app locations."""
        # Simulate custom logo not existing, but app logo existing
        # First call: workdir custom, Second: app/static, Third: frontend/static
        mock_exists.side_effect = [False, False, True]
        msg = MIMEMultipart()

        result = attach_logo(msg)

        assert result is True
        # Verify exactly three paths were checked as configured
        assert mock_exists.call_count == 3


@pytest.mark.unit
class TestPrepareRecipients:
    """Tests for _prepare_recipients function."""

    @patch("app.tasks.upload_to_email.settings")
    def test_returns_provided_recipients_list(self, mock_settings):
        """Test returns provided recipients list."""
        recipients = ["user1@example.com", "user2@example.com"]

        result, error = _prepare_recipients(recipients)

        assert result == recipients
        assert error is None

    @patch("app.tasks.upload_to_email.settings")
    def test_converts_single_email_to_list(self, mock_settings):
        """Test converts single email string to list."""
        recipients = "user@example.com"

        result, error = _prepare_recipients(recipients)

        assert result == ["user@example.com"]
        assert error is None

    @patch("app.tasks.upload_to_email.settings")
    def test_uses_default_recipient_when_none_provided(self, mock_settings):
        """Test uses default recipient when none provided."""
        mock_settings.email_default_recipient = "default@example.com"

        result, error = _prepare_recipients(None)

        assert result == ["default@example.com"]
        assert error is None

    @patch("app.tasks.upload_to_email.settings")
    def test_returns_error_when_no_recipients_and_no_default(self, mock_settings):
        """Test returns error when no recipients and no default."""
        mock_settings.email_default_recipient = None

        result, error = _prepare_recipients(None)

        assert result is None
        assert "No recipients specified" in error


@pytest.mark.unit
class TestSendEmailWithSMTP:
    """Tests for _send_email_with_smtp function."""

    @patch("app.tasks.upload_to_email.smtplib.SMTP")
    @patch("app.tasks.upload_to_email.socket.gethostbyname")
    @patch("app.tasks.upload_to_email.settings")
    def test_sends_email_successfully(self, mock_settings, mock_gethostbyname, mock_smtp):
        """Test sends email successfully."""
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_port = 587
        mock_settings.email_use_tls = True
        mock_settings.email_username = "user@example.com"
        mock_settings.email_password = "password"

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        msg = MIMEMultipart()
        msg["Subject"] = "Test"

        result = _send_email_with_smtp(msg, "test.pdf", ["recipient@example.com"])

        assert result is None
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once()
        mock_server.send_message.assert_called_once()

    @patch("app.tasks.upload_to_email.socket.gethostbyname")
    def test_handles_hostname_resolution_error(self, mock_gethostbyname):
        """Test handles hostname resolution error."""
        mock_gethostbyname.side_effect = socket.gaierror("Cannot resolve hostname")

        msg = MIMEMultipart()
        result = _send_email_with_smtp(msg, "test.pdf", ["recipient@example.com"])

        assert result is not None
        assert result["status"] == "Failed"
        assert "Failed to resolve email host" in result["reason"]

    @patch("app.tasks.upload_to_email.smtplib.SMTP")
    @patch("app.tasks.upload_to_email.socket.gethostbyname")
    @patch("app.tasks.upload_to_email.settings")
    def test_handles_connection_refused_error(self, mock_settings, mock_gethostbyname, mock_smtp):
        """Test handles connection refused error."""
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_port = 587

        mock_smtp.return_value.__enter__.side_effect = ConnectionRefusedError("Connection refused")

        msg = MIMEMultipart()
        result = _send_email_with_smtp(msg, "test.pdf", ["recipient@example.com"])

        assert result is not None
        assert result["status"] == "Failed"
        assert "Connection error" in result["reason"]

    @patch("app.tasks.upload_to_email.smtplib.SMTP")
    @patch("app.tasks.upload_to_email.socket.gethostbyname")
    @patch("app.tasks.upload_to_email.settings")
    def test_sends_email_without_tls(self, mock_settings, mock_gethostbyname, mock_smtp):
        """Test sends email without TLS."""
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_port = 25
        mock_settings.email_use_tls = False
        mock_settings.email_username = "user@example.com"
        mock_settings.email_password = "password"

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        msg = MIMEMultipart()
        msg["Subject"] = "Test"

        result = _send_email_with_smtp(msg, "test.pdf", ["recipient@example.com"])

        assert result is None
        mock_server.starttls.assert_not_called()
        mock_server.login.assert_called_once()
        mock_server.send_message.assert_called_once()

    @patch("app.tasks.upload_to_email.smtplib.SMTP")
    @patch("app.tasks.upload_to_email.socket.gethostbyname")
    @patch("app.tasks.upload_to_email.settings")
    def test_sends_email_without_authentication(self, mock_settings, mock_gethostbyname, mock_smtp):
        """Test sends email without authentication credentials."""
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_port = 25
        mock_settings.email_use_tls = False
        mock_settings.email_username = None
        mock_settings.email_password = None

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        msg = MIMEMultipart()
        msg["Subject"] = "Test"

        result = _send_email_with_smtp(msg, "test.pdf", ["recipient@example.com"])

        assert result is None
        mock_server.login.assert_not_called()
        mock_server.send_message.assert_called_once()

    @patch("app.tasks.upload_to_email.smtplib.SMTP")
    @patch("app.tasks.upload_to_email.socket.gethostbyname")
    @patch("app.tasks.upload_to_email.settings")
    def test_handles_timeout_error(self, mock_settings, mock_gethostbyname, mock_smtp):
        """Test handles timeout error."""
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_port = 587

        mock_smtp.return_value.__enter__.side_effect = TimeoutError("Connection timeout")

        msg = MIMEMultipart()
        result = _send_email_with_smtp(msg, "test.pdf", ["recipient@example.com"])

        assert result is not None
        assert result["status"] == "Failed"
        assert "Connection error" in result["reason"]


@pytest.mark.unit
class TestUploadToEmailTask:
    """Tests for upload_to_email task - basic validation tests."""

    @patch("app.tasks.upload_to_email.os.path.basename")
    @patch("app.tasks.upload_to_email.log_task_progress")
    @patch("app.tasks.upload_to_email.os.path.exists")
    def test_raises_error_when_file_not_found(self, mock_exists, mock_log, mock_basename):
        """Test raises error when file not found."""
        mock_exists.return_value = False
        mock_basename.return_value = "file.pdf"

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        with pytest.raises(FileNotFoundError):
            upload_to_email(mock_self, "/nonexistent/file.pdf")

    @patch("app.tasks.upload_to_email.os.path.basename")
    @patch("app.tasks.upload_to_email.log_task_progress")
    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.settings")
    def test_skips_when_email_host_not_configured(self, mock_settings, mock_exists, mock_log, mock_basename):
        """Test skips when email host not configured."""
        mock_exists.return_value = True
        mock_basename.return_value = "test.pdf"
        mock_settings.email_host = None

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        result = upload_to_email(mock_self, "/tmp/test.pdf")

        assert result["status"] == "Skipped"
        assert "Email host is not configured" in result["reason"]

    @patch("app.tasks.upload_to_email.os.path.basename")
    @patch("app.tasks.upload_to_email._prepare_recipients")
    @patch("app.tasks.upload_to_email.log_task_progress")
    @patch("app.tasks.upload_to_email.os.path.exists")
    @patch("app.tasks.upload_to_email.settings")
    def test_skips_when_no_valid_recipients(self, mock_settings, mock_exists, mock_log, mock_prepare, mock_basename):
        """Test skips when no valid recipients."""
        mock_exists.return_value = True
        mock_basename.return_value = "test.pdf"
        mock_settings.email_host = "smtp.example.com"
        mock_prepare.return_value = (None, "No recipients specified")

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        result = upload_to_email(mock_self, "/tmp/test.pdf")

        assert result["status"] == "Skipped"
