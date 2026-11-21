"""File-backed SQLite concurrency contracts for the durable IMAP outbox."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import imap_pipeline
from app import imap_pipeline_download as downloader
from app.database import Base
from app.models import ImapMessageLedger

pytestmark = pytest.mark.unit


@pytest.fixture
def sqlite_sessions(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'imap-outbox.sqlite'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    finally:
        engine.dispose()


def _candidate(uid: int) -> ImapMessageLedger:
    return ImapMessageLedger(
        owner_key="owner",
        mailbox_key="mailbox",
        uidvalidity="7",
        uid=uid,
        account_ref="account",
        lane="backlog",
        state="pending",
        discovery_state="ready",
        is_candidate=True,
    )


def test_file_sqlite_serializes_batch_caps_and_fences_execution(sqlite_sessions, monkeypatch):
    with sqlite_sessions() as db:
        db.add_all([_candidate(uid) for uid in range(1, 5)])
        db.commit()

    monkeypatch.setattr(imap_pipeline, "SessionLocal", sqlite_sessions)
    claim_barrier = Barrier(2)

    def claim():
        claim_barrier.wait()
        return imap_pipeline.claim_candidates(account_ref="account", lane="backlog", limit=2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: claim(), range(2)))

    nonempty = [(token, ids) for token, ids in claims if ids]
    assert len(nonempty) == 2
    assert all(1 <= len(ids) <= 2 for _, ids in nonempty)
    assert len({token for token, _ in nonempty}) == 2
    assert len({ledger_id for _, ids in nonempty for ledger_id in ids}) == 4

    token, ids = nonempty[0]
    execution_barrier = Barrier(2)

    def start_execution():
        execution_barrier.wait()
        with sqlite_sessions() as db:
            return downloader._claim_rows(db, "account", "backlog", ids, token)

    with ThreadPoolExecutor(max_workers=2) as executor:
        executions = list(executor.map(lambda _: start_execution(), range(2)))

    assert sorted(len(rows) for rows in executions) == [0, len(ids)]
    with sqlite_sessions() as db:
        rows = db.query(ImapMessageLedger).filter(ImapMessageLedger.id.in_(ids)).all()
        assert {row.discovery_state for row in rows} == {"downloading"}
        assert all(row.download_started_at is not None for row in rows)
        assert all(row.download_lease_expires_at - row.download_started_at >= timedelta(seconds=899) for row in rows)
