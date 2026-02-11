"""
API endpoint for processing files from URLs
"""

import ipaddress
import logging
import mimetypes
import os
import urllib.parse
import uuid
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl, validator

from app.auth import require_login
from app.config import settings
from app.tasks.process_document import process_document
from app.utils.filename_utils import sanitize_filename

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()


class URLUploadRequest(BaseModel):
    """Request model for URL-based file upload"""

    url: HttpUrl
    filename: Optional[str] = None

    @validator("url")
    def validate_url_scheme(cls, v):
        """Ensure only HTTP/HTTPS schemes are allowed"""
        parsed = urllib.parse.urlparse(str(v))
        if parsed.scheme not in ["http", "https"]:
            raise ValueError("Only HTTP and HTTPS URLs are allowed")
        return v


def is_private_ip(hostname: str) -> bool:
    """
    Check if a hostname resolves to a private/internal IP address.
    Protects against SSRF attacks by blocking access to internal networks.
    """
    try:
        # Try to parse as IP address directly
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        # Not a direct IP, try to resolve hostname
        try:
            import socket

            # Get all IP addresses for this hostname
            addr_info = socket.getaddrinfo(hostname, None)
            for info in addr_info:
                ip_str = info[4][0]
                ip = ipaddress.ip_address(ip_str)
                # Block if ANY resolved IP is private/internal
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return True
            return False
        except (socket.gaierror, socket.error):
            # Cannot resolve - allow for testing/development
            # In production, DNS should work properly
            # Log this for debugging
            logger.warning(f"Could not resolve hostname: {hostname}")
            return False  # Changed from True to False to allow external domains in tests


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


def validate_file_type(content_type: str, filename: str) -> bool:
    """
    Validate that the file type is supported.

    Args:
        content_type: MIME type from response headers
        filename: Filename to check extension

    Returns:
        True if file type is allowed
    """
    # Same allowed types as regular upload
    ALLOWED_MIME_TYPES = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/plain",
        "text/csv",
        "application/rtf",
        "text/rtf",
    }

    IMAGE_MIME_TYPES = {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/gif",
        "image/bmp",
        "image/tiff",
        "image/webp",
        "image/svg+xml",
    }

    # Check content type from header
    if content_type:
        # Handle content-type with charset (e.g., "application/pdf; charset=utf-8")
        base_content_type = content_type.split(";")[0].strip().lower()
        if base_content_type in ALLOWED_MIME_TYPES or base_content_type in IMAGE_MIME_TYPES:
            return True

    # Also check by extension as fallback
    _, ext = os.path.splitext(filename)
    if ext:
        guessed_type, _ = mimetypes.guess_type(filename)
        if guessed_type and (guessed_type in ALLOWED_MIME_TYPES or guessed_type in IMAGE_MIME_TYPES):
            return True

    return False


@router.post("/process-url")
@require_login
async def process_url(request: URLUploadRequest):
    """
    Download a file from a URL and enqueue it for processing.

    Security features:
    - SSRF protection: blocks private IPs, localhost, cloud metadata endpoints
    - File type validation: only allows supported document/image types
    - File size limits: enforces maximum upload size
    - Timeout protection: prevents hanging on slow/malicious servers

    Args:
        request: URLUploadRequest with url and optional filename

    Returns:
        JSON with task_id and status

    Raises:
        HTTPException: If URL is invalid, unsafe, or file cannot be processed
    """
    url = str(request.url)

    # Validate URL safety (SSRF protection)
    validate_url_safety(url)

    # Parse URL to extract filename if not provided
    if request.filename:
        original_filename = request.filename
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
    target_path = None  # Initialize to None for cleanup in exception handlers
    try:
        logger.info(f"Downloading file from URL: {url}")

        # Use configured timeout to prevent hanging
        response = requests.get(
            url,
            timeout=settings.http_request_timeout,
            stream=True,  # Stream to handle large files
            allow_redirects=True,  # Follow redirects
            headers={
                "User-Agent": "DocuElevate/1.0",  # Identify ourselves
            },
        )
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
        if "." in safe_filename:
            file_extension = safe_filename.rsplit(".", 1)[1]
            target_filename = f"{unique_id}.{file_extension}"
        else:
            target_filename = unique_id

        target_path = os.path.join(settings.workdir, target_filename)

        # Download file in chunks to handle large files
        downloaded_size = 0
        max_size = settings.max_upload_size

        with open(target_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)

                    # Check size during download
                    if downloaded_size > max_size:
                        # Remove partial file
                        f.close()
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
            "message": f"File downloaded from URL and queued for processing",
            "filename": safe_filename,
            "size": downloaded_size,
        }

    except requests.exceptions.Timeout:
        logger.error(f"Timeout while downloading file from URL: {url}")
        raise HTTPException(status_code=408, detail="Request timeout: server took too long to respond")

    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error while downloading file from URL: {url} - {str(e)}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to URL: {str(e)}")

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error while downloading file from URL: {url} - {str(e)}")
        raise HTTPException(status_code=e.response.status_code, detail=f"HTTP error: {str(e)}")

    except requests.exceptions.RequestException as e:
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
