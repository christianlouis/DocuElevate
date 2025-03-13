#!/usr/bin/env python3
import os
import json
import email
import imaplib
import logging
import redis
import re
from datetime import datetime, timedelta, timezone
from celery import shared_task
from app.config import settings
from app.tasks.upload_to_s3 import upload_to_s3
from app.tasks.convert_to_pdf import convert_to_pdf  # new conversion task

logger = logging.getLogger(__name__)

# Initialize Redis connection using Celery's Redis settings
redis_client = redis.StrictRedis.from_url(settings.redis_url, decode_responses=True)

LOCK_KEY = "imap_lock"  # Unique key for locking
LOCK_EXPIRE = 300       # Lock expires in 5 minutes

# Local cache file for tracking processed emails
CACHE_FILE = os.path.join(settings.workdir, "processed_mails.json")


def acquire_lock():
    """Attempt to acquire a Redis-based lock. If acquired, set an expiration."""
    lock_acquired = redis_client.setnx(LOCK_KEY, "locked")
    if lock_acquired:
        redis_client.expire(LOCK_KEY, LOCK_EXPIRE)
        logger.info("Lock acquired for IMAP processing.")
        return True
    logger.warning("Lock already held. Skipping this cycle.")
    return False


def release_lock():
    """Release the lock by deleting the Redis key."""
    redis_client.delete(LOCK_KEY)
    logger.info("Lock released.")


def load_processed_emails():
    """Load the list of already processed emails from a local JSON file."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                processed_emails = json.load(f)
                processed_emails = cleanup_old_entries(processed_emails)
                return processed_emails
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
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    valid_emails = {}
    for msg_id, date_str in processed_emails.items():
        naive_dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
        aware_dt = naive_dt.replace(tzinfo=timezone.utc)
        if aware_dt > seven_days_ago:
            valid_emails[msg_id] = date_str
    return valid_emails


@shared_task
def pull_all_inboxes():
    """
    Periodic Celery task that checks all configured IMAP mailboxes
    and fetches attachments from new emails.
    Ensures only one instance runs at a time using Redis-based locking.
    """
    if not acquire_lock():
        logger.info("Skipping execution: Another instance is running.")
        return

    try:
        logger.info("Starting pull_all_inboxes")

        # Mailbox #1 (non-Gmail)
        check_and_pull_mailbox(
            mailbox_key="imap1",
            host=settings.imap1_host,
            port=settings.imap1_port,
            username=settings.imap1_username,
            password=settings.imap1_password,
            use_ssl=settings.imap1_ssl,
            delete_after_process=settings.imap1_delete_after_process,
        )

        # Mailbox #2 (Gmail)
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

    finally:
        release_lock()


def check_and_pull_mailbox(
    mailbox_key: str,
    host: str | None,
    port: int | None,
    username: str | None,
    password: str | None,
    use_ssl: bool,
    delete_after_process: bool,
):
    """Validates config and invokes pulling from the mailbox if valid."""
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


def pull_inbox(mailbox_key, host, port, username, password, use_ssl, delete_after_process):
    """
    Connects to the IMAP inbox, fetches new unread emails from the last 3 days,
    and processes attachments while preserving the original unread status.
    
    For Gmail:
      - Attempts to select the localized All Mail folder.
      - Runs an X-GM-RAW query: "in:anywhere in:unread newer_than:3d has:attachment".
    
    For non-Gmail mailboxes, it falls back to selecting the INBOX with a SINCE/UNSEEN filter.
    """
    logger.info(f"Connecting to {mailbox_key} at {host}:{port} (SSL={use_ssl})")
    processed_emails = load_processed_emails()

    try:
        mail = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
        mail.login(username, password)

        is_gmail_host = "gmail" in host.lower()
        if is_gmail_host:
            # For Gmail, try to select the localized All Mail folder.
            all_mail_folder = find_all_mail_folder(mail)
            if all_mail_folder:
                logger.info(f"Using Gmail All Mail folder: {all_mail_folder}")
                mail.select(f'"{all_mail_folder}"')
            else:
                logger.warning("Gmail All Mail folder not found, falling back to INBOX.")
                mail.select("INBOX")
            # Use the X-GM-RAW query for Gmail.
            raw_query = "in:anywhere in:unread newer_than:3d has:attachment"
            status, search_data = mail.search(None, "X-GM-RAW", f'"{raw_query}"')
        else:
            # For non-Gmail, select INBOX and use SINCE/UNSEEN query.
            mail.select("INBOX")
            since_date = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%d-%b-%Y")
            status, search_data = mail.search(None, f'(SINCE {since_date} UNSEEN)')

        if status != "OK":
            logger.warning(f"Search failed on mailbox {mailbox_key}. Status={status}")
            mail.close()
            mail.logout()
            return

        msg_numbers = search_data[0].split()
        logger.info(f"Found {len(msg_numbers)} unread emails in {mailbox_key}.")

        for num in msg_numbers:
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

            if msg_id in processed_emails:
                logger.info(f"Skipping already processed email {msg_id} in {mailbox_key}")
                continue

            # For Gmail, check if the email already has the "Ingested" label.
            if is_gmail_host:
                if email_already_has_label(mail, num, "Ingested"):
                    logger.info(f"Skipping email {msg_id} in {mailbox_key}, already labeled 'Ingested'.")
                    continue

            # Process attachments (and convert non-PDF files)
            has_attachment = fetch_attachments_and_enqueue(email_message)

            if is_gmail_host:
                mark_as_processed_with_star(mail, num)
                mark_as_processed_with_label(mail, num, label="Ingested")

            processed_emails[msg_id] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            save_processed_emails(processed_emails)

            if delete_after_process:
                logger.info(f"Deleting message {num.decode()} from {mailbox_key}")
                mail.store(num, "+FLAGS", "\\Deleted")
            else:
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
    Extracts attachments from the email and processes only allowed file types.
    
    Allowed file types include:
      - PDF: application/pdf
      - Microsoft Office files:
          - Word: application/msword, application/vnd.openxmlformats-officedocument.wordprocessingml.document
          - Excel: application/vnd.ms-excel, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
          - PowerPoint: application/vnd.ms-powerpoint, application/vnd.openxmlformats-officedocument.presentationml.presentation
      - Other meaningful attachments:
          - Plain text: text/plain
          - CSV: text/csv
          - Rich Text Format: application/rtf, text/rtf
    
    - If the attachment is a PDF, it is enqueued for upload.
    - For any other allowed file, a conversion task is enqueued to convert it to PDF.
    
    Returns True if at least one allowed attachment was processed.
    """
    # Define allowed MIME types for office files and other meaningful attachments.
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
    
    has_attachment = False
    for part in email_message.walk():
        if part.get_content_maintype() == "multipart":
            continue

        filename = part.get_filename()
        if not filename:
            continue

        # Check the MIME type of the attachment.
        mime_type = part.get_content_type()
        if mime_type not in ALLOWED_MIME_TYPES:
            logger.info(f"Skipping attachment {filename} with MIME type {mime_type}")
            continue

        file_path = os.path.join(settings.workdir, filename)
        with open(file_path, "wb") as f:
            f.write(part.get_payload(decode=True))

        if mime_type == "application/pdf":
            upload_to_s3.delay(file_path)
            logger.info(f"Enqueued PDF for upload: {filename}")
        else:
            # Enqueue conversion to PDF using the Gotenberg service.
            convert_to_pdf.delay(file_path)
            logger.info(f"Enqueued file for conversion to PDF: {filename}")

        has_attachment = True
    return has_attachment



def email_already_has_label(mail, msg_id, label="Ingested"):
    """
    Checks if the given message (msg_id) has the specified Gmail label.
    Returns True if the label is found, False otherwise.
    """
    try:
        label_status, label_data = mail.fetch(msg_id, "(X-GM-LABELS)")
        if label_status == "OK" and label_data and len(label_data) > 0:
            raw_labels = label_data[0][1].decode("utf-8", errors="ignore")
            if label in raw_labels:
                return True
    except Exception as e:
        logger.error(f"Failed to fetch labels for msg_id={msg_id}: {e}")
    return False


def mark_as_processed_with_star(mail, msg_id):
    """Stars the email in Gmail."""
    try:
        mail.store(msg_id, "+FLAGS", "\\Flagged")
        logger.info(f"Email {msg_id} starred in Gmail.")
    except Exception as e:
        logger.error(f"Failed to star email {msg_id}: {e}")


def mark_as_processed_with_label(mail, msg_id, label="Ingested"):
    """Adds a custom label to the email in Gmail."""
    try:
        mail.store(msg_id, "+X-GM-LABELS", label)
        logger.info(f"Email {msg_id} labeled '{label}' in Gmail.")
    except Exception as e:
        logger.error(f"Failed to label email {msg_id} with {label}: {e}")


def find_all_mail_folder(mail):
    """
    Attempts to select the Gmail All Mail folder using known localized names.
    Falls back to using XLIST if needed.
    Returns the folder name if found, otherwise None.
    """
    COMMON_ALL_MAIL_NAMES = [
        "[Gmail]/Alle Nachrichten",
        "[Gmail]/All Mail",
        "[Gmail]/Todos",
        "[Gmail]/Tutte le mail",
        "[Gmail]/Tous les messages",
    ]
    for candidate in COMMON_ALL_MAIL_NAMES:
        status, _ = mail.select(f'"{candidate}"', readonly=True)
        if status == "OK":
            return candidate

    capabilities = get_capabilities(mail)
    if "XLIST" in capabilities:
        candidate = find_all_mail_xlist(mail)
        if candidate:
            return candidate
    return None


def get_capabilities(mail):
    """Returns a list of capabilities supported by the IMAP server."""
    typ, data = mail.capability()
    if typ == "OK" and data:
        caps = data[0].decode("utf-8", errors="ignore").upper().split()
        return caps
    return []


def find_all_mail_xlist(mail):
    """
    Uses XLIST to discover the mailbox flagged as All Mail.
    Returns the folder name if found, otherwise None.
    """
    tag = mail._new_tag().decode("ascii")
    command_str = f"{tag} XLIST \"\" \"*\""
    mail.send((command_str + "\r\n").encode("utf-8"))

    all_mail_folder = None
    while True:
        line = mail.readline()
        if not line:
            break
        line_str = line.decode("utf-8", errors="ignore").strip()
        if line_str.upper().startswith("* XLIST ") and "\\ALLMAIL" in line_str.upper():
            match = re.search(r'"([^"]+)"$', line_str)
            if match:
                candidate = match.group(1)
                logger.info(f"Found All Mail folder via XLIST: {candidate}")
                all_mail_folder = candidate
        if line_str.startswith(tag):
            break
    return all_mail_folder
