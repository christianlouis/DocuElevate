"""Process-safe per-account coordination between deletion and document work."""
from contextlib import contextmanager
import fcntl
import hashlib
from pathlib import Path
import threading

from sqlalchemy import text

from app.config import settings

_local = threading.local()
_registry_guard = threading.Lock()
_thread_locks: dict[str, threading.RLock] = {}


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
        with db.get_bind().connect() as connection:
            connection.execute(text(f"SELECT pg_advisory_lock{suffix}(:key)"), {"key": lock_id})
            held[key] = exclusive
            try:
                yield
            finally:
                held.pop(key, None)
                connection.execute(text(f"SELECT pg_advisory_unlock{suffix}(:key)"), {"key": lock_id})
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
