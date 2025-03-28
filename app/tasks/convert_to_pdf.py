#!/usr/bin/env python3
import os
import requests
import logging
import mimetypes
from celery import shared_task
from app.config import settings
from app.tasks.process_document import process_document  # Updated import

logger = logging.getLogger(__name__)

@shared_task
def convert_to_pdf(file_path):
    """
    Converts a file to PDF using Gotenberg's API.
    Determines the appropriate Gotenberg endpoint based on the file's MIME type.
    On success, saves the PDF locally and enqueues it for S3 upload.
    """
    gotenberg_url = getattr(settings, "gotenberg_url", None)
    if not gotenberg_url:
        logger.error("Gotenberg URL is not configured in settings.")
        return

    # Try to guess the MIME type based on file content (using extension-based fallback)
    mime_type, encoding = mimetypes.guess_type(file_path)
    logger.info(f"Guessed MIME type for '{file_path}' is: {mime_type}")

    endpoint = None
    form_key = "files"  # Default form key for most endpoints

    if mime_type:
        if mime_type == "text/html":
            endpoint = f"{gotenberg_url}/forms/chromium/convert/html"
            # The Chromium HTML endpoint expects the HTML file to be provided under the key "index.html"
            form_key = "index.html"
        elif mime_type.startswith("image/"):
            # For images, we use the LibreOffice endpoint (which supports image conversion)
            endpoint = f"{gotenberg_url}/forms/libreoffice/convert"
        elif mime_type.startswith("text/plain"):
            endpoint = f"{gotenberg_url}/forms/libreoffice/convert"
        elif mime_type in ["text/markdown", "text/x-markdown"]:
            # Optionally, you could use the Chromium markdown endpoint if you have an HTML wrapper.
            # For now, we'll fallback to LibreOffice.
            endpoint = f"{gotenberg_url}/forms/libreoffice/convert"
        else:
            # For all other MIME types (e.g. Office documents), use the LibreOffice endpoint.
            endpoint = f"{gotenberg_url}/forms/libreoffice/convert"
    else:
        # If MIME detection fails, fallback to extension-based detection.
        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".html", ".htm"]:
            endpoint = f"{gotenberg_url}/forms/chromium/convert/html"
            form_key = "index.html"
        else:
            endpoint = f"{gotenberg_url}/forms/libreoffice/convert"

    try:
        with open(file_path, "rb") as f:
            files = {form_key: f}
            response = requests.post(endpoint, files=files)

        if response.status_code == 200:
            converted_file_path = os.path.splitext(file_path)[0] + ".pdf"
            with open(converted_file_path, "wb") as out_file:
                out_file.write(response.content)
            logger.info(f"Converted file saved as PDF: {converted_file_path}")
            process_document.delay(converted_file_path)  # Updated function call
            return converted_file_path
        else:
            logger.error(f"Conversion failed for {file_path}. Status code: {response.status_code}")
    except Exception as e:
        logger.exception(f"Error converting {file_path} to PDF: {e}")
