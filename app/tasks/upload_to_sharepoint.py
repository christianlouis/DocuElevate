#!/usr/bin/env python3
"""Upload documents to Microsoft SharePoint via the Microsoft Graph API.

This module authenticates using MSAL (same OAuth2 flow as OneDrive) and
uploads files to a configurable SharePoint Online document library using
the chunked upload session approach for reliability with large files.

Key differences from the OneDrive provider:
- Uses ``/sites/{siteId}/drives/{driveId}`` instead of ``/me/drive``
- Requires a SharePoint site URL to resolve the site and drive IDs
- Targets a named document library (default: ``Documents``)
"""

import logging
import os
import time
import urllib.parse

import msal
import requests

from app.celery_app import celery
from app.config import settings
from app.tasks.retry_config import UploadTaskWithRetry
from app.utils import log_task_progress

logger = logging.getLogger(__name__)


def get_sharepoint_token() -> str:
    """Acquire a Microsoft Graph API access token for SharePoint.

    Uses MSAL ``ConfidentialClientApplication`` with the refresh-token flow
    (delegated permissions) or the client-credentials flow (application
    permissions) depending on configuration.

    Returns:
        A valid access token string.

    Raises:
        ValueError: When required settings are missing or token acquisition fails.
    """
    if not settings.sharepoint_client_id or not settings.sharepoint_client_secret:
        raise ValueError("SharePoint client ID and client secret must be configured")

    tenant = settings.sharepoint_tenant_id or "common"
    logger.info("Using SharePoint tenant: %s", tenant)

    scopes = ["https://graph.microsoft.com/.default"]

    if settings.sharepoint_refresh_token:
        app = msal.ConfidentialClientApplication(
            client_id=settings.sharepoint_client_id,
            client_credential=settings.sharepoint_client_secret,
            authority=f"https://login.microsoftonline.com/{tenant}",
        )

        logger.info("Attempting to acquire SharePoint token using refresh token")
        token_response = app.acquire_token_by_refresh_token(
            refresh_token=settings.sharepoint_refresh_token, scopes=scopes
        )

        if "access_token" not in token_response:
            error = token_response.get("error", "")
            error_desc = token_response.get("error_description", "Unknown error")
            logger.error("Failed to get SharePoint access token: %s - %s", error, error_desc)
            raise ValueError(f"Failed to get SharePoint access token: {error} - {error_desc}")

        if "refresh_token" in token_response:
            settings.sharepoint_refresh_token = token_response["refresh_token"]
            logger.info("Updated SharePoint refresh token in memory")

        return token_response["access_token"]

    elif settings.sharepoint_tenant_id and settings.sharepoint_tenant_id != "common":
        authority = f"https://login.microsoftonline.com/{settings.sharepoint_tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id=settings.sharepoint_client_id,
            client_credential=settings.sharepoint_client_secret,
            authority=authority,
        )

        token_response = app.acquire_token_for_client(scopes=scopes)

        if "access_token" not in token_response:
            error = token_response.get("error", "")
            error_desc = token_response.get("error_description", "Unknown error")
            raise ValueError(f"Failed to get SharePoint access token: {error} - {error_desc}")

        return token_response["access_token"]

    else:
        raise ValueError("For SharePoint, either a refresh token or a non-'common' tenant ID is required")


def resolve_sharepoint_drive(access_token: str, site_url: str, library_name: str) -> tuple[str, str]:
    """Resolve the Graph API site ID and drive ID for a SharePoint site.

    Args:
        access_token: Valid Microsoft Graph API token.
        site_url: Full SharePoint site URL, e.g.
            ``https://tenant.sharepoint.com/sites/sitename``.
        library_name: Display name of the document library (e.g. ``Documents``).

    Returns:
        A ``(site_id, drive_id)`` tuple.

    Raises:
        ValueError: When the site URL cannot be parsed.
        RuntimeError: When the Graph API call fails.
    """
    parsed = urllib.parse.urlparse(site_url)
    hostname = parsed.hostname
    site_path = parsed.path.rstrip("/")

    if not hostname or not site_path:
        raise ValueError(
            f"Invalid SharePoint site URL '{site_url}'. Expected format: https://tenant.sharepoint.com/sites/sitename"
        )

    headers = {"Authorization": f"Bearer {access_token}"}

    # Resolve site ID
    site_api_url = f"https://graph.microsoft.com/v1.0/sites/{hostname}:{site_path}"
    logger.info("Resolving SharePoint site: %s", site_api_url)
    resp = requests.get(site_api_url, headers=headers, timeout=settings.http_request_timeout)

    if resp.status_code != 200:
        raise RuntimeError(f"Failed to resolve SharePoint site: {resp.status_code} - {resp.text}")

    site_id = resp.json()["id"]
    logger.info("Resolved SharePoint site ID: %s", site_id)

    # Resolve drive ID from the document library name
    drives_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
    resp = requests.get(drives_url, headers=headers, timeout=settings.http_request_timeout)

    if resp.status_code != 200:
        raise RuntimeError(f"Failed to list SharePoint drives: {resp.status_code} - {resp.text}")

    drives = resp.json().get("value", [])
    drive_id = None
    for drive in drives:
        if drive.get("name", "").lower() == library_name.lower():
            drive_id = drive["id"]
            break

    if not drive_id:
        available = [d.get("name") for d in drives]
        raise RuntimeError(f"Document library '{library_name}' not found on site. Available libraries: {available}")

    logger.info("Resolved SharePoint drive ID: %s (library: %s)", drive_id, library_name)
    return site_id, drive_id


def create_sharepoint_upload_session(
    filename: str, folder_path: str | None, drive_id: str, site_id: str, access_token: str
) -> str:
    """Create a resumable upload session on a SharePoint document library.

    Args:
        filename: Name of the file to upload.
        folder_path: Optional subfolder path inside the library.
        drive_id: Graph API drive ID of the document library.
        site_id: Graph API site ID.
        access_token: Valid access token.

    Returns:
        The upload session URL for chunked PUT requests.

    Raises:
        RuntimeError: When session creation fails.
    """
    base_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}"

    if folder_path:
        folder_path = folder_path.strip("/")
        path_components = folder_path.split("/")
        encoded_path = "/".join(urllib.parse.quote(component) for component in path_components)
        encoded_filename = urllib.parse.quote(filename)
        item_path = f"/root:/{encoded_path}/{encoded_filename}:/createUploadSession"
    else:
        encoded_filename = urllib.parse.quote(filename)
        item_path = f"/root:/{encoded_filename}:/createUploadSession"

    url = f"{base_url}{item_path}"
    request_body = {"item": {"@microsoft.graph.conflictBehavior": "replace"}}
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    logger.info("Creating SharePoint upload session for %s at path %s", filename, folder_path)
    response = requests.post(url, headers=headers, json=request_body, timeout=settings.http_request_timeout)

    if response.status_code == 200:
        upload_url = response.json().get("uploadUrl")
        logger.info("SharePoint upload session created for %s", filename)
        return upload_url
    else:
        raise RuntimeError(f"Failed to create SharePoint upload session: {response.status_code} - {response.text}")


def upload_large_file_sharepoint(file_path: str, upload_url: str) -> dict:
    """Upload a file to SharePoint using a chunked upload session.

    Args:
        file_path: Local path to the file.
        upload_url: The upload session URL from ``create_sharepoint_upload_session``.

    Returns:
        The Graph API response dict containing file metadata.

    Raises:
        RuntimeError: When a chunk upload fails after retries.
    """
    file_size = os.path.getsize(file_path)
    chunk_size = 10 * 1024 * 1024  # 10 MB

    response = None
    with open(file_path, "rb") as f:
        chunk_number = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break

            chunk_start = chunk_number * chunk_size
            chunk_end = chunk_start + len(chunk) - 1
            content_range = f"bytes {chunk_start}-{chunk_end}/{file_size}"

            headers = {"Content-Length": str(len(chunk)), "Content-Range": content_range}

            max_retries = 3
            retry_delay = 2

            for attempt in range(max_retries):
                try:
                    response = requests.put(
                        upload_url, headers=headers, data=chunk, timeout=settings.http_request_timeout
                    )
                    if response.status_code in (201, 202):
                        break
                    else:
                        logger.warning(
                            "SharePoint chunk upload failed (attempt %d): %d", attempt + 1, response.status_code
                        )
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay * (attempt + 1))
                except Exception as e:
                    logger.warning("SharePoint chunk upload error (attempt %d): %s", attempt + 1, str(e))
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))

            if response is None or response.status_code not in (201, 202):
                status = response.status_code if response else "no response"
                text = response.text if response else ""
                raise RuntimeError(f"Failed to upload chunk after {max_retries} attempts: {status} - {text}")

            chunk_number += 1

    return response.json() if response else {}


@celery.task(base=UploadTaskWithRetry, bind=True)
def upload_to_sharepoint(self, file_path: str, file_id: int = None, folder_override: str = None):
    """Upload a file to SharePoint Online.

    Args:
        file_path: Path to the file to upload.
        file_id: Optional file ID to associate with logs.
        folder_override: Optional folder path override.

    Returns:
        A dict with upload status and file details.

    Raises:
        FileNotFoundError: When the file does not exist.
        ValueError: When SharePoint is not configured.
        RuntimeError: When the upload fails.
    """
    task_id = self.request.id
    logger.info("[%s] Starting SharePoint upload: %s", task_id, file_path)
    log_task_progress(
        task_id,
        "upload_to_sharepoint",
        "in_progress",
        f"Uploading to SharePoint: {os.path.basename(file_path)}",
        file_id=file_id,
    )

    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error("[%s] %s", task_id, error_msg)
        log_task_progress(task_id, "upload_to_sharepoint", "failure", error_msg, file_id=file_id)
        raise FileNotFoundError(error_msg)

    filename = os.path.basename(file_path)

    if not settings.sharepoint_client_id:
        error_msg = "SharePoint client ID is not configured"
        logger.error("[%s] %s", task_id, error_msg)
        log_task_progress(task_id, "upload_to_sharepoint", "failure", error_msg, file_id=file_id)
        raise ValueError(error_msg)

    if not settings.sharepoint_site_url:
        error_msg = "SharePoint site URL is not configured"
        logger.error("[%s] %s", task_id, error_msg)
        log_task_progress(task_id, "upload_to_sharepoint", "failure", error_msg, file_id=file_id)
        raise ValueError(error_msg)

    try:
        access_token = get_sharepoint_token()

        library_name = settings.sharepoint_document_library or "Documents"
        site_id, drive_id = resolve_sharepoint_drive(access_token, settings.sharepoint_site_url, library_name)

        folder_path = folder_override if folder_override is not None else settings.sharepoint_folder_path

        upload_url = create_sharepoint_upload_session(filename, folder_path, drive_id, site_id, access_token)
        result = upload_large_file_sharepoint(file_path, upload_url)

        web_url = result.get("webUrl", "Not available")
        logger.info("[%s] Successfully uploaded %s to SharePoint", task_id, filename)
        logger.info("[%s] File accessible at: %s", task_id, web_url)
        log_task_progress(
            task_id, "upload_to_sharepoint", "success", f"Uploaded to SharePoint: {filename}", file_id=file_id
        )

        return {
            "status": "Completed",
            "file_path": file_path,
            "sharepoint_path": f"{folder_path or ''}/{filename}",
            "web_url": web_url,
        }

    except Exception as e:
        error_msg = f"Failed to upload {filename} to SharePoint: {str(e)}"
        logger.error("[%s] %s", task_id, error_msg)
        log_task_progress(task_id, "upload_to_sharepoint", "failure", error_msg, file_id=file_id)
        raise RuntimeError(error_msg) from e
