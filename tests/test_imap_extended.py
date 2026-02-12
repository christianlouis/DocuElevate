"""Extended tests for app/tasks/imap_tasks.py module."""

import json
import os
from datetime import datetime, timezone
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.imap_tasks import (
    fetch_attachments_and_enqueue,
    find_all_mail_xlist,
    load_processed_emails,
    save_processed_emails,
)


@pytest.mark.unit
class TestSaveProcessedEmails:
    """Tests for save_processed_emails function."""

    @patch("app.tasks.imap_tasks.CACHE_FILE", "/tmp/test_save_processed.json")
    def test_saves_to_file(self):
        """Test that processed emails are saved to file."""
        emails = {"msg-1": "2024-01-01T00:00:00", "msg-2": "2024-01-02T00:00:00"}
        save_processed_emails(emails)
        assert os.path.exists("/tmp/test_save_processed.json")
        with open("/tmp/test_save_processed.json") as f:
            loaded = json.load(f)
        assert loaded == emails
        os.remove("/tmp/test_save_processed.json")


@pytest.mark.unit
class TestFetchAttachmentsExtended:
    """Extended tests for fetch_attachments_and_enqueue."""

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_processes_pdf_by_extension(self, mock_convert, mock_process, tmp_path):
        """Test PDF detection by extension even with wrong MIME type."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        # Create attachment with wrong MIME type but .pdf extension
        msg.add_attachment(b"%PDF-1.4", maintype="application", subtype="octet-stream", filename="invoice.pdf")

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            result = fetch_attachments_and_enqueue(msg)

        assert result is True
        mock_process.delay.assert_called_once()

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_processes_text_attachment(self, mock_convert, mock_process, tmp_path):
        """Test text/plain attachment is sent for conversion."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg.add_attachment(b"Hello world", maintype="text", subtype="plain", filename="notes.txt")

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            result = fetch_attachments_and_enqueue(msg)

        assert result is True
        mock_convert.delay.assert_called_once()

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_skips_multipart(self, mock_convert, mock_process):
        """Test that multipart parts are skipped."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg.set_content("Hello body")  # multipart text is skipped

        result = fetch_attachments_and_enqueue(msg)
        assert result is False

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_no_attachments(self, mock_convert, mock_process):
        """Test email with no attachments."""
        msg = EmailMessage()
        msg["Subject"] = "No attachments"
        msg.set_content("Plain text body")

        result = fetch_attachments_and_enqueue(msg)
        assert result is False


@pytest.mark.unit
class TestFindAllMailXlist:
    """Tests for find_all_mail_xlist function."""

    def test_finds_all_mail_via_xlist(self):
        """Test finding All Mail folder via XLIST."""
        mock_mail = MagicMock()
        mock_mail._new_tag.return_value = b"A001"

        # Simulate XLIST response
        mock_mail.readline.side_effect = [
            b'* XLIST (\\AllMail) "/" "[Gmail]/All Mail"\r\n',
            b"A001 OK XLIST completed\r\n",
        ]

        result = find_all_mail_xlist(mock_mail)
        assert result == "[Gmail]/All Mail"

    def test_returns_none_when_no_allmail(self):
        """Test returns None when XLIST doesn't find All Mail."""
        mock_mail = MagicMock()
        mock_mail._new_tag.return_value = b"A001"

        mock_mail.readline.side_effect = [
            b'* XLIST (\\Inbox) "/" "INBOX"\r\n',
            b"A001 OK XLIST completed\r\n",
        ]

        result = find_all_mail_xlist(mock_mail)
        assert result is None
