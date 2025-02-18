#!/usr/bin/env python3

import os
import json
import email
import imaplib
import logging
from datetime import datetime, timedelta

from celery import shared_task
from app.config import settings
from app.tasks.upload_to_s3 import upload_to_s3

logger = logging.getLogger(__name__)

# Local cache file for tracking processed emails
CACHE_FILE = os.path.join(settings.workdir, "processed_mails.json")


def load_processed_emails():
    """Load the list of already processed emails from a local JSON file."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning("Failed to decode JSON, resetting processed emails cache.")
            return {}
    return {}


def save_processed_emails(processed_emails):
    """Save the processed email IDs to a local JSON file."""
    with open(CACHE_FILE, "w") as f:
        json.dump(processed_emails, f, indent=4)


def cleanup_old_entries(processed_emails):
    """Remove entries older than 7 days from the cache to avoid infinite growth."""
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    return {
        msg_id: date
        for msg_id, date in processed_emails.items()
        if datetime.strptime(date, "%Y-%m-%dT%H:%M:%S") > seven_days_ago
    }


@shared_task
def pull_all_inboxes():
    """
    Periodic task that checks all configured IMAP mailboxes
    and fetches attachments from new emails.
    """
    logger.info("Starting pull_all_inboxes")

    # Process Mailbox #1
    check_and_pull_mailbox(
        mailbox_key="imap1",
        host=settings.imap1_host,
        port=settings.imap1_port,
        username=settings.imap1_username,
        password=settings.imap1_password,
        use_ssl=settings.imap1_ssl,
        delete_after_process=settings.imap1_delete_after_process,
    )

    # Process Mailbox #2
    check_and_pull_mailbox(
        mailbox_key="imap2",
        host=settings.imap2_host,
        port=settings.imap2_port,
        username=settings.imap2_username,
        password=settings.imap2_password,
        use_ssl=settings.imap2_ssl,
        delete_after_process=settings.imap2_delete_after_process,
    )

    logger.info("Finished pull_all_inboxes")


def check_and_pull_mailbox(
    mailbox_key: str,
    host: str | None,
    port: int | None,
    username: str | None,
    password: str | None,
    use_ssl: bool,
    delete_after_process: bool,
):
    """Check and pull new emails from a given mailbox."""
    if not (host and port and username and password):
        logger.warning(f"Mailbox {mailbox_key} is missing config, skipping.")
        return

    logger.info(f"Checking mailbox: {mailbox_key}")
    pull_inbox(
        mailbox_key=mailbox_key,
        host=host,
        port=port,
        username=username,
        password=password,
        use_ssl=use_ssl,
        delete_after_process=delete_after_process,
    )


def pull_inbox(
    mailbox_key: str,
    host: str,
    port: int,
    username: str,
    password: str,
    use_ssl: bool,
    delete_after_process: bool
):
    """
    Connects to the IMAP inbox, fetches new emails (last 3 days),
    and processes attachments while preserving the original unread status.
    """
    logger.info(f"Connecting to {mailbox_key} at {host}:{port} (SSL={use_ssl})")
    processed_emails = load_processed_emails()

    try:
        if use_ssl:
            mail = imaplib.IMAP4_SSL(host, port)
        else:
            mail = imaplib.IMAP4(host, port)

        mail.login(username, password)
        mail.select("INBOX")

        # Fetch emails from the last 3 days
        since_date = (datetime.utcnow() - timedelta(days=3)).strftime("%d-%b-%Y")
        status, search_data = mail.search(None, f'(SINCE {since_date})')
        if status != "OK":
            logger.warning(f"Search failed on mailbox {mailbox_key}. Status={status}")
            mail.close()
            mail.logout()
            return

        msg_numbers = search_data[0].split()
        logger.info(f"Found {len(msg_numbers)} emails from the last 3 days in {mailbox_key}.")

        for num in msg_numbers:
            # Check if email is unread
            status, flag_data = mail.fetch(num, "(FLAGS)")
            if status != "OK":
                logger.warning(f"Failed to fetch flags for message {num} in {mailbox_key}. Status={status}")
                continue

            is_unread = b"\\Seen" not in flag_data[0]  # Email was originally unread

            status, msg_data = mail.fetch(num, "(RFC822)")
            if status != "OK":
                logger.warning(f"Failed to fetch message {num} in {mailbox_key}. Status={status}")
                continue

            raw_email = msg_data[0][1]
            email_message = email.message_from_bytes(raw_email)
            msg_id = email_message.get("Message-ID")

            if not msg_id:
                logger.warning(f"Skipping email without Message-ID in {mailbox_key}")
                continue

            # Skip if already processed
            if msg_id in processed_emails:
                logger.info(f"Skipping already processed email {msg_id} in {mailbox_key}")
                continue

            # Process attachments
            has_attachment = fetch_attachments_and_enqueue(email_message)

            # Store processed email in cache
            processed_emails[msg_id] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
            save_processed_emails(cleanup_old_entries(processed_emails))

            # Handle deletion or unread restoration
            if delete_after_process:
                logger.info(f"Deleting message {num.decode()} from {mailbox_key}")
                mail.store(num, "+FLAGS", "\\Deleted")
            else:
                # Restore unread status if it was unread before processing
                if is_unread:
                    mail.store(num, "-FLAGS", "\\Seen")

        if delete_after_process:
            mail.expunge()

        mail.close()
        mail.logout()
        logger.info(f"Finished processing mailbox {mailbox_key}")

    except Exception as e:
        logger.exception(f"Error pulling mailbox {mailbox_key}: {e}")


def fetch_attachments_and_enqueue(email_message):
    """
    Extracts PDF attachments from an email and enqueues them for processing.

    Returns:
        bool: True if an attachment was found, False otherwise.
    """
    has_attachment = False

    for part in email_message.walk():
        content_type = part.get_content_type()
        filename = part.get_filename()

        if part.get_content_maintype() == 'multipart':
            continue  # Skip container parts
        if not filename:
            continue  # Skip if there's no filename

        # Process PDF attachments only
        if content_type == "application/pdf":
            logger.info(f"Found PDF attachment: {filename}")
            has_attachment = True

            # Save to temporary directory
            file_path = os.path.join(settings.workdir, filename)
            with open(file_path, "wb") as f:
                f.write(part.get_payload(decode=True))

            logger.info(f"Saved attachment to {file_path}")

            # Enqueue for upload
            upload_to_s3.delay(file_path)

    return has_attachment
