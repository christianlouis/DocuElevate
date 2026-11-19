import hashlib
import json
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def limit(self, *args):
        return self

    def all(self):
        return self.rows


class _Pipeline:
    def __init__(self, lengths):
        self.lengths = lengths
        self.names = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def llen(self, name):
        self.names.append(name)

    def execute(self):
        return self.lengths


def _broker(lengths):
    broker = MagicMock()
    pipeline = _Pipeline(lengths)
    broker.pipeline.return_value = pipeline
    broker._pipeline = pipeline
    return broker


def _start_admission_patches(imap_tasks, db, broker, *, disk=(0, 0, 10 * 1024**3)):
    patchers = [
        patch.object(imap_tasks, "_get_db_session", return_value=db),
        patch.object(imap_tasks.redis.StrictRedis, "from_url", return_value=broker),
        patch.object(imap_tasks.shutil, "disk_usage", return_value=disk),
    ]
    for patcher in patchers:
        patcher.start()
    return patchers


def _stop(patchers):
    for patcher in reversed(patchers):
        patcher.stop()


@pytest.mark.unit
def test_saturated_intake_admission_blocks_without_broker_read():
    from app.tasks import imap_tasks

    db = MagicMock()
    db.query.return_value = _Query([object()] * (imap_tasks.MAX_UNFINISHED_IMAP_INTAKES + 1))
    with (
        patch.object(imap_tasks, "_get_db_session", return_value=db),
        patch.object(imap_tasks.redis.StrictRedis, "from_url") as redis_from_url,
    ):
        assert not imap_tasks._historical_payload_admission_available()
        redis_from_url.assert_not_called()


@pytest.mark.unit
def test_queue_limit_uses_one_bounded_pipeline_and_blocks_at_limit():
    from app.tasks import imap_tasks

    db = MagicMock()
    db.query.side_effect = [_Query([]), _Query([])]
    broker = _broker([199] + [200] * 9)
    patchers = _start_admission_patches(imap_tasks, db, broker)
    try:
        assert imap_tasks._historical_payload_admission_available()
    finally:
        _stop(patchers)
    assert broker.pipeline.call_count == 1
    assert len(broker._pipeline.names) == 10

    db = MagicMock()
    db.query.side_effect = [_Query([]), _Query([])]
    broker = _broker([200] * 10)
    patchers = _start_admission_patches(imap_tasks, db, broker)
    try:
        assert not imap_tasks._historical_payload_admission_available()
    finally:
        _stop(patchers)


@pytest.mark.unit
def test_disk_or_redis_failure_fails_closed_with_fresh_fakes():
    from app.tasks import imap_tasks

    for broker, disk in [(_broker([0] * 10), OSError("unknown")), (None, (0, 0, 10 * 1024**3))]:
        db = MagicMock()
        db.query.side_effect = [_Query([]), _Query([])]
        patchers = [patch.object(imap_tasks, "_get_db_session", return_value=db)]
        if broker is None:
            patchers.append(patch.object(imap_tasks.redis.StrictRedis, "from_url", side_effect=OSError("redis")))
        else:
            patchers.append(patch.object(imap_tasks.redis.StrictRedis, "from_url", return_value=broker))
        patchers.append(
            patch.object(
                imap_tasks.shutil,
                "disk_usage",
                side_effect=disk if isinstance(disk, Exception) else None,
                return_value=disk,
            )
        )
        for patcher in patchers:
            patcher.start()
        try:
            assert not imap_tasks._historical_payload_admission_available()
        finally:
            _stop(patchers)


@pytest.mark.unit
def test_real_db_capacity_allows_one_unfinished_intake(db_session):
    from app.models import DocumentIntake, ImapMessageLedger, ImapScanCursor
    from app.tasks import imap_tasks

    db_session.add(
        DocumentIntake(
            principal_id="owner",
            idempotency_key="imap-1",
            source="imap",
            original_filename="scan.pdf",
            metadata_json=json.dumps({}),
            state="pending",
        )
    )
    db_session.commit()
    broker = _broker([0] * 10)
    patchers = _start_admission_patches(imap_tasks, db_session, broker)
    try:
        assert imap_tasks._historical_payload_admission_available()
    finally:
        _stop(patchers)
    assert db_session.query(ImapMessageLedger).count() == 0
    assert db_session.query(ImapScanCursor).count() == 0


@pytest.mark.unit
def test_poll_blocked_historical_uid_has_no_ledger_then_ingests_when_allowed(db_session):
    from app.models import ImapMessageLedger, ImapScanCursor
    from app.tasks import imap_tasks

    factory = sessionmaker(bind=db_session.get_bind())
    message = EmailMessage()
    message["Message-ID"] = "<historical@example.test>"
    message.set_content("scan")
    message.add_attachment(b"%PDF-1.7", maintype="application", subtype="pdf", filename="scan.pdf")
    mail = MagicMock()
    mail.select.return_value = ("OK", [b"1"])
    mail.response.side_effect = lambda key: (key, [b"4294967296" if key == "UIDNEXT" else b"1"])

    def uid(command, *args):
        if command == "search":
            return "OK", [b"1"]
        if args[1] == "(UID BODYSTRUCTURE)":
            return "NO", []
        return "OK", [(b"FLAGS (\\Seen)", message.as_bytes())]

    mail.uid.side_effect = uid
    admission = iter((False, True))
    with (
        patch.object(imap_tasks, "_get_db_session", factory),
        patch.object(imap_tasks.imaplib, "IMAP4_SSL", return_value=mail),
        patch.object(imap_tasks, "is_private_ip", return_value=False),
        patch.object(imap_tasks, "_historical_payload_admission_available", side_effect=admission),
        patch.object(imap_tasks, "fetch_attachments_and_enqueue", return_value=True),
    ):
        assert imap_tasks.pull_inbox("test", "imap.example", 993, "user", "pw", True, False, owner_id="owner")
        with factory() as check:
            assert check.query(ImapMessageLedger).count() == 0
            assert check.query(ImapScanCursor).count() == 0
        assert imap_tasks.pull_inbox("test", "imap.example", 993, "user", "pw", True, False, owner_id="owner")

    with factory() as check:
        assert check.query(ImapMessageLedger).filter_by(state="completed").count() == 1
        assert check.query(ImapScanCursor).one().last_uid == 1


@pytest.mark.unit
def test_blocked_history_does_not_starve_fresh_tail_or_durable_retry(db_session):
    from app.models import ImapMessageLedger, ImapScanCursor
    from app.tasks import imap_tasks

    factory = sessionmaker(bind=db_session.get_bind())
    mailbox_key = hashlib.sha256(json.dumps(["", "imap.example", 993, "user", "INBOX"]).encode()).hexdigest()
    db_session.add(
        ImapMessageLedger(
            owner_key="legacy",
            mailbox_key=mailbox_key,
            uidvalidity="44",
            uid=2,
            state="failed",
            attempts=2,
            updated_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
    )
    db_session.commit()
    mail = MagicMock()
    mail.select.return_value = ("OK", [b"50001"])
    mail.response.side_effect = lambda key: (key, [b"50002" if key == "UIDNEXT" else b"44"])
    fetched = []
    message = EmailMessage()
    message["Message-ID"] = "<fairness@example.test>"
    message.set_content("scan")
    message.add_attachment(b"%PDF-1.7", maintype="application", subtype="pdf", filename="scan.pdf")

    def imap_command(command, *args):
        if command == "search":
            return "OK", [b"1 2 50001"]
        if args[1] == "(UID BODYSTRUCTURE)":
            return "NO", []
        fetched.append(int(args[0]))
        return "OK", [(b"data", message.as_bytes())]

    mail.uid.side_effect = imap_command
    with (
        patch.object(imap_tasks, "POLL_BATCH_SIZE", 3),
        patch.object(imap_tasks, "_get_db_session", factory),
        patch.object(imap_tasks.imaplib, "IMAP4_SSL", return_value=mail),
        patch.object(imap_tasks, "is_private_ip", return_value=False),
        patch.object(imap_tasks, "_historical_payload_admission_available", return_value=False),
        patch.object(imap_tasks, "fetch_attachments_and_enqueue", return_value=True),
    ):
        assert imap_tasks.pull_inbox("test", "imap.example", 993, "user", "pw", True, False)

    assert set(fetched) == {2, 50001}
    with factory() as check:
        assert check.query(ImapMessageLedger).filter_by(uid=1).count() == 0
        assert check.query(ImapMessageLedger).filter_by(uid=2, state="completed").count() == 1
        assert check.query(ImapMessageLedger).filter_by(uid=50001, state="completed").count() == 1
        assert check.query(ImapScanCursor).count() == 0
