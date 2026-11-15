#!/usr/bin/env python3
import email
import hashlib
import imaplib
import json
import logging
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone

import redis
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from app.config import settings
from app.tasks.convert_to_pdf import convert_to_pdf  # new conversion task
from app.tasks.imap_intake import reconcile_imap_intakes
from app.tasks.process_document import process_document  # Updated import
from app.utils.allowed_types import (
    ALL_CATEGORIES,
    DEFAULT_CATEGORIES,
    get_allowed_types_for_categories,
)
from app.utils.imap import IMAP_SOCKET_TIMEOUT_SECONDS, _shutdown_imap_connection
from app.utils.network import is_private_ip

# Database session for per-user IMAP accounts (imported lazily to avoid circular imports)
_db_session_factory = None

# Maximum length to store as last_error to prevent DB bloat
_MAX_ERROR_LENGTH = 500


def _get_db_session():
    """Return a new SQLAlchemy session (lazy import to avoid startup issues)."""
    global _db_session_factory  # noqa: PLW0603
    if _db_session_factory is None:
        from app.database import SessionLocal

        _db_session_factory = SessionLocal
    return _db_session_factory()


logger = logging.getLogger(__name__)

# Initialize Redis connection using Celery's Redis settings
redis_client = redis.StrictRedis.from_url(
    settings.redis_url, decode_responses=True, socket_connect_timeout=5, socket_timeout=5
)


def _decrypt_imap_password(password: str | None) -> str | None:
    """Decrypt an IMAP account password stored in the database.

    Passwords are stored encrypted (Fernet, ``enc:`` prefix) for new records;
    legacy plaintext records are returned unchanged so existing accounts
    continue to work until they are next updated via the API.
    """
    from app.utils.encryption import decrypt_value

    return decrypt_value(password)


def _resolve_categories_for_profile(profile_id: int | None) -> list[str]:
    """Return the list of allowed categories for a profile ID.

    Loads the profile from the database.  If ``profile_id`` is ``None`` or the
    profile is not found, falls back to the global ``settings.imap_attachment_filter``
    string (``'documents_only'`` → default categories; ``'all'`` → all categories).
    """
    if profile_id is not None:
        try:
            from app.models import ImapIngestionProfile

            db = _get_db_session()
            try:
                profile = db.query(ImapIngestionProfile).filter(ImapIngestionProfile.id == profile_id).first()
                if profile:
                    return json.loads(profile.allowed_categories)
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not load IMAP ingestion profile %d (%s: %s) — using global default",
                profile_id,
                type(exc).__name__,
                exc,
            )

    # Fall back to global setting
    if settings.imap_attachment_filter == "all":
        return ALL_CATEGORIES
    return DEFAULT_CATEGORIES


LOCK_KEY = "imap_lock"  # Unique key for locking
LOCK_EXPIRE = 300  # Lock expires in 5 minutes
POLL_BATCH_SIZE = 50
POLL_BUDGET_SECONDS = 240
POLL_CHECKPOINT_TTL_SECONDS = 24 * 60 * 60
POLL_CHECKPOINT_PREFIX = "docuelevate:imap:last_success:"

# Local cache file for tracking processed emails
CACHE_FILE = os.path.join(settings.workdir, "processed_mails.json")


def record_poll_success(mailbox_key: str, *, now: datetime | None = None) -> None:
    """Record the epoch time of a successful mailbox poll, including empty polls."""
    observed_at = now or datetime.now(timezone.utc)
    redis_client.set(
        f"{POLL_CHECKPOINT_PREFIX}{mailbox_key}",
        str(int(observed_at.timestamp())),
        ex=POLL_CHECKPOINT_TTL_SECONDS,
    )


def acquire_lock():
    """Acquire an expiring owner-token lock atomically.

    The old implementation could leave a permanent ``locked`` key between
    SETNX and EXPIRE.  Such a legacy key is removed once and replaced with a
    tokenised lease; current owners can only be released by their token.
    """
    token = str(uuid.uuid4())
    try:
        if redis_client.set(LOCK_KEY, token, nx=True, ex=LOCK_EXPIRE):
            logger.info("Lock acquired for IMAP processing.")
            return token
        if redis_client.ttl(LOCK_KEY) == -1:
            # Atomically replace only the exact pre-token sentinel.
            script = "if redis.call('get', KEYS[1]) == 'locked' and redis.call('ttl', KEYS[1]) == -1 then redis.call('set', KEYS[1], ARGV[1], 'EX', ARGV[2]) return 1 end return 0"
            if redis_client.eval(script, 1, LOCK_KEY, token, LOCK_EXPIRE):
                logger.warning("Recovered legacy IMAP lock without a TTL.")
                return token
    except Exception:  # noqa: BLE001
        logger.exception("Unable to acquire IMAP lock")
    logger.warning("Lock already held. Skipping this cycle.")
    return None


def release_lock(token=None):
    """Release only our own lease (compare-and-delete)."""
    if not token:
        return
    script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
    redis_client.eval(script, 1, LOCK_KEY, token)
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


@shared_task(soft_time_limit=240, time_limit=270)
def pull_all_inboxes():
    """
    Periodic Celery task that checks all configured IMAP mailboxes
    and fetches attachments from new emails.
    Ensures only one instance runs at a time using Redis-based locking.

    Processes:
    1. System-level mailboxes configured via environment variables (IMAP1, IMAP2).
    2. Per-user IMAP accounts stored in the ``user_imap_accounts`` database table.
    """
    lock_token = acquire_lock()
    if not lock_token:
        logger.info("Skipping execution: Another instance is running.")
        return

    try:
        logger.info("Starting pull_all_inboxes")

        # Legacy instance-level mailboxes are optional. A completely empty
        # slot is the normal fresh-install state and must not emit a warning on
        # every beat interval. Partially configured slots still flow through
        # validation so operators get an actionable warning.
        deadline = time.monotonic() + POLL_BUDGET_SECONDS
        reconcile_imap_intakes(limit=POLL_BATCH_SIZE)
        legacy_deadline = min(deadline, time.monotonic() + 60)
        for mailbox in (
            {
                "mailbox_key": "imap1",
                "host": settings.imap1_host,
                "port": settings.imap1_port,
                "username": settings.imap1_username,
                "password": settings.imap1_password,
                "use_ssl": settings.imap1_ssl,
                "delete_after_process": settings.imap1_delete_after_process,
            },
            {
                "mailbox_key": "imap2",
                "host": settings.imap2_host,
                "port": settings.imap2_port,
                "username": settings.imap2_username,
                "password": settings.imap2_password,
                "use_ssl": settings.imap2_ssl,
                "delete_after_process": settings.imap2_delete_after_process,
            },
        ):
            if any(mailbox[field] for field in ("host", "username", "password")):
                if _legacy_mailbox_has_owned_integration(mailbox["host"], mailbox["port"], mailbox["username"]):
                    logger.info(
                        "Skipping legacy mailbox %s; an owned IMAP integration covers it.", mailbox["mailbox_key"]
                    )
                    continue
                try:
                    check_and_pull_mailbox(**mailbox, deadline=min(legacy_deadline, time.monotonic() + 30))
                except SoftTimeLimitExceeded:
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.error("Error polling mailbox %s: %s", mailbox["mailbox_key"], type(exc).__name__)
            else:
                logger.debug("Mailbox %s is not configured; skipping silently.", mailbox["mailbox_key"])

        # Per-user IMAP accounts from the database
        _pull_user_imap_accounts(deadline=min(deadline, time.monotonic() + 60))

        # Per-user IMAP integrations from the UserIntegration model
        _pull_user_integration_imap(deadline=deadline)

        logger.info("Finished pull_all_inboxes")

    finally:
        release_lock(lock_token)


def _rotate_accounts(accounts, kind):
    """Persistently rotate the first account so a slow source cannot starve peers."""
    if len(accounts) < 2:
        return accounts
    offset = (int(redis_client.incr(f"docuelevate:imap:rotation:{kind}")) - 1) % len(accounts)
    return accounts[offset:] + accounts[:offset]


def _account_identity(host, port, username):
    return (str(host or "").strip().lower().rstrip("."), int(port or 993), str(username or "").strip())


def _pull_user_imap_accounts(*, deadline=None) -> None:
    """Iterate over all active per-user IMAP accounts and pull their inboxes."""
    try:
        from app.models import UserImapAccount

        db = _get_db_session()
        try:
            accounts = db.query(UserImapAccount).filter(UserImapAccount.is_active.is_(True)).all()
            logger.info("Processing %d per-user IMAP account(s)", len(accounts))
            for acct in _rotate_accounts(accounts, "accounts"):
                if deadline is not None and time.monotonic() >= deadline:
                    break
                if _legacy_mailbox_has_owned_integration(acct.host, acct.port, acct.username, owner_id=acct.owner_id):
                    continue
                # Use a descriptive identifier for logging and processed-email cache keys
                account_identifier = f"user_{acct.owner_id}_{acct.id}"
                try:
                    poll_ok = pull_inbox(
                        mailbox_key=account_identifier,
                        host=acct.host,
                        port=acct.port,
                        username=acct.username,
                        password=_decrypt_imap_password(acct.password),
                        use_ssl=acct.use_ssl,
                        delete_after_process=acct.delete_after_process,
                        owner_id=acct.owner_id,
                        allowed_categories=_resolve_categories_for_profile(acct.profile_id),
                        deadline=min(deadline, time.monotonic() + 45) if deadline else None,
                    )
                    if poll_ok is not True:
                        raise RuntimeError("IMAP poll did not complete successfully")
                    # Record successful poll
                    acct.last_checked_at = datetime.now(timezone.utc)
                    acct.last_error = None
                    db.commit()
                    record_poll_success(account_identifier)
                except SoftTimeLimitExceeded:
                    raise
                except Exception as exc:  # noqa: BLE001
                    error_msg = str(exc)[:_MAX_ERROR_LENGTH]
                    logger.error(
                        "Error pulling user IMAP account %d (%s@%s): %s",
                        acct.id,
                        acct.username,
                        acct.host,
                        error_msg,
                    )
                    try:
                        acct.last_checked_at = datetime.now(timezone.utc)
                        acct.last_error = error_msg
                        db.commit()
                    except Exception:  # noqa: BLE001
                        db.rollback()
        finally:
            db.close()
    except SoftTimeLimitExceeded:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to process per-user IMAP accounts: %s", exc)


def _legacy_mailbox_has_owned_integration(host, port, username, owner_id=None) -> bool:
    """Prevent legacy env mailboxes from ingesting the same account as owner None."""
    try:
        from app.models import IntegrationDirection, IntegrationType, UserImapAccount, UserIntegration

        db = _get_db_session()
        try:
            for integ in (
                db.query(UserIntegration)
                .filter(
                    UserIntegration.integration_type == IntegrationType.IMAP,
                    UserIntegration.direction == IntegrationDirection.SOURCE,
                    UserIntegration.is_active.is_(True),
                )
                .all()
            ):
                if owner_id is not None and integ.owner_id != owner_id:
                    continue
                try:
                    cfg = json.loads(integ.config) if integ.config else {}
                    if _account_identity(cfg.get("host"), cfg.get("port"), cfg.get("username")) == _account_identity(
                        host, port, username
                    ):
                        return True
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
            if owner_id is None:
                for acct in db.query(UserImapAccount).filter(UserImapAccount.is_active.is_(True)).all():
                    if _account_identity(acct.host, acct.port, acct.username) == _account_identity(
                        host, port, username
                    ):
                        return True
        finally:
            db.close()
    except SoftTimeLimitExceeded:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not check legacy IMAP ownership: %s", exc)
        # Do not fall back to ownerless ingestion when the ownership check fails.
        raise
    return False


def _pull_user_integration_imap(*, deadline=None) -> None:
    """Iterate over all active IMAP UserIntegrations and pull their inboxes.

    This polls the ``user_integrations`` table for records with
    ``integration_type='IMAP'``, ``direction='SOURCE'``, and ``is_active=True``.
    Each integration's config/credentials are decoded and passed to
    :func:`pull_inbox` with the owning user's ``owner_id`` so that ingested
    documents are correctly attributed.

    Individual connection failures are caught and recorded on the integration
    without crashing the polling loop.
    """
    try:
        import json as _json

        from app.models import IntegrationDirection, IntegrationType, UserIntegration
        from app.utils.encryption import decrypt_value

        db = _get_db_session()
        try:
            integrations = (
                db.query(UserIntegration)
                .filter(
                    UserIntegration.integration_type == IntegrationType.IMAP,
                    UserIntegration.direction == IntegrationDirection.SOURCE,
                    UserIntegration.is_active.is_(True),
                )
                .all()
            )
            logger.info("Processing %d IMAP UserIntegration(s)", len(integrations))
            for integ in _rotate_accounts(integrations, "integrations"):
                if deadline is not None and time.monotonic() >= deadline:
                    break
                account_identifier = f"integration_{integ.owner_id}_{integ.id}"
                try:
                    cfg = _json.loads(integ.config) if integ.config else {}
                    raw_creds = decrypt_value(integ.credentials) if integ.credentials else None
                    creds = _json.loads(raw_creds) if raw_creds else {}

                    host = cfg.get("host")
                    port = int(cfg.get("port", 993))
                    username = cfg.get("username")
                    password = creds.get("password")
                    use_ssl = cfg.get("use_ssl", True)
                    delete_after = cfg.get("delete_after_process", False)
                    gmail_labels = cfg.get("gmail_apply_labels", True)
                    # Integrations can store a profile_id in config; fall back to global default
                    profile_id = cfg.get("profile_id")
                    allowed_categories = _resolve_categories_for_profile(profile_id)

                    if not (host and username and password):
                        logger.warning(
                            "IMAP integration %d (owner %s) has incomplete config — skipping.",
                            integ.id,
                            integ.owner_id,
                        )
                        continue

                    poll_ok = pull_inbox(
                        mailbox_key=account_identifier,
                        host=host,
                        port=port,
                        username=username,
                        password=password,
                        use_ssl=use_ssl,
                        delete_after_process=delete_after,
                        owner_id=integ.owner_id,
                        source_integration_id=integ.id,
                        gmail_apply_labels=gmail_labels,
                        allowed_categories=allowed_categories,
                        deadline=min(deadline, time.monotonic() + 60) if deadline else None,
                    )
                    if poll_ok is not True:
                        raise RuntimeError("IMAP poll did not complete successfully")
                    integ.last_used_at = datetime.now(timezone.utc)
                    integ.last_error = None
                    db.commit()
                    record_poll_success(account_identifier)
                except SoftTimeLimitExceeded:
                    raise
                except Exception as exc:  # noqa: BLE001
                    error_msg = str(exc)[:_MAX_ERROR_LENGTH]
                    logger.error(
                        "Error pulling IMAP integration %d (owner %s): %s",
                        integ.id,
                        integ.owner_id,
                        error_msg,
                    )
                    try:
                        integ.last_used_at = datetime.now(timezone.utc)
                        integ.last_error = error_msg
                        db.commit()
                    except Exception:  # noqa: BLE001
                        db.rollback()
        finally:
            db.close()
    except SoftTimeLimitExceeded:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to process IMAP UserIntegrations: %s", exc)


def check_and_pull_mailbox(
    mailbox_key: str,
    host: str | None,
    port: int | None,
    username: str | None,
    password: str | None,
    use_ssl: bool,
    delete_after_process: bool,
    deadline: float | None = None,
):
    """Validates config and invokes pulling from the mailbox if valid."""
    if not (host and port and username and password):
        logger.warning(f"Mailbox {mailbox_key} is missing config, skipping.")
        return False

    logger.info(f"Checking mailbox: {mailbox_key}")
    succeeded = pull_inbox(
        mailbox_key=mailbox_key,
        host=host,
        port=port,
        username=username,
        password=password,
        use_ssl=use_ssl,
        delete_after_process=delete_after_process,
        deadline=deadline,
    )
    if succeeded is True:
        record_poll_success(mailbox_key)
    return succeeded


def _ledger_get_or_create(owner_key, mailbox_key, uidvalidity, uid):
    from app.models import ImapMessageLedger

    db = _get_db_session()
    try:
        row = (
            db.query(ImapMessageLedger)
            .filter_by(
                owner_key=owner_key,
                mailbox_key=mailbox_key,
                uidvalidity=str(uidvalidity),
                uid=int(uid),
            )
            .first()
        )
        if row is None:
            row = ImapMessageLedger(
                owner_key=owner_key,
                mailbox_key=mailbox_key,
                uidvalidity=str(uidvalidity),
                uid=int(uid),
                state="pending",
            )
            db.add(row)
            db.flush()
        if row.state == "completed":
            return None
        row.attempts = (row.attempts or 0) + 1
        row.state = "processing"
        row.last_error = None
        db.commit()
        ledger_id = row.id
        return ledger_id
    finally:
        db.close()


def _ledger_is_completed(owner_key, mailbox_key, uidvalidity, uid):
    from app.models import ImapMessageLedger

    db = _get_db_session()
    try:
        return (
            db.query(ImapMessageLedger.id)
            .filter_by(
                owner_key=owner_key,
                mailbox_key=mailbox_key,
                uidvalidity=str(uidvalidity),
                uid=int(uid),
                state="completed",
            )
            .first()
            is not None
        )
    finally:
        db.close()


def _ledger_finish(ledger_id, *, state, message_id=None, error=None):
    from app.models import ImapMessageLedger

    db = _get_db_session()
    try:
        row = db.query(ImapMessageLedger).filter(ImapMessageLedger.id == ledger_id).first()
        if row:
            row.state = state
            if message_id:
                row.message_id = message_id[:998]
            row.last_error = str(error)[:_MAX_ERROR_LENGTH] if error else None
            db.commit()
    finally:
        db.close()


def _extract_uidvalidity(mail, select_data=None) -> str:
    """Read UIDVALIDITY; refuse ingestion when a server omits it."""
    def valid_value(value):
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, bytes):
            try:
                value = value.decode("ascii")
            except UnicodeDecodeError:
                return None
        if isinstance(value, int):
            number = value
        else:
            value = str(value).strip()
            if not value or any(char not in "0123456789" for char in value):
                return None
            number = int(value)
        if number <= 0 or number > 4_294_967_295:
            return None
        return str(number)

    try:
        response = mail.response("UIDVALIDITY")
        values = response[1] if response and len(response) > 1 else []
        if isinstance(values, (bytes, str)):
            values = [values]
        if values:
            value = valid_value(values[0])
            if value is not None:
                return value
    except SoftTimeLimitExceeded:
        raise
    except Exception:  # noqa: BLE001
        logger.warning("Could not read IMAP UIDVALIDITY response")
    if select_data and isinstance(select_data, dict):
        for key in (b"UIDVALIDITY", "UIDVALIDITY"):
            if key in select_data:
                value = select_data[key]
                if isinstance(value, (list, tuple)):
                    if not value:
                        continue
                    value = value[0]
                value = valid_value(value)
                if value is not None:
                    return value
    return "unknown"


def pull_inbox(
    mailbox_key,
    host,
    port,
    username,
    password,
    use_ssl,
    delete_after_process,
    owner_id=None,
    source_integration_id=None,
    gmail_apply_labels=True,
    allowed_categories=None,
    deadline=None,
):
    """
    Connects to the configured mailbox and fetches all messages incrementally,
    and processes attachments while preserving the original unread status.

    Gmail uses the localized All Mail folder, other servers use INBOX.
    Both use ALL UIDs, independent of message dates and read flags.

    Args:
        owner_id: Optional user identifier. When provided, ingested documents are
                  attributed to this user via ``process_document`` / ``convert_to_pdf``.
        gmail_apply_labels: Whether to apply Gmail-specific labels and stars to
                  processed emails. Only relevant for Gmail hosts. Defaults to True.
        allowed_categories: List of file-type category keys to ingest (e.g.
                  ``["pdf", "office", "images"]``).  ``None`` falls back to the
                  global ``settings.imap_attachment_filter`` mapping.
    """
    if allowed_categories is None:
        allowed_categories = _resolve_categories_for_profile(None)
    deadline = deadline or (time.monotonic() + POLL_BUDGET_SECONDS)
    if time.monotonic() >= deadline:
        logger.warning("IMAP poll budget exhausted before connecting to %s", mailbox_key)
        return False

    effective_mime_types, effective_extensions = get_allowed_types_for_categories(allowed_categories)
    logger.info(
        "Connecting to %s at %s:%s (SSL=%s) — categories: %s",
        mailbox_key,
        host,
        port,
        use_ssl,
        allowed_categories,
    )
    # Security: Prevent SSRF by blocking connections to internal IPs
    if is_private_ip(host):
        logger.warning("SSRF blocked: Attempt to pull mailbox from private IP %s", host)
        return

    mail = None
    completed = False
    try:
        mail = (
            imaplib.IMAP4_SSL(host, port, timeout=IMAP_SOCKET_TIMEOUT_SECONDS)
            if use_ssl
            else imaplib.IMAP4(host, port, timeout=IMAP_SOCKET_TIMEOUT_SECONDS)
        )
        mail.login(username, password)

        is_gmail_host = "gmail" in host.lower()
        if is_gmail_host:
            # For Gmail, try to select the localized All Mail folder.
            all_mail_folder = find_all_mail_folder(mail)
            if all_mail_folder:
                logger.info("Using Gmail All Mail folder: %s", all_mail_folder)
                selected_folder = all_mail_folder
                select_status, select_data = mail.select(
                    f'"{all_mail_folder}"',
                    readonly=settings.imap_readonly_mode or not (delete_after_process or gmail_apply_labels),
                )
            else:
                logger.warning("Gmail All Mail folder not found, falling back to INBOX.")
                selected_folder = "INBOX"
                select_status, select_data = mail.select(
                    "INBOX", readonly=settings.imap_readonly_mode or not (delete_after_process or gmail_apply_labels)
                )
            if select_status != "OK":
                logger.warning("Mailbox %s select failed. Status=%s", mailbox_key, select_status)
                return False
            status, search_data = mail.uid("search", None, "ALL")
        else:
            # Read-only INBOX/ALL scan: do not depend on Seen state or dates.
            selected_folder = "INBOX"
            select_status, select_data = mail.select(
                "INBOX", readonly=settings.imap_readonly_mode or not delete_after_process
            )
            if select_status != "OK":
                logger.warning("Mailbox %s select failed. Status=%s", mailbox_key, select_status)
                return False
            status, search_data = mail.uid("search", None, "ALL")

        if status != "OK":
            logger.warning("Search failed on mailbox %s. Status=%s", mailbox_key, status)
            mail.close()
            mail.logout()
            return False

        msg_numbers = search_data[0].split()
        uidvalidity = _extract_uidvalidity(mail, select_data)
        if uidvalidity == "unknown":
            logger.error("Mailbox %s did not provide UIDVALIDITY; refusing unsafe scan", mailbox_key)
            return False
        identity = json.dumps(
            [str(owner_id or ""), host.strip().lower().rstrip("."), int(port), username.strip(), selected_folder],
            ensure_ascii=False,
        )
        account_hash = hashlib.sha256(identity.encode()).hexdigest()
        owner_key = str(owner_id or "legacy")
        mailbox_key = account_hash
        from app.models import ImapScanCursor

        db = _get_db_session()
        try:
            scan_cursor = (
                db.query(ImapScanCursor).filter_by(mailbox_key=account_hash, uidvalidity=str(uidvalidity)).first()
            )
            cursor = scan_cursor.last_uid if scan_cursor else 0
        finally:
            db.close()
        ordered = sorted(int(value) for value in msg_numbers)
        from app.models import ImapMessageLedger

        db = _get_db_session()
        try:
            completed_uids = {
                row[0]
                for row in db.query(ImapMessageLedger.uid)
                .filter_by(
                    owner_key=owner_key, mailbox_key=mailbox_key, uidvalidity=str(uidvalidity), state="completed"
                )
                .all()
            }
            retry_rows = (
                db.query(ImapMessageLedger.uid)
                .filter_by(owner_key=owner_key, mailbox_key=mailbox_key, uidvalidity=str(uidvalidity))
                .filter(ImapMessageLedger.state != "completed")
                .order_by(ImapMessageLedger.updated_at.asc())
                .all()
            )
            retry_order = [row[0] for row in retry_rows]
        finally:
            db.close()
        unfinished = [uid for uid in ordered if uid not in completed_uids]
        new_uids = [uid for uid in unfinished if uid > cursor]
        retry_uids = [uid for uid in unfinished if uid <= cursor]
        retry_rank = {uid: index for index, uid in enumerate(retry_order)}
        retry_uids.sort(key=lambda uid: (retry_rank.get(uid, len(retry_rank)), uid))
        if new_uids and retry_uids:
            retry_slots = min(len(retry_uids), max(1, POLL_BATCH_SIZE // 5))
            selected_uids = retry_uids[:retry_slots] + new_uids[: POLL_BATCH_SIZE - retry_slots]
            if len(selected_uids) < POLL_BATCH_SIZE:
                selected_uids += retry_uids[retry_slots : retry_slots + POLL_BATCH_SIZE - len(selected_uids)]
        elif retry_uids:
            selected_uids = retry_uids[:POLL_BATCH_SIZE]
        else:
            selected_uids = unfinished[:POLL_BATCH_SIZE]
        msg_numbers = [str(uid).encode() for uid in selected_uids]
        had_failure = False
        deleted_any = False

        for num in msg_numbers:
            if time.monotonic() >= deadline:
                break
            uid = int(num)
            db = _get_db_session()
            try:
                scan_cursor = (
                    db.query(ImapScanCursor).filter_by(mailbox_key=account_hash, uidvalidity=str(uidvalidity)).first()
                )
                if scan_cursor is None:
                    scan_cursor = ImapScanCursor(mailbox_key=account_hash, uidvalidity=str(uidvalidity))
                    db.add(scan_cursor)
                if uid > cursor:
                    scan_cursor.last_uid = uid
                db.commit()
            finally:
                db.close()
            ledger_id = _ledger_get_or_create(owner_key, mailbox_key, uidvalidity, uid)
            if ledger_id is None:
                continue
            status, msg_data = mail.uid("fetch", num, "(BODY.PEEK[])")
            if status != "OK":
                logger.warning("Failed to fetch message %s in %s. Status=%s", num, mailbox_key, status)
                had_failure = True
                _ledger_finish(ledger_id, state="failed", error=f"fetch status {status}")
                continue

            raw_email = next((item[1] for item in msg_data if isinstance(item, tuple) and len(item) > 1), None)
            if not raw_email:
                had_failure = True
                _ledger_finish(ledger_id, state="failed", error="empty fetch response")
                continue
            email_message = email.message_from_bytes(raw_email)
            msg_id = email_message.get("Message-ID")

            if not msg_id:
                msg_id = f"<imap-uid-{uidvalidity}-{uid}@{mailbox_key}>"
                logger.info("Message %s has no Message-ID; using UID identity", uid)

            # Process attachments using the resolved mime types / extensions.
            try:
                accepted = fetch_attachments_and_enqueue(
                    email_message,
                    owner_id=owner_id,
                    source_integration_id=source_integration_id,
                    effective_mime_types=effective_mime_types,
                    effective_extensions=effective_extensions,
                    ingestion_prefix=f"{owner_key}:{mailbox_key}:{uidvalidity}:{uid}",
                )
                _ledger_finish(ledger_id, state="completed", message_id=msg_id)
            except SoftTimeLimitExceeded:
                raise
            except Exception as exc:  # noqa: BLE001
                had_failure = True
                logger.exception("Attachment handoff failed for %s", msg_id)
                _ledger_finish(ledger_id, state="failed", message_id=msg_id, error=exc)
                continue

            if not accepted:
                _ledger_finish(ledger_id, state="completed", message_id=msg_id)
                continue

            if settings.imap_readonly_mode:
                logger.info("Readonly mode: skipping mailbox modifications for %s in %s", msg_id, mailbox_key)
            else:
                if is_gmail_host and gmail_apply_labels:
                    mark_as_processed_with_star(mail, num)
                    mark_as_processed_with_label(mail, num, label="Ingested")

                if delete_after_process:
                    logger.info("Deleting message %s from %s", num.decode(), mailbox_key)
                    # Deletion remains an explicit mailbox setting.  Normal
                    # ingestion never changes Seen state (BODY.PEEK above).
                    delete_status, _ = mail.uid("store", num, "+FLAGS", "\\Deleted")
                    if delete_status == "OK":
                        deleted_any = True

        if not settings.imap_readonly_mode and delete_after_process and deleted_any:
            mail.expunge()

        mail.close()
        mail.logout()
        completed = True
        logger.info("Finished processing mailbox %s", mailbox_key)
        return not had_failure

    except SoftTimeLimitExceeded:
        raise
    except Exception as e:
        logger.exception("Error pulling mailbox %s: %s", mailbox_key, e)
        return False
    finally:
        if mail is not None and not completed:
            _shutdown_imap_connection(mail)


def fetch_attachments_and_enqueue(
    email_message,
    owner_id: str | None = None,
    source_integration_id: int | None = None,
    effective_mime_types: frozenset[str] | None = None,
    effective_extensions: frozenset[str] | None = None,
    ingestion_prefix: str | None = None,
):
    """
    Extracts attachments from the email and processes only allowed file types.

    The caller is responsible for computing ``effective_mime_types`` and
    ``effective_extensions`` from the relevant :class:`ImapIngestionProfile` (or
    the global default) via :func:`app.utils.allowed_types.get_allowed_types_for_categories`
    before calling this function.  ``pull_inbox`` does this automatically.

    If either set is ``None`` the function falls back to the default category list
    so the function still works correctly when called directly in tests or from
    other contexts.

    If the attachment is a PDF (by extension or MIME type), it is enqueued for upload;
    any other allowed file is enqueued for conversion to PDF.

    Args:
        email_message: The parsed email message to extract attachments from.
        owner_id: Optional user identifier forwarded to ``process_document`` /
                  ``convert_to_pdf`` for multi-tenant attribution.
        effective_mime_types: Pre-computed frozenset of allowed MIME type strings.
        effective_extensions: Pre-computed frozenset of allowed file extension strings.

    Returns True if at least one allowed attachment was processed.
    """
    if effective_mime_types is None or effective_extensions is None:
        effective_mime_types, effective_extensions = get_allowed_types_for_categories(DEFAULT_CATEGORIES)

    has_attachment = False
    for part_index, part in enumerate(email_message.walk()):
        if part.get_content_maintype() == "multipart":
            continue

        filename = part.get_filename()
        if not filename:
            continue

        # Check if it's a PDF file by extension, regardless of MIME type
        is_pdf_by_extension = filename.lower().endswith(".pdf")

        mime_type = part.get_content_type()
        file_ext = os.path.splitext(filename)[1].lower()

        # Accept file if it has an allowed MIME type, an allowed extension, OR is a PDF by extension
        if mime_type not in effective_mime_types and file_ext not in effective_extensions and not is_pdf_by_extension:
            logger.info(
                "Skipping attachment %s (MIME: %s, ext: %s) — not in effective allowed set",
                filename,
                mime_type,
                file_ext,
            )
            continue

        # Attachment names are untrusted.  Keep the original name for the
        # document record while writing only a basename inside the workdir.
        safe_filename = os.path.basename(filename.replace("\\", "/"))
        if safe_filename in {"", ".", ".."}:
            logger.warning("Skipping unsafe attachment filename %r", filename)
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            raise ValueError("Attachment payload could not be decoded")
        if ingestion_prefix:
            from app.tasks.imap_intake import prepare_imap_attachment

            digest = hashlib.sha256(payload).hexdigest()
            prepare_imap_attachment(
                owner_id=owner_id,
                source_integration_id=source_integration_id,
                idempotency_key=f"{ingestion_prefix}:{part_index}:{digest}",
                filename=safe_filename,
                payload=payload,
                mime_type=mime_type,
                is_pdf=mime_type == "application/pdf" or is_pdf_by_extension,
            )
        else:
            # Direct callers also need collision-free paths; scheduled imports
            # always use the durable intake path above.
            os.makedirs(settings.workdir, exist_ok=True)
            fd, file_path = tempfile.mkstemp(prefix="imap-", suffix=file_ext, dir=settings.workdir)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
            task = process_document if mime_type == "application/pdf" or is_pdf_by_extension else convert_to_pdf
            task.delay(
                file_path,
                original_filename=safe_filename,
                owner_id=owner_id,
                source_integration_id=source_integration_id,
            )
        has_attachment = True
    return has_attachment


def email_already_has_label(mail, msg_id, label="Ingested"):
    """
    Checks if the given message (msg_id) has the specified Gmail label.
    Returns True if the label is found, False otherwise.
    """
    try:
        # Convert msg_id to bytes if it's an integer
        if isinstance(msg_id, int):
            msg_id = str(msg_id).encode()

        label_status, label_data = mail.uid("fetch", msg_id, "(X-GM-LABELS)")
        if label_status == "OK" and label_data and len(label_data) > 0:
            raw_labels = label_data[0][1].decode("utf-8", errors="ignore")
            if label in raw_labels:
                return True
    except Exception as e:
        logger.error("Failed to fetch labels for msg_id=%s: %s", msg_id, e)
    return False


def mark_as_processed_with_star(mail, msg_id):
    """Stars the email in Gmail."""
    try:
        mail.uid("store", msg_id, "+FLAGS", "\\Flagged")
        logger.info("Email %s starred in Gmail.", msg_id)
    except Exception as e:
        logger.error("Failed to star email %s: %s", msg_id, e)


def mark_as_processed_with_label(mail, msg_id, label="Ingested"):
    """Adds a custom label to the email in Gmail."""
    try:
        mail.uid("store", msg_id, "+X-GM-LABELS", label)
        logger.info("Email %s labeled '%s' in Gmail.", msg_id, label)
    except Exception as e:
        logger.error("Failed to label email %s with %s: %s", msg_id, label, e)


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
    command_str = f'{tag} XLIST "" "*"'
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
                logger.info("Found All Mail folder via XLIST: %s", candidate)
                all_mail_folder = candidate
        if line_str.startswith(tag):
            break
    return all_mail_folder
