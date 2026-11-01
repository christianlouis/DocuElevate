"""Process-safe per-account coordination between deletion and document work."""

import asyncio
import fcntl
import hashlib
import threading
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.config import settings

_local = threading.local()
_registry_guard = threading.Lock()
_thread_locks: dict[str, threading.RLock] = {}
_pg_engines = {}


def _dedicated_pg_engine(bind):
    # Locks must not exhaust the application's bounded connection pool.
    with _registry_guard:
        if bind not in _pg_engines:
            _pg_engines[bind] = create_engine(bind.url, creator=bind.pool._creator, poolclass=NullPool)
        return _pg_engines[bind]


@contextmanager
def account_lifecycle_lock(db, owner_id: str, *, exclusive: bool = False):
    """Hold a shared task lock or exclusive deletion lock until the context exits.

    PostgreSQL uses a dedicated connection, so application session commits do
    not return the advisory lock to the pool. SQLite uses a local workdir lock;
    all processes using that SQLite database must share this workdir.
    """
    if not owner_id:
        raise ValueError("owner is required for lifecycle locking")
    digest = hashlib.sha256(owner_id.encode("utf-8")).digest()
    key = digest.hex()
    held = getattr(_local, "held", None)
    if held is None:
        held = _local.held = {}
    if key in held:
        if exclusive and not held[key]:
            raise RuntimeError("cannot upgrade a shared lifecycle lock")
        yield
        return
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        lock_id = int.from_bytes(digest[:8], "big", signed=True)
        suffix = "" if exclusive else "_shared"
        with _dedicated_pg_engine(db.get_bind()).connect() as connection:
            connection.execute(text(f"SELECT pg_advisory_lock{suffix}(:key)"), {"key": lock_id})
            held[key] = exclusive
            try:
                yield
            finally:
                held.pop(key, None)
                try:
                    released = connection.execute(
                        text(f"SELECT pg_advisory_unlock{suffix}(:key)"), {"key": lock_id}
                    ).scalar()
                    if released is not True:
                        raise RuntimeError("PostgreSQL lifecycle lock was not released")
                except BaseException:
                    # A pooled session must never retain a session-level lock.
                    connection.invalidate()
                    raise
    elif dialect == "sqlite":
        with _registry_guard:
            lock = _thread_locks.setdefault(key, threading.RLock())
        with lock:
            directory = Path(settings.workdir) / ".account-lifecycle-locks"
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            with (directory / key).open("a+b") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                held[key] = exclusive
                try:
                    yield
                finally:
                    held.pop(key, None)
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    else:
        raise RuntimeError(f"account lifecycle locking unsupported for database dialect {dialect}")


@asynccontextmanager
async def async_account_lifecycle_lock(db, owner_id: str):
    """Hold a shared lock across async request awaits without blocking the loop."""
    if not owner_id:
        raise ValueError("owner is required for lifecycle locking")
    digest = hashlib.sha256(owner_id.encode("utf-8")).digest()
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        directory = Path(settings.workdir) / ".account-lifecycle-locks"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (directory / digest.hex()).open("a+b") as handle:
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(0.025)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    elif dialect == "postgresql":
        lock_id = int.from_bytes(digest[:8], "big", signed=True)
        lock_engine = _dedicated_pg_engine(db.get_bind())
        while True:
            connect_task = asyncio.create_task(asyncio.to_thread(lock_engine.connect))
            try:
                connection = await asyncio.shield(connect_task)
            except asyncio.CancelledError:
                connection = await connect_task
                await asyncio.to_thread(connection.close)
                raise
            try:
                acquired = await asyncio.to_thread(
                    lambda connection=connection: connection.execute(
                        text("SELECT pg_try_advisory_lock_shared(:key)"), {"key": lock_id}
                    ).scalar()
                )
                if acquired:
                    try:
                        yield
                    finally:
                        try:
                            released = await asyncio.to_thread(
                                lambda connection=connection: connection.execute(
                                    text("SELECT pg_advisory_unlock_shared(:key)"), {"key": lock_id}
                                ).scalar()
                            )
                            if released is not True:
                                raise RuntimeError("PostgreSQL lifecycle lock was not released")
                        except BaseException:
                            await asyncio.to_thread(connection.invalidate)
                            raise
                    return
            finally:
                await asyncio.to_thread(connection.close)
            # Do not retain a server connection while deletion is in progress.
            await asyncio.sleep(0.1)
    else:
        raise RuntimeError(f"account lifecycle locking unsupported for database dialect {dialect}")
