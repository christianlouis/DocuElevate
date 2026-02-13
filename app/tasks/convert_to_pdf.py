#!/usr/bin/env python3
import logging
import mimetypes
import os
from typing import Optional, Tuple

import filetype
import puremagic
import requests
from celery import shared_task

from app.config import settings
from app.tasks.process_document import process_document
from app.utils import log_task_progress

logger = logging.getLogger(__name__)


def _detect_mime_type_from_magic(file_path: str) -> Optional[str]:
    """
    Detect MIME type from file headers using platform-agnostic libraries.

    Args:
        file_path: Path to the file on disk.

    Returns:
        Detected MIME type or None if unknown.
    """
    try:
        matches = puremagic.from_file(file_path)
        if matches:
            return matches[0].mime_type
    except puremagic.PureError:
        pass

    guess = filetype.guess(file_path)
    if guess:
        return guess.mime

    return None


def _detect_mime_type(file_path: str, original_filename: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Detect MIME type using extension, original filename, or magic bytes.

    Args:
        file_path: Path to the file on disk.
        original_filename: Optional original filename provided at upload time.

    Returns:
        Tuple of detected MIME type and encoding.
    """
    mime_type, encoding = mimetypes.guess_type(file_path)
    if mime_type:
        return mime_type, encoding

    if original_filename:
        mime_type, encoding = mimetypes.guess_type(original_filename)
        if mime_type:
            return mime_type, encoding

    return _detect_mime_type_from_magic(file_path), encoding


def _detect_extension(file_path: str, original_filename: Optional[str], mime_type: Optional[str]) -> str:
    """
    Detect file extension from file path, original filename, or MIME type.

    Args:
        file_path: Path to the file on disk.
        original_filename: Optional original filename provided at upload time.
        mime_type: Detected MIME type if available.

    Returns:
        File extension with leading dot (e.g., ".pdf") or empty string if unknown.
    """
    file_ext = os.path.splitext(file_path)[1].lower()
    if file_ext:
        return file_ext

    if original_filename:
        file_ext = os.path.splitext(original_filename)[1].lower()
        if file_ext:
            return file_ext

    if mime_type:
        return mimetypes.guess_extension(mime_type) or ""

    try:
        matches = puremagic.from_file(file_path)
        if matches and matches[0].extension:
            return f".{matches[0].extension.lstrip('.')}"
    except puremagic.PureError:
        pass

    guess = filetype.guess(file_path)
    if guess and guess.extension:
        return f".{guess.extension.lstrip('.')}"

    return ""


def _build_filename(file_path: str, original_filename: Optional[str], file_ext: str) -> str:
    """
    Build a filename for upload that includes a valid extension when possible.

    Args:
        file_path: Path to the file on disk.
        original_filename: Optional original filename provided at upload time.
        file_ext: Detected file extension.

    Returns:
        Filename to send to Gotenberg.
    """
    if original_filename and os.path.splitext(original_filename)[1]:
        return original_filename

    base_name = os.path.basename(file_path)
    if file_ext and not base_name.lower().endswith(file_ext):
        return f"{base_name}{file_ext}"

    return base_name


OFFICE_EXTENSIONS = {
    ".doc",
    ".docx",
    ".docm",
    ".dot",
    ".dotx",
    ".dotm",
    ".xls",
    ".xlsx",
    ".xlsm",
    ".xlsb",
    ".xlt",
    ".xltx",
    ".xlw",
    ".ppt",
    ".pptx",
    ".pptm",
    ".pps",
    ".ppsx",
    ".pot",
    ".potx",
    ".odt",
    ".ods",
    ".odp",
    ".odg",
    ".odf",
    ".rtf",
    ".txt",
    ".csv",
    ".pdf",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".svg"}

HTML_EXTENSIONS = {".html", ".htm"}

MARKDOWN_MIMES = {"text/markdown", "text/x-markdown"}
MARKDOWN_EXTENSIONS = {".md", ".markdown"}


def _is_office_or_image(mime_type: Optional[str], file_ext: str) -> bool:
    """Check if the file is an office document or image."""
    if mime_type and ("office" in mime_type or "opendocument" in mime_type or mime_type.startswith("image/")):
        return True
    return file_ext in OFFICE_EXTENSIONS or file_ext in IMAGE_EXTENSIONS


def _is_html(mime_type: Optional[str], file_ext: str) -> bool:
    """Check if the file is an HTML document."""
    return (mime_type and mime_type == "text/html") or file_ext in HTML_EXTENSIONS


def _is_markdown(mime_type: Optional[str], file_ext: str) -> bool:
    """Check if the file is a Markdown document."""
    return (mime_type and mime_type in MARKDOWN_MIMES) or file_ext in MARKDOWN_EXTENSIONS


def _select_gotenberg_endpoint(
    gotenberg_url: str, file_path: str, original_filename: Optional[str], mime_type: Optional[str], file_ext: str
) -> Tuple[Optional[str], dict, dict]:
    """
    Select the appropriate Gotenberg endpoint, form data, and files based on file type.

    Returns:
        Tuple of (endpoint URL, form_data dict, files dict).
    """
    if _is_office_or_image(mime_type, file_ext):
        return (
            f"{gotenberg_url}/forms/libreoffice/convert",
            {
                "landscape": "false",
                "exportBookmarks": "true",
                "exportNotes": "false",
                "losslessImageCompression": "true",
                "pdfa": "PDF/A-2b",
            },
            {"files": (_build_filename(file_path, original_filename, file_ext), open(file_path, "rb"))},
        )

    if _is_html(mime_type, file_ext):
        return (
            f"{gotenberg_url}/forms/chromium/convert/html",
            {
                "paperWidth": "8.27",
                "paperHeight": "11.7",
                "marginTop": "0.4",
                "marginBottom": "0.4",
                "marginLeft": "0.4",
                "marginRight": "0.4",
                "printBackground": "true",
                "preferCssPageSize": "false",
                "waitDelay": "2s",
            },
            {"index.html": ("index.html", open(file_path, "rb"))},
        )

    if _is_markdown(mime_type, file_ext):
        return _prepare_markdown_conversion(gotenberg_url, file_path)

    # Fallback to LibreOffice
    logger.warning(f"Using fallback conversion for unknown type: {mime_type} / {file_ext}")
    return (
        f"{gotenberg_url}/forms/libreoffice/convert",
        {},
        {"files": (_build_filename(file_path, original_filename, file_ext), open(file_path, "rb"))},
    )


def _prepare_markdown_conversion(gotenberg_url: str, file_path: str) -> Tuple[str, dict, dict]:
    """Prepare Gotenberg endpoint, form data, and files for Markdown conversion."""
    markdown_filename = os.path.basename(file_path)
    html_wrapper = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Converted Markdown</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 2em;
            max-width: 50em;
        }}
    </style>
</head>
<body>
    {{{{ toHTML "{markdown_filename}" }}}}
</body>
</html>"""

    wrapper_path = os.path.join(os.path.dirname(file_path), "md_wrapper.html")
    with open(wrapper_path, "w") as f:
        f.write(html_wrapper)

    try:
        files = {
            "index.html": ("index.html", open(wrapper_path, "rb")),
            markdown_filename: (markdown_filename, open(file_path, "rb")),
        }
        form_data = {
            "paperWidth": "8.27",
            "paperHeight": "11.7",
            "marginTop": "0.4",
            "marginBottom": "0.4",
            "marginLeft": "0.4",
            "marginRight": "0.4",
        }
    finally:
        if os.path.exists(wrapper_path):
            os.remove(wrapper_path)

    return f"{gotenberg_url}/forms/chromium/convert/markdown", form_data, files


@shared_task(bind=True)
def convert_to_pdf(self, file_path: str, original_filename: Optional[str] = None) -> Optional[str]:
    """
    Converts a file to PDF using Gotenberg's API.
    Determines the appropriate Gotenberg endpoint based on the file's MIME type.
    On success, saves the PDF locally and enqueues it for processing.

    Args:
        file_path: Path to the file to convert
        original_filename: Optional original filename (if different from path basename)
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting PDF conversion: {file_path}")
    log_task_progress(task_id, "convert_to_pdf", "in_progress", f"Converting file: {os.path.basename(file_path)}")

    gotenberg_url = getattr(settings, "gotenberg_url", None)
    if not gotenberg_url:
        logger.error(f"[{task_id}] Gotenberg URL is not configured in settings.")
        log_task_progress(task_id, "convert_to_pdf", "failure", "Gotenberg URL not configured")
        return

    # Try to guess the MIME type based on file content and extension
    mime_type, encoding = _detect_mime_type(file_path, original_filename)
    file_ext = _detect_extension(file_path, original_filename, mime_type)
    logger.info(f"[{task_id}] Guessed MIME type for '{file_path}' is: {mime_type}, extension: {file_ext}")
    if not mime_type and not file_ext:
        log_task_progress(
            task_id,
            "detect_file_type",
            "failure",
            "Unable to determine file type for conversion",
            detail=(
                f"File: {file_path}\n"
                f"Original filename: {original_filename or 'N/A'}\n"
                "No extension and no detectable magic header."
            ),
        )
        logger.error(f"[{task_id}] Unable to determine file type for conversion: {file_path}")
        return None
    log_task_progress(task_id, "detect_file_type", "success", f"File type: {mime_type or file_ext}")

    # Determine which Gotenberg endpoint to use
    endpoint, form_data, files = _select_gotenberg_endpoint(
        gotenberg_url, file_path, original_filename, mime_type, file_ext
    )

    if not endpoint:
        logger.error(f"[{task_id}] Could not determine Gotenberg endpoint for file type: {mime_type}")
        log_task_progress(task_id, "convert_to_pdf", "failure", f"Unknown file type: {mime_type}")
        return None

    try:
        logger.info(f"[{task_id}] Converting {file_path} using endpoint: {endpoint}")
        log_task_progress(task_id, "call_gotenberg", "in_progress", "Calling Gotenberg API")

        # Send the conversion request to Gotenberg
        response = requests.post(endpoint, files=files, data=form_data, timeout=settings.http_request_timeout)

        if response.status_code == 200:
            # Save the converted PDF
            converted_file_path = os.path.splitext(file_path)[0] + ".pdf"
            with open(converted_file_path, "wb") as out_file:
                out_file.write(response.content)

            logger.info(f"[{task_id}] Converted file saved as PDF: {converted_file_path}")
            log_task_progress(task_id, "call_gotenberg", "success", "PDF conversion successful")
            log_task_progress(
                task_id, "convert_to_pdf", "success", f"Converted to PDF: {os.path.basename(converted_file_path)}"
            )

            # Enqueue the PDF for further processing, preserving original filename if provided
            if original_filename:
                # Change extension to .pdf for the original filename
                original_base = os.path.splitext(original_filename)[0]
                pdf_original_filename = f"{original_base}.pdf"
                process_document.delay(converted_file_path, original_filename=pdf_original_filename)
            else:
                process_document.delay(converted_file_path)

            return converted_file_path
        else:
            error_msg = f"Status code: {response.status_code}"
            logger.error(
                f"[{task_id}] Conversion failed for {file_path}. "
                f"{error_msg}, "
                f"Response: {response.text[:500]}..."
            )
            log_task_progress(task_id, "call_gotenberg", "failure", error_msg)
            log_task_progress(task_id, "convert_to_pdf", "failure", f"Conversion failed: {error_msg}")
            return None
    except Exception as e:
        logger.exception(f"[{task_id}] Error converting {file_path} to PDF: {e}")
        log_task_progress(task_id, "convert_to_pdf", "failure", f"Exception: {str(e)}")
        return None
