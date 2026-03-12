"""Tests for app/tasks/imap_tasks.py module."""

import os
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.imap_tasks import (
    acquire_lock,
    check_and_pull_mailbox,
    cleanup_old_entries,
    email_already_has_label,
    fetch_attachments_and_enqueue,
    find_all_mail_folder,
    find_all_mail_xlist,
    get_capabilities,
    load_processed_emails,
    mark_as_processed_with_label,
    mark_as_processed_with_star,
    pull_all_inboxes,
    pull_inbox,
    release_lock,
    save_processed_emails,
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

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_skips_image_when_documents_only(self, mock_convert, mock_process):
        """Test that image attachments are skipped with documents_only filter."""
        msg = EmailMessage()
        msg["Subject"] = "Photo"
        msg.add_attachment(b"\xff\xd8\xff", maintype="image", subtype="jpeg", filename="photo.jpg")

        result = fetch_attachments_and_enqueue(msg, attachment_filter="documents_only")
        assert result is False
        mock_process.delay.assert_not_called()
        mock_convert.delay.assert_not_called()

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_processes_image_when_all_filter(self, mock_convert, mock_process, tmp_path):
        """Test that image attachments are processed with 'all' filter."""
        msg = EmailMessage()
        msg["Subject"] = "Photo"
        msg.add_attachment(b"\xff\xd8\xff", maintype="image", subtype="jpeg", filename="photo.jpg")

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            result = fetch_attachments_and_enqueue(msg, attachment_filter="all")

        assert result is True
        mock_convert.delay.assert_called_once()

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_skips_image_with_image_extension_documents_only(self, mock_convert, mock_process):
        """Test image files identified by extension are skipped with documents_only."""
        msg = EmailMessage()
        msg["Subject"] = "Screenshot"
        msg.add_attachment(b"\x89PNG", maintype="application", subtype="octet-stream", filename="screenshot.png")

        result = fetch_attachments_and_enqueue(msg, attachment_filter="documents_only")
        assert result is False
        mock_process.delay.assert_not_called()
        mock_convert.delay.assert_not_called()

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_processes_pdf_regardless_of_filter(self, mock_convert, mock_process, tmp_path):
        """Test that PDFs are always processed, even with documents_only filter."""
        msg = EmailMessage()
        msg["Subject"] = "Invoice"
        msg.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf", filename="invoice.pdf")

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            result = fetch_attachments_and_enqueue(msg, attachment_filter="documents_only")

        assert result is True
        mock_process.delay.assert_called_once()

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_uses_global_setting_when_no_filter(self, mock_convert, mock_process):
        """Test that the global settings.imap_attachment_filter is used when no filter is passed."""
        msg = EmailMessage()
        msg["Subject"] = "Photo"
        msg.add_attachment(b"\xff\xd8\xff", maintype="image", subtype="jpeg", filename="photo.jpg")

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.imap_attachment_filter = "documents_only"
            mock_settings.workdir = "/tmp"
            result = fetch_attachments_and_enqueue(msg)

        assert result is False
        mock_process.delay.assert_not_called()
        mock_convert.delay.assert_not_called()


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

    @patch("app.tasks.imap_tasks.find_all_mail_xlist")
    @patch("app.tasks.imap_tasks.get_capabilities")
    def test_uses_xlist_when_available(self, mock_get_caps, mock_xlist):
        """Test that it uses XLIST when available and common names fail."""
        mock_mail = MagicMock()
        mock_mail.select.return_value = ("NO", None)  # All common names fail
        mock_get_caps.return_value = ["XLIST", "IMAP4REV1"]
        mock_xlist.return_value = "[Gmail]/All Mail"

        result = find_all_mail_folder(mock_mail)
        assert result == "[Gmail]/All Mail"
        mock_xlist.assert_called_once_with(mock_mail)


@pytest.mark.unit
class TestFindAllMailXlist:
    """Tests for find_all_mail_xlist function."""

    def test_finds_all_mail_via_xlist(self):
        """Test finding All Mail folder via XLIST."""
        mock_mail = MagicMock()
        mock_mail._new_tag.return_value = b"A001"

        # Mock the readline responses
        responses = [
            b'* XLIST (\\HasNoChildren \\AllMail) "/" "[Gmail]/All Mail"\r\n',
            b"A001 OK XLIST completed\r\n",
        ]
        mock_mail.readline.side_effect = responses

        result = find_all_mail_xlist(mock_mail)
        assert result == "[Gmail]/All Mail"

    def test_returns_none_when_no_allmail_flag(self):
        """Test returns None when XLIST doesn't have AllMail flag."""
        mock_mail = MagicMock()
        mock_mail._new_tag.return_value = b"A001"

        # Mock responses without AllMail flag
        responses = [
            b'* XLIST (\\HasNoChildren) "/" "INBOX"\r\n',
            b"A001 OK XLIST completed\r\n",
        ]
        mock_mail.readline.side_effect = responses

        result = find_all_mail_xlist(mock_mail)
        assert result is None


@pytest.mark.unit
class TestLockingMechanism:
    """Tests for Redis-based locking functions."""

    @patch("app.tasks.imap_tasks.redis_client")
    def test_acquire_lock_success(self, mock_redis):
        """Test successfully acquiring the lock."""
        mock_redis.setnx.return_value = True

        result = acquire_lock()
        assert result is True
        mock_redis.setnx.assert_called_once_with("imap_lock", "locked")
        mock_redis.expire.assert_called_once_with("imap_lock", 300)

    @patch("app.tasks.imap_tasks.redis_client")
    def test_acquire_lock_failure(self, mock_redis):
        """Test failing to acquire the lock when already held."""
        mock_redis.setnx.return_value = False

        result = acquire_lock()
        assert result is False
        mock_redis.expire.assert_not_called()

    @patch("app.tasks.imap_tasks.redis_client")
    def test_release_lock(self, mock_redis):
        """Test releasing the lock."""
        release_lock()
        mock_redis.delete.assert_called_once_with("imap_lock")


@pytest.mark.unit
class TestPullAllInboxes:
    """Tests for pull_all_inboxes task."""

    @patch("app.tasks.imap_tasks.check_and_pull_mailbox")
    @patch("app.tasks.imap_tasks.release_lock")
    @patch("app.tasks.imap_tasks.acquire_lock")
    @patch("app.tasks.imap_tasks.settings")
    def test_pulls_both_mailboxes(self, mock_settings, mock_acquire, mock_release, mock_check):
        """Test that both mailboxes are checked when lock is acquired."""
        mock_acquire.return_value = True
        mock_settings.imap1_host = "imap1.example.com"
        mock_settings.imap1_port = 993
        mock_settings.imap1_username = "user1"
        mock_settings.imap1_password = _TEST_CREDENTIAL
        mock_settings.imap1_ssl = True
        mock_settings.imap1_delete_after_process = False

        mock_settings.imap2_host = "imap.gmail.com"
        mock_settings.imap2_port = 993
        mock_settings.imap2_username = "user2@gmail.com"
        mock_settings.imap2_password = _TEST_CREDENTIAL
        mock_settings.imap2_ssl = True
        mock_settings.imap2_delete_after_process = False

        pull_all_inboxes()

        assert mock_check.call_count == 2
        mock_release.assert_called_once()

    @patch("app.tasks.imap_tasks.acquire_lock")
    def test_skips_when_lock_held(self, mock_acquire):
        """Test that execution is skipped when lock cannot be acquired."""
        mock_acquire.return_value = False

        pull_all_inboxes()

        mock_acquire.assert_called_once()

    @patch("app.tasks.imap_tasks.check_and_pull_mailbox")
    @patch("app.tasks.imap_tasks.release_lock")
    @patch("app.tasks.imap_tasks.acquire_lock")
    def test_releases_lock_on_exception(self, mock_acquire, mock_release, mock_check):
        """Test that lock is released even when exception occurs."""
        mock_acquire.return_value = True
        mock_check.side_effect = Exception("Test error")

        with pytest.raises(Exception):
            pull_all_inboxes()

        mock_release.assert_called_once()


@pytest.mark.unit
class TestPullInbox:
    """Tests for pull_inbox function."""

    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    @patch("app.tasks.imap_tasks.save_processed_emails")
    def test_non_gmail_inbox_fetch(self, mock_save, mock_load, mock_imap_class):
        """Test fetching from a non-Gmail inbox."""
        mock_load.return_value = {}
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail

        # Mock successful login and folder selection
        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b""])  # No messages

        pull_inbox(
            mailbox_key="imap1",
            host="imap.example.com",
            port=993,
            username="user",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
        )

        mock_mail.login.assert_called_once_with("user", _TEST_CREDENTIAL)
        mock_mail.select.assert_called_once_with("INBOX")
        mock_mail.close.assert_called_once()
        mock_mail.logout.assert_called_once()

    @patch("app.tasks.imap_tasks.imaplib.IMAP4")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    def test_non_ssl_connection(self, mock_load, mock_imap_class):
        """Test connecting without SSL."""
        mock_load.return_value = {}
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail

        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b""])

        pull_inbox(
            mailbox_key="imap1",
            host="imap.example.com",
            port=143,
            username="user",
            password=_TEST_CREDENTIAL,
            use_ssl=False,
            delete_after_process=False,
        )

        mock_imap_class.assert_called_once_with("imap.example.com", 143)

    @patch("app.tasks.imap_tasks.find_all_mail_folder")
    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    def test_gmail_uses_all_mail_folder(self, mock_load, mock_imap_class, mock_find_all):
        """Test that Gmail uses All Mail folder when found."""
        mock_load.return_value = {}
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail
        mock_find_all.return_value = "[Gmail]/All Mail"

        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b""])

        pull_inbox(
            mailbox_key="imap2",
            host="imap.gmail.com",
            port=993,
            username="user@gmail.com",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
        )

        mock_find_all.assert_called_once_with(mock_mail)
        mock_mail.select.assert_called_once_with('"[Gmail]/All Mail"')

    @patch("app.tasks.imap_tasks.find_all_mail_folder")
    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    def test_gmail_fallback_to_inbox(self, mock_load, mock_imap_class, mock_find_all):
        """Test that Gmail falls back to INBOX when All Mail not found."""
        mock_load.return_value = {}
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail
        mock_find_all.return_value = None  # All Mail not found

        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b""])

        pull_inbox(
            mailbox_key="imap2",
            host="imap.gmail.com",
            port=993,
            username="user@gmail.com",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
        )

        # Should select INBOX as fallback
        assert any(call_args[0][0] == "INBOX" for call_args in mock_mail.select.call_args_list)

    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    def test_search_failure_handling(self, mock_load, mock_imap_class):
        """Test handling of search failure."""
        mock_load.return_value = {}
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail

        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("NO", [])  # Search failed

        pull_inbox(
            mailbox_key="imap1",
            host="imap.example.com",
            port=993,
            username="user",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
        )

        # Should close and logout despite search failure
        mock_mail.close.assert_called_once()
        mock_mail.logout.assert_called_once()

    @patch("app.tasks.imap_tasks.fetch_attachments_and_enqueue")
    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    @patch("app.tasks.imap_tasks.save_processed_emails")
    @patch("app.tasks.imap_tasks.settings")
    def test_processes_messages_and_marks_as_read(
        self, mock_settings, mock_save, mock_load, mock_imap_class, mock_fetch
    ):
        """Test processing messages and marking them as read."""
        mock_settings.workdir = "/tmp"
        mock_settings.imap_readonly_mode = False
        mock_load.return_value = {}
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail

        # Create a simple email message
        import email

        msg = email.message.EmailMessage()
        msg["Message-ID"] = "<test@example.com>"
        msg["Subject"] = "Test"
        raw_email = msg.as_bytes()

        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [[None, raw_email]])

        pull_inbox(
            mailbox_key="imap1",
            host="imap.example.com",
            port=993,
            username="user",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
        )

        # Should mark as unread (remove Seen flag)
        mock_mail.store.assert_called_with(b"1", "-FLAGS", "\\Seen")
        mock_save.assert_called()

    @patch("app.tasks.imap_tasks.fetch_attachments_and_enqueue")
    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    @patch("app.tasks.imap_tasks.save_processed_emails")
    @patch("app.tasks.imap_tasks.settings")
    def test_delete_after_process(self, mock_settings, mock_save, mock_load, mock_imap_class, mock_fetch):
        """Test deleting messages after processing."""
        mock_settings.workdir = "/tmp"
        mock_settings.imap_readonly_mode = False
        mock_load.return_value = {}
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail

        import email

        msg = email.message.EmailMessage()
        msg["Message-ID"] = "<test@example.com>"
        raw_email = msg.as_bytes()

        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [[None, raw_email]])

        pull_inbox(
            mailbox_key="imap1",
            host="imap.example.com",
            port=993,
            username="user",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=True,
        )

        # Should mark for deletion and expunge
        mock_mail.store.assert_called_with(b"1", "+FLAGS", "\\Deleted")
        mock_mail.expunge.assert_called_once()

    @patch("app.tasks.imap_tasks.email_already_has_label")
    @patch("app.tasks.imap_tasks.mark_as_processed_with_label")
    @patch("app.tasks.imap_tasks.mark_as_processed_with_star")
    @patch("app.tasks.imap_tasks.fetch_attachments_and_enqueue")
    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    @patch("app.tasks.imap_tasks.save_processed_emails")
    @patch("app.tasks.imap_tasks.settings")
    def test_gmail_labels_and_star(
        self,
        mock_settings,
        mock_save,
        mock_load,
        mock_imap_class,
        mock_fetch,
        mock_star,
        mock_label,
        mock_has_label,
    ):
        """Test that Gmail messages are starred and labeled."""
        mock_settings.workdir = "/tmp"
        mock_settings.imap_readonly_mode = False
        mock_load.return_value = {}
        mock_has_label.return_value = False
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail

        import email

        msg = email.message.EmailMessage()
        msg["Message-ID"] = "<test@gmail.com>"
        raw_email = msg.as_bytes()

        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [[None, raw_email]])

        pull_inbox(
            mailbox_key="imap2",
            host="imap.gmail.com",
            port=993,
            username="user@gmail.com",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
        )

        mock_star.assert_called_once_with(mock_mail, b"1")
        mock_label.assert_called_once_with(mock_mail, b"1", label="Ingested")

    @patch("app.tasks.imap_tasks.email_already_has_label")
    @patch("app.tasks.imap_tasks.mark_as_processed_with_label")
    @patch("app.tasks.imap_tasks.mark_as_processed_with_star")
    @patch("app.tasks.imap_tasks.fetch_attachments_and_enqueue")
    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    @patch("app.tasks.imap_tasks.save_processed_emails")
    @patch("app.tasks.imap_tasks.settings")
    def test_gmail_labels_disabled_when_gmail_apply_labels_false(
        self,
        mock_settings,
        mock_save,
        mock_load,
        mock_imap_class,
        mock_fetch,
        mock_star,
        mock_label,
        mock_has_label,
    ):
        """Gmail star/label operations should be skipped when gmail_apply_labels=False."""
        mock_settings.workdir = "/tmp"
        mock_settings.imap_readonly_mode = False
        mock_load.return_value = {}
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail

        import email

        msg = email.message.EmailMessage()
        msg["Message-ID"] = "<test-no-labels@gmail.com>"
        raw_email = msg.as_bytes()

        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [[None, raw_email]])

        pull_inbox(
            mailbox_key="imap2",
            host="imap.gmail.com",
            port=993,
            username="user@gmail.com",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
            gmail_apply_labels=False,
        )

        mock_star.assert_not_called()
        mock_label.assert_not_called()
        mock_has_label.assert_not_called()
        mock_fetch.assert_called()

    @patch("app.tasks.imap_tasks.email_already_has_label")
    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    @patch("app.tasks.imap_tasks.settings")
    def test_skips_already_labeled_gmail_messages(self, mock_settings, mock_load, mock_imap_class, mock_has_label):
        """Test that already labeled Gmail messages are skipped."""
        mock_settings.workdir = "/tmp"
        mock_load.return_value = {}
        mock_has_label.return_value = True  # Already labeled
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail

        import email

        msg = email.message.EmailMessage()
        msg["Message-ID"] = "<test@gmail.com>"
        raw_email = msg.as_bytes()

        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [[None, raw_email]])

        pull_inbox(
            mailbox_key="imap2",
            host="imap.gmail.com",
            port=993,
            username="user@gmail.com",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
        )

        # Message should be skipped, so no store operations
        mock_mail.store.assert_not_called()

    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    def test_skips_message_without_message_id(self, mock_load, mock_imap_class):
        """Test that messages without Message-ID are skipped."""
        mock_load.return_value = {}
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail

        import email

        msg = email.message.EmailMessage()
        # No Message-ID
        msg["Subject"] = "Test"
        raw_email = msg.as_bytes()

        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [[None, raw_email]])

        pull_inbox(
            mailbox_key="imap1",
            host="imap.example.com",
            port=993,
            username="user",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
        )

        # Should not process the message
        mock_mail.store.assert_not_called()

    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    def test_skips_already_processed_messages(self, mock_load, mock_imap_class):
        """Test that already processed messages are skipped."""
        mock_load.return_value = {"<test@example.com>": "2024-01-01T00:00:00"}
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail

        import email

        msg = email.message.EmailMessage()
        msg["Message-ID"] = "<test@example.com>"
        raw_email = msg.as_bytes()

        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [[None, raw_email]])

        pull_inbox(
            mailbox_key="imap1",
            host="imap.example.com",
            port=993,
            username="user",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
        )

        # Should not process the message
        mock_mail.store.assert_not_called()

    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    def test_handles_fetch_failure(self, mock_load, mock_imap_class):
        """Test handling of message fetch failure."""
        mock_load.return_value = {}
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail

        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("NO", [])  # Fetch failed

        pull_inbox(
            mailbox_key="imap1",
            host="imap.example.com",
            port=993,
            username="user",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
        )

        # Should close and logout despite fetch failure
        mock_mail.close.assert_called_once()
        mock_mail.logout.assert_called_once()

    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    def test_handles_connection_exception(self, mock_load, mock_imap_class):
        """Test handling of connection exceptions."""
        mock_load.return_value = {}
        mock_imap_class.side_effect = Exception("Connection error")

        # Should not raise, just log
        pull_inbox(
            mailbox_key="imap1",
            host="imap.example.com",
            port=993,
            username="user",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
        )

    @patch("app.tasks.imap_tasks.email_already_has_label")
    @patch("app.tasks.imap_tasks.mark_as_processed_with_label")
    @patch("app.tasks.imap_tasks.mark_as_processed_with_star")
    @patch("app.tasks.imap_tasks.fetch_attachments_and_enqueue")
    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    @patch("app.tasks.imap_tasks.save_processed_emails")
    @patch("app.tasks.imap_tasks.settings")
    def test_readonly_mode_skips_gmail_modifications(
        self,
        mock_settings,
        mock_save,
        mock_load,
        mock_imap_class,
        mock_fetch,
        mock_star,
        mock_label,
        mock_has_label,
    ):
        """Test that readonly mode skips starring and labeling Gmail messages."""
        mock_settings.workdir = "/tmp"
        mock_settings.imap_readonly_mode = True
        mock_load.return_value = {}
        mock_has_label.return_value = False
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail

        import email

        msg = email.message.EmailMessage()
        msg["Message-ID"] = "<test@gmail.com>"
        raw_email = msg.as_bytes()

        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [[None, raw_email]])

        pull_inbox(
            mailbox_key="imap2",
            host="imap.gmail.com",
            port=993,
            username="user@gmail.com",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
        )

        # Attachments should still be processed
        mock_fetch.assert_called_once()
        # But no mailbox modifications
        mock_star.assert_not_called()
        mock_label.assert_not_called()
        mock_mail.store.assert_not_called()
        # Processed emails cache should still be updated
        mock_save.assert_called()

    @patch("app.tasks.imap_tasks.fetch_attachments_and_enqueue")
    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    @patch("app.tasks.imap_tasks.save_processed_emails")
    @patch("app.tasks.imap_tasks.settings")
    def test_readonly_mode_skips_delete(self, mock_settings, mock_save, mock_load, mock_imap_class, mock_fetch):
        """Test that readonly mode skips deletion even when delete_after_process is True."""
        mock_settings.workdir = "/tmp"
        mock_settings.imap_readonly_mode = True
        mock_load.return_value = {}
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail

        import email

        msg = email.message.EmailMessage()
        msg["Message-ID"] = "<test@example.com>"
        raw_email = msg.as_bytes()

        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [[None, raw_email]])

        pull_inbox(
            mailbox_key="imap1",
            host="imap.example.com",
            port=993,
            username="user",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=True,
        )

        # Attachments should still be processed
        mock_fetch.assert_called_once()
        # But no mailbox modifications (no delete, no flag changes)
        mock_mail.store.assert_not_called()
        mock_mail.expunge.assert_not_called()
        # Processed emails cache should still be updated
        mock_save.assert_called()

    @patch("app.tasks.imap_tasks.fetch_attachments_and_enqueue")
    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.load_processed_emails")
    @patch("app.tasks.imap_tasks.save_processed_emails")
    @patch("app.tasks.imap_tasks.settings")
    def test_readonly_mode_skips_unseen_flag(self, mock_settings, mock_save, mock_load, mock_imap_class, mock_fetch):
        """Test that readonly mode skips removing Seen flag on non-Gmail."""
        mock_settings.workdir = "/tmp"
        mock_settings.imap_readonly_mode = True
        mock_load.return_value = {}
        mock_mail = MagicMock()
        mock_imap_class.return_value = mock_mail

        import email

        msg = email.message.EmailMessage()
        msg["Message-ID"] = "<test@example.com>"
        raw_email = msg.as_bytes()

        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [[None, raw_email]])

        pull_inbox(
            mailbox_key="imap1",
            host="imap.example.com",
            port=993,
            username="user",
            password=_TEST_CREDENTIAL,
            use_ssl=True,
            delete_after_process=False,
        )

        # No flag changes in readonly mode
        mock_mail.store.assert_not_called()


@pytest.mark.unit
class TestFetchAttachmentsExtended:
    """Extended tests for fetch_attachments_and_enqueue function."""

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_handles_multipart_messages(self, mock_convert, mock_process):
        """Test that multipart messages are skipped correctly."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg.set_content("Body text")

        result = fetch_attachments_and_enqueue(msg)

        # No attachments, should return False
        assert result is False

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_pdf_by_extension_with_wrong_mime(self, mock_convert, mock_process, tmp_path):
        """Test that PDFs are accepted by extension even with wrong MIME type."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg.add_attachment(
            b"%PDF-1.4",
            maintype="application",
            subtype="octet-stream",  # Wrong MIME type
            filename="document.pdf",  # But correct extension
        )

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            result = fetch_attachments_and_enqueue(msg)

        assert result is True
        mock_process.delay.assert_called_once()
        mock_convert.delay.assert_not_called()

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_processes_excel_file(self, mock_convert, mock_process, tmp_path):
        """Test that Excel files are sent for conversion."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg.add_attachment(
            b"excel content",
            maintype="application",
            subtype="vnd.ms-excel",
            filename="spreadsheet.xls",
        )

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            result = fetch_attachments_and_enqueue(msg)

        assert result is True
        mock_convert.delay.assert_called_once()
        mock_process.delay.assert_not_called()

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_processes_powerpoint_file(self, mock_convert, mock_process, tmp_path):
        """Test that PowerPoint files are sent for conversion."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg.add_attachment(
            b"ppt content",
            maintype="application",
            subtype="vnd.ms-powerpoint",
            filename="presentation.ppt",
        )

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            result = fetch_attachments_and_enqueue(msg)

        assert result is True
        mock_convert.delay.assert_called_once()

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_processes_text_file(self, mock_convert, mock_process, tmp_path):
        """Test that text files are sent for conversion."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg.add_attachment(
            b"plain text content",
            maintype="text",
            subtype="plain",
            filename="document.txt",
        )

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            result = fetch_attachments_and_enqueue(msg)

        assert result is True
        mock_convert.delay.assert_called_once()

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_processes_csv_file(self, mock_convert, mock_process, tmp_path):
        """Test that CSV files are sent for conversion."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg.add_attachment(
            b"col1,col2\nval1,val2",
            maintype="text",
            subtype="csv",
            filename="data.csv",
        )

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            result = fetch_attachments_and_enqueue(msg)

        assert result is True
        mock_convert.delay.assert_called_once()

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_processes_rtf_file(self, mock_convert, mock_process, tmp_path):
        """Test that RTF files are sent for conversion."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg.add_attachment(
            b"{\\rtf1 content}",
            maintype="application",
            subtype="rtf",
            filename="document.rtf",
        )

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            result = fetch_attachments_and_enqueue(msg)

        assert result is True
        mock_convert.delay.assert_called_once()

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_attachment_without_filename(self, mock_convert, mock_process):
        """Test that attachments without filename are skipped."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        # Add a part without filename
        msg.add_attachment(b"content", maintype="application", subtype="pdf")
        # Remove the filename header
        for part in msg.iter_parts():
            if part.get_filename():
                part.del_param("filename", header="content-disposition")

        result = fetch_attachments_and_enqueue(msg)

        assert result is False
        mock_process.delay.assert_not_called()
        mock_convert.delay.assert_not_called()


@pytest.mark.unit
class TestLoadProcessedEmailsEdgeCases:
    """Extended tests for load_processed_emails edge cases."""

    @patch("app.tasks.imap_tasks.CACHE_FILE", "/tmp/test_invalid.json")
    def test_handles_invalid_json(self):
        """Test that invalid JSON is handled gracefully."""
        # Write invalid JSON to the file
        with open("/tmp/test_invalid.json", "w") as f:
            f.write("{ invalid json")

        result = load_processed_emails()
        assert result == {}

        # Clean up
        if os.path.exists("/tmp/test_invalid.json"):
            os.remove("/tmp/test_invalid.json")


@pytest.mark.unit
class TestEmailAlreadyHasLabelExtended:
    """Extended tests for email_already_has_label."""

    def test_handles_integer_msg_id(self):
        """Test that integer msg_id is converted to bytes."""
        mock_mail = MagicMock()
        mock_mail.fetch.return_value = ("OK", [(None, b'"Ingested"')])

        result = email_already_has_label(mock_mail, 123, "Ingested")

        # Should convert int to bytes
        mock_mail.fetch.assert_called_once()
        assert result is True

    def test_handles_empty_label_data(self):
        """Test handling when label data is empty."""
        mock_mail = MagicMock()
        mock_mail.fetch.return_value = ("OK", [])

        result = email_already_has_label(mock_mail, b"1", "Ingested")
        assert result is False


@pytest.mark.unit
class TestGetCapabilitiesEdgeCases:
    """Test edge cases for get_capabilities function."""

    def test_get_capabilities_with_failed_response(self):
        """Test get_capabilities when server returns error."""
        mock_mail = MagicMock()
        mock_mail.capability.return_value = ("NO", None)

        result = get_capabilities(mock_mail)
        assert result == []

    def test_get_capabilities_with_empty_data(self):
        """Test get_capabilities with empty capability data."""
        mock_mail = MagicMock()
        mock_mail.capability.return_value = ("OK", [b""])

        result = get_capabilities(mock_mail)
        assert isinstance(result, list)


@pytest.mark.unit
class TestFindAllMailXlistEdgeCases:
    """Test edge cases for find_all_mail_xlist function."""

    def test_find_all_mail_xlist_no_allmail_flag(self):
        """Test XLIST when no folder has ALLMAIL flag."""
        mock_mail = MagicMock()
        mock_mail._new_tag.return_value = b"A001"
        # Simulate responses without ALLMAIL flag
        mock_mail.readline.side_effect = [
            b'* XLIST (\\HasNoChildren) "/" "INBOX"\r\n',
            b"A001 OK XLIST completed\r\n",
        ]

        result = find_all_mail_xlist(mock_mail)
        assert result is None

    def test_find_all_mail_xlist_with_valid_allmail(self):
        """Test XLIST when folder has ALLMAIL flag."""
        mock_mail = MagicMock()
        mock_mail._new_tag.return_value = b"A001"
        # Simulate response with ALLMAIL flag
        mock_mail.readline.side_effect = [
            b'* XLIST (\\AllMail \\HasNoChildren) "/" "[Gmail]/All Mail"\r\n',
            b"A001 OK XLIST completed\r\n",
        ]

        result = find_all_mail_xlist(mock_mail)
        assert result == "[Gmail]/All Mail"


@pytest.mark.unit
class TestAcquireReleaseLockEdgeCases:
    """Test edge cases for lock acquisition and release."""

    @patch("app.tasks.imap_tasks.redis_client")
    def test_acquire_lock_when_already_held(self, mock_redis):
        """Test lock acquisition when lock is already held."""
        mock_redis.setnx.return_value = False

        result = acquire_lock()
        assert result is False
        # Should not call expire if lock not acquired
        mock_redis.expire.assert_not_called()

    @patch("app.tasks.imap_tasks.redis_client")
    def test_release_lock_always_attempts_delete(self, mock_redis):
        """Test that release_lock always attempts to delete the key."""
        release_lock()
        mock_redis.delete.assert_called_once()


@pytest.mark.unit
class TestPullInboxEdgeCases:
    """Test edge cases for pull_inbox function."""

    @patch("app.tasks.imap_tasks.load_processed_emails")
    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.settings")
    def test_pull_inbox_search_failed_status(self, mock_settings, mock_imap_class, mock_load):
        """Test pull_inbox when search returns non-OK status."""
        mock_settings.workdir = "/tmp"
        mock_load.return_value = {}

        mock_mail = MagicMock()
        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("NO", [])  # Search failed
        mock_imap_class.return_value = mock_mail

        # Should handle gracefully and not raise
        pull_inbox("test", "imap.example.com", 993, "user", "pass", True, False)

        mock_mail.close.assert_called_once()
        mock_mail.logout.assert_called_once()

    @patch("app.tasks.imap_tasks.load_processed_emails")
    @patch("app.tasks.imap_tasks.save_processed_emails")
    @patch("app.tasks.imap_tasks.fetch_attachments_and_enqueue")
    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.settings")
    def test_pull_inbox_email_without_message_id(
        self, mock_settings, mock_imap_class, mock_fetch, mock_save, mock_load
    ):
        """Test that emails without Message-ID are skipped."""
        mock_settings.workdir = "/tmp"
        mock_load.return_value = {}

        mock_mail = MagicMock()
        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b"1"])

        # Create email without Message-ID header
        email_without_id = EmailMessage()
        email_without_id["Subject"] = "Test"
        raw_email = email_without_id.as_bytes()

        mock_mail.fetch.return_value = ("OK", [(None, raw_email)])
        mock_imap_class.return_value = mock_mail

        pull_inbox("test", "imap.example.com", 993, "user", "pass", True, False)

        # Should skip processing since no Message-ID
        mock_fetch.assert_not_called()

    @patch("app.tasks.imap_tasks.load_processed_emails")
    @patch("app.tasks.imap_tasks.imaplib.IMAP4_SSL")
    @patch("app.tasks.imap_tasks.settings")
    def test_pull_inbox_fetch_failed_status(self, mock_settings, mock_imap_class, mock_load):
        """Test pull_inbox when fetch returns non-OK status."""
        mock_settings.workdir = "/tmp"
        mock_load.return_value = {}

        mock_mail = MagicMock()
        mock_mail.login.return_value = ("OK", [])
        mock_mail.select.return_value = ("OK", [])
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("NO", [])  # Fetch failed
        mock_imap_class.return_value = mock_mail

        # Should handle gracefully
        pull_inbox("test", "imap.example.com", 993, "user", "pass", True, False)

        mock_mail.close.assert_called_once()


@pytest.mark.unit
class TestMarkAsProcessedFunctions:
    """Test mark_as_processed_with_star and mark_as_processed_with_label functions."""

    def test_mark_as_processed_with_star_handles_exception(self):
        """Test that star marking handles exceptions gracefully."""
        mock_mail = MagicMock()
        mock_mail.store.side_effect = Exception("Connection error")

        # Should not raise, just log error
        mark_as_processed_with_star(mock_mail, b"1")

    def test_mark_as_processed_with_label_handles_exception(self):
        """Test that label marking handles exceptions gracefully."""
        mock_mail = MagicMock()
        mock_mail.store.side_effect = Exception("Connection error")

        # Should not raise, just log error
        mark_as_processed_with_label(mock_mail, b"1", "Ingested")


@pytest.mark.unit
class TestEmailAlreadyHasLabelExceptions:
    """Test exception handling in email_already_has_label."""

    def test_email_already_has_label_fetch_exception(self):
        """Test that fetch exceptions are handled gracefully."""
        mock_mail = MagicMock()
        mock_mail.fetch.side_effect = Exception("Fetch failed")

        result = email_already_has_label(mock_mail, b"1", "Ingested")

        # Should return False on error
        assert result is False


# ---------------------------------------------------------------------------
# Tests for multi-tenant IMAP user integration polling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFetchAttachmentsOwnerIdPassthrough:
    """Test that fetch_attachments_and_enqueue forwards owner_id correctly."""

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_pdf_attachment_forwards_owner_id(self, mock_convert, mock_process, tmp_path):
        """PDF attachments should forward owner_id to process_document."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf", filename="doc.pdf")

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            result = fetch_attachments_and_enqueue(msg, owner_id="user-42")

        assert result is True
        mock_process.delay.assert_called_once()
        call_kwargs = mock_process.delay.call_args
        assert call_kwargs.kwargs.get("owner_id") == "user-42"

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_non_pdf_attachment_forwards_owner_id(self, mock_convert, mock_process, tmp_path):
        """Non-PDF attachments should forward owner_id to convert_to_pdf."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg.add_attachment(
            b"excel content",
            maintype="application",
            subtype="vnd.ms-excel",
            filename="spreadsheet.xls",
        )

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            result = fetch_attachments_and_enqueue(msg, owner_id="user-99")

        assert result is True
        mock_convert.delay.assert_called_once()
        call_kwargs = mock_convert.delay.call_args
        assert call_kwargs.kwargs.get("owner_id") == "user-99"

    @patch("app.tasks.imap_tasks.process_document")
    @patch("app.tasks.imap_tasks.convert_to_pdf")
    def test_no_owner_id_defaults_to_none(self, mock_convert, mock_process, tmp_path):
        """When owner_id is not provided, it defaults to None."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf", filename="doc.pdf")

        with patch("app.tasks.imap_tasks.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            fetch_attachments_and_enqueue(msg)

        call_kwargs = mock_process.delay.call_args
        assert call_kwargs.kwargs.get("owner_id") is None


@pytest.mark.unit
class TestPullUserIntegrationImap:
    """Tests for _pull_user_integration_imap() multi-tenant IMAP polling."""

    @patch("app.tasks.imap_tasks._get_db_session")
    @patch("app.tasks.imap_tasks.pull_inbox")
    def test_polls_active_imap_integrations(self, mock_pull, mock_session_factory):
        """Active IMAP integrations should be polled with correct owner_id."""
        from app.tasks.imap_tasks import _pull_user_integration_imap

        mock_integ = MagicMock()
        mock_integ.id = 10
        mock_integ.owner_id = "owner-abc"
        mock_integ.config = '{"host": "imap.example.com", "port": 993, "username": "user@test.com", "use_ssl": true}'
        mock_integ.credentials = "enc:encrypted"
        mock_integ.is_active = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_integ]
        mock_session_factory.return_value = mock_db

        with patch("app.utils.encryption.decrypt_value", return_value='{"password": "secret"}'):
            _pull_user_integration_imap()

        mock_pull.assert_called_once()
        call_kwargs = mock_pull.call_args
        assert call_kwargs.kwargs.get("owner_id") == "owner-abc"
        assert call_kwargs.kwargs.get("host") == "imap.example.com"
        assert call_kwargs.kwargs.get("password") == "secret"  # noqa: S105

    @patch("app.tasks.imap_tasks._get_db_session")
    @patch("app.tasks.imap_tasks.pull_inbox")
    def test_skips_incomplete_config(self, mock_pull, mock_session_factory):
        """Integrations missing host/username/password should be skipped."""
        from app.tasks.imap_tasks import _pull_user_integration_imap

        mock_integ = MagicMock()
        mock_integ.id = 11
        mock_integ.owner_id = "owner-xyz"
        mock_integ.config = '{"host": "", "port": 993, "username": ""}'
        mock_integ.credentials = None
        mock_integ.is_active = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_integ]
        mock_session_factory.return_value = mock_db

        _pull_user_integration_imap()

        mock_pull.assert_not_called()

    @patch("app.tasks.imap_tasks._get_db_session")
    @patch("app.tasks.imap_tasks.pull_inbox")
    def test_handles_connection_failure_gracefully(self, mock_pull, mock_session_factory):
        """Connection failures should be recorded but not crash the loop."""
        from app.tasks.imap_tasks import _pull_user_integration_imap

        mock_integ = MagicMock()
        mock_integ.id = 12
        mock_integ.owner_id = "owner-fail"
        mock_integ.config = '{"host": "bad.host", "port": 993, "username": "u@x.com", "use_ssl": true}'
        mock_integ.credentials = "enc:encrypted"
        mock_integ.is_active = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_integ]
        mock_session_factory.return_value = mock_db

        mock_pull.side_effect = Exception("Connection refused")

        with patch("app.utils.encryption.decrypt_value", return_value='{"password": "p"}'):
            # Should not raise
            _pull_user_integration_imap()

        # last_error should be recorded
        assert mock_integ.last_error is not None
        assert "Connection refused" in mock_integ.last_error
        mock_db.commit.assert_called()

    @patch("app.tasks.imap_tasks._get_db_session")
    def test_handles_db_failure_gracefully(self, mock_session_factory):
        """Database failures should be caught without crashing."""
        from app.tasks.imap_tasks import _pull_user_integration_imap

        mock_session_factory.side_effect = Exception("DB unavailable")
        # Should not raise
        _pull_user_integration_imap()

    @patch("app.tasks.imap_tasks._get_db_session")
    @patch("app.tasks.imap_tasks.pull_inbox")
    def test_records_last_used_at_on_success(self, mock_pull, mock_session_factory):
        """Successful polling should update last_used_at and clear last_error."""
        from app.tasks.imap_tasks import _pull_user_integration_imap

        mock_integ = MagicMock()
        mock_integ.id = 13
        mock_integ.owner_id = "owner-ok"
        mock_integ.config = '{"host": "imap.ok.com", "port": 993, "username": "ok@ok.com", "use_ssl": true}'
        mock_integ.credentials = "enc:encrypted"
        mock_integ.last_error = "previous error"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_integ]
        mock_session_factory.return_value = mock_db

        with patch("app.utils.encryption.decrypt_value", return_value='{"password": "ok"}'):
            _pull_user_integration_imap()

        assert mock_integ.last_error is None
        assert mock_integ.last_used_at is not None

    @patch("app.tasks.imap_tasks._get_db_session")
    @patch("app.tasks.imap_tasks.pull_inbox")
    def test_passes_gmail_apply_labels_config_to_pull_inbox(self, mock_pull, mock_session_factory):
        """gmail_apply_labels config should be forwarded to pull_inbox."""
        from app.tasks.imap_tasks import _pull_user_integration_imap

        mock_integ = MagicMock()
        mock_integ.id = 14
        mock_integ.owner_id = "owner-gmail"
        mock_integ.config = (
            '{"host": "imap.gmail.com", "port": 993, "username": "u@gmail.com",'
            ' "use_ssl": true, "gmail_apply_labels": false}'
        )
        mock_integ.credentials = "enc:encrypted"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_integ]
        mock_session_factory.return_value = mock_db

        with patch("app.utils.encryption.decrypt_value", return_value='{"password": "p"}'):
            _pull_user_integration_imap()

        mock_pull.assert_called_once()
        call_kwargs = mock_pull.call_args
        assert call_kwargs.kwargs.get("gmail_apply_labels") is False

    @patch("app.tasks.imap_tasks._get_db_session")
    @patch("app.tasks.imap_tasks.pull_inbox")
    def test_gmail_apply_labels_defaults_to_true(self, mock_pull, mock_session_factory):
        """Config without gmail_apply_labels should default to True."""
        from app.tasks.imap_tasks import _pull_user_integration_imap

        mock_integ = MagicMock()
        mock_integ.id = 15
        mock_integ.owner_id = "owner-gmail2"
        mock_integ.config = '{"host": "imap.gmail.com", "port": 993, "username": "u@gmail.com", "use_ssl": true}'
        mock_integ.credentials = "enc:encrypted"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_integ]
        mock_session_factory.return_value = mock_db

        with patch("app.utils.encryption.decrypt_value", return_value='{"password": "p"}'):
            _pull_user_integration_imap()

        mock_pull.assert_called_once()
        call_kwargs = mock_pull.call_args
        assert call_kwargs.kwargs.get("gmail_apply_labels") is True


@pytest.mark.unit
class TestPullAllInboxesCallsIntegrations:
    """Test that pull_all_inboxes calls both legacy and new integration polling."""

    @patch("app.tasks.imap_tasks._pull_user_integration_imap")
    @patch("app.tasks.imap_tasks._pull_user_imap_accounts")
    @patch("app.tasks.imap_tasks.check_and_pull_mailbox")
    @patch("app.tasks.imap_tasks.acquire_lock", return_value=True)
    @patch("app.tasks.imap_tasks.release_lock")
    def test_calls_both_legacy_and_integration_polling(
        self, mock_release, mock_lock, mock_check, mock_legacy, mock_integ
    ):
        """pull_all_inboxes should call both _pull_user_imap_accounts and _pull_user_integration_imap."""
        pull_all_inboxes()
        mock_legacy.assert_called_once()
        mock_integ.assert_called_once()
