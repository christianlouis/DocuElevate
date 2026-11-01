import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AccountDeletionTombstone, FileRecord, Tenant, Tribe
from app.services.account_deletion import tombstone_key
from app.services.account_lifecycle_lock import account_lifecycle_lock
from app.tasks.retry_config import BaseTaskWithRetry


def test_exclusive_waits_for_active_shared_task(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    factory = sessionmaker(bind=engine)
    acquired = threading.Event()
    release = threading.Event()
    exclusive = threading.Event()

    def active():
        with factory() as db, account_lifecycle_lock(db, "alice"):
            acquired.set()
            assert release.wait(5)

    def delete():
        assert acquired.wait(5)
        with factory() as db, account_lifecycle_lock(db, "alice", exclusive=True):
            exclusive.set()

    first = threading.Thread(target=active)
    second = threading.Thread(target=delete)
    first.start()
    second.start()
    assert acquired.wait(5)
    assert not exclusive.wait(0.1)
    release.set()
    first.join(5)
    second.join(5)
    assert exclusive.is_set()


def test_queued_document_task_checks_fence_after_wait(tmp_path, monkeypatch):
    import app.database
    from app.config import settings

    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(app.database, "SessionLocal", factory)
    with factory() as db:
        db.add_all(
            [Tenant(id="default", name="test"), Tribe(id="default-quarantine", tenant_id="default", name="quarantine")]
        )
        db.add(
            FileRecord(
                id=10,
                owner_id="alice",
                filehash="a",
                local_filename="x",
                file_size=1,
                tenant_id="default",
                tribe_id="default-quarantine",
            )
        )
        db.commit()
    ran = []

    class DocumentTask(BaseTaskWithRetry):
        def run(self, file_id):
            ran.append(file_id)

    result = []
    with factory() as db, account_lifecycle_lock(db, "alice", exclusive=True):
        worker = threading.Thread(target=lambda: result.append(DocumentTask()(10)))
        worker.start()
        db.add(AccountDeletionTombstone(owner_id=tombstone_key("alice"), status="deleting"))
        db.commit()
    worker.join(5)
    assert not worker.is_alive()
    assert result == [{"status": "skipped", "reason": "account_deletion"}]
    assert ran == []


def test_unrelated_task_is_unchanged():
    class GlobalTask(BaseTaskWithRetry):
        def run(self, value):
            return value + 1

    from celery import Celery

    task = Celery("test").register_task(GlobalTask())
    assert task(4) == 5


def test_missing_file_never_runs(tmp_path, monkeypatch):
    import app.database

    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(app.database, "SessionLocal", sessionmaker(bind=engine))
    ran = []

    class DocumentTask(BaseTaskWithRetry):
        def run(self, file_id):
            ran.append(file_id)

    assert DocumentTask()(123) == {"status": "skipped", "reason": "file_not_found"}
    assert ran == []


def test_unsupported_backend_fails_closed():
    class DB:
        def get_bind(self):
            class Bind:
                class dialect:
                    name = "mysql"

            return Bind()

    import pytest

    with pytest.raises(RuntimeError, match="unsupported"):
        with account_lifecycle_lock(DB(), "alice", exclusive=True):
            pass


def test_ownerless_single_user_task_runs(tmp_path, monkeypatch):
    from celery import Celery

    import app.database
    from app.config import settings

    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(app.database, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(settings, "multi_user_enabled", False)

    class DocumentTask(BaseTaskWithRetry):
        name = "test.ownerless"

        def run(self, file_id=None):
            return "ran"

    task = Celery("test-ownerless").register_task(DocumentTask())
    assert task() == "ran"
    monkeypatch.setattr(settings, "multi_user_enabled", True)
    assert task() == {"status": "skipped", "reason": "owner_unavailable"}


def test_postgres_unlocks_when_task_raises():
    from unittest.mock import MagicMock

    import pytest

    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"
    connection = db.get_bind.return_value.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar.return_value = True
    with pytest.raises(ValueError, match="crash"):
        with account_lifecycle_lock(db, "alice"):
            raise ValueError("crash")
    assert connection.execute.call_count == 2
    assert "pg_advisory_unlock_shared" in str(connection.execute.call_args.args[0])
    connection.invalidate.assert_not_called()


def test_postgres_failed_unlock_invalidates_connection():
    from unittest.mock import MagicMock

    import pytest

    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"
    connection = db.get_bind.return_value.connect.return_value.__enter__.return_value
    connection.execute.side_effect = [MagicMock(), RuntimeError("connection failed")]
    with pytest.raises(RuntimeError, match="connection failed"):
        with account_lifecycle_lock(db, "alice", exclusive=True):
            pass
    connection.invalidate.assert_called_once()
