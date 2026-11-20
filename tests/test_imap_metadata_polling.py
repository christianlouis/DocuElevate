"""Integration coverage for conservative IMAP metadata completion."""

from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker


def _raw_message(uid: int) -> bytes:
    message = EmailMessage()
    message["Message-ID"] = f"<uid-{uid}@example.test>"
    message.set_content("plain message")
    return message.as_bytes()


def _mail_for_uids(uids: list[int]) -> MagicMock:
    mail = MagicMock()
    mail.login.return_value = ("OK", [])
    mail.select.return_value = ("OK", [str(len(uids)).encode()])
    mail.response.side_effect = lambda key: (key, [str(max(uids) + 1).encode() if key == "UIDNEXT" else b"11"])
    return mail


@pytest.mark.unit
@pytest.mark.parametrize("delete_after_process", [False, True])
def test_metadata_fast_path_completes_200_plain_messages_and_advances_cursor(db_session, delete_after_process):
    from app.models import ImapMessageLedger, ImapScanCursor
    from app.tasks import imap_tasks

    factory = sessionmaker(bind=db_session.get_bind())
    uids = list(range(1, 201))
    mail = _mail_for_uids(uids)
    mail.list.return_value = (
        "OK",
        [b'(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"'],
    )
    metadata_fetches: list[str] = []
    payload_fetches: list[str] = []

    def imap_command(command, *args):
        if command == "search":
            return "OK", [b" ".join(str(uid).encode() for uid in uids)]
        if command == "fetch" and args[1] == "(UID BODYSTRUCTURE)":
            metadata_fetches.append(args[0])
            return (
                "OK",
                [
                    f'{uid} (UID {uid} BODYSTRUCTURE ("TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "7BIT" 12 1))'.encode()
                    for uid in uids
                ],
            )
        if command == "fetch" and args[1] == "(BODY.PEEK[])":
            payload_fetches.append(args[0])
            raise AssertionError("proven text-only metadata must not fetch a payload")
        raise AssertionError(f"unexpected IMAP command: {command} {args}")

    mail.uid.side_effect = imap_command
    with (
        patch.object(imap_tasks, "_get_db_session", factory),
        patch.object(imap_tasks, "_historical_payload_admission_available", return_value=False),
        patch.object(imap_tasks.imaplib, "IMAP4_SSL", return_value=mail),
        patch.object(imap_tasks, "is_private_ip", return_value=False),
        patch.object(imap_tasks.settings, "imap_readonly_mode", False),
    ):
        assert imap_tasks.pull_inbox("test", "imap.gmail.com", 993, "user", "pw", True, delete_after_process)

    assert metadata_fetches == [",".join(str(uid) for uid in uids)]
    mail.select.assert_called_once_with('"[Gmail]/All Mail"', readonly=False)
    assert payload_fetches == []
    mail.expunge.assert_not_called()
    assert all(call.args[0] != "store" for call in mail.uid.call_args_list)
    with factory() as db:
        assert db.query(ImapMessageLedger).filter_by(state="completed").count() == 200
        assert db.query(ImapScanCursor).one().last_uid == 200


@pytest.mark.unit
def test_metadata_fetch_can_expire_budget_before_processing_loop(db_session, caplog):
    from app.models import ImapMessageLedger
    from app.tasks import imap_tasks

    factory = sessionmaker(bind=db_session.get_bind())
    mail = _mail_for_uids([1])

    def imap_command(command, *args):
        if command == "search":
            return "OK", [b"1"]
        if command == "fetch" and args[1] == "(UID BODYSTRUCTURE)":
            return "OK", [b'1 (UID 1 BODYSTRUCTURE ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 12 1))']
        raise AssertionError(f"unexpected IMAP command: {command} {args}")

    mail.uid.side_effect = imap_command
    clock = iter([0, 0, 11])
    with (
        patch.object(imap_tasks, "_get_db_session", factory),
        patch.object(imap_tasks, "find_all_mail_folder", return_value="INBOX"),
        patch.object(imap_tasks.imaplib, "IMAP4_SSL", return_value=mail),
        patch.object(imap_tasks, "is_private_ip", return_value=False),
        patch.object(imap_tasks.settings, "imap_readonly_mode", False),
        patch.object(imap_tasks.time, "monotonic", side_effect=lambda: next(clock, 11)),
    ):
        assert imap_tasks.pull_inbox("test", "imap.example.com", 993, "user", "pw", True, False, deadline=10)

    summary = next(record.message for record in caplog.records if "IMAP poll summary" in record.message)
    assert "metadata_completed=0" in summary
    assert "deadline_exhausted=True" in summary
    with factory() as db:
        assert db.query(ImapMessageLedger).filter_by(state="completed").count() == 0


@pytest.mark.unit
def test_metadata_safe_uid_is_not_starved_by_slow_payload_batch(db_session):
    """A safe UID outside the payload batch must complete before the budget ends."""
    from app.models import ImapMessageLedger
    from app.tasks import imap_tasks

    factory = sessionmaker(bind=db_session.get_bind())
    mail = _mail_for_uids(list(range(1, 52)))
    payload_uids: list[int] = []

    def imap_command(command, *args):
        if command == "search":
            return "OK", [b" ".join(str(uid).encode() for uid in range(1, 52))]
        if command == "fetch" and args[1] == "(UID BODYSTRUCTURE)":
            return "OK", [
                *[
                    f'{uid} (UID {uid} BODYSTRUCTURE ("APPLICATION" "PDF" NIL NIL NIL "BASE64" 12))'.encode()
                    for uid in range(1, 51)
                ],
                b'51 (UID 51 BODYSTRUCTURE ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 12 1))',
            ]
        if command == "fetch" and args[1] == "(BODY.PEEK[])":
            uid = int(args[0])
            payload_uids.append(uid)
            elapsed[0] += 1
            return "OK", [(f"{uid} FETCH (BODY[])").encode(), _raw_message(uid)]
        raise AssertionError(f"unexpected IMAP command: {command} {args}")

    mail.uid.side_effect = imap_command
    elapsed = [0]

    def monotonic():
        return elapsed[0]

    with (
        patch.object(imap_tasks, "_get_db_session", factory),
        patch.object(imap_tasks, "find_all_mail_folder", return_value="INBOX"),
        patch.object(imap_tasks.imaplib, "IMAP4_SSL", return_value=mail),
        patch.object(imap_tasks, "is_private_ip", return_value=False),
        patch.object(imap_tasks, "_historical_payload_admission_available", return_value=True),
        patch.object(imap_tasks, "fetch_attachments_and_enqueue", return_value=False),
        patch.object(imap_tasks.settings, "imap_readonly_mode", False),
        patch.object(imap_tasks, "POLL_BATCH_SIZE", 50),
        patch.object(imap_tasks.time, "monotonic", side_effect=monotonic),
    ):
        imap_tasks.pull_inbox("test", "imap.example.com", 993, "user", "pw", True, False, deadline=10)

    assert payload_uids
    with factory() as db:
        assert db.query(ImapMessageLedger).filter_by(uid=51, state="completed").count() == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "metadata_item",
    [
        b'1 FETCH (UID 1 BODYSTRUCTURE ("APPLICATION" "PDF" NIL NIL NIL "BASE64" 12))',
        b'1 FETCH (UID 1 BODYSTRUCTURE ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 12 1)) trailing',
        b"1 FETCH (UID 1 FLAGS (\\Seen))",
    ],
    ids=["attachment", "unknown", "missing-metadata"],
)
def test_unproven_metadata_always_fetches_the_payload(db_session, metadata_item):
    from app.models import ImapMessageLedger
    from app.tasks import imap_tasks

    factory = sessionmaker(bind=db_session.get_bind())
    mail = _mail_for_uids([1])
    payload_fetches: list[str] = []

    def imap_command(command, *args):
        if command == "search":
            return "OK", [b"1"]
        if command == "fetch" and args[1] == "(UID BODYSTRUCTURE)":
            return "OK", [metadata_item]
        if command == "fetch" and args[1] == "(BODY.PEEK[])":
            payload_fetches.append(args[0])
            return "OK", [(b"1 FETCH (BODY[])", _raw_message(1))]
        raise AssertionError(f"unexpected IMAP command: {command} {args}")

    mail.uid.side_effect = imap_command
    with (
        patch.object(imap_tasks, "_get_db_session", factory),
        patch.object(imap_tasks.imaplib, "IMAP4_SSL", return_value=mail),
        patch.object(imap_tasks, "is_private_ip", return_value=False),
        patch.object(imap_tasks, "fetch_attachments_and_enqueue", return_value=False),
        patch.object(imap_tasks.settings, "imap_readonly_mode", False),
    ):
        assert imap_tasks.pull_inbox("test", "imap.example", 993, "user", "pw", True, False)

    assert payload_fetches == [b"1"]
    with factory() as db:
        assert db.query(ImapMessageLedger).filter_by(uid=1, state="completed").count() == 1


@pytest.mark.unit
def test_requested_mailbox_mutation_is_preserved_for_attachment_metadata(db_session):
    from app.tasks import imap_tasks

    factory = sessionmaker(bind=db_session.get_bind())
    mail = _mail_for_uids([1])
    payload_fetches: list[str] = []

    def imap_command(command, *args):
        if command == "search":
            return "OK", [b"1"]
        if command == "fetch" and args[1] == "(UID BODYSTRUCTURE)":
            return "OK", [b'1 (UID 1 BODYSTRUCTURE ("APPLICATION" "PDF" NIL NIL NIL "BASE64" 12))']
        if command == "fetch" and args[1] == "(BODY.PEEK[])":
            payload_fetches.append(args[0])
            return "OK", [(b"1 FETCH (BODY[])", _raw_message(1))]
        if command == "store":
            return "OK", []
        raise AssertionError(f"unexpected IMAP command: {command} {args}")

    mail.uid.side_effect = imap_command
    with (
        patch.object(imap_tasks, "_get_db_session", factory),
        patch.object(imap_tasks.imaplib, "IMAP4_SSL", return_value=mail),
        patch.object(imap_tasks, "is_private_ip", return_value=False),
        patch.object(imap_tasks, "fetch_attachments_and_enqueue", return_value=True),
        patch.object(imap_tasks.settings, "imap_readonly_mode", False),
    ):
        assert imap_tasks.pull_inbox("test", "imap.example", 993, "user", "pw", True, True)

    assert payload_fetches == [b"1"]
    mail.expunge.assert_called_once()
