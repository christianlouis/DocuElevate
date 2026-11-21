"""Bounded, lease-fenced IMAP payload downloading for the pipeline.

The scanner owns discovery and the outbox owns scheduling.  This module only
consumes the explicitly claimed ledger ids, validates the claim and account at
execution time, then stages attachments through the established IMAP intake
helper.
"""

from __future__ import annotations

import email
import hashlib
import imaplib
import json
import logging
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, update

from app.config import settings
from app.database import SessionLocal
from app.models import ImapMessageLedger, UserImapAccount, UserIntegration
from app.tasks.imap_tasks import (
    _decrypt_imap_password,
    _extract_uidvalidity,
    _resolve_categories_for_profile,
    fetch_attachments_and_enqueue,
    find_all_mail_folder,
    mark_as_processed_with_label,
    mark_as_processed_with_star,
)
from app.utils.allowed_types import get_allowed_types_for_categories
from app.utils.imap import IMAP_SOCKET_TIMEOUT_SECONDS, _shutdown_imap_connection
from app.utils.network import is_private_ip

logger = logging.getLogger(__name__)

MIN_WORKDIR_FREE_BYTES = 5 * 1024**3
DOWNLOAD_LEASE_SECONDS = 900
DOWNLOAD_SOFT_DEADLINE_SECONDS = 180
DOWNLOAD_HARD_DEADLINE_SECONDS = 270
_CLAIM_LOCKS: dict[str, threading.Lock] = {}
_CLAIM_LOCKS_GUARD = threading.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _lock_for(token: str) -> threading.Lock:
    with _CLAIM_LOCKS_GUARD:
        return _CLAIM_LOCKS.setdefault(token, threading.Lock())


def _set_state(row: ImapMessageLedger, state: str, *, error: str | None = None) -> None:
    row.state = state
    if error is not None:
        row.last_error = str(error)[:500]
    if hasattr(row, "discovery_state"):
        row.discovery_state = "completed" if state == "completed" else ("ready" if state == "retry_wait" else state)
    if state == "completed":
        row.is_candidate = False
        if hasattr(row, "downloaded_at"):
            row.downloaded_at = _utcnow()
    elif state == "retry_wait" and hasattr(row, "next_download_at"):
        row.next_download_at = _utcnow() + timedelta(seconds=60)
    row.download_lease_token = None
    row.download_lease_expires_at = None


def _account_from_ref(db, account_ref: str) -> dict[str, Any] | None:
    """Resolve current account configuration without exposing credentials."""
    if account_ref in {"imap1", "imap2"}:
        n = account_ref[-1]
        return {
            "owner_id": None,
            "host": getattr(settings, f"imap{n}_host", None),
            "port": getattr(settings, f"imap{n}_port", 993),
            "username": getattr(settings, f"imap{n}_username", None),
            "password": getattr(settings, f"imap{n}_password", None),
            "use_ssl": getattr(settings, f"imap{n}_ssl", True),
            "delete_after_process": getattr(settings, f"imap{n}_delete_after_process", False),
            "profile_id": None,
            "source_integration_id": None,
        }
    if account_ref.startswith("user_"):
        try:
            _, owner, ident = account_ref.split("_", 2)
            account = db.query(UserImapAccount).filter(UserImapAccount.id == int(ident)).first()
        except (ValueError, TypeError):
            account = None
        if account is None or not account.is_active:
            return None
        return {
            "owner_id": account.owner_id,
            "host": account.host,
            "port": account.port,
            "username": account.username,
            "password": _decrypt_imap_password(account.password),
            "use_ssl": account.use_ssl,
            "delete_after_process": account.delete_after_process,
            "profile_id": account.profile_id,
            "source_integration_id": None,
        }
    if account_ref.startswith("integration_"):
        try:
            ident = int(account_ref.rsplit("_", 1)[1])
        except (ValueError, IndexError):
            return None
        account = db.query(UserIntegration).filter(UserIntegration.id == ident).first()
        if account is None or not account.is_active:
            return None
        try:
            config = json.loads(account.config or "{}")
            from app.utils.encryption import decrypt_value

            credentials = json.loads(decrypt_value(account.credentials) or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return {
            "owner_id": account.owner_id,
            "host": config.get("host"),
            "port": int(config.get("port", 993)),
            "username": config.get("username"),
            "password": credentials.get("password"),
            "use_ssl": config.get("use_ssl", True),
            "delete_after_process": config.get("delete_after_process", False),
            "gmail_apply_labels": config.get("gmail_apply_labels", True),
            "profile_id": config.get("profile_id"),
            "source_integration_id": account.id,
        }
    return None


def _owner_is_active(db, owner_id: str | None) -> bool:
    if not owner_id:
        return True
    try:
        from app.services.account_deletion import assert_account_active

        assert_account_active(db, str(owner_id))
    except Exception as exc:  # noqa: BLE001
        if type(exc).__name__ == "DeletionBlocked":
            return False
        raise
    return True


def _mailbox_key(owner_id: str | None, host: str, port: int, username: str, folder: str) -> str:
    identity = json.dumps(
        [str(owner_id or ""), host.strip().lower().rstrip("."), int(port), username.strip(), folder],
        ensure_ascii=False,
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def _free_space_ok() -> bool:
    try:
        return shutil.disk_usage(settings.workdir).free >= MIN_WORKDIR_FREE_BYTES
    except OSError:
        return False


def _claim_rows(db, account_ref: str, lane: str, ids: list[int], token: str) -> list[ImapMessageLedger]:
    now = _utcnow()
    exact_ids = list(dict.fromkeys(int(i) for i in ids))
    predicates = [
        ImapMessageLedger.id.in_(exact_ids),
        ImapMessageLedger.account_ref == account_ref,
        ImapMessageLedger.lane == lane,
        ImapMessageLedger.download_lease_token == token,
        ImapMessageLedger.download_lease_expires_at > now,
        ImapMessageLedger.is_candidate.is_(True),
        # The scanner's claim transition is the durable execution fence.
        ImapMessageLedger.discovery_state == "claimed",
    ]
    # UPDATE is the cross-process CAS.  A process-local lock alone cannot
    # prevent two pods from staging the same valid token concurrently.
    changed = db.execute(
        update(ImapMessageLedger)
        .where(and_(*predicates))
        .values(state="downloading", discovery_state="downloading")
    ).rowcount
    if changed != len(exact_ids):
        db.rollback()
        return []
    rows = db.query(ImapMessageLedger).filter(ImapMessageLedger.id.in_(exact_ids)).order_by(ImapMessageLedger.id).all()
    db.commit()
    return rows


def download_claimed_batch(account_ref: str, lane: str, ledger_ids: list[int], claim_token: str) -> dict[str, int | str]:
    """Download exactly one durable claim; stale claims perform no network I/O."""
    stats: dict[str, int | str] = {"downloaded": 0, "failed": 0, "deferred": 0, "lane": lane}
    if not ledger_ids or not claim_token:
        return stats
    lock = _lock_for(f"{account_ref}:{lane}:{claim_token}")
    if not lock.acquire(blocking=False):
        stats["deferred"] = len(ledger_ids)
        return stats
    mail = None
    started = time.monotonic()
    deadline = started + DOWNLOAD_SOFT_DEADLINE_SECONDS
    db = SessionLocal()
    rows: list[ImapMessageLedger] = []
    try:
        # Claim validity and CAS happen before account lookup or any network work.
        rows = _claim_rows(db, account_ref, lane, ledger_ids, claim_token)
        if not rows:
            stats["deferred"] = len(ledger_ids)
            return stats
        if not _free_space_ok():
            for row in rows:
                row.state = "retry_wait"
                if hasattr(row, "discovery_state"):
                    row.discovery_state = "ready"
                if hasattr(row, "next_download_at"):
                    row.next_download_at = _utcnow() + timedelta(seconds=60)
                row.download_lease_token = None
                row.download_lease_expires_at = None
            db.commit()
            stats["deferred"] = len(rows)
            return stats
        account = _account_from_ref(db, account_ref)
        if not account or not account.get("host") or not account.get("username") or not account.get("password"):
            for row in rows:
                _set_state(row, "retry_wait", error="source account unavailable or disabled")
            db.commit()
            stats["deferred"] = len(rows)
            return stats
        if not _owner_is_active(db, account.get("owner_id")):
            for row in rows:
                _set_state(row, "retry_wait", error="owner inactive")
            db.commit()
            stats["deferred"] = len(rows)
            return stats
        host, port = str(account["host"]), int(account.get("port") or 993)
        if is_private_ip(host):
            raise RuntimeError("IMAP host rejected")
        mail = imaplib.IMAP4_SSL(host, port, timeout=IMAP_SOCKET_TIMEOUT_SECONDS) if account.get("use_ssl", True) else imaplib.IMAP4(host, port, timeout=IMAP_SOCKET_TIMEOUT_SECONDS)
        mail.login(account["username"], account["password"])
        folder = find_all_mail_folder(mail) if "gmail" in host.lower() else "INBOX"
        folder = folder or "INBOX"
        is_gmail = "gmail" in host.lower()
        gmail_labels = bool(account.get("gmail_apply_labels", True))
        readonly = bool(settings.imap_readonly_mode or not (account.get("delete_after_process") or (is_gmail and gmail_labels)))
        status, select_data = mail.select(f'"{folder}"' if is_gmail else folder, readonly=readonly)
        if status != "OK":
            raise RuntimeError("mailbox select failed")
        uidvalidity = _extract_uidvalidity(mail, select_data)
        expected_key = _mailbox_key(account.get("owner_id"), host, port, account["username"], folder)
        if uidvalidity == "unknown" or any(r.mailbox_key != expected_key or str(r.uidvalidity) != str(uidvalidity) for r in rows):
            for row in rows:
                _set_state(row, "retry_wait", error="mailbox identity changed")
            db.commit()
            stats["deferred"] = len(rows)
            return stats
        categories = _resolve_categories_for_profile(account.get("profile_id"))
        mime_types, extensions = get_allowed_types_for_categories(categories)
        for row in rows:
            if time.monotonic() >= deadline or time.monotonic() - started >= DOWNLOAD_HARD_DEADLINE_SECONDS:
                _set_state(row, "retry_wait", error="download deadline")
                stats["deferred"] = int(stats["deferred"]) + 1
                continue
            try:
                fetch_status, data = mail.uid("fetch", str(row.uid), "(BODY.PEEK[])")
                raw = next((item[1] for item in data or [] if isinstance(item, tuple) and len(item) > 1), None)
                if fetch_status != "OK" or not raw:
                    search_status, search_data = mail.uid("search", None, "UID", f"{row.uid}:{row.uid}")
                    vanished = search_status == "OK" and isinstance(search_data, (list, tuple)) and search_data and search_data[0] == b""
                    _set_state(row, "vanished" if vanished else "retry_wait", error="UID vanished" if vanished else "fetch failed")
                    stats["deferred" if vanished else "failed"] = int(stats["deferred" if vanished else "failed"]) + 1
                    db.commit()
                    continue
                # Re-fence immediately before staging, after network I/O.
                fresh = db.query(ImapMessageLedger.id).filter(and_(ImapMessageLedger.id == row.id, ImapMessageLedger.download_lease_token == claim_token, ImapMessageLedger.download_lease_expires_at > _utcnow(), ImapMessageLedger.state == "downloading")).first()
                if fresh is None:
                    continue
                message = email.message_from_bytes(raw)
                msg_id = message.get("Message-ID") or f"<imap-uid-{uidvalidity}-{row.uid}@{row.mailbox_key}>"
                accepted = fetch_attachments_and_enqueue(message, owner_id=account.get("owner_id"), source_integration_id=account.get("source_integration_id"), effective_mime_types=mime_types, effective_extensions=extensions, ingestion_prefix=f"{row.owner_key}:{row.mailbox_key}:{row.uidvalidity}:{row.uid}", background=lane == "backlog")
                if accepted and not settings.imap_readonly_mode:
                    if is_gmail and gmail_labels:
                        mark_as_processed_with_star(mail, str(row.uid).encode())
                        mark_as_processed_with_label(mail, str(row.uid).encode(), label="Ingested")
                    if account.get("delete_after_process"):
                        mail.uid("store", str(row.uid), "+FLAGS", "\\Deleted")
                row.message_id = msg_id[:998]
                _set_state(row, "completed")
                stats["downloaded"] = int(stats["downloaded"]) + 1
            except Exception as exc:  # noqa: BLE001
                _set_state(row, "retry_wait", error=f"{type(exc).__name__}: {exc}")
                stats["failed"] = int(stats["failed"]) + 1
            db.commit()
        return stats
    except Exception as exc:  # noqa: BLE001
        for row in rows:
            if row.state == "downloading":
                _set_state(row, "retry_wait", error=f"{type(exc).__name__}: {exc}")
                stats["failed"] = int(stats["failed"]) + 1
        db.commit()
        return stats
    finally:
        if mail is not None:
            _shutdown_imap_connection(mail)
        db.close()
        lock.release()

