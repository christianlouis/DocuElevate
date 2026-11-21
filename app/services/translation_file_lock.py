"""Non-blocking per-file lock for durable translation work."""

import fcntl
import hashlib
import threading
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.config import settings

_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}
_engines = {}


class TranslationFileBusy(RuntimeError):
    """Another worker currently owns this file's translation admission."""


def _engine(bind):
    with _guard:
        if bind not in _engines:
            _engines[bind] = create_engine(bind.url, creator=bind.pool._creator, poolclass=NullPool)
        return _engines[bind]


@contextmanager
def translation_file_lock(db, file_id: int):
    digest = hashlib.sha256(f"translation:{file_id}".encode()).digest()
    key = digest.hex()
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        lock_id = int.from_bytes(digest[:8], "big", signed=True)
        with _engine(db.get_bind()).connect() as connection:
            acquired = connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_id}).scalar()
            if not acquired:
                raise TranslationFileBusy(f"translation file {file_id} is already being processed")
            connection.commit()
            try:

                def session_factory():
                    if connection.closed or connection.invalidated:
                        raise RuntimeError("translation lock connection is no longer usable")
                    return Session(bind=connection)

                yield session_factory
            finally:
                if not connection.closed and not connection.invalidated:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_id})
    elif dialect == "sqlite":
        with _guard:
            lock = _locks.setdefault(key, threading.Lock())
        if not lock.acquire(blocking=False):
            raise TranslationFileBusy(f"translation file {file_id} is already being processed")
        try:
            directory = Path(settings.workdir) / ".translation-file-locks"
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            with (directory / key).open("a+b") as handle:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise TranslationFileBusy(f"translation file {file_id} is already being processed") from exc
                try:
                    yield lambda: Session(bind=db.get_bind())
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock.release()
    else:
        raise RuntimeError(f"translation file locking unsupported for database dialect {dialect}")
