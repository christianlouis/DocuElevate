"""Tests for app/tasks/imap_tasks.py module."""

import os
import json
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from email.message import EmailMessage

from app.tasks.imap_tasks import (
    load_processed_emails,
    save_processed_emails,
    cleanup_old_entries,
    check_and_pull_mailbox,
    fetch_attachments_and_enqueue,
    email_already_has_label,
    mark_as_processed_with_star,
    mark_as_processed_with_label,
    find_all_mail_folder,
    get_capabilities,
)

_TEST_CREDENTIAL = "pass"  # noqa: S105


@pytest.mark.unit
class TestCleanupOldEntries:
    """Tests for cleanup_old_entries function."""

    def test_removes_old_entries(self):
        """Test that entries older than 7 days are removed."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S")
        recent_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        processed = {"old-msg": old_date, "recent-msg": recent_date}
        result = cleanup_old_entries(processed)
        assert "old-msg" not in result
        assert "recent-msg" in result

    def test_keeps_recent_entries(self):
        """Test that entries within 7 days are kept."""
        recent_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        processed = {"msg-1": recent_date, "msg-2": recent_date}
        result = cleanup_old_entries(processed)
        assert len(result) == 2

    def test_empty_dict(self):
        """Test with empty dictionary."""
        result = cleanup_old_entries({})
        assert result == {}


@pytest.mark.unit
class TestLoadSaveProcessedEmails:
    """Tests for load_processed_emails and save_processed_emails."""

    @patch("app.tasks.imap_tasks.CACHE_FILE", "/tmp/test_processed_mails.json")
    def test_load_returns_empty_when_no_file(self):
        """Test load returns empty dict when file doesn't exist."""
        if os.path.exists("/tmp/test_processed_mails.json"):
            os.remove("/tmp/test_processed_mails.json")
        result = load_processed_emails()
        assert result == {}

    @patch("app.tasks.imap_tasks.CACHE_FILE", "/tmp/test_processed_mails.json")
    def test_save_and_load_roundtrip(self):
        """Test saving and loading processed emails."""
        recent_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        emails = {"msg-1": recent_date}
        save_processed_emails(emails)
        result = load_processed_emails()
        assert "msg-1" in result

        # Clean up
        os.remove("/tmp/test_processed_mails.json")


@pytest.mark.unit
class TestCheckAndPullMailbox:
    """Tests for check_and_pull_mailbox function."""

    @patch("app.tasks.imap_tasks.pull_inbox")
    def test_skips_when_no_host(self, mock_pull):
        """Test that it skips when host is not configured."""
        check_and_pull_mailbox(
            mailbox_key="imap1",
            host=None,
            port=993,
            username="user",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
        )
        mock_pull.assert_not_called()

    @patch("app.tasks.imap_tasks.pull_inbox")
    def test_skips_when_no_password(self, mock_pull):
        """Test that it skips when password is not configured."""
        check_and_pull_mailbox(
            mailbox_key="imap1",
            host="imap.example.com",
            port=993,
            username="user",
            password=None,
            use_ssl=True,
            delete_after_process=False,
        )
        mock_pull.assert_not_called()

    @patch("app.tasks.imap_tasks.pull_inbox")
    def test_calls_pull_inbox_when_configured(self, mock_pull):
        """Test that it calls pull_inbox when properly configured."""
        check_and_pull_mailbox(
            mailbox_key="imap1",
            host="imap.example.com",
            port=993,
            username="user",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
        )
        mock_pull.assert_called_once()


@pytest.mark.unit
class TestFetchAttachmentsAndEnqueue:
    """Tests for fetch_attachments_and_enqueue function."""

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_skips_non_allowed_mime_types(self, mock_convert, mock_process):
        """Test that non-allowed MIME types are skipped."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg.add_attachment(b"data", maintype="application", subtype="octet-stream", filename="test.exe")

        result = fetch_attachments_and_enqueue(msg)
        assert result is False
        mock_process.delay.assert_not_called()
        mock_convert.delay.assert_not_called()

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_processes_pdf_attachment(self, mock_convert, mock_process, tmp_path):
        """Test that PDF attachments are processed directly."""
        msg = EmailMessage()
        msg["Subject"] = "Test PDF"
        msg.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf", filename="test.pdf")

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            result = fetch_attachments_and_enqueue(msg)

        assert result is True
        mock_process.delay.assert_called_once()

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_converts_docx_attachment(self, mock_convert, mock_process, tmp_path):
        """Test that DOCX attachments are sent for conversion."""
        msg = EmailMessage()
        msg["Subject"] = "Test DOCX"
        msg.add_attachment(
            b"docx content",
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename="test.docx",
        )

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            result = fetch_attachments_and_enqueue(msg)

        assert result is True
        mock_convert.delay.assert_called_once()


@pytest.mark.unit
class TestEmailAlreadyHasLabel:
    """Tests for email_already_has_label function."""

    def test_returns_true_when_label_found(self):
        """Test returns True when label is found."""
        mock_mail = MagicMock()
        mock_mail.fetch.return_value = ("OK", [(None, b'"Ingested" "INBOX"')])

        result = email_already_has_label(mock_mail, b"1", "Ingested")
        assert result is True

    def test_returns_false_when_label_not_found(self):
        """Test returns False when label is not found."""
        mock_mail = MagicMock()
        mock_mail.fetch.return_value = ("OK", [(None, b'"INBOX" "Sent"')])

        result = email_already_has_label(mock_mail, b"1", "Ingested")
        assert result is False

    def test_handles_exception(self):
        """Test handles exception gracefully."""
        mock_mail = MagicMock()
        mock_mail.fetch.side_effect = Exception("IMAP error")

        result = email_already_has_label(mock_mail, b"1", "Ingested")
        assert result is False


@pytest.mark.unit
class TestMarkAsProcessed:
    """Tests for mark_as_processed functions."""

    def test_mark_with_star(self):
        """Test marking email with star."""
        mock_mail = MagicMock()
        mark_as_processed_with_star(mock_mail, b"1")
        mock_mail.store.assert_called_once_with(b"1", "+FLAGS", "\\Flagged")

    def test_mark_with_label(self):
        """Test marking email with label."""
        mock_mail = MagicMock()
        mark_as_processed_with_label(mock_mail, b"1", "Ingested")
        mock_mail.store.assert_called_once_with(b"1", "+X-GM-LABELS", "Ingested")

    def test_mark_with_star_handles_exception(self):
        """Test mark_as_processed_with_star handles exception."""
        mock_mail = MagicMock()
        mock_mail.store.side_effect = Exception("IMAP error")
        # Should not raise
        mark_as_processed_with_star(mock_mail, b"1")

    def test_mark_with_label_handles_exception(self):
        """Test mark_as_processed_with_label handles exception."""
        mock_mail = MagicMock()
        mock_mail.store.side_effect = Exception("IMAP error")
        # Should not raise
        mark_as_processed_with_label(mock_mail, b"1", "Ingested")


@pytest.mark.unit
class TestGetCapabilities:
    """Tests for get_capabilities function."""

    def test_returns_capabilities(self):
        """Test returns list of capabilities."""
        mock_mail = MagicMock()
        mock_mail.capability.return_value = ("OK", [b"IMAP4REV1 IDLE XLIST"])

        result = get_capabilities(mock_mail)
        assert "IMAP4REV1" in result
        assert "XLIST" in result

    def test_returns_empty_on_failure(self):
        """Test returns empty list on failure."""
        mock_mail = MagicMock()
        mock_mail.capability.return_value = ("NO", None)

        result = get_capabilities(mock_mail)
        assert result == []


@pytest.mark.unit
class TestFindAllMailFolder:
    """Tests for find_all_mail_folder function."""

    def test_finds_english_all_mail(self):
        """Test finding English All Mail folder."""
        mock_mail = MagicMock()
        # First attempt fails, second succeeds
        mock_mail.select.side_effect = [
            ("NO", None),  # German
            ("OK", None),  # English
        ]

        result = find_all_mail_folder(mock_mail)
        assert result == "[Gmail]/All Mail"

    def test_returns_none_when_not_found(self):
        """Test returns None when All Mail folder is not found."""
        mock_mail = MagicMock()
        mock_mail.select.return_value = ("NO", None)
        mock_mail.capability.return_value = ("OK", [b"IMAP4REV1"])

        result = find_all_mail_folder(mock_mail)
        assert result is None
