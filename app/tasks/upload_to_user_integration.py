#!/usr/bin/env python3
"""
Upload dispatcher for user-specific destination integrations.

This module provides a Celery task that uploads a processed document to a
specific ``UserIntegration`` record using that integration's own stored
config and decrypted credentials — instead of the global application settings.

It is the per-destination counterpart of :func:`send_to_all_destinations`
and is dispatched by :func:`send_to_user_destinations` once per active
DESTINATION integration that belongs to the document's owner.

Credential shapes per integration type (mirrors the UserIntegration docstring):

DROPBOX     credentials = {"refresh_token", "app_key", "app_secret"}
            config      = {"folder": "/DocuElevate"}

S3          credentials = {"access_key_id", "secret_access_key"}
            config      = {"bucket", "region", "endpoint_url", "folder_prefix"}

GOOGLE_DRIVE
  OAuth     credentials = {"client_id", "client_secret", "refresh_token"}
            config      = {"folder_id"}
  SA        credentials = {"credentials_json"}
            config      = {"folder_id"}

ONEDRIVE    credentials = {"client_id", "client_secret", "refresh_token"}
            config      = {"folder_path", "tenant_id"}

WEBDAV /
NEXTCLOUD   credentials = {"username", "password"}
            config      = {"url", "folder"}

FTP         credentials = {"password"}
            config      = {"host", "username", "port", "folder", "use_tls"}

SFTP        credentials = {"password"} or {"private_key"}
            config      = {"host", "username", "port", "folder"}

EMAIL       credentials = {"password"}
            config      = {"host", "username", "port", "recipient",
                           "use_tls", "sender_name"}

PAPERLESS   credentials = {"api_token"}
            config      = {"host"}

RCLONE      credentials = {"rclone_conf"}   (full rclone config file text)
            config      = {"remote": "myremote:", "folder": "dest/path"}
"""

import ftplib  # nosec B402
import json
import logging
import os
import subprocess  # nosec B404
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

from app.celery_app import celery
from app.database import SessionLocal
from app.models import IntegrationType, UserIntegration
from app.tasks.retry_config import UploadTaskWithRetry
from app.utils.encryption import decrypt_value
from app.utils.logging import log_task_progress

logger = logging.getLogger(__name__)

# Maximum characters to store in UserIntegration.last_error
_MAX_ERROR_LENGTH = 500


# ---------------------------------------------------------------------------
# Per-type upload helpers
# ---------------------------------------------------------------------------


def _upload_dropbox(file_path: str, cfg: dict[str, Any], creds: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Upload *file_path* to Dropbox using per-user OAuth credentials."""
    import dropbox

    app_key = creds.get("app_key") or ""
    app_secret = creds.get("app_secret") or ""
    refresh_token = creds.get("refresh_token") or ""

    if not (app_key and app_secret and refresh_token):
        raise ValueError("Dropbox integration is missing app_key, app_secret or refresh_token in credentials")

    dbx = dropbox.Dropbox(app_key=app_key, app_secret=app_secret, oauth2_refresh_token=refresh_token)

    remote_folder = cfg.get("folder", "/DocuElevate").rstrip("/")
    filename = os.path.basename(file_path)
    remote_path = f"{remote_folder}/{filename}"
    if not remote_path.startswith("/"):
        remote_path = "/" + remote_path

    file_size = os.path.getsize(file_path)
    with open(file_path, "rb") as fh:
        if file_size > 10 * 1024 * 1024:
            chunk_size = 4 * 1024 * 1024
            session_start = dbx.files_upload_session_start(fh.read(chunk_size))
            cursor = dropbox.files.UploadSessionCursor(session_start.session_id, fh.tell())
            while fh.tell() < file_size:
                if (file_size - fh.tell()) <= chunk_size:
                    dbx.files_upload_session_finish(
                        fh.read(chunk_size),
                        cursor,
                        dropbox.files.CommitInfo(path=remote_path, mode=dropbox.files.WriteMode.overwrite),
                    )
                else:
                    dbx.files_upload_session_append_v2(fh.read(chunk_size), cursor)
                    cursor.offset = fh.tell()
        else:
            dbx.files_upload(fh.read(), remote_path, mode=dropbox.files.WriteMode.overwrite)

    logger.info("[%s] Dropbox upload complete: %s", task_id, remote_path)
    return {"status": "Completed", "dropbox_path": remote_path}


def _upload_s3(file_path: str, cfg: dict[str, Any], creds: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Upload *file_path* to Amazon S3 (or S3-compatible) using per-user credentials."""
    import boto3
    from botocore.exceptions import ClientError

    bucket = cfg.get("bucket") or ""
    region = cfg.get("region") or "us-east-1"
    endpoint_url = cfg.get("endpoint_url") or None
    folder_prefix = cfg.get("folder_prefix") or ""
    storage_class = cfg.get("storage_class") or "STANDARD"

    access_key = creds.get("access_key_id") or ""
    secret_key = creds.get("secret_access_key") or ""

    if not bucket:
        raise ValueError("S3 integration is missing bucket in config")
    if not (access_key and secret_key):
        raise ValueError("S3 integration is missing access_key_id or secret_access_key in credentials")

    client_kwargs: dict[str, Any] = {
        "region_name": region,
        "aws_access_key_id": access_key,
        "aws_secret_access_key": secret_key,
    }
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url

    s3 = boto3.client("s3", **client_kwargs)

    filename = os.path.basename(file_path)
    s3_key = f"{folder_prefix.rstrip('/')}/{filename}" if folder_prefix else filename

    try:
        s3.upload_file(file_path, bucket, s3_key, ExtraArgs={"StorageClass": storage_class})
    except ClientError as exc:
        raise RuntimeError(f"S3 upload failed: {exc}") from exc

    logger.info("[%s] S3 upload complete: s3://%s/%s", task_id, bucket, s3_key)
    return {"status": "Completed", "s3_bucket": bucket, "s3_key": s3_key}


def _upload_google_drive(file_path: str, cfg: dict[str, Any], creds: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Upload *file_path* to Google Drive using per-user OAuth or service-account credentials."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    folder_id = cfg.get("folder_id") or ""
    filename = os.path.basename(file_path)

    # Prefer OAuth credentials (client_id + client_secret + refresh_token)
    client_id = creds.get("client_id") or ""
    client_secret = creds.get("client_secret") or ""
    refresh_token = creds.get("refresh_token") or ""
    credentials_json = creds.get("credentials_json") or ""

    if client_id and client_secret and refresh_token:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials as OAuthCredentials

        google_creds = OAuthCredentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        google_creds.refresh(Request())
        service = build("drive", "v3", credentials=google_creds)
    elif credentials_json:
        from google.oauth2.service_account import Credentials as SACredentials

        creds_dict = json.loads(credentials_json)
        sa_creds = SACredentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/drive"])
        service = build("drive", "v3", credentials=sa_creds)
    else:
        raise ValueError("Google Drive integration requires either OAuth credentials or credentials_json")

    file_metadata: dict[str, Any] = {"name": filename}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaFileUpload(file_path, mimetype="application/pdf", resumable=True)
    file_obj = service.files().create(body=file_metadata, media_body=media, fields="id,name,webViewLink").execute()

    gdrive_id = file_obj.get("id")
    web_link = file_obj.get("webViewLink")
    logger.info("[%s] Google Drive upload complete: %s (%s)", task_id, gdrive_id, web_link)
    return {"status": "Completed", "google_drive_file_id": gdrive_id, "web_link": web_link}


def _upload_onedrive(file_path: str, cfg: dict[str, Any], creds: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Upload *file_path* to OneDrive using per-user MSAL credentials."""
    import urllib.parse

    import msal
    import requests as _requests

    client_id = creds.get("client_id") or ""
    client_secret = creds.get("client_secret") or ""
    refresh_token = creds.get("refresh_token") or ""
    tenant = cfg.get("tenant_id") or "common"
    folder_path = cfg.get("folder_path") or ""

    if not (client_id and client_secret):
        raise ValueError("OneDrive integration is missing client_id or client_secret in credentials")

    scopes = ["https://graph.microsoft.com/.default"]
    msal_app = msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant}",
    )

    if refresh_token:
        token_resp = msal_app.acquire_token_by_refresh_token(refresh_token=refresh_token, scopes=scopes)
    else:
        token_resp = msal_app.acquire_token_for_client(scopes=scopes)

    if "access_token" not in token_resp:
        raise ValueError(f"OneDrive token acquisition failed: {token_resp.get('error_description', 'unknown')}")

    access_token = token_resp["access_token"]
    filename = os.path.basename(file_path)

    # Build upload-session URL
    if folder_path:
        folder_path = folder_path.strip("/")
        encoded_path = "/".join(urllib.parse.quote(p) for p in folder_path.split("/"))
        encoded_file = urllib.parse.quote(filename)
        item_path = f"/root:/{encoded_path}/{encoded_file}:/createUploadSession"
    else:
        encoded_file = urllib.parse.quote(filename)
        item_path = f"/root:/{encoded_file}:/createUploadSession"

    session_url = f"https://graph.microsoft.com/v1.0/me/drive{item_path}"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    resp = _requests.post(
        session_url, headers=headers, json={"item": {"@microsoft.graph.conflictBehavior": "replace"}}, timeout=30
    )
    resp.raise_for_status()
    upload_url = resp.json()["uploadUrl"]

    file_size = os.path.getsize(file_path)
    chunk_size = 10 * 1024 * 1024
    with open(file_path, "rb") as fh:
        chunk_num = 0
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            start = chunk_num * chunk_size
            end = start + len(chunk) - 1
            upload_headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{file_size}",
            }
            upload_resp = _requests.put(upload_url, headers=upload_headers, data=chunk, timeout=120)
            if upload_resp.status_code not in (201, 202):
                raise RuntimeError(f"OneDrive chunk upload failed: {upload_resp.status_code}")
            chunk_num += 1

    logger.info("[%s] OneDrive upload complete: %s/%s", task_id, folder_path, filename)
    return {"status": "Completed", "onedrive_folder": folder_path, "filename": filename}


def _upload_webdav(file_path: str, cfg: dict[str, Any], creds: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Upload *file_path* to a WebDAV server using per-user credentials."""
    import requests as _requests

    url = cfg.get("url") or ""
    folder = cfg.get("folder") or ""
    username = creds.get("username") or ""
    password = creds.get("password") or ""
    verify_ssl = cfg.get("verify_ssl", True)

    if not url:
        raise ValueError("WebDAV integration is missing url in config")

    filename = os.path.basename(file_path)
    folder = folder.lstrip("/")
    target = urljoin(url.rstrip("/") + "/", folder)
    if not target.endswith("/"):
        target += "/"
    dest = urljoin(target, filename)

    with open(file_path, "rb") as fh:
        resp = _requests.put(dest, auth=(username, password), data=fh, verify=verify_ssl, timeout=120)

    if resp.status_code not in (200, 201, 204):
        raise RuntimeError(f"WebDAV upload failed: {resp.status_code} {resp.text[:200]}")

    logger.info("[%s] WebDAV upload complete: %s", task_id, dest)
    return {"status": "Completed", "webdav_url": dest}


def _upload_nextcloud(file_path: str, cfg: dict[str, Any], creds: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Upload *file_path* to Nextcloud (WebDAV) using per-user credentials."""
    # Nextcloud uses WebDAV under the hood; reuse the WebDAV helper.
    return _upload_webdav(file_path, cfg, creds, task_id)


def _upload_ftp(file_path: str, cfg: dict[str, Any], creds: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Upload *file_path* to an FTP/FTPS server using per-user credentials."""
    host = cfg.get("host") or ""
    port = int(cfg.get("port") or 21)
    username = cfg.get("username") or ""
    folder = cfg.get("folder") or ""
    use_tls = cfg.get("use_tls", True)
    password = creds.get("password") or ""
    filename = os.path.basename(file_path)

    if not host:
        raise ValueError("FTP integration is missing host in config")

    ftp: ftplib.FTP
    if use_tls:
        ftp = ftplib.FTP_TLS()  # nosec B321  # noqa: S321
        ftp.connect(host=host, port=port)
        ftp.login(user=username, passwd=password)
        ftp.prot_p()
    else:
        ftp = ftplib.FTP()  # nosec B321  # noqa: S321
        ftp.connect(host=host, port=port)
        ftp.login(user=username, passwd=password)

    if folder:
        folder_stripped = folder.lstrip("/")
        try:
            ftp.cwd(folder_stripped)
        except ftplib.error_perm:
            parts = folder_stripped.split("/")
            current = ""
            for part in parts:
                if not part:
                    continue
                current += f"/{part}"
                try:
                    ftp.cwd(current)
                except ftplib.error_perm:
                    ftp.mkd(current)
                    ftp.cwd(current)

    with open(file_path, "rb") as fh:
        ftp.storbinary(f"STOR {filename}", fh)
    ftp.quit()

    logger.info("[%s] FTP upload complete: %s/%s", task_id, host, filename)
    return {"status": "Completed", "ftp_host": host, "filename": filename}


def _upload_sftp(file_path: str, cfg: dict[str, Any], creds: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Upload *file_path* to an SFTP server using per-user credentials."""
    import paramiko

    host = cfg.get("host") or ""
    port = int(cfg.get("port") or 22)
    username = cfg.get("username") or ""
    folder = cfg.get("folder") or ""
    password = creds.get("password") or ""
    private_key_text = creds.get("private_key") or ""
    filename = os.path.basename(file_path)

    if not host:
        raise ValueError("SFTP integration is missing host in config")

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())

    connect_kwargs: dict[str, Any] = {"hostname": host, "port": port, "username": username}
    if private_key_text:
        import io

        pkey = paramiko.RSAKey.from_private_key(io.StringIO(private_key_text))
        connect_kwargs["pkey"] = pkey
    elif password:
        connect_kwargs["password"] = password
    else:
        raise ValueError("SFTP integration requires password or private_key in credentials")

    ssh.connect(**connect_kwargs)
    sftp = ssh.open_sftp()

    remote_path = f"{folder.rstrip('/')}/{filename}" if folder else filename
    if folder and folder.startswith("/") and not remote_path.startswith("/"):
        remote_path = "/" + remote_path

    sftp.put(file_path, remote_path)
    sftp.close()
    ssh.close()

    logger.info("[%s] SFTP upload complete: %s:%s", task_id, host, remote_path)
    return {"status": "Completed", "sftp_host": host, "sftp_path": remote_path}


def _upload_paperless(file_path: str, cfg: dict[str, Any], creds: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Upload *file_path* to a Paperless-ngx instance using per-user API token."""
    import time

    import requests as _requests

    host = (cfg.get("host") or "").rstrip("/")
    api_token = creds.get("api_token") or ""
    filename = os.path.basename(file_path)

    if not host:
        raise ValueError("Paperless integration is missing host in config")
    if not api_token:
        raise ValueError("Paperless integration is missing api_token in credentials")

    headers = {"Authorization": f"Token {api_token}"}
    post_url = f"{host}/api/documents/post_document/"

    with open(file_path, "rb") as fh:
        resp = _requests.post(
            post_url,
            headers=headers,
            files={"document": (filename, fh, "application/pdf")},
            data={"title": filename},
            timeout=120,
        )
    resp.raise_for_status()
    raw_task_id = resp.text.strip().strip('"').strip("'")

    # Poll for completion (up to 30 s)
    task_url = f"{host}/api/tasks/"
    doc_id = None
    for _ in range(10):
        time.sleep(3)
        try:
            poll_resp = _requests.get(task_url, headers=headers, params={"task_id": raw_task_id}, timeout=30)
            poll_resp.raise_for_status()
            tasks_data = poll_resp.json()
            if isinstance(tasks_data, dict) and "results" in tasks_data:
                tasks_data = tasks_data["results"]
            if tasks_data:
                info = tasks_data[0]
                status = info.get("status")
                if status == "SUCCESS":
                    doc_id = info.get("related_document")
                    break
                elif status == "FAILURE":
                    raise RuntimeError(f"Paperless processing failed: {info.get('result')}")
        except RuntimeError:
            raise
        except Exception as poll_exc:
            logger.warning("[%s] Paperless poll error: %s", task_id, poll_exc)

    logger.info("[%s] Paperless upload complete: doc_id=%s", task_id, doc_id)
    return {"status": "Completed", "paperless_host": host, "paperless_document_id": doc_id}


def _upload_email(file_path: str, cfg: dict[str, Any], creds: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Send *file_path* as an email attachment using per-user SMTP credentials."""
    import smtplib
    from email.mime.application import MIMEApplication
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    host = cfg.get("host") or ""
    port = int(cfg.get("port") or 587)
    username = cfg.get("username") or ""
    recipient = cfg.get("recipient") or ""
    use_tls = cfg.get("use_tls", True)
    sender_name = cfg.get("sender_name") or "DocuElevate"
    password = creds.get("password") or ""
    filename = os.path.basename(file_path)

    if not (host and recipient):
        raise ValueError("Email integration is missing host or recipient in config")

    msg = MIMEMultipart()
    msg["From"] = f"{sender_name} <{username}>" if username else sender_name
    msg["To"] = recipient
    msg["Subject"] = f"Document: {filename}"
    msg.attach(MIMEText(f"Please find the attached document: {filename}", "plain"))

    with open(file_path, "rb") as fh:
        part = MIMEApplication(fh.read(), Name=filename)
    part["Content-Disposition"] = f'attachment; filename="{filename}"'
    msg.attach(part)

    if use_tls:
        import ssl

        tls_context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls(context=tls_context)
            if username and password:
                smtp.login(username, password)
            smtp.sendmail(msg["From"], [recipient], msg.as_string())
    else:
        # Plaintext SMTP — only use when explicitly configured and TLS is unavailable.
        # Credentials and content will be transmitted without encryption.
        with smtplib.SMTP(host, port, timeout=30) as smtp:  # nosec B608
            if username and password:
                smtp.login(username, password)
            smtp.sendmail(msg["From"], [recipient], msg.as_string())

    logger.info("[%s] Email upload complete: sent to %s", task_id, recipient)
    return {"status": "Completed", "recipient": recipient}


def _upload_rclone(file_path: str, cfg: dict[str, Any], creds: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Copy *file_path* to an rclone remote using per-user rclone config."""
    import re
    import tempfile

    remote = cfg.get("remote") or ""
    folder = cfg.get("folder") or ""
    rclone_conf_text = creds.get("rclone_conf") or ""
    filename = os.path.basename(file_path)

    if not remote:
        raise ValueError("Rclone integration is missing remote in config")
    if not rclone_conf_text:
        raise ValueError("Rclone integration is missing rclone_conf in credentials")

    # Validate remote and folder to prevent shell metacharacter injection.
    # rclone remote names are alphanumeric + hyphens/underscores followed by ':'.
    # folder paths must not contain shell-dangerous characters.
    _SAFE_REMOTE_RE = re.compile(r"^[A-Za-z0-9_\-]+:(/[A-Za-z0-9_.@\-/ ]*)?$")
    _SAFE_FOLDER_RE = re.compile(r"^[A-Za-z0-9_.@\-/ ]*$")
    if not _SAFE_REMOTE_RE.match(remote):
        raise ValueError(f"Rclone remote contains unsafe characters: {remote!r}")
    if folder and not _SAFE_FOLDER_RE.match(folder):
        raise ValueError(f"Rclone folder contains unsafe characters: {folder!r}")

    # Write the user's rclone config to a temp file so we don't touch the system config
    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as tmp_conf:
        tmp_conf.write(rclone_conf_text)
        conf_path = tmp_conf.name

    dest = f"{remote.rstrip('/')}/{folder.strip('/')}/{filename}" if folder else f"{remote.rstrip('/')}/{filename}"
    dest = dest.replace("//", "/")

    try:
        result = subprocess.run(  # nosec B603  # noqa: S603 S607
            ["rclone", "copyto", f"--config={conf_path}", file_path, dest],  # noqa: S603 S607
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"rclone exited {result.returncode}: {result.stderr[:300]}")
    finally:
        os.unlink(conf_path)

    logger.info("[%s] Rclone upload complete: %s", task_id, dest)
    return {"status": "Completed", "rclone_dest": dest}


def _upload_sharepoint(file_path: str, cfg: dict[str, Any], creds: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Upload *file_path* to SharePoint using per-user MSAL credentials."""
    import urllib.parse

    import msal
    import requests as _requests

    client_id = creds.get("client_id") or ""
    client_secret = creds.get("client_secret") or ""
    refresh_token = creds.get("refresh_token") or ""
    tenant = cfg.get("tenant_id") or "common"
    site_url = cfg.get("site_url") or ""
    library_name = cfg.get("document_library") or "Documents"
    folder_path = cfg.get("folder_path") or ""

    if not (client_id and client_secret):
        raise ValueError("SharePoint integration is missing client_id or client_secret in credentials")
    if not site_url:
        raise ValueError("SharePoint integration is missing site_url in config")

    scopes = ["https://graph.microsoft.com/.default"]
    msal_app = msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant}",
    )

    if refresh_token:
        token_resp = msal_app.acquire_token_by_refresh_token(refresh_token=refresh_token, scopes=scopes)
    else:
        token_resp = msal_app.acquire_token_for_client(scopes=scopes)

    if "access_token" not in token_resp:
        raise ValueError(f"SharePoint token acquisition failed: {token_resp.get('error_description', 'unknown')}")

    access_token = token_resp["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # Resolve site ID
    parsed = urllib.parse.urlparse(site_url)
    hostname = parsed.hostname
    site_path = parsed.path.rstrip("/")
    if not hostname or not site_path:
        raise ValueError(f"Invalid SharePoint site URL: {site_url}")

    resp = _requests.get(f"https://graph.microsoft.com/v1.0/sites/{hostname}:{site_path}", headers=headers, timeout=30)
    resp.raise_for_status()
    site_id = resp.json()["id"]

    # Resolve drive ID
    resp = _requests.get(f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives", headers=headers, timeout=30)
    resp.raise_for_status()
    drive_id = None
    for drive in resp.json().get("value", []):
        if drive.get("name", "").lower() == library_name.lower():
            drive_id = drive["id"]
            break
    if not drive_id:
        raise RuntimeError(f"Document library '{library_name}' not found on SharePoint site")

    filename = os.path.basename(file_path)

    # Build upload-session URL
    base_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}"
    if folder_path:
        folder_path = folder_path.strip("/")
        encoded_path = "/".join(urllib.parse.quote(p) for p in folder_path.split("/"))
        encoded_file = urllib.parse.quote(filename)
        item_path = f"/root:/{encoded_path}/{encoded_file}:/createUploadSession"
    else:
        encoded_file = urllib.parse.quote(filename)
        item_path = f"/root:/{encoded_file}:/createUploadSession"

    session_url = f"{base_url}{item_path}"
    session_headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    resp = _requests.post(
        session_url,
        headers=session_headers,
        json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        timeout=30,
    )
    resp.raise_for_status()
    upload_url = resp.json()["uploadUrl"]

    file_size = os.path.getsize(file_path)
    chunk_size = 10 * 1024 * 1024
    with open(file_path, "rb") as fh:
        chunk_num = 0
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            start = chunk_num * chunk_size
            end = start + len(chunk) - 1
            upload_headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{file_size}",
            }
            upload_resp = _requests.put(upload_url, headers=upload_headers, data=chunk, timeout=120)
            if upload_resp.status_code not in (201, 202):
                raise RuntimeError(f"SharePoint chunk upload failed: {upload_resp.status_code}")
            chunk_num += 1

    logger.info("[%s] SharePoint upload complete: %s/%s", task_id, folder_path, filename)
    return {"status": "Completed", "sharepoint_folder": folder_path, "filename": filename}


def _upload_icloud(file_path: str, cfg: dict[str, Any], creds: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Upload *file_path* to iCloud Drive using per-user credentials.

    Expected *cfg* keys:
        * ``folder`` – target folder path inside iCloud Drive (e.g. ``Documents/Uploads``).
        * ``cookie_directory`` – (optional) path for session cookie persistence.

    Expected *creds* keys:
        * ``username`` – Apple ID email address.
        * ``password`` – app-specific password.
    """
    from app.tasks.upload_to_icloud import _get_icloud_api, _navigate_to_folder

    username = creds.get("username") or ""
    password = creds.get("password") or ""
    folder = cfg.get("folder") or ""
    cookie_directory = cfg.get("cookie_directory") or None

    if not username or not password:
        raise ValueError("iCloud integration is missing username or password in credentials")

    api = _get_icloud_api(username, password, cookie_directory)
    folder_node = _navigate_to_folder(api.drive, folder)

    with open(file_path, "rb") as fh:
        folder_node.upload(fh)

    logger.info("[%s] iCloud Drive upload complete: folder=%s", task_id, folder or "/")
    return {"status": "Completed", "icloud_folder": folder or "/"}


# Map IntegrationType → upload helper
_UPLOAD_HANDLERS = {
    IntegrationType.DROPBOX: _upload_dropbox,
    IntegrationType.S3: _upload_s3,
    IntegrationType.GOOGLE_DRIVE: _upload_google_drive,
    IntegrationType.ONEDRIVE: _upload_onedrive,
    IntegrationType.WEBDAV: _upload_webdav,
    IntegrationType.NEXTCLOUD: _upload_nextcloud,
    IntegrationType.FTP: _upload_ftp,
    IntegrationType.SFTP: _upload_sftp,
    IntegrationType.PAPERLESS: _upload_paperless,
    IntegrationType.EMAIL: _upload_email,
    IntegrationType.RCLONE: _upload_rclone,
    IntegrationType.SHAREPOINT: _upload_sharepoint,
    IntegrationType.ICLOUD: _upload_icloud,
}


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery.task(base=UploadTaskWithRetry, bind=True)
def upload_to_user_integration(self, file_path: str, integration_id: int, file_id: int | None = None) -> dict[str, Any]:
    """Upload *file_path* to the destination described by the given UserIntegration record.

    This task is dispatched once per active DESTINATION UserIntegration that
    belongs to a document's owner.  Credentials are decrypted at runtime so
    they never travel across the Celery message bus in plaintext.

    Args:
        file_path: Absolute path to the processed document file.
        integration_id: Primary key of the ``UserIntegration`` record.
        file_id: Optional ``FileRecord.id`` used for progress logging.

    Returns:
        A dict with at least ``{"status": "Completed", ...}`` on success.

    Raises:
        FileNotFoundError: When *file_path* does not exist.
        ValueError: When the integration record is not found or has missing config.
        RuntimeError: When the underlying upload operation fails.
    """
    task_id = self.request.id
    filename = os.path.basename(file_path)

    log_task_progress(
        task_id,
        f"upload_to_user_integration_{integration_id}",
        "in_progress",
        f"Uploading {filename} to integration {integration_id}",
        file_id=file_id,
    )

    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error("[%s] %s", task_id, error_msg)
        log_task_progress(
            task_id, f"upload_to_user_integration_{integration_id}", "failure", error_msg, file_id=file_id
        )
        raise FileNotFoundError(error_msg)

    with SessionLocal() as db:
        integration: UserIntegration | None = (
            db.query(UserIntegration).filter(UserIntegration.id == integration_id).first()
        )
        if integration is None:
            error_msg = f"UserIntegration {integration_id} not found"
            logger.error("[%s] %s", task_id, error_msg)
            log_task_progress(
                task_id, f"upload_to_user_integration_{integration_id}", "failure", error_msg, file_id=file_id
            )
            raise ValueError(error_msg)

        itype = integration.integration_type
        int_name = integration.name
        owner_id = integration.owner_id

        # Parse config (non-sensitive) and decrypt credentials (sensitive)
        try:
            cfg: dict[str, Any] = json.loads(integration.config) if integration.config else {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"Integration {integration_id} has invalid JSON in config: {exc}") from exc

        try:
            raw_creds = decrypt_value(integration.credentials) if integration.credentials else None
            creds: dict[str, Any] = json.loads(raw_creds) if raw_creds else {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"Integration {integration_id} has invalid JSON in credentials: {exc}") from exc

    handler = _UPLOAD_HANDLERS.get(itype)
    if handler is None:
        error_msg = f"No upload handler registered for integration type '{itype}' (integration {integration_id})"
        logger.warning("[%s] %s", task_id, error_msg)
        log_task_progress(
            task_id, f"upload_to_user_integration_{integration_id}", "skipped", error_msg, file_id=file_id
        )
        return {"status": "Skipped", "reason": error_msg}

    logger.info(
        "[%s] Uploading %s via %s integration '%s' (id=%d, owner=%s)",
        task_id,
        filename,
        itype,
        int_name,
        integration_id,
        owner_id,
    )

    try:
        result = handler(file_path, cfg, creds, task_id)

        # Update last_used_at on success
        with SessionLocal() as db:
            integ = db.query(UserIntegration).filter(UserIntegration.id == integration_id).first()
            if integ:
                integ.last_used_at = datetime.now(timezone.utc)
                integ.last_error = None
                db.commit()

        log_task_progress(
            task_id,
            f"upload_to_user_integration_{integration_id}",
            "success",
            f"Uploaded to {itype} '{int_name}': {filename}",
            file_id=file_id,
        )
        return result

    except Exception as exc:
        error_msg = str(exc)[:_MAX_ERROR_LENGTH]
        logger.error(
            "[%s] Upload to integration %d (%s '%s') failed: %s",
            task_id,
            integration_id,
            itype,
            int_name,
            error_msg,
        )

        # Persist error for operator visibility
        try:
            with SessionLocal() as db:
                integ = db.query(UserIntegration).filter(UserIntegration.id == integration_id).first()
                if integ:
                    integ.last_used_at = datetime.now(timezone.utc)
                    integ.last_error = error_msg
                    db.commit()
        except Exception as db_exc:  # noqa: BLE001
            logger.warning("[%s] Could not persist last_error for integration %d: %s", task_id, integration_id, db_exc)

        log_task_progress(
            task_id,
            f"upload_to_user_integration_{integration_id}",
            "failure",
            f"Upload to {itype} '{int_name}' failed: {error_msg}",
            file_id=file_id,
        )
        raise
