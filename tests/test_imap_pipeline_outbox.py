"""Durable outbox contracts (run against the shared SQLAlchemy test database)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.unit


def _factory(db_session):
    return sessionmaker(bind=db_session.get_bind(), autoflush=False)


def _fields(model):
    return {column.name for column in model.__table__.columns}


def _row(model, **overrides):
    values = {
        "owner_key": "owner",
        "mailbox_key": "mailbox",
        "uidvalidity": "42",
        "uid": 1,
        "state": "pending",
        "lane": "backlog",
        "account_ref": "acct",
        "is_candidate": True,
        "discovery_state": "ready",
    }
    values.update(overrides)
    return model(**{key: value for key, value in values.items() if key in _fields(model)})


def _requires_columns(*names):
    from app.models import ImapMessageLedger

    return pytest.mark.skipif(
        not set(names).issubset(_fields(ImapMessageLedger)), reason="requires durable outbox columns"
    )


def test_terminal_rows_are_excluded_and_identity_is_not_mixed(db_session):
    from app import imap_pipeline
    from app.models import ImapMessageLedger

    factory = _factory(db_session)
    with factory() as db:
        db.add_all(
            [
                _row(ImapMessageLedger, uid=1),
                _row(ImapMessageLedger, uid=2, state="completed", discovery_state="completed"),
                _row(ImapMessageLedger, uid=3, mailbox_key="other"),
            ]
        )
        db.commit()
    with patch.object(imap_pipeline, "SessionLocal", factory):
        token, ids = imap_pipeline.claim_candidates(account_ref="acct", lane="backlog", limit=10)
    assert token and len(ids) == 1


@_requires_columns("next_download_at")
def test_retry_wait_respects_due_time(db_session):
    from app import imap_pipeline
    from app.models import ImapMessageLedger

    factory = _factory(db_session)
    now = datetime.now(timezone.utc)
    with factory() as db:
        db.add_all(
            [
                _row(ImapMessageLedger, uid=1, discovery_state="retry_wait", next_download_at=now + timedelta(hours=1)),
                _row(
                    ImapMessageLedger, uid=2, discovery_state="retry_wait", next_download_at=now - timedelta(seconds=1)
                ),
            ]
        )
        db.commit()
    with patch.object(imap_pipeline, "SessionLocal", factory):
        _, ids = imap_pipeline.claim_candidates(account_ref="acct", lane="backlog", limit=10)
    with factory() as db:
        assert [db.get(ImapMessageLedger, item).uid for item in ids] == [2]


def test_new_lane_has_one_active_batch(db_session):
    from app import imap_pipeline
    from app.models import ImapMessageLedger

    factory = _factory(db_session)
    with factory() as db:
        db.add_all([_row(ImapMessageLedger, uid=index, lane="new") for index in range(1, 4)])
        db.commit()
    with patch.object(imap_pipeline, "SessionLocal", factory):
        _, first = imap_pipeline.claim_candidates(account_ref="acct", lane="new", limit=1)
        _, second = imap_pipeline.claim_candidates(account_ref="acct", lane="new", limit=1)
    assert first and not second


def test_broker_failure_keeps_fenced_claim(db_session):
    from app import imap_pipeline
    from app.models import ImapMessageLedger

    factory = _factory(db_session)
    with factory() as db:
        db.add(_row(ImapMessageLedger))
        db.commit()
    with (
        patch.object(imap_pipeline, "SessionLocal", factory),
        patch.object(imap_pipeline.download_imap_batch, "apply_async", side_effect=RuntimeError("broker")),
    ):
        assert imap_pipeline.publish_candidate_batches("acct", "backlog") == 0
    with factory() as db:
        row = db.query(ImapMessageLedger).one()
        assert row.discovery_state == "claimed" and row.download_lease_token


def test_download_task_retries_database_failure_without_ack(monkeypatch):
    from app import imap_pipeline

    class RetryRequested(Exception):
        pass

    failure = OperationalError("database unavailable", {}, ConnectionError())
    def retry(**kwargs):
        assert kwargs["countdown"] == 60
        raise RetryRequested

    monkeypatch.setattr(
        "app.imap_pipeline_download.download_claimed_batch",
        lambda *_args: (_ for _ in ()).throw(failure),
    )
    monkeypatch.setattr(imap_pipeline.download_imap_batch, "retry", retry)
    assert imap_pipeline.download_imap_batch.max_retries is None
    with pytest.raises(RetryRequested):
        imap_pipeline.download_imap_batch.run("acct", "backlog", [1], "token")


def test_snapshot_database_failure_is_explicit(monkeypatch):
    from app import imap_pipeline

    class BrokenSession:
        def __enter__(self):
            raise RuntimeError("unavailable")

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(imap_pipeline, "SessionLocal", BrokenSession)
    assert imap_pipeline.pipeline_snapshot("acct")["status"] == "unknown"


@_requires_columns("scanned_at", "downloaded_at")
def test_snapshot_reports_counts_and_recent_rates(db_session):
    from app import imap_pipeline
    from app.models import ImapMessageLedger

    factory = _factory(db_session)
    now = datetime.now(timezone.utc)
    with factory() as db:
        db.add(_row(ImapMessageLedger, scanned_at=now, discovery_state="ready"))
        db.add(
            _row(
                ImapMessageLedger,
                uid=2,
                state="completed",
                discovery_state="completed",
                scanned_at=now,
                downloaded_at=now,
            )
        )
        db.commit()
    with patch.object(imap_pipeline, "SessionLocal", factory):
        snapshot = imap_pipeline.pipeline_snapshot("acct")
    assert snapshot["status"] == "ok"
    assert snapshot["backlog_ready"] == 1
    assert snapshot["scanned_last_hour"] == 2
    assert snapshot["downloaded_last_hour"] == 1
