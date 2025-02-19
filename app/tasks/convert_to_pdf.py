#!/usr/bin/env python3
import os
import requests
import logging
from celery import shared_task
from app.config import settings
from app.tasks.upload_to_s3 import upload_to_s3

logger = logging.getLogger(__name__)

@shared_task
def convert_to_pdf(file_path):
    """
    Converts a file to PDF using Gotenberg's API.
    On success, saves the PDF locally and enqueues it for S3 upload.
    """
    # Ensure that settings contain the Gotenberg URL (e.g., "http://gotenberg:3000")
    gotenberg_url = getattr(settings, "gotenberg_url", None)
    if not gotenberg_url:
        logger.error("Gotenberg URL is not configured in settings.")
        return

    try:
        with open(file_path, "rb") as f:
            files = {"file": f}
            # Adjust the endpoint path if needed.
            response = requests.post(f"{gotenberg_url}/convert", files=files)
        if response.status_code == 200:
            converted_file_path = os.path.splitext(file_path)[0] + ".pdf"
            with open(converted_file_path, "wb") as f:
                f.write(response.content)
            logger.info(f"Converted file saved as PDF: {converted_file_path}")
            # Enqueue the upload of the converted PDF.
            upload_to_s3.delay(converted_file_path)
            return converted_file_path
        else:
            logger.error(f"Conversion failed for {file_path}. Status code: {response.status_code}")
    except Exception as e:
        logger.exception(f"Error converting {file_path} to PDF: {e}")
