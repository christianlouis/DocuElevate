"""PostgreSQL-only concurrency and migration checks for the IMAP outbox."""

import importlib.util
import os
import threading
import uuid

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

URL = os.environ.get("IMAP_PIPELINE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="IMAP_PIPELINE_TEST_DATABASE_URL is not configured")


def _db():
    engine = create_engine(URL, isolation_level="READ COMMITTED")
    schema = "imap_test_" + uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    return engine, schema, sessionmaker(bind=engine, expire_on_commit=False)


def _cleanup(engine, schema):
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    engine.dispose()


def _ledger_table(conn):
    conn.execute(
        text("""
        CREATE TABLE imap_message_ledger (
          id SERIAL PRIMARY KEY, owner_key VARCHAR(255) NOT NULL,
          mailbox_key VARCHAR(255) NOT NULL, uidvalidity VARCHAR(255) NOT NULL,
          uid BIGINT NOT NULL, state VARCHAR(32) NOT NULL DEFAULT 'pending',
          is_candidate BOOLEAN NOT NULL DEFAULT TRUE, account_ref VARCHAR(255),
          lane VARCHAR(16) NOT NULL DEFAULT 'backlog', discovery_state VARCHAR(24) NOT NULL DEFAULT 'ready',
          download_lease_token VARCHAR(64), download_lease_expires_at TIMESTAMPTZ,
          next_download_at TIMESTAMPTZ, scanned_at TIMESTAMPTZ, downloaded_at TIMESTAMPTZ,
          download_task_id VARCHAR(255), download_started_at TIMESTAMPTZ, metadata_json TEXT,
          attempts INTEGER NOT NULL DEFAULT 0, download_attempts INTEGER NOT NULL DEFAULT 0,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE(owner_key, mailbox_key, uidvalidity, uid)
        )
    """)
    )
    conn.execute(
        text("""CREATE TABLE imap_pipeline_cursors (
      id SERIAL PRIMARY KEY, owner_key VARCHAR(255) NOT NULL, mailbox_key VARCHAR(255) NOT NULL,
      uidvalidity VARCHAR(255) NOT NULL, lane VARCHAR(16) NOT NULL, last_uid BIGINT NOT NULL DEFAULT 0,
      highwater_uid BIGINT, initialized BOOLEAN NOT NULL DEFAULT FALSE, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE(owner_key, mailbox_key, uidvalidity, lane))""")
    )


def test_two_sessions_claim_disjoint_rows_and_cap_backlog():
    engine, schema, Session = _db()
    try:
        with engine.begin() as conn:
            conn.execute(text(f'SET search_path TO "{schema}"'))
            _ledger_table(conn)
        with engine.begin() as conn:
            for uid in range(5):
                conn.execute(
                    text(
                        "INSERT INTO imap_message_ledger(owner_key,mailbox_key,uidvalidity,uid,account_ref,lane,discovery_state) VALUES ('o','m','7',:uid,'a','backlog','ready')"
                    ),
                    {"uid": uid},
                )
        barrier = threading.Barrier(2)
        results = []

        def claim():
            db = Session()
            db.execute(text(f'SET search_path TO "{schema}"'))
            barrier.wait()
            rows = (
                db.execute(
                    text("""UPDATE imap_message_ledger SET discovery_state='claimed', download_lease_token=:token
              WHERE id IN (SELECT id FROM imap_message_ledger WHERE lane='backlog' AND discovery_state='ready' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 2)
              RETURNING id"""),
                    {"token": uuid.uuid4().hex},
                )
                .scalars()
                .all()
            )
            db.commit()
            results.append(rows)
            db.close()

        threads = [threading.Thread(target=claim), threading.Thread(target=claim)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(len(rows) <= 2 for rows in results)
        assert len(set(sum(results, []))) == sum(map(len, results))
    finally:
        _cleanup(engine, schema)


def test_execution_cas_same_token_has_one_winner():
    engine, schema, Session = _db()
    try:
        with engine.begin() as conn:
            conn.execute(text(f'SET search_path TO "{schema}"'))
            _ledger_table(conn)
            conn.execute(
                text(
                    "INSERT INTO imap_message_ledger(owner_key,mailbox_key,uidvalidity,uid,account_ref,lane,discovery_state,download_lease_token,download_lease_expires_at) VALUES ('o','m','7',1,'a','backlog','claimed','same',now()+interval '5 minutes')"
                )
            )

        def cas(db):
            return db.execute(
                text(
                    "UPDATE imap_message_ledger SET discovery_state='downloading' WHERE id=1 AND discovery_state='claimed' AND download_lease_token='same' RETURNING id"
                )
            ).scalar()

        first, second = Session(), Session()
        first.execute(text(f'SET search_path TO "{schema}"'))
        second.execute(text(f'SET search_path TO "{schema}"'))
        assert cas(first) == 1
        first.commit()
        assert cas(second) is None
        second.rollback()
        first.close()
        second.close()
    finally:
        _cleanup(engine, schema)


def test_migration_preserves_old_terminal_and_pending_rows():
    engine, schema, _ = _db()
    try:
        with engine.begin() as conn:
            conn.execute(text(f'SET search_path TO "{schema}"'))
            conn.execute(
                text(
                    "CREATE TABLE imap_message_ledger (id SERIAL PRIMARY KEY, owner_key VARCHAR(255) NOT NULL, mailbox_key VARCHAR(255) NOT NULL, uidvalidity VARCHAR(255) NOT NULL, uid BIGINT NOT NULL, state VARCHAR(32) NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(owner_key,mailbox_key,uidvalidity,uid) )"
                )
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
            ctx = MigrationContext.configure(conn)
            module.op = Operations(ctx)
            module.upgrade()
            rows = conn.execute(
                text("SELECT uid,state,lane,discovery_state,is_candidate FROM imap_message_ledger ORDER BY uid")
            ).all()
            assert [(r.uid, r.state) for r in rows] == [(1, "completed"), (2, "pending")]
            assert all(r.lane == "backlog" for r in rows)
            assert conn.execute(text("SELECT count(*) FROM imap_pipeline_cursors")).scalar() == 0
    finally:
        _cleanup(engine, schema)
