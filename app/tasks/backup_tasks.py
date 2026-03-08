"""
Backup and restore tasks for DocuElevate.

Retention strategy
------------------
- **hourly** backups  – retained for 4 days  (``backup_retain_hourly``, default 96)
- **daily** backups   – retained for 3 weeks (``backup_retain_daily``,  default 21)
- **weekly** backups  – retained for 13 weeks (``backup_retain_weekly``, default 13)

Three separate Celery-beat entries call ``create_backup`` with the appropriate
``backup_type`` argument:
- every hour  → ``create_backup("hourly")``
- every day   → ``create_backup("daily")``
- every week  → ``create_backup("weekly")``

After each backup is created ``_apply_retention`` prunes old local backups for
that tier.  Remote copies are pruned by ``_prune_remote_backups`` which mirrors
the same retention limits.

Supported database backends
----------------------------
- **SQLite**    – dumped via Python's built-in ``sqlite3.iterdump()``; archive extension ``.db.gz``
- **PostgreSQL** – dumped via ``pg_dump --format=plain``; archive extension ``.pgsql.gz``
- **MySQL / MariaDB** – dumped via ``mysqldump --single-transaction``; archive extension ``.mysql.gz``
"""

import gzip
import hashlib
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import BackupRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_BACKUP_TYPE_RETAIN: dict[str, str] = {
    "hourly": "backup_retain_hourly",
    "daily": "backup_retain_daily",
    "weekly": "backup_retain_weekly",
}

#: Map of backend name → archive file extension.
_BACKEND_EXTENSIONS: dict[str, str] = {
    "sqlite": ".db.gz",
    "postgresql": ".pgsql.gz",
    "mysql": ".mysql.gz",
}


def _backup_dir() -> Path:
    """Return (and create) the local backup directory."""
    raw = getattr(settings, "backup_dir", None) or os.path.join(settings.workdir, "backups")
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _db_backend() -> str:
    """Return the database backend name (e.g. ``'sqlite'``, ``'postgresql'``, ``'mysql'``)."""
    from sqlalchemy.engine.url import make_url

    url = make_url(settings.database_url)
    return url.get_backend_name()


def _db_path() -> Path | None:
    """Return the SQLite database file path, or None for non-SQLite databases."""
    from sqlalchemy.engine.url import make_url

    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite":
        return None
    db = url.database
    if not db or db == ":memory:":
        return None
    return Path(db)


def _archive_ext_for_backend(backend: str) -> str:
    """Return the archive file extension for the given database backend.

    Args:
        backend: Backend name as returned by
            ``sqlalchemy.engine.url.URL.get_backend_name()`` (e.g. ``'sqlite'``).

    Returns:
        File extension string including the leading dot, e.g. ``'.db.gz'``.
        Falls back to ``'.sql.gz'`` for unknown backends.
    """
    return _BACKEND_EXTENSIONS.get(backend, ".sql.gz")


def _sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of *path*."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _dump_sqlite(db_path: Path, dest: Path) -> None:
    """Write a gzip-compressed SQL dump of *db_path* to *dest*."""
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        with gzip.open(str(dest), "wt", encoding="utf-8") as gz:
            for line in conn.iterdump():
                gz.write(line + "\n")
    finally:
        conn.close()


def _dump_postgresql(db_url: str, dest: Path) -> None:
    """Write a gzip-compressed ``pg_dump`` of the PostgreSQL database to *dest*.

    Uses ``PGPASSWORD`` environment variable so the password is never exposed on
    the process command line.

    Args:
        db_url: Full SQLAlchemy database URL (e.g. ``postgresql://user:pass@host/db``).
        dest: Destination path for the ``.pgsql.gz`` archive.

    Raises:
        RuntimeError: If ``pg_dump`` exits with a non-zero return code.
        FileNotFoundError: If the ``pg_dump`` binary is not found.
    """
    from sqlalchemy.engine.url import make_url

    url = make_url(db_url)
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = str(url.password)

    # Command arguments are built from the SQLAlchemy URL (admin-configured DATABASE_URL),
    # not from user-controlled input.  shell=False (the default when passing a list) is used
    # so there is no shell interpretation of the argument values.
    cmd: list[str] = ["pg_dump", "--format=plain", "--no-password"]
    if url.host:
        cmd.extend(["-h", url.host])
    if url.port:
        cmd.extend(["-p", str(url.port)])
    if url.username:
        cmd.extend(["-U", url.username])
    if url.database:
        cmd.append(url.database)

    with gzip.open(str(dest), "wb") as gz:
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        stdout = proc.stdout
        if stdout is None:  # pragma: no cover – guaranteed by stdout=PIPE
            raise RuntimeError("pg_dump produced no stdout pipe")
        try:
            while True:
                chunk = stdout.read(65536)
                if not chunk:
                    break
                gz.write(chunk)
        finally:
            stdout.close()
            stderr_bytes = proc.stderr.read() if proc.stderr else b""
            proc.wait()

    if proc.returncode != 0:
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"pg_dump exited with code {proc.returncode}: {stderr_bytes.decode(errors='replace').strip()}"
        )


def _dump_mysql(db_url: str, dest: Path) -> None:
    """Write a gzip-compressed ``mysqldump`` of the MySQL database to *dest*.

    Uses the ``MYSQL_PWD`` environment variable so the password is never exposed
    on the process command line.

    Args:
        db_url: Full SQLAlchemy database URL
            (e.g. ``mysql+pymysql://user:pass@host/db``).
        dest: Destination path for the ``.mysql.gz`` archive.

    Raises:
        RuntimeError: If ``mysqldump`` exits with a non-zero return code.
        FileNotFoundError: If the ``mysqldump`` binary is not found.
    """
    from sqlalchemy.engine.url import make_url

    url = make_url(db_url)
    env = os.environ.copy()
    if url.password:
        env["MYSQL_PWD"] = str(url.password)

    # Command arguments are built from the SQLAlchemy URL (admin-configured DATABASE_URL).
    # shell=False (list form) prevents shell interpretation of argument values.
    cmd: list[str] = ["mysqldump", "--single-transaction", "--routines", "--triggers"]
    if url.host:
        cmd.extend(["-h", url.host])
    if url.port:
        cmd.extend(["-P", str(url.port)])
    if url.username:
        cmd.extend(["-u", url.username])
    if url.database:
        cmd.append(url.database)

    with gzip.open(str(dest), "wb") as gz:
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        stdout = proc.stdout
        if stdout is None:  # pragma: no cover – guaranteed by stdout=PIPE
            raise RuntimeError("mysqldump produced no stdout pipe")
        try:
            while True:
                chunk = stdout.read(65536)
                if not chunk:
                    break
                gz.write(chunk)
        finally:
            stdout.close()
            stderr_bytes = proc.stderr.read() if proc.stderr else b""
            proc.wait()

    if proc.returncode != 0:
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"mysqldump exited with code {proc.returncode}: {stderr_bytes.decode(errors='replace').strip()}"
        )


def _restore_sqlite(db_path: Path, archive_path: Path) -> None:
    """Restore a SQLite database from a gzip-compressed SQL dump archive.

    Validates the SQL by replaying it on an in-memory database before touching
    the live file.  Saves a ``<db_path>.pre_restore`` rollback copy first.

    Args:
        db_path: Path to the live SQLite database file to overwrite.
        archive_path: Path to the ``.db.gz`` gzip-compressed SQL dump.

    Raises:
        ValueError: If the archive cannot be decompressed or contains invalid SQL.
        RuntimeError: If writing the restored database fails.
    """
    import shutil
    import sqlite3

    # Decompress and read SQL statements
    try:
        with gzip.open(str(archive_path), "rt", encoding="utf-8") as gz:
            sql_script = gz.read()
    except Exception as exc:
        raise ValueError(f"Failed to decompress backup file: {exc}") from exc

    # Validate by replaying on an in-memory database
    try:
        mem_conn = sqlite3.connect(":memory:")
        mem_conn.executescript(sql_script)
        mem_conn.close()
    except sqlite3.Error as exc:
        raise ValueError(f"Backup file contains invalid SQL: {exc}") from exc

    # Preserve the current DB before overwriting
    bak = str(db_path) + ".pre_restore"
    try:
        shutil.copy2(str(db_path), bak)
    except OSError as exc:
        logger.warning(f"Could not create pre-restore backup at {bak}: {exc}")

    try:
        restore_conn = sqlite3.connect(str(db_path))
        restore_conn.executescript(sql_script)
        restore_conn.close()
    except sqlite3.Error as exc:
        # Attempt rollback to the pre-restore copy
        try:
            if os.path.exists(bak):
                shutil.copy2(bak, str(db_path))
        except OSError as rollback_exc:
            logger.error(f"Rollback failed; database may be corrupted: {rollback_exc}")
        raise RuntimeError(f"SQLite restore failed: {exc}") from exc


def _restore_postgresql(db_url: str, archive_path: Path) -> None:
    """Restore a PostgreSQL database from a gzip-compressed SQL dump archive.

    Pipes the decompressed dump to ``psql``.  Uses ``PGPASSWORD`` so the
    password is never exposed on the process command line.

    Args:
        db_url: Full SQLAlchemy database URL.
        archive_path: Path to the ``.pgsql.gz`` gzip-compressed ``pg_dump`` archive.

    Raises:
        RuntimeError: If ``psql`` exits with a non-zero return code.
        FileNotFoundError: If the ``psql`` binary is not found.
    """
    from sqlalchemy.engine.url import make_url

    url = make_url(db_url)
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = str(url.password)

    # Command arguments are built from the SQLAlchemy URL (admin-configured DATABASE_URL).
    # shell=False (list form) prevents shell interpretation of argument values.
    cmd: list[str] = ["psql", "--no-password"]
    if url.host:
        cmd.extend(["-h", url.host])
    if url.port:
        cmd.extend(["-p", str(url.port)])
    if url.username:
        cmd.extend(["-U", url.username])
    if url.database:
        cmd.append(url.database)

    with gzip.open(str(archive_path), "rb") as gz:
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        _, stderr_bytes = proc.communicate(input=gz.read())

    if proc.returncode != 0:
        raise RuntimeError(f"psql exited with code {proc.returncode}: {stderr_bytes.decode(errors='replace').strip()}")


def _restore_mysql(db_url: str, archive_path: Path) -> None:
    """Restore a MySQL database from a gzip-compressed SQL dump archive.

    Pipes the decompressed dump to ``mysql``.  Uses the ``MYSQL_PWD``
    environment variable so the password is never exposed on the command line.

    Args:
        db_url: Full SQLAlchemy database URL.
        archive_path: Path to the ``.mysql.gz`` gzip-compressed ``mysqldump`` archive.

    Raises:
        RuntimeError: If ``mysql`` exits with a non-zero return code.
        FileNotFoundError: If the ``mysql`` binary is not found.
    """
    from sqlalchemy.engine.url import make_url

    url = make_url(db_url)
    env = os.environ.copy()
    if url.password:
        env["MYSQL_PWD"] = str(url.password)

    # Command arguments are built from the SQLAlchemy URL (admin-configured DATABASE_URL).
    # shell=False (list form) prevents shell interpretation of argument values.
    cmd: list[str] = ["mysql"]
    if url.host:
        cmd.extend(["-h", url.host])
    if url.port:
        cmd.extend(["-P", str(url.port)])
    if url.username:
        cmd.extend(["-u", url.username])
    if url.database:
        cmd.append(url.database)

    with gzip.open(str(archive_path), "rb") as gz:
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        _, stderr_bytes = proc.communicate(input=gz.read())

    if proc.returncode != 0:
        raise RuntimeError(f"mysql exited with code {proc.returncode}: {stderr_bytes.decode(errors='replace').strip()}")


def _apply_retention(backup_type: str, db: object) -> None:
    """Delete local backups beyond the retention limit for *backup_type*.

    Args:
        backup_type: One of ``hourly``, ``daily``, ``weekly``.
        db: Active SQLAlchemy session.
    """
    retain_attr = _BACKUP_TYPE_RETAIN.get(backup_type, "backup_retain_hourly")
    retain = int(getattr(settings, retain_attr, 96))

    # Query ALL records for this tier (with or without a local file) so that
    # remote-only and already-pruned records still count toward the retention window.
    records = (
        db.query(BackupRecord)
        .filter(BackupRecord.backup_type == backup_type)
        .order_by(BackupRecord.created_at.desc())
        .all()
    )

    to_prune = records[retain:]
    for rec in to_prune:
        if rec.local_path and os.path.exists(rec.local_path):
            try:
                os.remove(rec.local_path)
                logger.info(f"Pruned local backup: {rec.local_path}")
            except OSError as exc:
                logger.warning(f"Failed to remove local backup {rec.local_path}: {exc}")
        rec.local_path = None
        # If no remote copy either, delete the record entirely
        if not rec.remote_path:
            db.delete(rec)

    db.commit()


def _prune_remote_backups(backup_type: str, db: object) -> None:
    """Prune remote backup records beyond the retention limit.

    The actual remote deletion is best-effort (logged but not fatal).

    Args:
        backup_type: One of ``hourly``, ``daily``, ``weekly``.
        db: Active SQLAlchemy session.
    """
    retain_attr = _BACKUP_TYPE_RETAIN.get(backup_type, "backup_retain_hourly")
    retain = int(getattr(settings, retain_attr, 96))

    # Query ALL records for this tier so that already-pruned local records
    # still count toward the retention window.
    records = (
        db.query(BackupRecord)
        .filter(BackupRecord.backup_type == backup_type)
        .order_by(BackupRecord.created_at.desc())
        .all()
    )

    to_prune = [r for r in records[retain:] if r.remote_path]
    for rec in to_prune:
        _delete_remote_copy(rec)
        rec.remote_path = None
        rec.remote_destination = None
        if not rec.local_path:
            db.delete(rec)

    db.commit()


def _delete_remote_copy(rec: BackupRecord) -> None:  # noqa: C901
    """Best-effort deletion of the remote copy described by *rec*."""
    dest = rec.remote_destination
    remote_path = rec.remote_path
    if not dest or not remote_path:
        return

    try:
        if dest == "s3":
            import boto3

            s3 = boto3.client(
                "s3",
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )
            s3.delete_object(Bucket=settings.s3_bucket_name, Key=remote_path)
            logger.info(f"Deleted remote S3 backup: s3://{settings.s3_bucket_name}/{remote_path}")

        elif dest == "dropbox":
            import dropbox as dbx_module

            dbx = dbx_module.Dropbox(settings.dropbox_refresh_token)
            dbx.files_delete_v2(remote_path)
            logger.info(f"Deleted remote Dropbox backup: {remote_path}")

        elif dest in ("ftp", "sftp", "nextcloud", "webdav", "google_drive", "onedrive", "email"):
            # For other providers best-effort is logged only – deletion not implemented yet.
            logger.debug(f"Remote deletion not implemented for destination '{dest}', skipping {remote_path}")

    except Exception as exc:
        logger.warning(f"Failed to delete remote backup {remote_path} from {dest}: {exc}")


def _upload_remote(archive_path: Path, filename: str) -> tuple[str, str] | None:  # noqa: C901
    """Upload *archive_path* to the configured remote destination.

    Returns:
        ``(destination, remote_path)`` on success, ``None`` on failure or when
        no remote destination is configured.
    """
    dest = getattr(settings, "backup_remote_destination", None)
    if not dest:
        return None

    remote_folder = getattr(settings, "backup_remote_folder", "backups") or "backups"
    remote_key = f"{remote_folder}/{filename}"

    try:
        if dest == "s3":
            import boto3

            s3 = boto3.client(
                "s3",
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )
            with open(archive_path, "rb") as fh:
                s3.upload_fileobj(fh, settings.s3_bucket_name, remote_key)
            logger.info(f"Uploaded backup to S3: s3://{settings.s3_bucket_name}/{remote_key}")
            return (dest, remote_key)

        elif dest == "dropbox":
            import dropbox as dbx_module

            dbx = dbx_module.Dropbox(settings.dropbox_refresh_token)
            dropbox_path = f"/{remote_key}"
            with open(archive_path, "rb") as fh:
                dbx.files_upload(fh.read(), dropbox_path, mode=dbx_module.files.WriteMode("overwrite"))
            logger.info(f"Uploaded backup to Dropbox: {dropbox_path}")
            return (dest, dropbox_path)

        elif dest == "email":
            _email_backup(archive_path, filename)
            return (dest, f"email:{filename}")

        elif dest == "nextcloud":
            import requests

            url = f"{settings.nextcloud_upload_url}/{remote_key}"
            with open(archive_path, "rb") as fh:
                resp = requests.put(
                    url,
                    data=fh,
                    auth=(settings.nextcloud_username, settings.nextcloud_password),
                    timeout=120,
                )
            resp.raise_for_status()
            logger.info(f"Uploaded backup to Nextcloud: {url}")
            return (dest, url)

        elif dest == "webdav":
            import requests

            url = f"{settings.webdav_url}/{remote_key}"
            with open(archive_path, "rb") as fh:
                resp = requests.put(
                    url,
                    data=fh,
                    auth=(settings.webdav_username, settings.webdav_password),
                    verify=settings.webdav_verify_ssl,
                    timeout=120,
                )
            resp.raise_for_status()
            logger.info(f"Uploaded backup to WebDAV: {url}")
            return (dest, url)

        else:
            logger.warning(f"Backup remote destination '{dest}' upload not implemented; keeping local only.")
            return None

    except Exception as exc:
        logger.error(f"Failed to upload backup to {dest}: {exc}", exc_info=True)
        return None


def _email_backup(archive_path: Path, filename: str) -> None:
    """Send *archive_path* as an e-mail attachment to the default recipient."""
    import smtplib
    from email.mime.application import MIMEApplication
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    recipient = settings.email_default_recipient
    if not recipient:
        raise ValueError("email_default_recipient is not configured")

    msg = MIMEMultipart()
    msg["Subject"] = f"[DocuElevate] Database backup – {filename}"
    msg["From"] = settings.email_sender or settings.email_username or "docuelevate@localhost"
    msg["To"] = recipient

    body = MIMEText(f"Automated database backup from DocuElevate.\n\nFile: {filename}\n", "plain")
    msg.attach(body)

    with open(archive_path, "rb") as fh:
        part = MIMEApplication(fh.read(), Name=filename)
        part["Content-Disposition"] = f'attachment; filename="{filename}"'
        msg.attach(part)

    with smtplib.SMTP(settings.email_host, settings.email_port, timeout=60) as server:
        if settings.email_use_tls:
            server.starttls()
        if settings.email_username and settings.email_password:
            server.login(settings.email_username, settings.email_password)
        server.sendmail(msg["From"], [recipient], msg.as_string())

    logger.info(f"Backup e-mailed to {recipient}: {filename}")


# ---------------------------------------------------------------------------
# Public Celery tasks
# ---------------------------------------------------------------------------


@celery.task(name="app.tasks.backup_tasks.create_backup", bind=True)
def create_backup(self, backup_type: str = "hourly") -> dict:
    """Create a database backup archive and apply retention.

    Supports SQLite (``.db.gz``), PostgreSQL (``.pgsql.gz``), and
    MySQL / MariaDB (``.mysql.gz``) databases.  The native dump tool for the
    configured backend (``sqlite3``, ``pg_dump``, or ``mysqldump``) must be
    available on the worker's ``PATH``.

    Args:
        backup_type: ``"hourly"``, ``"daily"``, or ``"weekly"``.

    Returns:
        A dict with ``filename``, ``size_bytes``, and ``status``.
    """
    if backup_type not in _BACKUP_TYPE_RETAIN:
        backup_type = "hourly"

    if not getattr(settings, "backup_enabled", True):
        logger.debug("Backup is disabled; skipping create_backup task.")
        return {"status": "disabled"}

    backend = _db_backend()
    ext = _archive_ext_for_backend(backend)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"backup_{backup_type}_{ts}{ext}"
    archive_path = _backup_dir() / filename

    # SQLite: verify the database file exists before attempting to dump it
    db_path: Path | None = None
    if backend == "sqlite":
        db_path = _db_path()
        if db_path is None:
            logger.warning("Backup task skipped: in-memory SQLite databases are not supported.")
            return {"status": "unsupported_db"}
        if not db_path.exists():
            logger.error(f"Database file not found: {db_path}")
            return {"status": "error", "detail": f"DB file missing: {db_path}"}
    elif backend not in ("postgresql", "mysql"):
        logger.warning(f"Backup task skipped: unsupported database backend '{backend}'.")
        return {"status": "unsupported_db"}

    status = "ok"
    checksum: str | None = None
    size_bytes = 0
    remote_destination: str | None = None
    remote_path: str | None = None

    try:
        if backend == "sqlite":
            # db_path is guaranteed non-None: we returned early if it were None
            if db_path is None:  # pragma: no cover
                return {"status": "error", "detail": "db_path unexpectedly None"}
            _dump_sqlite(db_path, archive_path)
        elif backend == "postgresql":
            _dump_postgresql(settings.database_url, archive_path)
        elif backend == "mysql":
            _dump_mysql(settings.database_url, archive_path)
        size_bytes = archive_path.stat().st_size
        checksum = _sha256(archive_path)
        logger.info(f"Created {backup_type} backup: {archive_path} ({size_bytes:,} bytes)")
    except Exception as exc:
        logger.error(f"Failed to create backup archive {filename}: {exc}", exc_info=True)
        status = "failed"
        # Record the failure so it is visible in the dashboard
        with SessionLocal() as db:
            rec = BackupRecord(
                filename=filename,
                local_path=None,
                backup_type=backup_type,
                size_bytes=0,
                checksum=None,
                status="failed",
            )
            db.add(rec)
            db.commit()
        return {"status": "error", "detail": str(exc)}

    # Optional remote upload
    result = _upload_remote(archive_path, filename)
    if result:
        remote_destination, remote_path = result

    with SessionLocal() as db:
        rec = BackupRecord(
            filename=filename,
            local_path=str(archive_path),
            backup_type=backup_type,
            size_bytes=size_bytes,
            checksum=checksum,
            status=status,
            remote_destination=remote_destination,
            remote_path=remote_path,
        )
        db.add(rec)
        db.commit()

        # Apply retention policy for this tier
        _apply_retention(backup_type, db)
        if remote_destination:
            _prune_remote_backups(backup_type, db)

    return {
        "filename": filename,
        "size_bytes": size_bytes,
        "status": status,
        "remote_destination": remote_destination,
    }


@celery.task(name="app.tasks.backup_tasks.cleanup_old_backups")
def cleanup_old_backups() -> dict:
    """Manually trigger retention clean-up for all backup tiers.

    This is also called automatically after each ``create_backup`` run.
    """
    with SessionLocal() as db:
        for btype in ("hourly", "daily", "weekly"):
            _apply_retention(btype, db)
            _prune_remote_backups(btype, db)
    return {"status": "ok"}
