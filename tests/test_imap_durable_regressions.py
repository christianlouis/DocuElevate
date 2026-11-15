"""Regression tests for resumable IMAP ingestion.

These tests deliberately exercise the mailbox boundary (UIDs and leases), rather
than the downstream document pipeline.  They are kept separate from the older
IMAP tests so the production fixes can evolve without weakening the legacy
coverage.
"""

from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker


def _message(uid: int, filename: str = "scan.pdf") -> bytes:
    message = EmailMessage()
    message["Message-ID"] = f"<uid-{uid}@example.test>"
    message.set_content("scan")
    message.add_attachment(b"%PDF-1.7", maintype="application", subtype="pdf", filename=filename)
    return message.as_bytes()


@pytest.mark.unit
def test_lock_uses_atomic_ttl_and_owner_token():
    from app.tasks import imap_tasks

    redis = MagicMock()
    redis.set.return_value = True
    with patch.object(imap_tasks, "redis_client", redis):
        token = imap_tasks.acquire_lock()

    assert token and token != "locked"
    redis.set.assert_called_once_with("imap_lock", token, nx=True, ex=imap_tasks.LOCK_EXPIRE)
    redis.ttl.assert_not_called()


@pytest.mark.unit
def test_legacy_permanent_lock_is_recovered_with_a_bounded_new_lease():
    from app.tasks import imap_tasks

    redis = MagicMock()
    redis.set.return_value = False
    redis.ttl.return_value = -1
    redis.eval.return_value = 1
    with patch.object(imap_tasks, "redis_client", redis):
        token = imap_tasks.acquire_lock()
        imap_tasks.release_lock(token)
    assert token and token != "locked"
    recovery, release = redis.eval.call_args_list
    assert recovery.args[1:] == (1, imap_tasks.LOCK_KEY, token, imap_tasks.LOCK_EXPIRE)
    assert "== 'locked'" in recovery.args[0]
    assert "== -1" in recovery.args[0]
    assert release.args[1:] == (1, imap_tasks.LOCK_KEY, token)
    assert "== ARGV[1]" in release.args[0]
    assert imap_tasks.pull_all_inboxes.soft_time_limit < imap_tasks.pull_all_inboxes.time_limit < imap_tasks.LOCK_EXPIRE


@pytest.mark.unit
def test_soft_timeout_releases_own_lock_and_is_not_suppressed():
    from celery.exceptions import SoftTimeLimitExceeded

    from app.tasks import imap_tasks

    with (
        patch.object(imap_tasks, "acquire_lock", return_value="our-token"),
        patch.object(imap_tasks, "release_lock") as release,
        patch.object(imap_tasks, "reconcile_imap_intakes", side_effect=SoftTimeLimitExceeded),
    ):
        with pytest.raises(SoftTimeLimitExceeded):
            imap_tasks.pull_all_inboxes.run()
    release.assert_called_once_with("our-token")


@pytest.mark.unit
def test_mailbox_scan_does_not_drop_old_uids_after_new_batch(db_session):
    """Read and old mail survives catch-up batching and process restarts."""
    from app.models import ImapMessageLedger
    from app.tasks import imap_tasks

    factory = sessionmaker(bind=db_session.get_bind())
    mail = MagicMock()
    mail.login.return_value = ("OK", [])
    mail.select.return_value = ("OK", [b"60"])
    mail.response.return_value = ("UIDVALIDITY", [b"1"])
    fetched = []

    def imap_command(command, *args):
        if command == "search":
            assert args == (None, "ALL")
            return "OK", [b" ".join(str(uid).encode() for uid in range(1, 61))]
        assert command == "fetch"
        assert args[1] == "(BODY.PEEK[])"
        uid = int(args[0])
        fetched.append(uid)
        message = EmailMessage()
        message["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"
        message["Message-ID"] = f"<uid-{uid}@example.test>"
        message.set_content("old scan")
        message.add_attachment(b"%PDF-1.7", maintype="application", subtype="pdf", filename="scan.pdf")
        return "OK", [(b"FLAGS (\\Seen)", message.as_bytes())]

    mail.uid.side_effect = imap_command
    with (
        patch.object(imap_tasks, "_get_db_session", factory),
        patch.object(imap_tasks.imaplib, "IMAP4_SSL", return_value=mail),
        patch.object(imap_tasks, "is_private_ip", return_value=False),
        patch.object(imap_tasks, "fetch_attachments_and_enqueue", return_value=True),
    ):
        for expected in (50, 60, 60):
            assert imap_tasks.pull_inbox("test", "imap.example", 993, "user", "pw", True, False, owner_id="owner")
            assert len(fetched) == expected
    assert fetched == list(range(1, 61))
    with factory() as db:
        assert db.query(ImapMessageLedger).filter_by(state="completed").count() == 60


@pytest.mark.unit
def test_failed_old_message_does_not_starve_new_mail_and_is_retried(db_session):
    from app.models import ImapMessageLedger
    from app.tasks import imap_tasks

    factory = sessionmaker(bind=db_session.get_bind())
    mail = MagicMock()
    mail.select.return_value = ("OK", [b"3"])
    mail.response.return_value = ("UIDVALIDITY", [b"9"])
    fetched = []
    fail = True

    def imap_command(command, *args):
        if command == "search":
            return "OK", [b"1 2 3"]
        uid = int(args[0])
        fetched.append(uid)
        if uid == 1 and fail:
            return "NO", []
        return "OK", [(b"data", _message(uid))]

    mail.uid.side_effect = imap_command
    with (
        patch.object(imap_tasks, "_get_db_session", factory),
        patch.object(imap_tasks, "POLL_BATCH_SIZE", 2),
        patch.object(imap_tasks.imaplib, "IMAP4_SSL", return_value=mail),
        patch.object(imap_tasks, "is_private_ip", return_value=False),
        patch.object(imap_tasks, "fetch_attachments_and_enqueue", return_value=True),
    ):
        assert not imap_tasks.pull_inbox("test", "imap.example", 993, "user", "pw", True, False)
        fail = False
        assert imap_tasks.pull_inbox("test", "imap.example", 993, "user", "pw", True, False)
    assert fetched == [1, 2, 1, 3]
    with factory() as db:
        assert db.query(ImapMessageLedger).filter_by(state="completed").count() == 3


@pytest.mark.unit
def test_fair_polling_rotates_retries_and_new_mail_when_only_one_attempt_fits(db_session):
    from app.tasks import imap_tasks

    factory = sessionmaker(bind=db_session.get_bind())
    mail = MagicMock()
    mail.select.return_value = ("OK", [b"1"])
    mail.response.return_value = ("UIDVALIDITY", [b"11"])
    fetched = []
    newest_uid = 3
    clock = [0]

    def imap_command(command, *args):
        if command == "search":
            return "OK", [b" ".join(str(uid).encode() for uid in range(1, newest_uid + 1))]
        uid = int(args[0])
        fetched.append(uid)
        if uid in {1, 2, 3}:
            return "NO", []
        return "OK", [(b"data", _message(uid))]

    mail.uid.side_effect = imap_command
    with (
        patch.object(imap_tasks, "_get_db_session", factory),
        patch.object(imap_tasks, "POLL_BATCH_SIZE", 3),
        patch.object(imap_tasks.imaplib, "IMAP4_SSL", return_value=mail),
        patch.object(imap_tasks, "is_private_ip", return_value=False),
        patch.object(imap_tasks, "fetch_attachments_and_enqueue", return_value=True),
        patch.object(imap_tasks.time, "monotonic", side_effect=lambda: clock[0]),
    ):
        # Seed three durable failures before a continuous stream of new mail.
        assert not imap_tasks.pull_inbox("test", "imap.example", 993, "user", "pw", True, False)

        def poll_with_one_attempt():
            clock[0] = 0
            # The fetch flips the clock; the loop may select a batch but gets
            # exactly one attempt before its deadline.
            original_command = mail.uid.side_effect

            def deadline_after_first_attempt(command, *args, _original_command=original_command):
                result = _original_command(command, *args)
                if command == "fetch":
                    clock[0] = 1
                return result

            mail.uid.side_effect = deadline_after_first_attempt
            imap_tasks.pull_inbox("test", "imap.example", 993, "user", "pw", True, False, deadline=1)
            mail.uid.side_effect = original_command

        # With no new UIDs, retries remain eligible and progress.
        poll_with_one_attempt()
        assert fetched[-1] == 1
        for _ in range(12):
            newest_uid += 3
            poll_with_one_attempt()

    assert all(fetched.count(uid) >= 3 for uid in (1, 2, 3))
    assert sum(uid > 3 for uid in fetched) == 6


@pytest.mark.unit
def test_attachment_filename_cannot_escape_workdir_and_is_not_shared(tmp_path):
    from app.tasks import imap_tasks

    first = EmailMessage()
    first.add_attachment(b"a", maintype="application", subtype="pdf", filename="../scan.pdf")
    second = EmailMessage()
    second.add_attachment(b"b", maintype="application", subtype="pdf", filename="scan.pdf")
    with (
        patch.object(imap_tasks, "settings", workdir=str(tmp_path)),
        patch.object(imap_tasks.process_document, "delay") as enqueue,
    ):
        imap_tasks.fetch_attachments_and_enqueue(first)
        imap_tasks.fetch_attachments_and_enqueue(second)

    paths = [call.args[0] for call in enqueue.call_args_list]
    assert paths
    assert all(path.startswith(str(tmp_path) + "/") for path in paths)
    assert len(set(paths)) == len(paths)
    assert all(call.kwargs["original_filename"] == "scan.pdf" for call in enqueue.call_args_list)


@pytest.mark.unit
@pytest.mark.parametrize("value", [None, b"", b"0", b"invalid", b"\xff1", b"4294967296"])
def test_uidvalidity_rejects_non_positive_or_invalid_values(value):
    from app.tasks import imap_tasks

    mail = MagicMock()
    mail.response.return_value = ("UIDVALIDITY", [value])
    assert imap_tasks._extract_uidvalidity(mail, {b"UIDVALIDITY": [None]}) == "unknown"


@pytest.mark.unit
@pytest.mark.parametrize("filename", [".", "..", r"C:\\tmp\\..", "/"])
def test_durable_attachment_normalizes_dot_path_filename(filename):
    from app.tasks import imap_tasks

    message = EmailMessage()
    message.add_attachment(b"a", maintype="application", subtype="pdf", filename=filename)
    with patch("app.tasks.imap_intake.prepare_imap_attachment") as prepare:
        assert imap_tasks.fetch_attachments_and_enqueue(message, ingestion_prefix="owner:mail:1:7")
    assert prepare.call_args.kwargs["filename"] == "attachment"


@pytest.mark.unit
def test_durable_attachment_uses_safe_original_filename():
    from app.tasks import imap_tasks

    message = EmailMessage()
    message.add_attachment(b"a", maintype="application", subtype="pdf", filename="C:\\tmp\\scan.pdf")
    with patch("app.tasks.imap_intake.prepare_imap_attachment") as prepare:
        assert imap_tasks.fetch_attachments_and_enqueue(message, ingestion_prefix="owner:mail:1:7")
    assert prepare.call_args.kwargs["filename"] == "scan.pdf"


@pytest.mark.unit
def test_filtered_message_is_not_modified_or_expunged(db_session):
    from app.models import ImapMessageLedger
    from app.tasks import imap_tasks

    factory = sessionmaker(bind=db_session.get_bind())
    mail = MagicMock()
    mail.login.return_value = ("OK", [])
    mail.select.return_value = ("OK", [b"1"])
    mail.response.return_value = ("UIDVALIDITY", [b"1"])
    message = EmailMessage()
    message["Message-ID"] = "<filtered@example.test>"
    message.add_attachment(b"image", maintype="image", subtype="jpeg", filename="photo.jpg")

    def imap_command(command, *args):
        if command == "search":
            return "OK", [b"1"]
        return "OK", [(b"data", message.as_bytes())]

    mail.uid.side_effect = imap_command
    with (
        patch.object(imap_tasks, "_get_db_session", factory),
        patch.object(imap_tasks.imaplib, "IMAP4_SSL", return_value=mail),
        patch.object(imap_tasks, "is_private_ip", return_value=False),
        patch.object(imap_tasks, "find_all_mail_folder", return_value="[Gmail]/All Mail"),
        patch.object(imap_tasks, "settings", imap_readonly_mode=False),
    ):
        assert imap_tasks.pull_inbox(
            "test", "imap.gmail.com", 993, "user", "pw", True, True, allowed_categories=["pdf"]
        )

    assert not any(call.args[0] == "store" for call in mail.uid.call_args_list)
    mail.expunge.assert_not_called()
    with factory() as db:
        assert db.query(ImapMessageLedger).filter_by(state="completed").count() == 1


@pytest.mark.unit
def test_failed_mailbox_poll_is_not_reported_as_success():
    from app.tasks import imap_tasks

    with (
        patch.object(imap_tasks, "pull_inbox", return_value=False),
        patch.object(imap_tasks, "record_poll_success") as checkpoint,
    ):
        result = imap_tasks.check_and_pull_mailbox("test", "imap.example", 993, "user", "pw", True, False)

    assert result is False
    checkpoint.assert_not_called()


@pytest.mark.unit
def test_ledger_identity_is_uidvalidity_and_owner_scoped(db_session):
    """The same UID may be reused after UIDVALIDITY changes or by another owner."""
    from app.models import ImapMessageLedger

    db_session.add_all(
        [
            ImapMessageLedger(owner_key="owner-a", mailbox_key="mail", uidvalidity="1", uid=7),
            ImapMessageLedger(owner_key="owner-a", mailbox_key="mail", uidvalidity="2", uid=7),
            ImapMessageLedger(owner_key="owner-b", mailbox_key="mail", uidvalidity="1", uid=7),
        ]
    )
    db_session.commit()
    assert db_session.query(ImapMessageLedger).count() == 3
    db_session.add(ImapMessageLedger(owner_key="owner-a", mailbox_key="mail", uidvalidity="1", uid=7))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.unit
def test_document_intake_reservation_is_durable_and_deduplicated(db_session):
    from app.models import DocumentIntake

    row = DocumentIntake(
        principal_id="owner-a",
        idempotency_key="imap:mail:uidvalidity-1:uid-7:part-1",
        source="imap",
        original_filename="scan.pdf",
        local_path="/workdir/intake/scan.pdf",
        state="queued",
    )
    db_session.add(row)
    db_session.commit()
    duplicate = DocumentIntake(
        principal_id="owner-a",
        idempotency_key=row.idempotency_key,
        source="imap",
        original_filename="scan.pdf",
        state="queued",
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
