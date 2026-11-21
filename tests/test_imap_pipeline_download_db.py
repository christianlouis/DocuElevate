"""Database-level fencing checks for IMAP download claims.

These tests deliberately exercise two independent SQLAlchemy sessions.  The
process-local lock in the worker is not a correctness boundary.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import imap_pipeline_download as downloader
from app.database import Base
from app.models import ImapMessageLedger


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
