"""Bounded, lease-fenced IMAP payload downloading for the pipeline.

The scanner owns discovery and the outbox owns scheduling.  This module only
consumes the explicitly claimed ledger ids, validates the claim and account at
execution time, then stages attachments through the established IMAP intake
helper.
"""

from __future__ import annotations

import atexit
import email
import hashlib
import imaplib
import json
import logging
import shutil
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from celery.signals import worker_shutdown
from sqlalchemy import and_, update

from app.config import settings
from app.database import SessionLocal
from app.models import ImapMessageLedger, IntegrationDirection, IntegrationType, UserImapAccount, UserIntegration
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


@dataclass
class _CachedConnection:
    mail: imaplib.IMAP4
    fingerprint: str
    folder: str
    uidvalidity: str
    created_at: float
    last_used_at: float


_CONNECTION_CACHE: dict[str, _CachedConnection] = {}
_CONNECTION_CACHE_LOCK = threading.Lock()


def _connection_fingerprint(account: dict[str, Any], readonly: bool) -> str:
    # Keep credentials out of logs and cache keys while invalidating reuse when
    # the current password or mailbox settings change.
    secret = hashlib.sha256(str(account.get("password") or "").encode()).hexdigest()
    return hashlib.sha256(
        json.dumps(
            [account.get("host"), account.get("port"), account.get("username"), secret, account.get("use_ssl", True), readonly],
            sort_keys=True,
        ).encode()
    ).hexdigest()


def _close_connection(entry: _CachedConnection) -> None:
    try:
        _shutdown_imap_connection(entry.mail)
    except Exception:  # noqa: BLE001
        logger.debug("Failed to close cached IMAP connection", exc_info=True)


def _close_all_cached_connections(*_args, **_kwargs) -> None:
    with _CONNECTION_CACHE_LOCK:
        entries = list(_CONNECTION_CACHE.values())
        _CONNECTION_CACHE.clear()
    for entry in entries:
        _close_connection(entry)


atexit.register(_close_all_cached_connections)
worker_shutdown.connect(_close_all_cached_connections, weak=False)


def _touch_cached_connection(cache_key: str, mail: imaplib.IMAP4 | None) -> None:
    if mail is None:
        return
    with _CONNECTION_CACHE_LOCK:
        entry = _CONNECTION_CACHE.get(cache_key)
        if entry is not None and entry.mail is mail:
            entry.last_used_at = time.monotonic()


def _discard_cached_connection(cache_key: str, mail: imaplib.IMAP4 | None = None) -> None:
    with _CONNECTION_CACHE_LOCK:
        entry = _CONNECTION_CACHE.get(cache_key)
        if entry is None or (mail is not None and entry.mail is not mail):
            return
        _CONNECTION_CACHE.pop(cache_key, None)
    _close_connection(entry)


def _open_or_reuse_connection(
    account_ref: str, account: dict[str, Any], readonly: bool
) -> tuple[imaplib.IMAP4, str, str, str, bool]:
    """Return a bounded-lifetime connection and selected mailbox identity."""
    now = time.monotonic()
    fingerprint = _connection_fingerprint(account, readonly)
    cache_key = account_ref
    with _CONNECTION_CACHE_LOCK:
        entry = _CONNECTION_CACHE.get(cache_key)
        if entry and (
            entry.fingerprint != fingerprint
            or now - entry.created_at >= int(settings.imap_pipeline_connection_ttl_seconds)
            or now - entry.last_used_at >= int(settings.imap_pipeline_connection_idle_seconds)
        ):
            _CONNECTION_CACHE.pop(cache_key, None)
            stale_entry = entry
            entry = None
        else:
            stale_entry = None
    if stale_entry is not None:
        _close_connection(stale_entry)
    if entry is not None:
        try:
            entry.mail.noop()
            response = entry.mail.response("UIDVALIDITY")
            values = response[1] if isinstance(response, tuple) and len(response) > 1 else None
            if values and str(values[0]).strip("b'") != str(entry.uidvalidity):
                raise imaplib.IMAP4.error("cached mailbox identity changed")
            return entry.mail, entry.folder, entry.uidvalidity, cache_key, True
        except Exception:
            _discard_cached_connection(cache_key, entry.mail)

    host, port = str(account["host"]), int(account.get("port") or 993)
    mail = (
        imaplib.IMAP4_SSL(host, port, timeout=IMAP_SOCKET_TIMEOUT_SECONDS)
        if account.get("use_ssl", True)
        else imaplib.IMAP4(host, port, timeout=IMAP_SOCKET_TIMEOUT_SECONDS)
    )
    try:
        mail.login(account["username"], account["password"])
        folder = find_all_mail_folder(mail) if "gmail" in host.lower() else "INBOX"
        folder = folder or "INBOX"
        status, select_data = mail.select(f'"{folder}"' if "gmail" in host.lower() else folder, readonly=readonly)
        if status != "OK":
            raise imaplib.IMAP4.error("mailbox select failed")
        uidvalidity = _extract_uidvalidity(mail, select_data)
        entry = _CachedConnection(mail, fingerprint, folder, uidvalidity, now, now)
        with _CONNECTION_CACHE_LOCK:
            _CONNECTION_CACHE[cache_key] = entry
        return mail, folder, uidvalidity, cache_key, False
    except Exception:
        _shutdown_imap_connection(mail)
        raise


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _retry_delay_seconds(row: ImapMessageLedger) -> int:
    """Back off retryable source failures without starving other messages."""
    return min(60 * (2 ** min(int(row.download_attempts or 0), 6)), 3600)


def _finish_fenced(
    db,
    row: ImapMessageLedger,
    claim_token: str,
    outcome: str,
    *,
    error_type: str | None = None,
    message_id: str | None = None,
) -> bool:
    """Finish only the still-current lease; stale workers cannot overwrite it."""
    now = _utcnow()
    values: dict[str, Any] = {
        "download_lease_token": None,
        "download_lease_expires_at": None,
    }
    if outcome == "completed":
        values.update(
            state="completed",
            discovery_state="completed",
            is_candidate=False,
            downloaded_at=now,
            next_download_at=None,
            message_id=message_id,
            last_error=None,
        )
    elif outcome == "vanished":
        values.update(
            state="vanished",
            discovery_state="vanished",
            is_candidate=False,
            next_download_at=None,
            last_error=error_type,
        )
    elif outcome == "permanent_failure":
        values.update(
            state="failed",
            discovery_state="permanent_failure",
            is_candidate=False,
            next_download_at=None,
            last_error=error_type,
        )
    else:
        values.update(
            state="retry_wait",
            discovery_state="retry_wait",
            is_candidate=True,
            next_download_at=now + timedelta(seconds=_retry_delay_seconds(row)),
            last_error=error_type,
        )
    changed = db.execute(
        update(ImapMessageLedger)
        .where(
            ImapMessageLedger.id == row.id,
            ImapMessageLedger.download_lease_token == claim_token,
            ImapMessageLedger.download_lease_expires_at > now,
            ImapMessageLedger.discovery_state == "downloading",
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    ).rowcount
    if changed:
        db.commit()
        return True
    db.rollback()
    return False


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
            ident = int(account_ref.rsplit("_", 1)[1])
            account = db.query(UserImapAccount).filter(UserImapAccount.id == int(ident)).first()
        except (ValueError, TypeError, IndexError):
            account = None
        if account is None or not account.is_active or account_ref != f"user_{account.owner_id}_{account.id}":
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
        if (
            account is None
            or not account.is_active
            or account.direction != IntegrationDirection.SOURCE
            or account.integration_type != IntegrationType.IMAP
            or account_ref != f"integration_{account.owner_id}_{account.id}"
        ):
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
        .values(
            state="downloading",
            discovery_state="downloading",
            download_started_at=now,
            # A queued task may start shortly before its publisher lease
            # expires.  Renew before I/O, long enough for the worker limit.
            download_lease_expires_at=now
            + timedelta(seconds=max(DOWNLOAD_LEASE_SECONDS, int(settings.imap_pipeline_lease_seconds))),
        )
    ).rowcount
    if changed != len(exact_ids):
        db.rollback()
        return []
    rows = db.query(ImapMessageLedger).filter(ImapMessageLedger.id.in_(exact_ids)).order_by(ImapMessageLedger.id).all()
    db.commit()
    return rows


def _refill_lane(account_ref: str, lane: str) -> None:
    """Schedule a successor after a completed batch without relying on a tick."""
    try:
        from app.imap_pipeline import publish_candidate_batches

        publish_candidate_batches(account_ref, lane, limit=1)
    except Exception as exc:  # noqa: BLE001 - recovery tick will republish the durable claim
        logger.warning("IMAP download refill failed account=%s lane=%s: %s", account_ref, lane, type(exc).__name__)


def download_claimed_batch(
    account_ref: str, lane: str, ledger_ids: list[int], claim_token: str
) -> dict[str, int | str]:
    """Download exactly one durable claim; stale claims perform no network I/O."""
    stats: dict[str, int | str] = {"downloaded": 0, "failed": 0, "deferred": 0, "lane": lane}
    if not ledger_ids or not claim_token:
        return stats
    mail = None
    cache_key = account_ref
    keep_connection = False
    rows: list[ImapMessageLedger] = []
    deleted_any = False
    source_ready = False
    connection_reused = False
    setup_seconds = 0.0
    fetch_seconds = 0.0
    handoff_seconds = 0.0
    connection_broken = False
    started = time.monotonic()
    deadline = started + DOWNLOAD_SOFT_DEADLINE_SECONDS
    db = SessionLocal()
    try:
        rows = _claim_rows(db, account_ref, lane, ledger_ids, claim_token)
        if not rows:
            stats["deferred"] = len(ledger_ids)
            return stats
        if not _free_space_ok():
            for row in rows:
                _finish_fenced(db, row, claim_token, "retry_wait", error_type="WorkdirCapacity")
            stats["deferred"] = len(rows)
            return stats
        account = _account_from_ref(db, account_ref)
        if not account or not account.get("host") or not account.get("username") or not account.get("password"):
            for row in rows:
                _finish_fenced(db, row, claim_token, "retry_wait", error_type="SourceUnavailable")
            stats["deferred"] = len(rows)
            return stats
        owner_key = str(account.get("owner_id") or "legacy")
        if any(row.owner_key != owner_key for row in rows):
            for row in rows:
                _finish_fenced(db, row, claim_token, "permanent_failure", error_type="OwnerMismatch")
            stats["failed"] = len(rows)
            return stats
        if not _owner_is_active(db, account.get("owner_id")):
            for row in rows:
                _finish_fenced(db, row, claim_token, "retry_wait", error_type="OwnerInactive")
            stats["deferred"] = len(rows)
            return stats
        host = str(account["host"])
        if is_private_ip(host):
            raise RuntimeError("IMAP host rejected")
        is_gmail = "gmail" in host.lower()
        gmail_labels = bool(account.get("gmail_apply_labels", True))
        readonly = bool(
            settings.imap_readonly_mode or not (account.get("delete_after_process") or (is_gmail and gmail_labels))
        )
        setup_started = time.monotonic()
        mail, folder, uidvalidity, cache_key, connection_reused = _open_or_reuse_connection(account_ref, account, readonly)
        setup_seconds = time.monotonic() - setup_started
        keep_connection = True
        port = int(account.get("port") or 993)
        expected_key = _mailbox_key(account.get("owner_id"), host, port, account["username"], folder)
        if uidvalidity == "unknown" or any(
            row.mailbox_key != expected_key or str(row.uidvalidity) != str(uidvalidity) for row in rows
        ):
            _discard_cached_connection(cache_key, mail)
            keep_connection = False
            for row in rows:
                _finish_fenced(db, row, claim_token, "retry_wait", error_type="MailboxIdentityChanged")
            stats["deferred"] = len(rows)
            return stats
        categories = _resolve_categories_for_profile(account.get("profile_id"))
        mime_types, extensions = get_allowed_types_for_categories(categories)
        source_ready = True
        for row in rows:
            if connection_broken:
                if _finish_fenced(db, row, claim_token, "retry_wait", error_type="ConnectionLost"):
                    stats["deferred"] = int(stats["deferred"]) + 1
                continue
            if time.monotonic() >= deadline or time.monotonic() - started >= DOWNLOAD_HARD_DEADLINE_SECONDS:
                if _finish_fenced(db, row, claim_token, "retry_wait", error_type="DownloadDeadline"):
                    stats["deferred"] = int(stats["deferred"]) + 1
                continue
            if not _free_space_ok():
                if _finish_fenced(db, row, claim_token, "retry_wait", error_type="WorkdirCapacity"):
                    stats["deferred"] = int(stats["deferred"]) + 1
                continue
            try:
                fetch_started = time.monotonic()
                fetch_status, data = mail.uid("fetch", str(row.uid), "(BODY.PEEK[])")
                fetch_seconds += time.monotonic() - fetch_started
                raw = next((item[1] for item in data or [] if isinstance(item, tuple) and len(item) > 1), None)
                if fetch_status != "OK" or not raw:
                    search_status, search_data = mail.uid("search", None, "UID", f"{row.uid}:{row.uid}")
                    vanished = (
                        search_status == "OK"
                        and isinstance(search_data, (list, tuple))
                        and search_data
                        and search_data[0] == b""
                    )
                    if _finish_fenced(
                        db,
                        row,
                        claim_token,
                        "vanished" if vanished else "retry_wait",
                        error_type="UidVanished" if vanished else "FetchFailed",
                    ):
                        stats["deferred" if vanished else "failed"] = (
                            int(stats["deferred" if vanished else "failed"]) + 1
                        )
                    continue
                # Re-fence immediately before a non-idempotent staging handoff.
                fresh = (
                    db.query(ImapMessageLedger.id)
                    .filter(
                        ImapMessageLedger.id == row.id,
                        ImapMessageLedger.download_lease_token == claim_token,
                        ImapMessageLedger.download_lease_expires_at > _utcnow(),
                        ImapMessageLedger.discovery_state == "downloading",
                    )
                    .first()
                )
                if fresh is None:
                    stats["deferred"] = int(stats["deferred"]) + 1
                    continue
                message = email.message_from_bytes(raw)
                msg_id = message.get("Message-ID") or f"<imap-uid-{uidvalidity}-{row.uid}@{row.mailbox_key}>"
                handoff_started = time.monotonic()
                accepted = fetch_attachments_and_enqueue(
                    message,
                    owner_id=account.get("owner_id"),
                    source_integration_id=account.get("source_integration_id"),
                    effective_mime_types=mime_types,
                    effective_extensions=extensions,
                    ingestion_prefix=f"{row.owner_key}:{row.mailbox_key}:{row.uidvalidity}:{row.uid}",
                    background=lane == "backlog",
                )
                handoff_seconds += time.monotonic() - handoff_started
                if accepted and not settings.imap_readonly_mode:
                    if is_gmail and gmail_labels:
                        mark_as_processed_with_star(mail, str(row.uid).encode())
                        mark_as_processed_with_label(mail, str(row.uid).encode(), label="Ingested")
                    if account.get("delete_after_process"):
                        mail.uid("store", str(row.uid), "+FLAGS", "\\Deleted")
                        deleted_any = True
                if _finish_fenced(db, row, claim_token, "completed", message_id=msg_id[:998]):
                    stats["downloaded"] = int(stats["downloaded"]) + 1
                else:
                    stats["deferred"] = int(stats["deferred"]) + 1
            except Exception as exc:  # noqa: BLE001
                if isinstance(exc, (OSError, EOFError, TimeoutError, imaplib.IMAP4.error, BrokenPipeError)):
                    _discard_cached_connection(cache_key, mail)
                    keep_connection = False
                    connection_broken = True
                if _finish_fenced(db, row, claim_token, "retry_wait", error_type=type(exc).__name__):
                    stats["failed"] = int(stats["failed"]) + 1
                else:
                    stats["deferred"] = int(stats["deferred"]) + 1
        if deleted_any and not readonly:
            try:
                mail.expunge()
            except Exception as exc:  # noqa: BLE001
                logger.warning("IMAP expunge failed: %s", type(exc).__name__)
        logger.info(
            "IMAP download batch account=%s lane=%s rows=%d downloaded=%d failed=%d deferred=%d "
            "connection_reused=%s setup_seconds=%.3f fetch_seconds=%.3f handoff_seconds=%.3f",
            account_ref,
            lane,
            len(rows),
            stats["downloaded"],
            stats["failed"],
            stats["deferred"],
            connection_reused,
            setup_seconds,
            fetch_seconds,
            handoff_seconds,
        )
        return stats
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, (OSError, EOFError, TimeoutError, imaplib.IMAP4.error, BrokenPipeError)):
            _discard_cached_connection(cache_key, mail)
            keep_connection = False
        for row in rows:
            if _finish_fenced(db, row, claim_token, "retry_wait", error_type=type(exc).__name__):
                stats["failed"] = int(stats["failed"]) + 1
        return stats
    finally:
        if mail is not None and not keep_connection:
            _shutdown_imap_connection(mail)
        elif keep_connection:
            _touch_cached_connection(cache_key, mail)
        db.close()
        # An unavailable source or full disk must wait for the next poll;
        # immediately refilling would churn through the entire candidate
        # backlog with repeated connection/storage failures.
        if rows and source_ready and _free_space_ok():
            _refill_lane(account_ref, lane)
