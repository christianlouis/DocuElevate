"""
API endpoint for processing files from URLs
"""

import logging
import mimetypes
import os
import urllib.parse
import uuid
from typing import Optional

import aiofiles
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, HttpUrl, field_validator

from app.auth import require_login
from app.config import settings
from app.middleware.upload_rate_limit import require_upload_rate_limit
from app.tasks.process_document import process_document
from app.utils.allowed_types import ALLOWED_MIME_TYPES
from app.utils.filename_utils import sanitize_filename
from app.utils.network import is_private_ip

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()


class URLUploadRequest(BaseModel):
    """Request model for URL-based file upload"""

    url: HttpUrl
    filename: Optional[str] = None

    @field_validator("url")
    @classmethod
    def validate_url_scheme(cls, v):
        """Ensure only HTTP/HTTPS schemes are allowed"""
        parsed = urllib.parse.urlparse(str(v))
        if parsed.scheme not in ["http", "https"]:
            raise ValueError("Only HTTP and HTTPS URLs are allowed")
        return v


def validate_url_safety(url: str) -> None:
    """
    Validate that URL is safe to fetch (SSRF protection).

    Raises:
        HTTPException: If URL is unsafe
    """
    parsed = urllib.parse.urlparse(url)

    # Check scheme
    if parsed.scheme not in ["http", "https"]:
        raise HTTPException(status_code=400, detail="Only HTTP and HTTPS URLs are supported")

    # Check hostname exists
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="Invalid URL: no hostname")

    # Block private/internal IPs (SSRF protection)
    if is_private_ip(parsed.hostname):
        raise HTTPException(
            status_code=400,
            detail="Access to private/internal IP addresses is not allowed for security reasons",
        )

    # Block well-known metadata endpoints (cloud provider SSRF)
    metadata_endpoints = [
        "169.254.169.254",  # AWS, Azure, GCP metadata
        "metadata.google.internal",  # GCP
        "169.254.169.253",  # AWS link-local
    ]
    if parsed.hostname in metadata_endpoints:
        raise HTTPException(status_code=400, detail="Access to cloud metadata endpoints is not allowed")


async def check_redirect(response: httpx.Response) -> None:
    # Hook to validate redirect URLs before they are followed to prevent SSRF
    if response.is_redirect:
        next_url = response.headers.get("Location")
        if next_url:
            full_url = str(response.url.join(next_url))
            validate_url_safety(full_url)


def validate_file_type(content_type: str, filename: str) -> bool:
    """
    Validate that the file type is supported (i.e. processable by Gotenberg).

    Args:
        content_type: MIME type from response headers
        filename: Filename to check extension

    Returns:
        True if file type is allowed
    """
    # Check content type from header
    if content_type:
        # Handle content-type with charset (e.g., "application/pdf; charset=utf-8")
        base_content_type = content_type.split(";", maxsplit=1)[0].strip().lower()
        if base_content_type in ALLOWED_MIME_TYPES:
            return True

    # Also check by extension as fallback
    _, ext = os.path.splitext(filename)
    if ext:
        guessed_type, _ = mimetypes.guess_type(filename)
        if guessed_type and guessed_type in ALLOWED_MIME_TYPES:
            return True

    return False


@router.post("/process-url")
@require_login
async def process_url(
    request: Request,
    url_request: URLUploadRequest,
    _rate_ok: None = Depends(require_upload_rate_limit),
):
    """
    Download a file from a URL and enqueue it for processing.

    Security features:
    - SSRF protection: blocks private IPs, localhost, cloud metadata endpoints
    - File type validation: only allows supported document/image types
    - File size limits: enforces maximum upload size
    - Timeout protection: prevents hanging on slow/malicious servers

    Args:
        request: Starlette Request object (used by require_login decorator)
        url_request: URLUploadRequest with url and optional filename

    Returns:
        JSON with task_id and status

    Raises:
        HTTPException: If URL is invalid, unsafe, or file cannot be processed
    """
    url = str(url_request.url)

    # Validate URL safety (SSRF protection)
    validate_url_safety(url)

    # Parse URL to extract filename if not provided
    if url_request.filename:
        original_filename = url_request.filename
    else:
        # Extract filename from URL path
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        original_filename = os.path.basename(path) if path else "download"

    # Sanitize filename
    safe_filename = sanitize_filename(original_filename)
    if not safe_filename:
        safe_filename = "download"

    # Download file with security measures
    # Initialize target_path to None to prevent UnboundLocalError in exception handlers
    # that may execute before target_path is assigned during error cases
    target_path = None
    try:
        logger.info(f"Downloading file from URL: {url}")

        # Use configured timeout to prevent hanging
        async with httpx.AsyncClient(
            timeout=settings.http_request_timeout,
            follow_redirects=True,
            event_hooks={"response": [check_redirect]},
            headers={
                "User-Agent": "DocuElevate/1.0",  # Identify ourselves
            },
        ) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()

                # Validate content type
                content_type = response.headers.get("Content-Type", "")
                if not validate_file_type(content_type, safe_filename):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unsupported file type: {content_type}. "
                        "Supported types: PDF, Office documents, images, plain text",
                    )

                # Check content length before downloading
                content_length = response.headers.get("Content-Length")
                if content_length:
                    file_size = int(content_length)
                    max_size = settings.max_upload_size
                    if file_size > max_size:
                        raise HTTPException(
                            status_code=413,
                            detail=f"File too large: {file_size} bytes (max {max_size} bytes)",
                        )

                # Generate unique filename
                unique_id = str(uuid.uuid4())

                # Check for extension using original_filename to avoid any CodeQL issues
                # with safe_filename which is derived from the URL directly.
                if "." in original_filename:
                    _, ext = os.path.splitext(original_filename)
                    # Strip out the leading dot and any non-alphanumeric chars
                    clean_ext = "".join(c for c in ext if c.isalnum())
                    if not clean_ext:
                        clean_ext = "bin"
                    target_filename = f"{unique_id}.{clean_ext}"
                else:
                    target_filename = unique_id

                target_path = os.path.join(settings.workdir, target_filename)

                # Download file in chunks to handle large files
                downloaded_size = 0
                max_size = settings.max_upload_size

                async with aiofiles.open(target_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if chunk:
                            await f.write(chunk)
                            downloaded_size += len(chunk)

                            # Check size during download
                            if downloaded_size > max_size:
                                # Remove partial file
                                await f.close()
                                os.remove(target_path)
                                raise HTTPException(
                                    status_code=413,
                                    detail=f"File too large: exceeded {max_size} bytes during download",
                                )

        logger.info(f"Downloaded file from URL '{url}' as '{target_filename}' ({downloaded_size} bytes)")

        # Enqueue for processing
        task = process_document.delay(target_path, original_filename=safe_filename)

        return {
            "task_id": task.id,
            "status": "queued",
            "message": "File downloaded from URL and queued for processing",
            "filename": safe_filename,
            "size": downloaded_size,
        }

    except httpx.TimeoutException:
        logger.error(f"Timeout while downloading file from URL: {url}")
        raise HTTPException(status_code=408, detail="Request timeout: server took too long to respond")

    except httpx.ConnectError as e:
        logger.error(f"Connection error while downloading file from URL: {url} - {str(e)}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to URL: {str(e)}")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while downloading file from URL: {url} - {str(e)}")
        raise HTTPException(status_code=e.response.status_code, detail=f"HTTP error: {str(e)}")

    except httpx.RequestError as e:
        logger.error(f"Error downloading file from URL: {url} - {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to download file: {str(e)}")

    except HTTPException:
        # Re-raise FastAPI HTTPExceptions (validation errors, file too large, etc.)
        raise

    except OSError as e:
        logger.error(f"Error saving file from URL: {url} - {str(e)}")
        # Clean up partial file if it exists
        if target_path and os.path.exists(target_path):
            os.remove(target_path)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    except Exception as e:
        logger.exception(f"Unexpected error processing URL: {url}")
        # Clean up partial file if it exists
        if target_path and os.path.exists(target_path):
            os.remove(target_path)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
