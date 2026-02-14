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
