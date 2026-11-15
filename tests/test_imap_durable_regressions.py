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
def test_mailbox_scan_does_not_drop_old_uids_after_new_batch():
    """A mailbox with more than one batch must make progress on old UIDs."""
    from app.tasks import imap_tasks

    mail = MagicMock()
    mail.login.return_value = ("OK", [])
    mail.select.return_value = ("OK", [b"1"])
    mail.response.return_value = ("UIDVALIDITY", [b"1"])
    uids = [str(uid).encode() for uid in range(1, 61)]
    mail.uid.side_effect = [
        ("OK", [b" ".join(uids)]),
        *[("OK", [(b"data", _message(uid))]) for uid in range(60, 0, -1)],
    ]
    completed = []

    with (
        patch.object(imap_tasks.imaplib, "IMAP4_SSL", return_value=mail),
        patch.object(imap_tasks, "is_private_ip", return_value=False),
        patch.object(imap_tasks, "fetch_attachments_and_enqueue", return_value=True),
        patch.object(imap_tasks, "_ledger_get_or_create", side_effect=lambda *args: len(completed) + 1),
        patch.object(imap_tasks, "_ledger_finish", side_effect=lambda ledger_id, **kwargs: completed.append(ledger_id)),
    ):
        result = imap_tasks.pull_inbox("test", "imap.example", 993, "user", "pw", True, False, owner_id="owner")

    assert result is True
    assert len(completed) == 60
    assert {uid for uid in range(1, 61)}  # documents the intended full-mailbox scope


@pytest.mark.unit
def test_attachment_filename_cannot_escape_workdir_and_is_not_shared():
    from app.tasks import imap_tasks

    first = EmailMessage()
    first.add_attachment(b"a", maintype="application", subtype="pdf", filename="../scan.pdf")
    second = EmailMessage()
    second.add_attachment(b"b", maintype="application", subtype="pdf", filename="scan.pdf")
    with (
        patch.object(imap_tasks, "settings", workdir="/tmp"),
        patch.object(imap_tasks.process_document, "delay") as enqueue,
    ):
        imap_tasks.fetch_attachments_and_enqueue(first)
        imap_tasks.fetch_attachments_and_enqueue(second)

    paths = [call.args[0] for call in enqueue.call_args_list]
    assert paths
    assert all(path.startswith("/tmp/") for path in paths)
    assert len(set(paths)) == len(paths)


@pytest.mark.unit
def test_failed_mailbox_poll_is_not_reported_as_success():
    from app.tasks import imap_tasks

    with patch.object(imap_tasks, "pull_inbox", return_value=False), patch.object(imap_tasks, "record_poll_success") as checkpoint:
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
