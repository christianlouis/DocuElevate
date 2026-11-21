"""Lane-separated, metadata-first IMAP discovery and download handoff.

The module deliberately keeps credentials out of Celery arguments.  Discovery
commits ledger rows and its cursor in one transaction; publishing is an
idempotent, bounded follow-up operation and can be recovered by a later tick.
"""

from __future__ import annotations

import imaplib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from celery import shared_task
from sqlalchemy import or_

from app.config import settings
from app.database import SessionLocal
from app.models import ImapMessageLedger, ImapPipelineCursor
from app.utils.imap_bodystructure import bodystructure_proves_no_named_attachment, metadata_uid_and_structure

logger = logging.getLogger(__name__)

LANE_NEW = "new"
LANE_BACKLOG = "backlog"
QUEUE_METADATA = "imap_metadata"
QUEUE_DOWNLOAD_NEW = "imap_download_new"
QUEUE_DOWNLOAD_BACKLOG = "imap_download_backlog"
_METRICS_PREFIX = "docuelevate:imap:pipeline:"


@dataclass(frozen=True)
class ImapAccountConfig:
    account_ref: str
    host: str
    port: int
    username: str
    password: str
    use_ssl: bool = True
    owner_id: str | None = None
    source_integration_id: int | None = None
    delete_after_process: bool = False


def classify_bodystructure(item: object) -> tuple[int | None, bool, bytes | None]:
    """Return ``(uid, proven_no_document, structure)`` without fetching a body."""
    uid, structure = metadata_uid_and_structure(item)
    return uid, bool(structure and bodystructure_proves_no_named_attachment(structure)), structure


def _metric_key(account_ref: str) -> str:
    return f"{_METRICS_PREFIX}{account_ref}"


def record_metrics(account_ref: str, lane: str, *, scanned: int = 0, candidates: int = 0, **extra) -> None:
    """Increment safe operational counters; failures never stop discovery."""
    try:
        import redis

        values = {f"{lane}_{name}": int(value) for name, value in {"scanned": scanned, "candidates": candidates, **extra}.items() if value}
        if values:
            client = redis.StrictRedis.from_url(settings.redis_url, decode_responses=True)
            client.hset(_metric_key(account_ref), "updated_at", int(time.time()))
            for key, value in values.items():
                client.hincrby(_metric_key(account_ref), key, value)
    except Exception:  # pragma: no cover - metrics are best effort
        return


def pipeline_snapshot(account_ref: str) -> dict[str, int | str]:
    """Read a monitoring-safe snapshot without exposing account credentials."""
    try:
        import redis

        return redis.StrictRedis.from_url(settings.redis_url, decode_responses=True).hgetall(_metric_key(account_ref))
    except Exception:
        return {}


def _cursor(db, owner_key: str, mailbox_key: str, uidvalidity: str, lane: str) -> ImapPipelineCursor:
    row = db.query(ImapPipelineCursor).filter_by(owner_key=owner_key, mailbox_key=mailbox_key, uidvalidity=str(uidvalidity), lane=lane).one_or_none()
    if row is None:
        row = ImapPipelineCursor(owner_key=owner_key, mailbox_key=mailbox_key, uidvalidity=str(uidvalidity), lane=lane)
        db.add(row)
        db.flush()
    return row


def commit_metadata_batch(*, account_ref: str, owner_key: str, mailbox_key: str, uidvalidity: str, lane: str, examined: list[dict], last_uid: int, highwater_uid: int | None = None) -> dict[str, int]:
    """Atomically record every examined UID and advance its lane cursor."""
    with SessionLocal() as db:
        cursor = _cursor(db, owner_key, mailbox_key, uidvalidity, lane)
        candidate_count = 0
        for item in examined:
            uid = int(item["uid"])
            candidate = bool(item.get("candidate"))
            row = db.query(ImapMessageLedger).filter_by(owner_key=owner_key, mailbox_key=mailbox_key, uidvalidity=str(uidvalidity), uid=uid).one_or_none()
            if row is None:
                row = ImapMessageLedger(owner_key=owner_key, mailbox_key=mailbox_key, uidvalidity=str(uidvalidity), uid=uid, lane=lane, account_ref=account_ref)
                db.add(row)
            elif row.state in {"completed", "vanished"}:
                continue
            row.lane, row.account_ref, row.discovery_state, row.is_candidate = lane, account_ref, "completed", candidate
            row.metadata_json = json.dumps({"structure": item.get("structure")}) if item.get("structure") else None
            if candidate:
                candidate_count += 1
        cursor.last_uid = max(int(cursor.last_uid or 0), int(last_uid))
        if highwater_uid is not None:
            cursor.highwater_uid = int(highwater_uid)
        cursor.initialized = True
        db.commit()
    record_metrics(account_ref, lane, scanned=len(examined), candidates=candidate_count)
    return {"scanned": len(examined), "candidates": candidate_count, "last_uid": int(last_uid)}


def scan_lane_windows(mail, *, account_ref: str, owner_key: str, mailbox_key: str, uidvalidity: str, folder: str, deadline: float, legacy_last_uid: int = 0, uidnext: int | None = None) -> dict[str, int]:
    """Advance backlog and fresh cursors with bounded SEARCH/FETCH windows."""
    if uidnext is None:
        uidnext = int(mail.response("UIDNEXT")[1][0])
    highwater = max(0, uidnext - 1)
    with SessionLocal() as db:
        back = _cursor(db, owner_key, mailbox_key, uidvalidity, LANE_BACKLOG)
        fresh = _cursor(db, owner_key, mailbox_key, uidvalidity, LANE_NEW)
        if not back.initialized:
            back.last_uid = int(legacy_last_uid)
            back.highwater_uid = highwater
            back.initialized = True
        if not fresh.initialized:
            fresh.last_uid = highwater
            fresh.highwater_uid = highwater
            fresh.initialized = True
        db.commit()
        backlog_start = int(back.last_uid or 0) + 1
        fresh_start = max(int(fresh.last_uid or highwater) + 1, highwater + 1)
    totals = {"backlog_scanned": 0, "backlog_candidates": 0, "new_scanned": 0, "new_candidates": 0}
    # Fresh lane is intentionally first; backlog remains independently resumable.
    backlog_end = int(back.highwater_uid or highwater)
    for lane, initial_position, end in ((LANE_NEW, fresh_start, highwater), (LANE_BACKLOG, backlog_start, backlog_end)):
        position = initial_position
        while position <= end and time.monotonic() < deadline:
            stop = min(position + settings.imap_pipeline_metadata_batch_size - 1, end)
            status, data = mail.uid("search", None, "UID", f"{position}:{stop}")
            if status != "OK":
                break
            uids = [int(value) for value in (data[0] or b"").split() if position <= int(value) <= stop]
            if uids:
                result = discover_metadata_batch(mail, account_ref=account_ref, owner_key=owner_key, mailbox_key=mailbox_key, uidvalidity=uidvalidity, lane=lane, uids=uids, highwater_uid=highwater)
                totals[f"{lane}_scanned"] += result["scanned"]
                totals[f"{lane}_candidates"] += result["candidates"]
            # Advance over the complete UID window, including vanished UIDs.
            with SessionLocal() as db:
                row = _cursor(db, owner_key, mailbox_key, uidvalidity, lane)
                row.last_uid = stop
                db.commit()
            position = stop + 1
    return totals


def discover_metadata_batch(mail, *, account_ref: str, owner_key: str, mailbox_key: str, uidvalidity: str, lane: str, uids: list[int], highwater_uid: int | None = None) -> dict[str, int]:
    """Fetch BODYSTRUCTURE for a bounded UID batch and durably classify all UIDs."""
    if not uids:
        return {"scanned": 0, "candidates": 0, "last_uid": 0}
    status, data = mail.uid("fetch", ",".join(str(uid) for uid in sorted(uids)), "(UID BODYSTRUCTURE)")
    parsed: dict[int, tuple[bool, str | None]] = {}
    if status == "OK":
        for item in data or []:
            parsed_uid, proven, structure = classify_bodystructure(item)
            if parsed_uid is not None:
                parsed[parsed_uid] = (proven, structure.decode("ascii", "replace") if structure else None)
    examined: list[dict] = []
    for uid in uids:
        proven, structure = parsed.get(int(uid), (False, None))
        examined.append({"uid": int(uid), "candidate": not proven, "structure": structure})
    return commit_metadata_batch(account_ref=account_ref, owner_key=owner_key, mailbox_key=mailbox_key, uidvalidity=uidvalidity, lane=lane, examined=examined, last_uid=max(uids or [0]), highwater_uid=highwater_uid)


def claim_candidates(*, account_ref: str, lane: str, limit: int | None = None) -> tuple[str, list[int]]:
    """Claim bounded candidates with a fencing token; expired claims are reclaimable."""
    now = datetime.now(timezone.utc)
    token = uuid.uuid4().hex
    with SessionLocal() as db:
        rows = db.query(ImapMessageLedger).filter(ImapMessageLedger.account_ref == account_ref, ImapMessageLedger.lane == lane, ImapMessageLedger.is_candidate.is_(True), or_(ImapMessageLedger.discovery_state == "completed", ImapMessageLedger.download_lease_expires_at < now)).order_by(ImapMessageLedger.uid).limit(limit or settings.imap_pipeline_download_batch_size).with_for_update().all()
        expires = now + timedelta(seconds=settings.imap_pipeline_lease_seconds)
        for row in rows:
            row.discovery_state, row.download_lease_token, row.download_lease_expires_at = "download_claimed", token, expires
            row.download_attempts = (row.download_attempts or 0) + 1
        db.commit()
        return token, [int(row.id) for row in rows]


@shared_task(name="app.imap_pipeline.publish_candidate_batches")
def publish_candidate_batches(account_ref: str, lane: str = LANE_BACKLOG, limit: int | None = None) -> int:
    token, uids = claim_candidates(account_ref=account_ref, lane=lane, limit=limit)
    if not uids:
        return 0
    download_imap_batch.apply_async(args=[account_ref, lane, uids, token], queue=QUEUE_DOWNLOAD_NEW if lane == LANE_NEW else QUEUE_DOWNLOAD_BACKLOG, priority=0 if lane == LANE_NEW else 5)
    return len(uids)


@shared_task(name="app.imap_pipeline.discover_imap_metadata")
def discover_imap_metadata(account_ref: str, owner_key: str, mailbox_key: str, uidvalidity: str, lane: str, uids: list[int], highwater_uid: int | None = None) -> dict[str, int]:
    """Execution-time credential lookup plus metadata-only discovery."""
    cfg = resolve_account_config(account_ref)
    mail = imaplib.IMAP4_SSL(cfg.host, cfg.port) if cfg.use_ssl else imaplib.IMAP4(cfg.host, cfg.port)
    try:
        mail.login(cfg.username, cfg.password)
        mail.select(mailbox_key)
        return discover_metadata_batch(mail, account_ref=account_ref, owner_key=owner_key, mailbox_key=mailbox_key, uidvalidity=uidvalidity, lane=lane, uids=uids, highwater_uid=highwater_uid)
    finally:
        try:
            mail.logout()
        except Exception as exc:  # best-effort logout
            logger.debug("IMAP logout failed: %s", type(exc).__name__)


def recover_legacy_candidates(account_ref: str, owner_key: str, mailbox_key: str, uidvalidity: str, limit: int = 500) -> int:
    """Adopt old nonterminal ledger rows into the candidate outbox once."""
    with SessionLocal() as db:
        rows = db.query(ImapMessageLedger).filter(ImapMessageLedger.owner_key == owner_key, ImapMessageLedger.mailbox_key == mailbox_key, ImapMessageLedger.uidvalidity == str(uidvalidity), ImapMessageLedger.account_ref.is_(None), ImapMessageLedger.state.notin_(("completed", "vanished"))).limit(limit).with_for_update().all()
        for row in rows:
            row.account_ref, row.lane, row.is_candidate, row.discovery_state = account_ref, LANE_BACKLOG, True, "completed"
        db.commit()
        return len(rows)


@shared_task(bind=True, name="app.imap_pipeline.download_imap_batch", acks_late=True, reject_on_worker_lost=True)
def download_imap_batch(self, account_ref: str, lane: str, ledger_ids: list[int], claim_token: str) -> dict[str, int]:
    """Thin compatibility wrapper around the dedicated download worker."""
    from app.imap_pipeline_download import download_claimed_batch

    return download_claimed_batch(account_ref, lane, ledger_ids, claim_token)


def resolve_account_config(account_ref: str) -> ImapAccountConfig:
    """Resolve credentials at execution time from the existing account tables."""
    from app.models import UserImapAccount, UserIntegration
    from app.utils.encryption import decrypt_value

    kind, _, raw_id = account_ref.partition("_")
    with SessionLocal() as db:
        if kind == "user":
            # account refs are user_<owner>_<account-id>; use the final id so
            # owner identifiers containing underscores remain unambiguous.
            account_id = int(raw_id.rsplit("_", 1)[-1])
            row = db.query(UserImapAccount).filter(UserImapAccount.id == account_id, UserImapAccount.is_active.is_(True)).one()
            return ImapAccountConfig(account_ref, row.host, int(row.port or 993), row.username, decrypt_value(row.password), bool(row.use_ssl), str(row.owner_id), None, bool(row.delete_after_process))
        if kind == "integration":
            integration_id = int(raw_id.rsplit("_", 1)[-1])
            row = db.query(UserIntegration).filter(UserIntegration.id == integration_id, UserIntegration.is_active.is_(True)).one()
            config = json.loads(row.config or "{}")
            creds = json.loads(decrypt_value(row.credentials) or "{}")
            return ImapAccountConfig(account_ref, config["host"], int(config.get("port", 993)), config["username"], creds["password"], bool(config.get("use_ssl", True)), str(row.owner_id), integration_id, bool(config.get("delete_after_process", False)))
    raise ValueError(f"unknown IMAP account reference: {account_ref}")
