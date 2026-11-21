"""Database-level fencing checks for IMAP download claims.

These tests deliberately exercise two independent SQLAlchemy sessions.  The
process-local lock in the worker is not a correctness boundary.
"""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import imap_pipeline_download as downloader
from app.database import Base
from app.models import ImapMessageLedger, IntegrationDirection, IntegrationType, UserIntegration


def _factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False), engine


def _row(session, **values):
    row = ImapMessageLedger(
        owner_key="owner", mailbox_key="mailbox", uidvalidity="7", uid=42,
        account_ref="imap1", lane="backlog", state="pending",
        discovery_state="claimed", is_candidate=True, download_attempts=1,
        download_lease_token="fence", download_lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    for key, value in values.items():
        setattr(row, key, value)
    session.add(row)
    session.commit()
    return row


def test_claim_cas_transitions_exact_batch_once():
    Session, _ = _factory()
    first = Session()
    one = _row(first)
    two = _row(first, uid=43)
    ids = [one.id, two.id]
    second = Session()
    assert [r.id for r in downloader._claim_rows(second, "imap1", "backlog", ids, "fence")] == ids
    second.close()
    third = Session()
    assert downloader._claim_rows(third, "imap1", "backlog", ids, "fence") == []
    third.close()
    first.close()


def test_claim_is_all_or_none_for_mixed_token_batch():
    Session, _ = _factory()
    seed = Session()
    one = _row(seed)
    two = _row(seed, uid=43, download_lease_token="other")
    seed.close()
    attempt = Session()
    assert downloader._claim_rows(attempt, "imap1", "backlog", [one.id, two.id], "fence") == []
    attempt.close()
    verify = Session()
    assert [verify.get(ImapMessageLedger, row_id).discovery_state for row_id in (one.id, two.id)] == ["claimed", "claimed"]
    verify.close()


def test_stale_or_expired_claim_has_no_transition():
    Session, _ = _factory()
    seed = Session()
    row = _row(seed, download_lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    seed.close()
    attempt = Session()
    assert downloader._claim_rows(attempt, "imap1", "backlog", [row.id], "fence") == []
    attempt.close()


def test_identity_epoch_is_part_of_claimed_row():
    Session, _ = _factory()
    seed = Session()
    row = _row(seed, mailbox_key="epoch-a", uidvalidity="11")
    seed.close()
    attempt = Session()
    # A downloader receives the persisted row identity; a different epoch is
    # rejected later before payload fetch.  Claiming cannot rewrite it.
    claimed = downloader._claim_rows(attempt, "imap1", "backlog", [row.id], "fence")
    assert claimed[0].mailbox_key == "epoch-a"
    assert claimed[0].uidvalidity == "11"
    attempt.close()


def test_user_integration_resolver_requires_active_imap_source_and_preserves_owner():
    Session, _ = _factory()
    seed = Session()
    seed.add(UserIntegration(owner_id="owner_with_underscores", direction=IntegrationDirection.SOURCE,
                             integration_type=IntegrationType.IMAP, name="mail",
                             config=json.dumps({"host": "imap.example", "username": "u", "port": 993}),
                             credentials=json.dumps({"password": "p"}), is_active=True))
    seed.add(UserIntegration(owner_id="owner_with_underscores", direction=IntegrationDirection.DESTINATION,
                             integration_type=IntegrationType.IMAP, name="wrong", config="{}", credentials="{}", is_active=True))
    seed.commit()
    valid = downloader._account_from_ref(seed, "integration_owner_with_underscores_1")
    assert valid["owner_id"] == "owner_with_underscores"
    assert valid["host"] == "imap.example"
    assert downloader._account_from_ref(seed, "integration_owner_with_underscores_2") is None
    seed.close()


def test_download_batch_marks_success_and_retryable_failure(monkeypatch):
    Session, _ = _factory()
    seed = Session()
    first = _row(seed, uid=42)
    second = _row(seed, uid=43)
    ids = [first.id, second.id]
    seed.close()
    monkeypatch.setattr(downloader, "SessionLocal", Session)
    monkeypatch.setattr(downloader, "_free_space_ok", lambda: True)
    monkeypatch.setattr(downloader, "_account_from_ref", lambda *_: {"owner_id": "owner", "host": "imap.example", "port": 993, "username": "u", "password": "p", "use_ssl": True, "profile_id": None})
    monkeypatch.setattr(downloader, "is_private_ip", lambda _: False)
    monkeypatch.setattr(downloader, "find_all_mail_folder", lambda _: "INBOX")
    monkeypatch.setattr(downloader, "_resolve_categories_for_profile", lambda *_: [])
    monkeypatch.setattr(downloader, "get_allowed_types_for_categories", lambda *_: (frozenset({"application/pdf"}), frozenset({".pdf"})))
    monkeypatch.setattr(downloader, "_extract_uidvalidity", lambda *_: "7")
    accepted = []
    def enqueue(*args, **kwargs):
        accepted.append(kwargs["ingestion_prefix"])
        if len(accepted) == 2:
            raise RuntimeError("staging failure")
        return True
    monkeypatch.setattr(downloader, "fetch_attachments_and_enqueue", enqueue)
    class Mail:
        def login(self, *_): pass
        def select(self, *_args, **_kwargs): return "OK", {"UIDVALIDITY": [b"7"]}
        def uid(self, command, uid, *_args):
            assert command == "fetch"
            return "OK", [(b"header", b"From: a@example\nMessage-ID: <x>\n\nbody")]
    monkeypatch.setattr(downloader.imaplib, "IMAP4_SSL", lambda *args, **kwargs: Mail())
    monkeypatch.setattr(downloader, "_shutdown_imap_connection", lambda *_: None)
    monkeypatch.setattr(downloader, "_mailbox_key", lambda *_: "mailbox")
    result = downloader.download_claimed_batch("imap1", "backlog", ids, "fence")
    assert result["downloaded"] == 1
    verify = Session()
    states = [verify.get(ImapMessageLedger, row_id) for row_id in ids]
    assert states[0].state == "completed"
    assert states[1].state == "retry_wait"
    assert states[1].next_download_at > datetime.now(timezone.utc)
    assert accepted[0] == "owner:mailbox:7:42"
    verify.close()


def test_disk_pause_is_durable_and_does_not_connect(monkeypatch):
    Session, _ = _factory()
    seed = Session()
    row = _row(seed)
    row_id = row.id
    seed.close()
    monkeypatch.setattr(downloader, "SessionLocal", Session)
    monkeypatch.setattr(downloader, "_free_space_ok", lambda: False)
    monkeypatch.setattr(downloader.imaplib, "IMAP4_SSL", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network")))
    result = downloader.download_claimed_batch("imap1", "backlog", [row_id], "fence")
    assert result["deferred"] == 1
    verify = Session()
    persisted = verify.get(ImapMessageLedger, row_id)
    assert persisted.state == "retry_wait"
    assert persisted.next_download_at > datetime.now(timezone.utc)
    verify.close()
