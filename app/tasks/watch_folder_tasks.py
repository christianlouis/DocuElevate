#!/usr/bin/env python3
"""
Watch Folder Ingestion Tasks

Periodically scans configured directories (local filesystem, FTP, SFTP) for new files
and enqueues them for document processing.

Supported sources:
- Local filesystem paths (works with any mounted path: SMB/CIFS, NFS, etc.)
- FTP server directories (uses existing FTP connection settings)
- SFTP server directories (uses existing SFTP connection settings)
"""

import ftplib  # nosec B402 - FTP usage is intentional for legacy server support
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone

import redis
from celery import shared_task

from app.config import settings
from app.tasks.convert_to_pdf import convert_to_pdf
from app.tasks.process_document import process_document
from app.utils.allowed_types import ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES

logger = logging.getLogger(__name__)

redis_client = redis.StrictRedis.from_url(settings.redis_url, decode_responses=True)

WATCH_FOLDER_LOCK_KEY = "watch_folder_lock"
WATCH_FOLDER_LOCK_EXPIRE = 300  # 5 minutes

# Cache file for tracking already-ingested files (local watch folders)
WATCH_FOLDER_CACHE_FILE = os.path.join(settings.workdir, "watch_folder_processed.json")
# Cache file for tracking already-ingested files (FTP watch folder)
FTP_INGEST_CACHE_FILE = os.path.join(settings.workdir, "ftp_ingest_processed.json")
# Cache file for tracking already-ingested files (SFTP watch folder)
SFTP_INGEST_CACHE_FILE = os.path.join(settings.workdir, "sftp_ingest_processed.json")

_CACHE_RETENTION_DAYS = 30


# ---------------------------------------------------------------------------
# Locking helpers
# ---------------------------------------------------------------------------


def _acquire_lock(lock_key: str, expire: int = WATCH_FOLDER_LOCK_EXPIRE) -> bool:
    """Acquire a Redis-based distributed lock. Returns True if acquired."""
    acquired = redis_client.setnx(lock_key, "locked")
    if acquired:
        redis_client.expire(lock_key, expire)
        logger.debug("Lock acquired: %s", lock_key)
        return True
    logger.debug("Lock already held: %s — skipping.", lock_key)
    return False


def _release_lock(lock_key: str) -> None:
    """Release a Redis-based distributed lock."""
    redis_client.delete(lock_key)
    logger.debug("Lock released: %s", lock_key)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _load_cache(cache_file: str) -> dict[str, str]:
    """Load the set of already-processed file identifiers from a JSON cache file."""
    if os.path.exists(cache_file):
        try:
            with open(cache_file) as f:
                data: dict[str, str] = json.load(f)
            return _evict_old_entries(data)
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to read cache file %s — starting fresh.", cache_file)
    return {}


def _save_cache(cache_file: str, data: dict[str, str]) -> None:
    """Persist the processed-file cache to disk."""
    try:
        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2)
    except OSError as exc:
        logger.error("Failed to write cache file %s: %s", cache_file, exc)


def _evict_old_entries(data: dict[str, str]) -> dict[str, str]:
    """Remove entries older than CACHE_RETENTION_DAYS to prevent unbounded growth."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=_CACHE_RETENTION_DAYS)
    result = {}
    for key, date_str in data.items():
        try:
            dt = datetime.fromisoformat(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt > cutoff:
                result[key] = date_str
        except (ValueError, TypeError):
            pass  # Skip entries with malformed timestamps
    return result


def _mark_processed(cache: dict[str, str], key: str) -> None:
    """Add a file identifier to the in-memory cache dict."""
    cache[key] = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# File type helpers
# ---------------------------------------------------------------------------


def _is_allowed_file(filename: str) -> bool:
    """Return True if the file should be ingested based on its name/extension."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS or filename.lower().endswith(".pdf")


def _enqueue_file(file_path: str, *, filename: str | None = None) -> None:
    """Enqueue a local file path for document processing."""
    fname = filename or os.path.basename(file_path)
    _, ext = os.path.splitext(fname)
    mime_check = ext.lower() in {".pdf"}

    if mime_check or fname.lower().endswith(".pdf"):
        process_document.delay(file_path)
        logger.info("Enqueued for processing: %s", fname)
    else:
        convert_to_pdf.delay(file_path)
        logger.info("Enqueued for PDF conversion: %s", fname)


# ---------------------------------------------------------------------------
# Local filesystem watch folder scanning
# ---------------------------------------------------------------------------


def _scan_local_folder(folder_path: str, cache: dict[str, str], delete_after: bool) -> int:
    """
    Scan a single local directory for new, allowed files.

    Files already present in *cache* (keyed by their absolute path) are skipped.
    Returns the number of files newly enqueued.
    """
    if not os.path.isdir(folder_path):
        logger.warning("Watch folder does not exist or is not a directory: %s", folder_path)
        return 0

    count = 0
    try:
        entries = os.scandir(folder_path)
    except PermissionError as exc:
        logger.error("Cannot scan watch folder %s: %s", folder_path, exc)
        return 0

    for entry in entries:
        if not entry.is_file(follow_symlinks=True):
            continue
        if not _is_allowed_file(entry.name):
            logger.debug("Skipping unsupported file type: %s", entry.name)
            continue

        abs_path = entry.path
        if abs_path in cache:
            logger.debug("Already processed: %s", abs_path)
            continue

        # Copy file to workdir before enqueueing so the original isn't locked
        dest_filename = f"wf_{entry.name}"
        dest_path = os.path.join(settings.workdir, dest_filename)

        # Avoid overwriting if a file with the same name is already there
        if os.path.exists(dest_path):
            base, ext2 = os.path.splitext(dest_filename)
            dest_path = os.path.join(settings.workdir, f"{base}_{int(datetime.now().timestamp())}{ext2}")

        try:
            import shutil

            shutil.copy2(abs_path, dest_path)
        except OSError as exc:
            logger.error("Failed to copy %s to workdir: %s", abs_path, exc)
            continue

        _enqueue_file(dest_path)
        _mark_processed(cache, abs_path)
        count += 1

        if delete_after:
            try:
                os.remove(abs_path)
                logger.info("Deleted source file after ingestion: %s", abs_path)
            except OSError as exc:
                logger.warning("Could not delete source file %s: %s", abs_path, exc)

    return count


# ---------------------------------------------------------------------------
# FTP watch folder scanning
# ---------------------------------------------------------------------------


def _connect_ftp() -> ftplib.FTP | None:
    """Establish an FTP/FTPS connection using the global FTP settings."""
    host = getattr(settings, "ftp_host", None)
    port = getattr(settings, "ftp_port", 21) or 21
    username = getattr(settings, "ftp_username", None)
    password = getattr(settings, "ftp_password", None)

    if not (host and username and password):
        logger.warning("FTP ingest: connection settings incomplete — skipping.")
        return None

    use_tls: bool = getattr(settings, "ftp_use_tls", True)
    allow_plaintext: bool = getattr(settings, "ftp_allow_plaintext", True)

    if use_tls:
        try:
            ftp = ftplib.FTP_TLS()  # noqa: S321
            ftp.connect(host=host, port=port)
            ftp.login(user=username, passwd=password)
            ftp.prot_p()
            logger.debug("FTP ingest: connected via FTPS to %s:%s", host, port)
            return ftp
        except Exception as exc:
            if not allow_plaintext:
                logger.error("FTP ingest: FTPS failed and plaintext not allowed: %s", exc)
                return None
            logger.warning("FTP ingest: FTPS failed, falling back to plain FTP: %s", exc)

    try:
        ftp = ftplib.FTP()  # nosec B321  # noqa: S321
        ftp.connect(host=host, port=port)
        ftp.login(user=username, passwd=password)
        logger.debug("FTP ingest: connected via plain FTP to %s:%s", host, port)
        return ftp
    except Exception as exc:
        logger.error("FTP ingest: connection failed: %s", exc)
        return None


def _scan_ftp_folder(ftp: ftplib.FTP, remote_folder: str, cache: dict[str, str], delete_after: bool) -> int:
    """
    List *remote_folder* on the FTP server and download new allowed files to workdir.
    Returns the number of files newly enqueued.
    """
    count = 0
    try:
        ftp.cwd(remote_folder)
    except ftplib.error_perm as exc:
        logger.error("FTP ingest: cannot CWD to %s: %s", remote_folder, exc)
        return 0

    try:
        filenames: list[str] = ftp.nlst()
    except Exception as exc:
        logger.error("FTP ingest: NLST failed on %s: %s", remote_folder, exc)
        return 0

    for filename in filenames:
        if not _is_allowed_file(filename):
            logger.debug("FTP ingest: skipping %s (unsupported type)", filename)
            continue

        cache_key = f"ftp:{remote_folder}/{filename}"
        if cache_key in cache:
            logger.debug("FTP ingest: already processed %s", filename)
            continue

        dest_path = os.path.join(settings.workdir, f"ftp_{filename}")
        if os.path.exists(dest_path):
            base, ext2 = os.path.splitext(f"ftp_{filename}")
            dest_path = os.path.join(settings.workdir, f"{base}_{int(datetime.now().timestamp())}{ext2}")

        try:
            with open(dest_path, "wb") as local_file:
                ftp.retrbinary(f"RETR {filename}", local_file.write)
            logger.info("FTP ingest: downloaded %s to %s", filename, dest_path)
        except Exception as exc:
            logger.error("FTP ingest: failed to download %s: %s", filename, exc)
            if os.path.exists(dest_path):
                os.remove(dest_path)
            continue

        _enqueue_file(dest_path, filename=filename)
        _mark_processed(cache, cache_key)
        count += 1

        if delete_after:
            try:
                ftp.delete(filename)
                logger.info("FTP ingest: deleted remote file %s after ingestion", filename)
            except Exception as exc:
                logger.warning("FTP ingest: could not delete remote file %s: %s", filename, exc)

    return count


# ---------------------------------------------------------------------------
# SFTP watch folder scanning
# ---------------------------------------------------------------------------


def _get_sftp_connection():
    """
    Establish an SFTP connection using the global SFTP settings.
    Returns (ssh_client, sftp_client) tuple, or (None, None) on failure.
    """
    import paramiko

    host = getattr(settings, "sftp_host", None)
    port = getattr(settings, "sftp_port", 22) or 22
    username = getattr(settings, "sftp_username", None)

    if not (host and username):
        logger.warning("SFTP ingest: connection settings incomplete — skipping.")
        return None, None

    ssh = paramiko.SSHClient()

    if getattr(settings, "sftp_disable_host_key_verification", False):
        logger.warning(
            "SFTP ingest: host key verification is DISABLED — connections are vulnerable to MITM attacks. "
            "Set SFTP_DISABLE_HOST_KEY_VERIFICATION=False for production use."
        )
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # nosec B507  # noqa: S507
    else:
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.RejectPolicy())

    connect_kwargs: dict = {"hostname": host, "port": port, "username": username}

    sftp_key_path = getattr(settings, "sftp_private_key", None)
    sftp_key_passphrase = getattr(settings, "sftp_private_key_passphrase", None)
    sftp_password = getattr(settings, "sftp_password", None)

    if sftp_key_path and os.path.exists(sftp_key_path):
        connect_kwargs["key_filename"] = sftp_key_path
        if sftp_key_passphrase:
            connect_kwargs["passphrase"] = sftp_key_passphrase
    elif sftp_password:
        connect_kwargs["password"] = sftp_password
    else:
        logger.warning("SFTP ingest: no password or private key configured — skipping.")
        return None, None

    try:
        ssh.connect(**connect_kwargs)
        sftp = ssh.open_sftp()
        logger.debug("SFTP ingest: connected to %s:%s", host, port)
        return ssh, sftp
    except Exception as exc:
        logger.error("SFTP ingest: connection failed: %s", exc)
        try:
            ssh.close()
        except Exception:
            pass
        return None, None


def _scan_sftp_folder(sftp, remote_folder: str, cache: dict[str, str], delete_after: bool) -> int:
    """
    List *remote_folder* on the SFTP server and download new allowed files to workdir.
    Returns the number of files newly enqueued.
    """
    import stat as stat_module

    count = 0
    try:
        entries = sftp.listdir_attr(remote_folder)
    except Exception as exc:
        logger.error("SFTP ingest: cannot list %s: %s", remote_folder, exc)
        return 0

    for attr in entries:
        # Skip directories
        if stat_module.S_ISDIR(attr.st_mode or 0):
            continue

        filename = attr.filename
        if not _is_allowed_file(filename):
            logger.debug("SFTP ingest: skipping %s (unsupported type)", filename)
            continue

        remote_path = f"{remote_folder}/{filename}".replace("//", "/")
        cache_key = f"sftp:{remote_path}"
        if cache_key in cache:
            logger.debug("SFTP ingest: already processed %s", filename)
            continue

        dest_path = os.path.join(settings.workdir, f"sftp_{filename}")
        if os.path.exists(dest_path):
            base, ext2 = os.path.splitext(f"sftp_{filename}")
            dest_path = os.path.join(settings.workdir, f"{base}_{int(datetime.now().timestamp())}{ext2}")

        try:
            sftp.get(remote_path, dest_path)
            logger.info("SFTP ingest: downloaded %s to %s", remote_path, dest_path)
        except Exception as exc:
            logger.error("SFTP ingest: failed to download %s: %s", remote_path, exc)
            if os.path.exists(dest_path):
                os.remove(dest_path)
            continue

        _enqueue_file(dest_path, filename=filename)
        _mark_processed(cache, cache_key)
        count += 1

        if delete_after:
            try:
                sftp.remove(remote_path)
                logger.info("SFTP ingest: deleted remote file %s after ingestion", remote_path)
            except Exception as exc:
                logger.warning("SFTP ingest: could not delete remote file %s: %s", remote_path, exc)

    return count


# ---------------------------------------------------------------------------
# Main Celery tasks
# ---------------------------------------------------------------------------


@shared_task
def scan_local_watch_folders() -> dict:
    """
    Celery task: scan all configured local filesystem watch folders for new files.

    Reads the WATCH_FOLDERS setting (comma-separated list of absolute directory paths)
    and enqueues any new allowed files for document processing.  Already-processed files
    are tracked in a JSON cache file to prevent duplicate ingestion.
    """
    watch_folders_raw: str | None = getattr(settings, "watch_folders", None)
    if not watch_folders_raw:
        logger.debug("No local watch folders configured — nothing to scan.")
        return {"status": "skipped", "reason": "WATCH_FOLDERS not configured"}

    folder_paths = [p.strip() for p in watch_folders_raw.split(",") if p.strip()]
    if not folder_paths:
        return {"status": "skipped", "reason": "WATCH_FOLDERS is empty"}

    delete_after: bool = getattr(settings, "watch_folder_delete_after_process", False)
    cache = _load_cache(WATCH_FOLDER_CACHE_FILE)
    total = 0

    for folder_path in folder_paths:
        logger.info("Scanning local watch folder: %s", folder_path)
        n = _scan_local_folder(folder_path, cache, delete_after)
        logger.info("Local watch folder %s: %d new file(s) enqueued.", folder_path, n)
        total += n

    _save_cache(WATCH_FOLDER_CACHE_FILE, cache)
    return {"status": "ok", "files_enqueued": total, "folders_scanned": len(folder_paths)}


@shared_task
def scan_ftp_watch_folder() -> dict:
    """
    Celery task: scan the configured FTP ingest folder for new files.

    Uses the existing FTP connection settings and FTP_INGEST_FOLDER to poll for
    new documents to ingest.  Downloaded files are enqueued for processing and
    (optionally) deleted from the server after download.
    """
    if not getattr(settings, "ftp_ingest_enabled", False):
        logger.debug("FTP ingest is disabled — skipping.")
        return {"status": "skipped", "reason": "FTP_INGEST_ENABLED is False"}

    ingest_folder: str | None = getattr(settings, "ftp_ingest_folder", None)
    if not ingest_folder:
        logger.warning("FTP ingest enabled but FTP_INGEST_FOLDER is not set — skipping.")
        return {"status": "skipped", "reason": "FTP_INGEST_FOLDER not configured"}

    delete_after: bool = getattr(settings, "ftp_ingest_delete_after_process", False)
    cache = _load_cache(FTP_INGEST_CACHE_FILE)

    ftp = _connect_ftp()
    if ftp is None:
        return {"status": "error", "reason": "FTP connection failed"}

    try:
        n = _scan_ftp_folder(ftp, ingest_folder, cache, delete_after)
    finally:
        try:
            ftp.quit()
        except Exception:
            pass

    _save_cache(FTP_INGEST_CACHE_FILE, cache)
    logger.info("FTP ingest: %d new file(s) enqueued from %s.", n, ingest_folder)
    return {"status": "ok", "files_enqueued": n, "folder": ingest_folder}


@shared_task
def scan_sftp_watch_folder() -> dict:
    """
    Celery task: scan the configured SFTP ingest folder for new files.

    Uses the existing SFTP connection settings and SFTP_INGEST_FOLDER to poll for
    new documents to ingest.  Downloaded files are enqueued for processing and
    (optionally) deleted from the server after download.
    """
    if not getattr(settings, "sftp_ingest_enabled", False):
        logger.debug("SFTP ingest is disabled — skipping.")
        return {"status": "skipped", "reason": "SFTP_INGEST_ENABLED is False"}

    ingest_folder: str | None = getattr(settings, "sftp_ingest_folder", None)
    if not ingest_folder:
        logger.warning("SFTP ingest enabled but SFTP_INGEST_FOLDER is not set — skipping.")
        return {"status": "skipped", "reason": "SFTP_INGEST_FOLDER not configured"}

    delete_after: bool = getattr(settings, "sftp_ingest_delete_after_process", False)
    cache = _load_cache(SFTP_INGEST_CACHE_FILE)

    ssh, sftp = _get_sftp_connection()
    if sftp is None:
        return {"status": "error", "reason": "SFTP connection failed"}

    try:
        n = _scan_sftp_folder(sftp, ingest_folder, cache, delete_after)
    finally:
        try:
            sftp.close()
        except Exception:
            pass
        try:
            ssh.close()
        except Exception:
            pass

    _save_cache(SFTP_INGEST_CACHE_FILE, cache)
    logger.info("SFTP ingest: %d new file(s) enqueued from %s.", n, ingest_folder)
    return {"status": "ok", "files_enqueued": n, "folder": ingest_folder}


@shared_task
def scan_all_watch_folders() -> dict:
    """
    Main periodic Celery task that runs all watch-folder scans.

    Acquires a Redis lock to prevent concurrent runs, then sequentially:
    1. Scans local filesystem watch folders
    2. Scans FTP ingest folder (if enabled)
    3. Scans SFTP ingest folder (if enabled)
    """
    if not _acquire_lock(WATCH_FOLDER_LOCK_KEY):
        logger.info("Watch folder scan already running — skipping this cycle.")
        return {"status": "skipped", "reason": "lock held"}

    results: dict = {}
    try:
        results["local"] = scan_local_watch_folders()
        results["ftp"] = scan_ftp_watch_folder()
        results["sftp"] = scan_sftp_watch_folder()
    finally:
        _release_lock(WATCH_FOLDER_LOCK_KEY)

    return {"status": "ok", "results": results}
