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
def test_metadata_fast_path_completes_200_plain_messages_and_advances_cursor(db_session):
    from app.models import ImapMessageLedger, ImapScanCursor
    from app.tasks import imap_tasks

    factory = sessionmaker(bind=db_session.get_bind())
    uids = list(range(1, 201))
    mail = _mail_for_uids(uids)
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
        patch.object(imap_tasks.imaplib, "IMAP4_SSL", return_value=mail),
        patch.object(imap_tasks, "is_private_ip", return_value=False),
        patch.object(imap_tasks.settings, "imap_readonly_mode", False),
    ):
        assert imap_tasks.pull_inbox("test", "imap.example", 993, "user", "pw", True, False)

    assert metadata_fetches == [",".join(str(uid) for uid in uids)]
    assert payload_fetches == []
    with factory() as db:
        assert db.query(ImapMessageLedger).filter_by(state="completed").count() == 200
        assert db.query(ImapScanCursor).one().last_uid == 200


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
def test_requested_mailbox_mutation_disables_metadata_completion(db_session):
    from app.tasks import imap_tasks

    factory = sessionmaker(bind=db_session.get_bind())
    mail = _mail_for_uids([1])
    payload_fetches: list[str] = []

    def imap_command(command, *args):
        if command == "search":
            return "OK", [b"1"]
        if command == "fetch" and args[1] == "(UID BODYSTRUCTURE)":
            raise AssertionError("mutation-eligible polling must not complete from metadata")
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
