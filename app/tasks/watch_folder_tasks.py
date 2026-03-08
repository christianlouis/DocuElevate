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
from datetime import datetime, timedelta, timezone

import redis
from celery import shared_task

from app.config import settings
from app.tasks.convert_to_pdf import convert_to_pdf
from app.tasks.process_document import process_document
from app.utils.allowed_types import ALLOWED_EXTENSIONS

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
        except Exception as close_exc:
            logger.debug("SFTP ingest: error closing SSH after failed connection: %s", close_exc)
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
# Dropbox watch folder scanning
# ---------------------------------------------------------------------------

# Additional cache files for cloud providers
DROPBOX_INGEST_CACHE_FILE = os.path.join(settings.workdir, "dropbox_ingest_processed.json")
GDRIVE_INGEST_CACHE_FILE = os.path.join(settings.workdir, "gdrive_ingest_processed.json")
ONEDRIVE_INGEST_CACHE_FILE = os.path.join(settings.workdir, "onedrive_ingest_processed.json")
NEXTCLOUD_INGEST_CACHE_FILE = os.path.join(settings.workdir, "nextcloud_ingest_processed.json")
S3_INGEST_CACHE_FILE = os.path.join(settings.workdir, "s3_ingest_processed.json")
WEBDAV_INGEST_CACHE_FILE = os.path.join(settings.workdir, "webdav_ingest_processed.json")


def _scan_dropbox_folder(folder_path: str, cache: dict[str, str], delete_after: bool) -> int:
    """
    List *folder_path* in Dropbox and download new allowed files to workdir.
    Returns the number of files newly enqueued.
    """
    try:
        from app.tasks.upload_to_dropbox import get_dropbox_client
    except ImportError as exc:
        logger.error("Dropbox ingest: dropbox SDK not installed: %s", exc)
        return 0

    try:
        dbx = get_dropbox_client()
    except Exception as exc:
        logger.error("Dropbox ingest: authentication failed: %s", exc)
        return 0

    count = 0
    try:
        result = dbx.files_list_folder(folder_path)
        entries = result.entries
        while result.has_more:
            result = dbx.files_list_folder_continue(result.cursor)
            entries.extend(result.entries)
    except Exception as exc:
        logger.error("Dropbox ingest: cannot list folder %s: %s", folder_path, exc)
        return 0

    for entry in entries:
        # Only process files, not sub-folders
        import dropbox as dropbox_module

        if not isinstance(entry, dropbox_module.files.FileMetadata):
            continue

        filename = entry.name
        if not _is_allowed_file(filename):
            logger.debug("Dropbox ingest: skipping %s (unsupported type)", filename)
            continue

        cache_key = f"dropbox:{entry.id}"
        if cache_key in cache:
            logger.debug("Dropbox ingest: already processed %s", filename)
            continue

        dest_path = os.path.join(settings.workdir, f"dropbox_{filename}")
        if os.path.exists(dest_path):
            base, ext2 = os.path.splitext(f"dropbox_{filename}")
            dest_path = os.path.join(settings.workdir, f"{base}_{int(datetime.now().timestamp())}{ext2}")

        try:
            _meta, response = dbx.files_download(entry.path_lower)
            with open(dest_path, "wb") as f:
                f.write(response.content)
            logger.info("Dropbox ingest: downloaded %s to %s", filename, dest_path)
        except Exception as exc:
            logger.error("Dropbox ingest: failed to download %s: %s", filename, exc)
            if os.path.exists(dest_path):
                os.remove(dest_path)
            continue

        _enqueue_file(dest_path, filename=filename)
        _mark_processed(cache, cache_key)
        count += 1

        if delete_after:
            try:
                dbx.files_delete_v2(entry.path_lower)
                logger.info("Dropbox ingest: deleted %s after ingestion", entry.path_lower)
            except Exception as exc:
                logger.warning("Dropbox ingest: could not delete %s: %s", entry.path_lower, exc)

    return count


# ---------------------------------------------------------------------------
# Google Drive watch folder scanning
# ---------------------------------------------------------------------------


def _scan_google_drive_folder(folder_id: str, cache: dict[str, str], delete_after: bool) -> int:
    """
    List files in *folder_id* on Google Drive and download new allowed files to workdir.
    Returns the number of files newly enqueued.
    """
    try:
        from app.tasks.upload_to_google_drive import get_google_drive_service
    except ImportError as exc:
        logger.error("Google Drive ingest: google-api SDK not installed: %s", exc)
        return 0

    service = get_google_drive_service()
    if service is None:
        logger.error("Google Drive ingest: could not authenticate.")
        return 0

    count = 0
    query = f"'{folder_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'"
    page_token = None

    while True:
        try:
            params: dict = {
                "q": query,
                "fields": "nextPageToken, files(id, name, mimeType)",
                "pageSize": 100,
            }
            if page_token:
                params["pageToken"] = page_token
            response = service.files().list(**params).execute()
        except Exception as exc:
            logger.error("Google Drive ingest: listing folder %s failed: %s", folder_id, exc)
            break

        for file_meta in response.get("files", []):
            file_id_gd = file_meta["id"]
            filename = file_meta["name"]

            if not _is_allowed_file(filename):
                logger.debug("Google Drive ingest: skipping %s (unsupported type)", filename)
                continue

            cache_key = f"gdrive:{file_id_gd}"
            if cache_key in cache:
                logger.debug("Google Drive ingest: already processed %s", filename)
                continue

            dest_path = os.path.join(settings.workdir, f"gdrive_{filename}")
            if os.path.exists(dest_path):
                base, ext2 = os.path.splitext(f"gdrive_{filename}")
                dest_path = os.path.join(settings.workdir, f"{base}_{int(datetime.now().timestamp())}{ext2}")

            try:
                import io

                from googleapiclient.http import MediaIoBaseDownload

                request = service.files().get_media(fileId=file_id_gd)
                buf = io.BytesIO()
                downloader = MediaIoBaseDownload(buf, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                with open(dest_path, "wb") as f:
                    f.write(buf.getvalue())
                logger.info("Google Drive ingest: downloaded %s to %s", filename, dest_path)
            except Exception as exc:
                logger.error("Google Drive ingest: failed to download %s: %s", filename, exc)
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                continue

            _enqueue_file(dest_path, filename=filename)
            _mark_processed(cache, cache_key)
            count += 1

            if delete_after:
                try:
                    service.files().delete(fileId=file_id_gd).execute()
                    logger.info("Google Drive ingest: deleted %s after ingestion", filename)
                except Exception as exc:
                    logger.warning("Google Drive ingest: could not delete %s: %s", filename, exc)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return count


# ---------------------------------------------------------------------------
# OneDrive watch folder scanning
# ---------------------------------------------------------------------------


def _scan_onedrive_folder(folder_path: str, cache: dict[str, str], delete_after: bool) -> int:
    """
    List files in *folder_path* on OneDrive (Microsoft Graph) and download new allowed
    files to workdir.  Returns the number of files newly enqueued.
    """
    import requests as req_lib

    try:
        from app.tasks.upload_to_onedrive import get_onedrive_token
    except ImportError as exc:
        logger.error("OneDrive ingest: msal not installed: %s", exc)
        return 0

    try:
        token = get_onedrive_token()
    except Exception as exc:
        logger.error("OneDrive ingest: authentication failed: %s", exc)
        return 0

    headers = {"Authorization": f"Bearer {token}"}

    # URL-encode the path and construct the Graph API endpoint
    import urllib.parse

    encoded_path = urllib.parse.quote(folder_path.lstrip("/"))
    list_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}:/children"

    count = 0
    while list_url:
        try:
            resp = req_lib.get(list_url, headers=headers, timeout=getattr(settings, "http_request_timeout", 120))
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("OneDrive ingest: listing folder %s failed: %s", folder_path, exc)
            break

        for item in data.get("value", []):
            # Skip folders
            if "folder" in item:
                continue

            filename = item["name"]
            item_id = item["id"]

            if not _is_allowed_file(filename):
                logger.debug("OneDrive ingest: skipping %s (unsupported type)", filename)
                continue

            cache_key = f"onedrive:{item_id}"
            if cache_key in cache:
                logger.debug("OneDrive ingest: already processed %s", filename)
                continue

            # Get download URL
            download_url = item.get("@microsoft.graph.downloadUrl")
            if not download_url:
                logger.warning("OneDrive ingest: no download URL for %s — skipping.", filename)
                continue

            dest_path = os.path.join(settings.workdir, f"onedrive_{filename}")
            if os.path.exists(dest_path):
                base, ext2 = os.path.splitext(f"onedrive_{filename}")
                dest_path = os.path.join(settings.workdir, f"{base}_{int(datetime.now().timestamp())}{ext2}")

            try:
                dl_resp = req_lib.get(
                    download_url, headers=headers, timeout=getattr(settings, "http_request_timeout", 120)
                )
                dl_resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    f.write(dl_resp.content)
                logger.info("OneDrive ingest: downloaded %s to %s", filename, dest_path)
            except Exception as exc:
                logger.error("OneDrive ingest: failed to download %s: %s", filename, exc)
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                continue

            _enqueue_file(dest_path, filename=filename)
            _mark_processed(cache, cache_key)
            count += 1

            if delete_after:
                try:
                    del_resp = req_lib.delete(
                        f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}",
                        headers=headers,
                        timeout=getattr(settings, "http_request_timeout", 120),
                    )
                    del_resp.raise_for_status()
                    logger.info("OneDrive ingest: deleted %s after ingestion", filename)
                except Exception as exc:
                    logger.warning("OneDrive ingest: could not delete %s: %s", filename, exc)

        list_url = data.get("@odata.nextLink")

    return count


# ---------------------------------------------------------------------------
# Nextcloud watch folder scanning (WebDAV)
# ---------------------------------------------------------------------------


def _scan_nextcloud_folder(folder_path: str, cache: dict[str, str], delete_after: bool) -> int:
    """
    List files in *folder_path* on Nextcloud (via WebDAV PROPFIND) and download new
    allowed files to workdir.  Returns the number of files newly enqueued.
    """
    import defusedxml.ElementTree as ET
    import requests as req_lib
    from requests.auth import HTTPBasicAuth

    nc_url: str | None = getattr(settings, "nextcloud_upload_url", None)
    nc_user: str | None = getattr(settings, "nextcloud_username", None)
    nc_pass: str | None = getattr(settings, "nextcloud_password", None)

    if not (nc_url and nc_user and nc_pass):
        logger.warning("Nextcloud ingest: connection settings incomplete — skipping.")
        return 0

    auth = HTTPBasicAuth(nc_user, nc_pass)
    timeout = getattr(settings, "http_request_timeout", 120)

    # Build the WebDAV PROPFIND URL
    base = nc_url.rstrip("/")
    folder = folder_path.strip("/")
    propfind_url = f"{base}/{folder}/" if folder else f"{base}/"

    try:
        resp = req_lib.request(
            "PROPFIND",
            propfind_url,
            auth=auth,
            headers={"Depth": "1", "Content-Type": "application/xml"},
            timeout=timeout,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.error("Nextcloud ingest: PROPFIND on %s failed: %s", propfind_url, exc)
        return 0

    count = 0
    # Parse WebDAV multistatus response using defusedxml (safe against XML bomb attacks)
    try:
        root = ET.fromstring(resp.text)  # noqa: S314 — defusedxml is safe
    except Exception as exc:
        logger.error("Nextcloud ingest: failed to parse PROPFIND response: %s", exc)
        return 0

    ns = {"d": "DAV:"}
    for response_el in root.findall("d:response", ns):
        href_el = response_el.find("d:href", ns)
        if href_el is None or href_el.text is None:
            continue

        href = href_el.text
        # Skip the folder itself
        if href.rstrip("/").endswith(folder.rstrip("/")):
            continue

        filename = href.rstrip("/").split("/")[-1]
        import urllib.parse

        filename = urllib.parse.unquote(filename)

        if not _is_allowed_file(filename):
            logger.debug("Nextcloud ingest: skipping %s (unsupported type)", filename)
            continue

        # Use the href as cache key (stable across runs)
        cache_key = f"nextcloud:{href}"
        if cache_key in cache:
            logger.debug("Nextcloud ingest: already processed %s", filename)
            continue

        # Build absolute download URL
        if href.startswith("http"):
            file_url = href
        else:
            from urllib.parse import urlparse

            parsed = urlparse(nc_url)
            file_url = f"{parsed.scheme}://{parsed.netloc}{href}"

        dest_path = os.path.join(settings.workdir, f"nc_{filename}")
        if os.path.exists(dest_path):
            base_name, ext2 = os.path.splitext(f"nc_{filename}")
            dest_path = os.path.join(settings.workdir, f"{base_name}_{int(datetime.now().timestamp())}{ext2}")

        try:
            dl = req_lib.get(file_url, auth=auth, timeout=timeout)
            dl.raise_for_status()
            with open(dest_path, "wb") as f:
                f.write(dl.content)
            logger.info("Nextcloud ingest: downloaded %s to %s", filename, dest_path)
        except Exception as exc:
            logger.error("Nextcloud ingest: failed to download %s: %s", filename, exc)
            if os.path.exists(dest_path):
                os.remove(dest_path)
            continue

        _enqueue_file(dest_path, filename=filename)
        _mark_processed(cache, cache_key)
        count += 1

        if delete_after:
            try:
                del_resp = req_lib.request("DELETE", file_url, auth=auth, timeout=timeout)
                del_resp.raise_for_status()
                logger.info("Nextcloud ingest: deleted %s after ingestion", filename)
            except Exception as exc:
                logger.warning("Nextcloud ingest: could not delete %s: %s", filename, exc)

    return count


# ---------------------------------------------------------------------------
# S3 watch folder scanning
# ---------------------------------------------------------------------------


def _scan_s3_prefix(prefix: str, cache: dict[str, str], delete_after: bool) -> int:
    """
    List objects under *prefix* in the configured S3 bucket and download new allowed
    files to workdir.  Returns the number of files newly enqueued.
    """
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError as exc:
        logger.error("S3 ingest: boto3 not installed: %s", exc)
        return 0

    bucket = getattr(settings, "s3_bucket_name", None)
    if not bucket:
        logger.warning("S3 ingest: S3_BUCKET_NAME not set — skipping.")
        return 0

    try:
        s3 = boto3.client(
            "s3",
            region_name=getattr(settings, "aws_region", "us-east-1"),
            aws_access_key_id=getattr(settings, "aws_access_key_id", None),
            aws_secret_access_key=getattr(settings, "aws_secret_access_key", None),
        )
    except Exception as exc:
        logger.error("S3 ingest: failed to create S3 client: %s", exc)
        return 0

    count = 0
    paginator = s3.get_paginator("list_objects_v2")

    try:
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
    except Exception as exc:
        logger.error("S3 ingest: failed to list objects in %s/%s: %s", bucket, prefix, exc)
        return 0

    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            filename = key.split("/")[-1]

            # Skip zero-byte "folder marker" objects and unsupported types
            if not filename or not _is_allowed_file(filename):
                logger.debug("S3 ingest: skipping %s (unsupported or empty)", key)
                continue

            cache_key = f"s3:{bucket}/{key}"
            if cache_key in cache:
                logger.debug("S3 ingest: already processed %s", key)
                continue

            dest_path = os.path.join(settings.workdir, f"s3_{filename}")
            if os.path.exists(dest_path):
                base2, ext2 = os.path.splitext(f"s3_{filename}")
                dest_path = os.path.join(settings.workdir, f"{base2}_{int(datetime.now().timestamp())}{ext2}")

            try:
                s3.download_file(bucket, key, dest_path)
                logger.info("S3 ingest: downloaded s3://%s/%s to %s", bucket, key, dest_path)
            except ClientError as exc:
                logger.error("S3 ingest: failed to download %s: %s", key, exc)
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                continue

            _enqueue_file(dest_path, filename=filename)
            _mark_processed(cache, cache_key)
            count += 1

            if delete_after:
                try:
                    s3.delete_object(Bucket=bucket, Key=key)
                    logger.info("S3 ingest: deleted s3://%s/%s after ingestion", bucket, key)
                except Exception as exc:
                    logger.warning("S3 ingest: could not delete s3://%s/%s: %s", bucket, key, exc)

    return count


# ---------------------------------------------------------------------------
# WebDAV watch folder scanning
# ---------------------------------------------------------------------------


def _scan_webdav_folder(folder_path: str, cache: dict[str, str], delete_after: bool) -> int:
    """
    List files in *folder_path* on a WebDAV server (PROPFIND) and download new allowed
    files to workdir.  Returns the number of files newly enqueued.
    """
    import defusedxml.ElementTree as ET
    import requests as req_lib
    from requests.auth import HTTPBasicAuth

    webdav_url: str | None = getattr(settings, "webdav_url", None)
    webdav_user: str | None = getattr(settings, "webdav_username", None)
    webdav_pass: str | None = getattr(settings, "webdav_password", None)
    verify_ssl: bool = getattr(settings, "webdav_verify_ssl", True)
    timeout = getattr(settings, "http_request_timeout", 120)

    if not webdav_url:
        logger.warning("WebDAV ingest: WEBDAV_URL not configured — skipping.")
        return 0

    from urllib.parse import unquote, urlparse

    base = webdav_url.rstrip("/")
    folder = folder_path.strip("/")
    propfind_url = f"{base}/{folder}/" if folder else f"{base}/"

    auth = HTTPBasicAuth(webdav_user, webdav_pass) if webdav_user else None

    try:
        resp = req_lib.request(
            "PROPFIND",
            propfind_url,
            auth=auth,
            headers={"Depth": "1"},
            verify=verify_ssl,
            timeout=timeout,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.error("WebDAV ingest: PROPFIND on %s failed: %s", propfind_url, exc)
        return 0

    count = 0
    try:
        root = ET.fromstring(resp.text)  # noqa: S314 — defusedxml is safe
    except Exception as exc:
        logger.error("WebDAV ingest: failed to parse PROPFIND response: %s", exc)
        return 0

    ns = {"d": "DAV:"}
    for response_el in root.findall("d:response", ns):
        href_el = response_el.find("d:href", ns)
        if href_el is None or href_el.text is None:
            continue

        href = href_el.text
        # Skip the folder itself and anything that looks like a directory
        if href.endswith("/"):
            continue

        filename = unquote(href.split("/")[-1])
        if not _is_allowed_file(filename):
            logger.debug("WebDAV ingest: skipping %s (unsupported type)", filename)
            continue

        cache_key = f"webdav:{href}"
        if cache_key in cache:
            logger.debug("WebDAV ingest: already processed %s", filename)
            continue

        # Build absolute URL
        if href.startswith("http"):
            file_url = href
        else:
            parsed = urlparse(webdav_url)
            file_url = f"{parsed.scheme}://{parsed.netloc}{href}"

        dest_path = os.path.join(settings.workdir, f"webdav_{filename}")
        if os.path.exists(dest_path):
            base2, ext2 = os.path.splitext(f"webdav_{filename}")
            dest_path = os.path.join(settings.workdir, f"{base2}_{int(datetime.now().timestamp())}{ext2}")

        try:
            dl = req_lib.get(file_url, auth=auth, verify=verify_ssl, timeout=timeout)
            dl.raise_for_status()
            with open(dest_path, "wb") as f:
                f.write(dl.content)
            logger.info("WebDAV ingest: downloaded %s to %s", filename, dest_path)
        except Exception as exc:
            logger.error("WebDAV ingest: failed to download %s: %s", filename, exc)
            if os.path.exists(dest_path):
                os.remove(dest_path)
            continue

        _enqueue_file(dest_path, filename=filename)
        _mark_processed(cache, cache_key)
        count += 1

        if delete_after:
            try:
                del_resp = req_lib.request("DELETE", file_url, auth=auth, verify=verify_ssl, timeout=timeout)
                del_resp.raise_for_status()
                logger.info("WebDAV ingest: deleted %s after ingestion", filename)
            except Exception as exc:
                logger.warning("WebDAV ingest: could not delete %s: %s", filename, exc)

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
        except Exception as exc:
            logger.debug("FTP ingest: error during FTP quit: %s", exc)

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
        except Exception as exc:
            logger.debug("SFTP ingest: error closing SFTP channel: %s", exc)
        try:
            ssh.close()
        except Exception as exc:
            logger.debug("SFTP ingest: error closing SSH connection: %s", exc)

    _save_cache(SFTP_INGEST_CACHE_FILE, cache)
    logger.info("SFTP ingest: %d new file(s) enqueued from %s.", n, ingest_folder)
    return {"status": "ok", "files_enqueued": n, "folder": ingest_folder}


@shared_task
def scan_dropbox_watch_folder() -> dict:
    """
    Celery task: scan the configured Dropbox ingest folder for new files.

    Uses the existing Dropbox OAuth credentials and DROPBOX_INGEST_FOLDER to poll
    for new documents.
    """
    if not getattr(settings, "dropbox_ingest_enabled", False):
        return {"status": "skipped", "reason": "DROPBOX_INGEST_ENABLED is False"}

    ingest_folder: str | None = getattr(settings, "dropbox_ingest_folder", None)
    if not ingest_folder:
        logger.warning("Dropbox ingest enabled but DROPBOX_INGEST_FOLDER is not set — skipping.")
        return {"status": "skipped", "reason": "DROPBOX_INGEST_FOLDER not configured"}

    delete_after: bool = getattr(settings, "dropbox_ingest_delete_after_process", False)
    cache = _load_cache(DROPBOX_INGEST_CACHE_FILE)
    n = _scan_dropbox_folder(ingest_folder, cache, delete_after)
    _save_cache(DROPBOX_INGEST_CACHE_FILE, cache)
    logger.info("Dropbox ingest: %d new file(s) enqueued from %s.", n, ingest_folder)
    return {"status": "ok", "files_enqueued": n, "folder": ingest_folder}


@shared_task
def scan_google_drive_watch_folder() -> dict:
    """
    Celery task: scan the configured Google Drive ingest folder for new files.

    Uses the existing Google Drive credentials and GOOGLE_DRIVE_INGEST_FOLDER_ID to
    poll for new documents.
    """
    if not getattr(settings, "google_drive_ingest_enabled", False):
        return {"status": "skipped", "reason": "GOOGLE_DRIVE_INGEST_ENABLED is False"}

    folder_id: str | None = getattr(settings, "google_drive_ingest_folder_id", None)
    if not folder_id:
        logger.warning("Google Drive ingest enabled but GOOGLE_DRIVE_INGEST_FOLDER_ID is not set — skipping.")
        return {"status": "skipped", "reason": "GOOGLE_DRIVE_INGEST_FOLDER_ID not configured"}

    delete_after: bool = getattr(settings, "google_drive_ingest_delete_after_process", False)
    cache = _load_cache(GDRIVE_INGEST_CACHE_FILE)
    n = _scan_google_drive_folder(folder_id, cache, delete_after)
    _save_cache(GDRIVE_INGEST_CACHE_FILE, cache)
    logger.info("Google Drive ingest: %d new file(s) enqueued from folder %s.", n, folder_id)
    return {"status": "ok", "files_enqueued": n, "folder_id": folder_id}


@shared_task
def scan_onedrive_watch_folder() -> dict:
    """
    Celery task: scan the configured OneDrive ingest folder for new files.

    Uses the existing OneDrive MSAL credentials and ONEDRIVE_INGEST_FOLDER_PATH to
    poll for new documents.
    """
    if not getattr(settings, "onedrive_ingest_enabled", False):
        return {"status": "skipped", "reason": "ONEDRIVE_INGEST_ENABLED is False"}

    folder_path: str | None = getattr(settings, "onedrive_ingest_folder_path", None)
    if not folder_path:
        logger.warning("OneDrive ingest enabled but ONEDRIVE_INGEST_FOLDER_PATH is not set — skipping.")
        return {"status": "skipped", "reason": "ONEDRIVE_INGEST_FOLDER_PATH not configured"}

    delete_after: bool = getattr(settings, "onedrive_ingest_delete_after_process", False)
    cache = _load_cache(ONEDRIVE_INGEST_CACHE_FILE)
    n = _scan_onedrive_folder(folder_path, cache, delete_after)
    _save_cache(ONEDRIVE_INGEST_CACHE_FILE, cache)
    logger.info("OneDrive ingest: %d new file(s) enqueued from %s.", n, folder_path)
    return {"status": "ok", "files_enqueued": n, "folder": folder_path}


@shared_task
def scan_nextcloud_watch_folder() -> dict:
    """
    Celery task: scan the configured Nextcloud ingest folder for new files.

    Uses the existing Nextcloud WebDAV credentials and NEXTCLOUD_INGEST_FOLDER to
    poll for new documents.
    """
    if not getattr(settings, "nextcloud_ingest_enabled", False):
        return {"status": "skipped", "reason": "NEXTCLOUD_INGEST_ENABLED is False"}

    ingest_folder: str | None = getattr(settings, "nextcloud_ingest_folder", None)
    if not ingest_folder:
        logger.warning("Nextcloud ingest enabled but NEXTCLOUD_INGEST_FOLDER is not set — skipping.")
        return {"status": "skipped", "reason": "NEXTCLOUD_INGEST_FOLDER not configured"}

    delete_after: bool = getattr(settings, "nextcloud_ingest_delete_after_process", False)
    cache = _load_cache(NEXTCLOUD_INGEST_CACHE_FILE)
    n = _scan_nextcloud_folder(ingest_folder, cache, delete_after)
    _save_cache(NEXTCLOUD_INGEST_CACHE_FILE, cache)
    logger.info("Nextcloud ingest: %d new file(s) enqueued from %s.", n, ingest_folder)
    return {"status": "ok", "files_enqueued": n, "folder": ingest_folder}


@shared_task
def scan_s3_watch_folder() -> dict:
    """
    Celery task: scan the configured S3 ingest prefix for new objects.

    Uses the existing S3/AWS credentials and S3_INGEST_PREFIX to poll for new
    documents in the configured S3 bucket.
    """
    if not getattr(settings, "s3_ingest_enabled", False):
        return {"status": "skipped", "reason": "S3_INGEST_ENABLED is False"}

    ingest_prefix: str | None = getattr(settings, "s3_ingest_prefix", None)
    if not ingest_prefix:
        logger.warning("S3 ingest enabled but S3_INGEST_PREFIX is not set — skipping.")
        return {"status": "skipped", "reason": "S3_INGEST_PREFIX not configured"}

    delete_after: bool = getattr(settings, "s3_ingest_delete_after_process", False)
    cache = _load_cache(S3_INGEST_CACHE_FILE)
    n = _scan_s3_prefix(ingest_prefix, cache, delete_after)
    _save_cache(S3_INGEST_CACHE_FILE, cache)
    logger.info("S3 ingest: %d new file(s) enqueued from prefix %s.", n, ingest_prefix)
    return {"status": "ok", "files_enqueued": n, "prefix": ingest_prefix}


@shared_task
def scan_webdav_watch_folder() -> dict:
    """
    Celery task: scan the configured WebDAV ingest folder for new files.

    Uses the existing WebDAV URL/credentials and WEBDAV_INGEST_FOLDER to poll for
    new documents.
    """
    if not getattr(settings, "webdav_ingest_enabled", False):
        return {"status": "skipped", "reason": "WEBDAV_INGEST_ENABLED is False"}

    ingest_folder: str | None = getattr(settings, "webdav_ingest_folder", None)
    if not ingest_folder:
        logger.warning("WebDAV ingest enabled but WEBDAV_INGEST_FOLDER is not set — skipping.")
        return {"status": "skipped", "reason": "WEBDAV_INGEST_FOLDER not configured"}

    delete_after: bool = getattr(settings, "webdav_ingest_delete_after_process", False)
    cache = _load_cache(WEBDAV_INGEST_CACHE_FILE)
    n = _scan_webdav_folder(ingest_folder, cache, delete_after)
    _save_cache(WEBDAV_INGEST_CACHE_FILE, cache)
    logger.info("WebDAV ingest: %d new file(s) enqueued from %s.", n, ingest_folder)
    return {"status": "ok", "files_enqueued": n, "folder": ingest_folder}


@shared_task
def scan_all_watch_folders() -> dict:
    """
    Main periodic Celery task that runs all watch-folder scans.

    Acquires a Redis lock to prevent concurrent runs, then sequentially scans:
    1. Local filesystem watch folders
    2. FTP ingest folder (if enabled)
    3. SFTP ingest folder (if enabled)
    4. Dropbox ingest folder (if enabled)
    5. Google Drive ingest folder (if enabled)
    6. OneDrive ingest folder (if enabled)
    7. Nextcloud ingest folder (if enabled)
    8. Amazon S3 ingest prefix (if enabled)
    9. WebDAV ingest folder (if enabled)
    """
    if not _acquire_lock(WATCH_FOLDER_LOCK_KEY):
        logger.info("Watch folder scan already running — skipping this cycle.")
        return {"status": "skipped", "reason": "lock held"}

    results: dict = {}
    try:
        results["local"] = scan_local_watch_folders()
        results["ftp"] = scan_ftp_watch_folder()
        results["sftp"] = scan_sftp_watch_folder()
        results["dropbox"] = scan_dropbox_watch_folder()
        results["google_drive"] = scan_google_drive_watch_folder()
        results["onedrive"] = scan_onedrive_watch_folder()
        results["nextcloud"] = scan_nextcloud_watch_folder()
        results["s3"] = scan_s3_watch_folder()
        results["webdav"] = scan_webdav_watch_folder()
    finally:
        _release_lock(WATCH_FOLDER_LOCK_KEY)

    return {"status": "ok", "results": results}
