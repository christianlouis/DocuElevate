#!/usr/bin/env python3

import json
import logging
import os
import smtplib
import socket
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.celery_app import celery
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import log_task_progress

logger = logging.getLogger(__name__)

# Constants
_LOGO_FILENAME = "logo.png"


def get_email_template(template_name="default.html"):
    """
    Load email template from one of these locations in order of precedence:
    1. Custom template from workdir/templates/email/
    2. Default template from app/templates/email/
    """
    # First try to load from workdir (user customizable location)
    try:
        workdir_template_path = os.path.join(settings.workdir, "templates", "email")
        if os.path.exists(workdir_template_path):
            env = Environment(
                loader=FileSystemLoader(workdir_template_path), autoescape=select_autoescape(["html", "xml"])
            )
            env.globals["now"] = datetime.now  # Add the now function to the Jinja environment
            template = env.get_template(template_name)
            logger.info(f"Using custom email template from workdir: {template_name}")
            return template
    except Exception as e:
        logger.warning(f"Failed to load custom email template: {str(e)}")

    # Fallback to built-in template
    try:
        # Get the app directory path (where this file is)
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_template_path = os.path.join(current_dir, "templates", "email")
        env = Environment(loader=FileSystemLoader(app_template_path), autoescape=select_autoescape(["html", "xml"]))
        env.globals["now"] = datetime.now  # Add the now function to the Jinja environment
        template = env.get_template(template_name)
        logger.info(f"Using built-in email template: {template_name}")
        return template
    except Exception as e:
        logger.error(f"Failed to load built-in email template: {str(e)}")
        raise ValueError(f"Could not find any valid email template: {str(e)}")


def extract_metadata_from_file(file_path):
    """
    Try to extract metadata from a file using several methods:
    1. Check for a .json metadata file with the same name
    2. Extract metadata from PDF if it's embedded

    Returns a dictionary of metadata or None if not found
    """
    metadata = {}

    # Check for separate metadata JSON file
    metadata_path = os.path.splitext(file_path)[0] + ".json"
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
                logger.info(f"Loaded metadata from external JSON file: {metadata_path}")
                return metadata
        except Exception as e:
            logger.warning(f"Failed to load metadata from JSON file: {str(e)}")

    # TODO: For PDF files, try to extract embedded metadata using PyPDF2
    # This would require additional dependencies, so for now we'll just check for external JSON

    return metadata


def attach_logo(msg):
    """Attach the DocuElevate logo to the email with proper Content-ID."""
    try:
        # Try to find logo in workdir first (for customization)
        custom_logo_path = os.path.join(settings.workdir, "templates", "email", _LOGO_FILENAME)
        if os.path.exists(custom_logo_path):
            logo_path = custom_logo_path
        else:
            # Use built-in logo
            app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            logo_path = os.path.join(app_dir, "static", _LOGO_FILENAME)
            # Fallback to logo in frontend/static if app/static doesn't exist
            if not os.path.exists(logo_path):
                logo_path = os.path.join(app_dir, "..", "frontend", "static", _LOGO_FILENAME)

        if os.path.exists(logo_path):
            with open(logo_path, "rb") as img:
                logo_data = img.read()

            # Determine image MIME type based on extension
            mimetype = "image/svg+xml" if logo_path.endswith(".svg") else "image/png"
            logo_attach = MIMEImage(logo_data, mimetype)
            logo_attach.add_header("Content-ID", "<logo>")
            logo_attach.add_header("Content-Disposition", "inline", filename=_LOGO_FILENAME)
            msg.attach(logo_attach)
            logger.info(f"Logo attached from {logo_path}")
            return True
        else:
            logger.warning("Could not find logo file")
            return False

    except Exception as e:
        logger.warning(f"Error attaching logo: {str(e)}")
        return False


def _prepare_recipients(recipients):
    """Helper function to prepare email recipients list."""
    if not recipients:
        if not settings.email_default_recipient:
            error_msg = "No recipients specified and no default recipient configured"
            logger.error(error_msg)
            return None, error_msg
        return [settings.email_default_recipient], None
    elif isinstance(recipients, str):
        return [recipients], None  # Convert single email to list
    return recipients, None


def _send_email_with_smtp(msg, filename, recipients):
    """Helper function to handle SMTP connection and sending."""
    try:
        # First try to resolve the hostname
        socket.gethostbyname(settings.email_host)

        # Connect to the SMTP server
        with smtplib.SMTP(settings.email_host, settings.email_port, timeout=30) as server:
            # Use TLS if specified
            if settings.email_use_tls:
                server.starttls()

            # Login if credentials are provided
            if settings.email_username and settings.email_password:
                server.login(settings.email_username, settings.email_password)

            # Send the email
            server.send_message(msg)

        logger.info(f"Successfully sent {filename} via email to {', '.join(recipients)}")
        return None
    except socket.gaierror as e:
        error_msg = f"Failed to resolve email host: {settings.email_host} - {str(e)}"
        logger.error(error_msg)
        return {"status": "Failed", "reason": error_msg, "error": str(e)}
    except (ConnectionRefusedError, TimeoutError) as e:
        error_msg = f"Connection error to SMTP server {settings.email_host}:{settings.email_port} - {str(e)}"
        logger.error(error_msg)
        return {"status": "Failed", "reason": error_msg, "error": str(e)}


@celery.task(base=BaseTaskWithRetry, bind=True)
def upload_to_email(
    self,
    file_path: str,
    recipients=None,
    subject=None,
    message=None,
    template_name="default.html",
    include_metadata=True,
    file_id: int = None,
):
    """
    Sends a file via email to the specified recipients.
    If recipients is None, uses the configured default email recipient.

    Args:
        file_path: Path to the file to send
        recipients: Optional list of recipient email addresses
        subject: Optional email subject
        message: Optional custom message
        template_name: Email template to use
        include_metadata: Whether to include metadata in the email
        file_id: Optional file ID to associate with logs
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting email send: {file_path}")
    log_task_progress(
        task_id, "upload_to_email", "in_progress", f"Sending via email: {os.path.basename(file_path)}", file_id=file_id
    )

    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_email", "failure", error_msg, file_id=file_id)
        raise FileNotFoundError(error_msg)

    # Extract filename
    filename = os.path.basename(file_path)

    # Check if email settings are configured
    if not settings.email_host:
        error_msg = "Email host is not configured"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_email", "skipped", error_msg, file_id=file_id)
        return {"status": "Skipped", "reason": error_msg}

    # Log email configuration for debugging
    logger.debug(
        f"[{task_id}] Email config - Host: {settings.email_host}, Port: {settings.email_port}, "
        f"Username: {settings.email_username}, TLS: {settings.email_use_tls}"
    )

    # Process recipients
    recipients, error = _prepare_recipients(recipients)
    if error:
        logger.error(f"[{task_id}] {error}")
        log_task_progress(task_id, "upload_to_email", "skipped", error, file_id=file_id)
        return {"status": "Skipped", "reason": error}

    # Use provided subject or create default
    subject = subject or f"DocuElevate Document: {filename}"

    # Extract document metadata if available
    metadata = {}
    if include_metadata:
        metadata = extract_metadata_from_file(file_path)

    try:
        # Create the email
        msg = MIMEMultipart("related")
        msg["From"] = settings.email_sender or settings.email_username
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject

        # Create alternative part for HTML content
        alt_part = MIMEMultipart("alternative")
        msg.attach(alt_part)

        # Attach logo to the email
        has_logo = attach_logo(msg)

        # Load and render template
        template = get_email_template(template_name)

        # Context data for the template
        context = {
            "filename": filename,
            "message": message or f"Attached is the document: {filename}",
            "app_name": "DocuElevate",
            "app_url": f"https://{settings.external_hostname}" if settings.external_hostname else None,
            "custom_message": message,
            "metadata": metadata,
            "has_metadata": bool(metadata),
            "has_logo": has_logo,
            "current_year": datetime.now().year,
        }

        # Render HTML body
        html_content = template.render(**context)
        alt_part.attach(MIMEText(html_content, "html"))

        # Attach the file
        with open(file_path, "rb") as file:
            attachment = MIMEApplication(file.read(), _subtype="pdf")
            attachment.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(attachment)

        # Send the email through SMTP
        error_result = _send_email_with_smtp(msg, filename, recipients)
        if error_result:
            logger.error(f"[{task_id}] Failed to send email: {error_result.get('reason')}")
            log_task_progress(task_id, "upload_to_email", "failure", error_result.get("reason"), file_id=file_id)
            return error_result

        logger.info(f"[{task_id}] Successfully sent {filename} via email to {len(recipients)} recipients")
        log_task_progress(task_id, "upload_to_email", "success", f"Sent via email: {filename}", file_id=file_id)

        return {
            "status": "Completed",
            "file": file_path,
            "recipients": recipients,
            "subject": subject,
            "metadata_included": bool(metadata),
            "logo_included": has_logo,
        }

    except Exception as e:
        error_msg = f"Failed to send {filename} via email: {str(e)}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_email", "failure", error_msg, file_id=file_id)
        raise Exception(error_msg)
