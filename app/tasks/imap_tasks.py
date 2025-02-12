#!/usr/bin/env python3

import os
import time
import email
import imaplib
import tempfile
import logging
from datetime import datetime, timedelta

from celery import shared_task
from app.config import settings

# Import your pipeline's first-step task:
from app.tasks.upload_to_s3 import upload_to_s3

logger = logging.getLogger(__name__)

# We'll keep track of the last poll time in a dictionary (mailbox -> datetime).
# This is in-memory only, so if you have multiple workers or restarts, it won't persist.
LAST_POLL_TIMES = {
    "imap1": None,
    "imap2": None,
}


@shared_task
def pull_all_inboxes():
    """
    This task is run periodically (e.g., every minute).
    It checks each IMAP config, sees if it's time to poll (based on poll interval),
    and if so, fetches attachments.
    """
    logger.info("pull_all_inboxes - starting")

    # Check mailbox #1
    check_and_pull_mailbox(
        mailbox_key="imap1",
        host=settings.imap1_host,
        port=settings.imap1_port,
        username=settings.imap1_username,
        password=settings.imap1_password,
        use_ssl=settings.imap1_ssl,
        poll_interval=settings.imap1_poll_interval_minutes,
        delete_after_process=settings.imap1_delete_after_process,
    )

    # Check mailbox #2
    check_and_pull_mailbox(
        mailbox_key="imap2",
        host=settings.imap2_host,
        port=settings.imap2_port,
        username=settings.imap2_username,
        password=settings.imap2_password,
        use_ssl=settings.imap2_ssl,
        poll_interval=settings.imap2_poll_interval_minutes,
        delete_after_process=settings.imap2_delete_after_process,
    )

    logger.info("pull_all_inboxes - done")


def check_and_pull_mailbox(
    mailbox_key: str,
    host: str | None,
    port: int | None,
    username: str | None,
    password: str | None,
    use_ssl: bool,
    poll_interval: int,
    delete_after_process: bool,
):
    """Check if it's time to poll this mailbox. If so, do it."""
    # If not configured, skip
    if not (host and port and username and password):
        logger.warning(f"Mailbox {mailbox_key} is missing config, skipping.")
        return

    # If we never polled before, we can do it immediately.
    last_poll = LAST_POLL_TIMES.get(mailbox_key)
    now = datetime.utcnow()

    if last_poll is None or now - last_poll >= timedelta(minutes=poll_interval):
        logger.info(f"Time to poll mailbox {mailbox_key}!")
        pull_inbox(
            mailbox_key=mailbox_key,
            host=host,
            port=port,
            username=username,
            password=password,
            use_ssl=use_ssl,
            delete_after_process=delete_after_process
        )
        LAST_POLL_TIMES[mailbox_key] = now
    else:
        logger.debug(f"Skipping {mailbox_key}, not due yet.")


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
    Connect to the IMAP inbox, fetch UNSEEN messages, look for attachments,
    and enqueue them to the pipeline. Then either delete or mark read.
    """
    logger.info(f"Connecting to {mailbox_key} at {host}:{port} (SSL={use_ssl})")

    try:
        if use_ssl:
            mail = imaplib.IMAP4_SSL(host, port)
        else:
            mail = imaplib.IMAP4(host, port)

        mail.login(username, password)
        mail.select("INBOX")

        # fetch only unseen messages
        status, search_data = mail.search(None, "(UNSEEN)")
        if status != "OK":
            logger.warning(f"Search failed on mailbox {mailbox_key}. Status={status}")
            mail.close()
            mail.logout()
            return

        msg_numbers = search_data[0].split()
        logger.info(f"Found {len(msg_numbers)} new messages in {mailbox_key}.")

        for num in msg_numbers:
            # fetch the full RFC822 message
            status, msg_data = mail.fetch(num, "(RFC822)")
            if status != "OK":
                logger.warning(f"Failed to fetch message {num} in {mailbox_key}. Status={status}")
                continue

            raw_email = msg_data[0][1]
            email_message = email.message_from_bytes(raw_email)

            # Extract attachments and enqueue
            fetch_attachments_and_enqueue(email_message)

            # Mark read or delete
            if delete_after_process:
                logger.info(f"Deleting message {num.decode()} from {mailbox_key}")
                mail.store(num, "+FLAGS", "\\Deleted")
            else:
                logger.info(f"Marking message {num.decode()} as seen in {mailbox_key}")
                mail.store(num, "+FLAGS", "\\Seen")

        if delete_after_process:
            mail.expunge()

        mail.close()
        mail.logout()
        logger.info(f"Finished processing mailbox {mailbox_key}")

    except Exception as e:
        logger.exception(f"Error pulling mailbox {mailbox_key}: {e}")


def fetch_attachments_and_enqueue(email_message):
    """
    Iterate over parts of the email, extract PDF attachments,
    save them to settings.workdir/tmp, and then enqueue
    the pipeline with upload_to_s3.delay().
    """
    for part in email_message.walk():
        content_type = part.get_content_type()
        filename = part.get_filename()

        if part.get_content_maintype() == 'multipart':
            continue  # skip container parts
        if not filename:
            continue  # skip if there's no filename

        # Example: only PDF attachments
        if content_type == "application/pdf":
            logger.info(f"Found PDF attachment: {filename}")

            # Create a path in tmp with the original filename
            file_path = os.path.join(settings.workdir, filename)

            # If a file with that name exists, we could rename it, but let's just overwrite
            # or create a unique name. For simplicity:
            with open(file_path, "wb") as f:
                f.write(part.get_payload(decode=True))

            logger.info(f"Saved attachment to {file_path}")

            # Now enqueue the pipeline's first step:
            # E.g.: upload_to_s3 -> process_with_textract -> refine_text_with_gpt, etc.
            upload_to_s3.delay(file_path)

            # If you prefer to *only* do the PDF embedding steps, you'd queue that first, etc.
            # Or if you want to do the entire pipeline that you do in /process/ endpoint,
            # you can replicate that chain here.

    # End fetch_attachments_and_enqueue
