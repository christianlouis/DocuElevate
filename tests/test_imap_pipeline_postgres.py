"""PostgreSQL-only tests for the production IMAP outbox functions."""

import importlib.util
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker

URL = os.environ.get("IMAP_PIPELINE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="IMAP_PIPELINE_TEST_DATABASE_URL is not configured")


def _db():
    engine = create_engine(URL, isolation_level="READ COMMITTED", pool_pre_ping=True)
    schema = "imap_test_" + uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine.dispose()

    @event.listens_for(engine, "connect")
    def _search_path(dbapi_connection, _connection_record):
        previous = dbapi_connection.autocommit
        dbapi_connection.autocommit = True
        try:
            with dbapi_connection.cursor() as cursor:
                cursor.execute(f'SET search_path TO "{schema}"')
        finally:
            dbapi_connection.autocommit = previous

    return engine, schema, sessionmaker(bind=engine, expire_on_commit=False)


def _cleanup(engine, schema):
    engine.dispose()
    cleanup_engine = create_engine(URL, isolation_level="AUTOCOMMIT")
    try:
        with cleanup_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    finally:
        cleanup_engine.dispose()


def _create_tables(engine):
    from app.models import ImapMessageLedger, ImapPipelineCursor

    ImapMessageLedger.__table__.create(engine, checkfirst=True)
    ImapPipelineCursor.__table__.create(engine, checkfirst=True)


def _seed(Session, count=5):
    from app.models import ImapMessageLedger

    with Session() as db:
        db.add_all(
            [
                ImapMessageLedger(
                    owner_key="owner",
                    mailbox_key="mailbox",
                    uidvalidity="7",
                    uid=uid,
                    account_ref="acct",
                    lane="backlog",
                    state="pending",
                    discovery_state="ready",
                    is_candidate=True,
                )
                for uid in range(1, count + 1)
            ]
        )
        db.commit()


def test_two_real_publishers_are_disjoint_and_backlog_capped(monkeypatch):
    from app import imap_pipeline

    engine, schema, Session = _db()
    try:
        _create_tables(engine)
        _seed(Session, count=10)
        published = []
        barrier = threading.Barrier(2)

        def publish(*args, **kwargs):
            published.append((kwargs["task_id"], tuple(kwargs["args"][2]), kwargs["queue"]))
            return object()

        monkeypatch.setattr(imap_pipeline, "SessionLocal", Session)
        monkeypatch.setattr(imap_pipeline.settings, "imap_pipeline_download_batch_size", 2)
        monkeypatch.setattr(imap_pipeline.settings, "imap_pipeline_backlog_active_batches", 4)
        # ``download_imap_batch`` is a Celery ``shared_task`` proxy.  Patching
        # its bound method is thread-sensitive: each worker can resolve the
        # proxy against a different Celery app and accidentally publish to the
        # default localhost broker.  Replace the module-level task with a
        # concrete fake so every publisher thread calls the same capture.
        monkeypatch.setattr(
            imap_pipeline,
            "download_imap_batch",
            SimpleNamespace(apply_async=publish),
        )

        def run():
            barrier.wait()
            imap_pipeline.publish_candidate_batches.run("acct", "backlog")

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run) for _ in range(2)]
            for future in futures:
                future.result(timeout=10)

        assert len(published) == 4
        assert sum(len(ids) for _task_id, ids, _queue in published) == 8
        assert len({task_id for task_id, _ids, _queue in published}) == len(published)
        ids = [item for _task_id, item, _queue in published]
        assert len(set().union(*map(set, ids))) == sum(len(item) for item in ids)
        assert all(queue == "imap_download_backlog" for _task_id, _ids, queue in published)
    finally:
        _cleanup(engine, schema)


def test_claim_skips_busy_advisory_lock_without_waiting(monkeypatch):
    from app import imap_pipeline

    engine, schema, Session = _db()
    try:
        _create_tables(engine)
        _seed(Session, count=1)
        monkeypatch.setattr(imap_pipeline, "SessionLocal", Session)
        key = "docuelevate:imap:acct:backlog"
        blocker = engine.connect()
        blocker.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})
        try:
            started = time.monotonic()
            with ThreadPoolExecutor(max_workers=1) as pool:
                token, ids = pool.submit(
                    imap_pipeline.claim_candidates, account_ref="acct", lane="backlog"
                ).result(timeout=2)
            assert time.monotonic() - started < 1
            assert token and ids == []
        finally:
            blocker.rollback()
            blocker.close()
        _token, claimed = imap_pipeline.claim_candidates(account_ref="acct", lane="backlog")
        assert claimed
    finally:
        _cleanup(engine, schema)


def test_same_claim_token_has_one_real_execution_winner(monkeypatch):
    from app import imap_pipeline, imap_pipeline_download

    engine, schema, Session = _db()
    try:
        _create_tables(engine)
        _seed(Session, count=1)
        monkeypatch.setattr(imap_pipeline, "SessionLocal", Session)
        token, ids = imap_pipeline.claim_candidates(account_ref="acct", lane="backlog")
        assert ids
        monkeypatch.setattr(imap_pipeline_download, "SessionLocal", Session)
        barrier = threading.Barrier(2)
        winners = []

        def execute():
            with Session() as db:
                barrier.wait()
                winners.append(bool(imap_pipeline_download._claim_rows(db, "acct", "backlog", ids, token)))

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(execute) for _ in range(2)]
            for future in futures:
                future.result(timeout=10)
        assert sorted(winners) == [False, True]
    finally:
        _cleanup(engine, schema)


def test_stale_token_does_not_claim(monkeypatch):
    from app import imap_pipeline, imap_pipeline_download
    from app.models import ImapMessageLedger

    engine, schema, Session = _db()
    try:
        _create_tables(engine)
        _seed(Session, count=1)
        monkeypatch.setattr(imap_pipeline, "SessionLocal", Session)
        token, ids = imap_pipeline.claim_candidates(account_ref="acct", lane="backlog")
        assert ids
        with Session() as db:
            assert imap_pipeline_download._claim_rows(db, "acct", "backlog", ids, "stale-token") == []
        with Session() as db:
            row = db.query(ImapMessageLedger).one()
            assert row.discovery_state == "claimed" and row.download_lease_token == token
    finally:
        _cleanup(engine, schema)


def test_migration_upgrade_downgrade_upgrade_preserves_rows():
    engine, schema, _Session = _db()
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""CREATE TABLE imap_message_ledger (
                id SERIAL PRIMARY KEY, owner_key VARCHAR(255) NOT NULL,
                mailbox_key VARCHAR(255) NOT NULL, uidvalidity VARCHAR(255) NOT NULL,
                uid BIGINT NOT NULL, state VARCHAR(32) NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE(owner_key, mailbox_key, uidvalidity, uid))""")
            )
            conn.execute(
                text(
                    "INSERT INTO imap_message_ledger(owner_key,mailbox_key,uidvalidity,uid,state) VALUES ('o','m','7',1,'completed'),('o','m','7',2,'pending')"
                )
            )
            module_path = os.path.join(
                os.path.dirname(__file__), "..", "migrations", "versions", "074_imap_discovery_download_pipeline.py"
            )
            spec = importlib.util.spec_from_file_location("migration074", module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            context = MigrationContext.configure(conn)
            module.op = Operations(context)
            module.upgrade()
            columns = {column["name"] for column in inspect(conn).get_columns("imap_message_ledger")}
            assert {"lane", "discovery_state", "next_download_at", "scanned_at"}.issubset(columns)
            assert conn.execute(
                text("SELECT uid, state, lane, discovery_state, is_candidate FROM imap_message_ledger ORDER BY uid")
            ).all() == [
                (1, "completed", "backlog", "discovered", False),
                (2, "pending", "backlog", "discovered", False),
            ]
            assert {"ix_imap_ledger_outbox_claim", "ix_imap_ledger_lease_expiry"}.issubset(
                {index["name"] for index in inspect(conn).get_indexes("imap_message_ledger")}
            )
            module.downgrade()
            module.upgrade()
            assert conn.execute(
                text("SELECT uid, state, lane, discovery_state, is_candidate FROM imap_message_ledger ORDER BY uid")
            ).all() == [
                (1, "completed", "backlog", "discovered", False),
                (2, "pending", "backlog", "discovered", False),
            ]
            assert {"ix_imap_ledger_outbox_claim", "ix_imap_ledger_lease_expiry"}.issubset(
                {index["name"] for index in inspect(conn).get_indexes("imap_message_ledger")}
            )
    finally:
        _cleanup(engine, schema)
