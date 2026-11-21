"""Lane-separated, metadata-first IMAP discovery and download handoff.

The module deliberately keeps credentials out of Celery arguments.  Discovery
commits ledger rows and its cursor in one transaction; publishing is an
idempotent, bounded follow-up operation and can be recovered by a later tick.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from celery import shared_task
from sqlalchemy import func, or_, text

from app.config import settings
from app.database import SessionLocal
from app.models import ImapMessageLedger, ImapPipelineCursor
from app.utils.imap_bodystructure import bodystructure_proves_no_named_attachment, metadata_uid_and_structure

logger = logging.getLogger(__name__)

LANE_NEW = "new"
LANE_BACKLOG = "backlog"
QUEUE_DOWNLOAD_NEW = "imap_download_new"
QUEUE_DOWNLOAD_BACKLOG = "imap_download_backlog"


def classify_bodystructure(item: object) -> tuple[int | None, bool]:
    """Return ``(uid, proven_no_document)`` without fetching a body."""
    uid, structure = metadata_uid_and_structure(item)
    return uid, bool(structure and bodystructure_proves_no_named_attachment(structure))


def record_metrics(account_ref: str, lane: str, *, scanned: int = 0, candidates: int = 0, **extra) -> None:
    """Keep metrics in the ledger; Redis is not the source of truth.

    ``scanned_at`` is written by the scanner transaction.  This hook remains
    for compatibility with older callers and deliberately does not maintain
    cumulative Redis counters, which become false after a restart or replay.
    """
    logger.debug(
        "IMAP pipeline batch account=%s lane=%s scanned=%s candidates=%s", account_ref, lane, scanned, candidates
    )


def pipeline_snapshot(account_ref: str) -> dict[str, int | str]:
    """Read durable lane gauges and recent rates from PostgreSQL."""
    states = ("ready", "claimed", "downloading", "retry_wait", "completed", "vanished", "permanent_failure")
    lanes = (LANE_NEW, LANE_BACKLOG)
    try:
        with SessionLocal() as db:
            result: dict[str, int | str] = {"account_ref": account_ref, "status": "ok"}
            for lane in lanes:
                for state in states:
                    result[f"{lane}_{state}"] = 0
                result[f"{lane}_scanned_last_hour"] = 0
                result[f"{lane}_downloaded_last_hour"] = 0
            rows = (
                db.query(
                    ImapMessageLedger.lane,
                    ImapMessageLedger.discovery_state,
                    func.count(ImapMessageLedger.id),
                )
                .filter(ImapMessageLedger.account_ref == account_ref)
                .group_by(
                    ImapMessageLedger.lane,
                    ImapMessageLedger.discovery_state,
                )
                .all()
            )
            for lane, state, count in rows:
                if lane in lanes and state in states:
                    result[f"{lane}_{state}"] = int(count)
            since = datetime.now(timezone.utc) - timedelta(hours=1)
            for lane in lanes:
                result[f"{lane}_scanned_last_hour"] = int(
                    db.query(func.count(ImapMessageLedger.id))
                    .filter(
                        ImapMessageLedger.account_ref == account_ref,
                        ImapMessageLedger.lane == lane,
                        ImapMessageLedger.scanned_at >= since,
                    )
                    .scalar()
                    or 0
                )
                result[f"{lane}_downloaded_last_hour"] = int(
                    db.query(func.count(ImapMessageLedger.id))
                    .filter(
                        ImapMessageLedger.account_ref == account_ref,
                        ImapMessageLedger.lane == lane,
                        ImapMessageLedger.downloaded_at >= since,
                    )
                    .scalar()
                    or 0
                )
            for state in states:
                result[f"total_{state}"] = sum(int(result[f"{lane}_{state}"]) for lane in lanes)
            result["scanned_last_hour"] = sum(int(result[f"{lane}_scanned_last_hour"]) for lane in lanes)
            result["downloaded_last_hour"] = sum(int(result[f"{lane}_downloaded_last_hour"]) for lane in lanes)
            return result
    except Exception as exc:
        logger.warning("Unable to read IMAP pipeline snapshot: %s", type(exc).__name__)
        return {"account_ref": account_ref, "status": "unknown", "error": type(exc).__name__}


def _cursor(db, owner_key: str, mailbox_key: str, uidvalidity: str, lane: str) -> ImapPipelineCursor:
    row = (
        db.query(ImapPipelineCursor)
        .filter_by(owner_key=owner_key, mailbox_key=mailbox_key, uidvalidity=str(uidvalidity), lane=lane)
        .one_or_none()
    )
    if row is None:
        row = ImapPipelineCursor(owner_key=owner_key, mailbox_key=mailbox_key, uidvalidity=str(uidvalidity), lane=lane)
        db.add(row)
        db.flush()
    return row


def commit_metadata_batch(
    *,
    account_ref: str,
    owner_key: str,
    mailbox_key: str,
    uidvalidity: str,
    lane: str,
    examined: list[dict],
    last_uid: int,
    highwater_uid: int | None = None,
) -> dict[str, int]:
    """Atomically record every examined UID and advance its lane cursor."""
    with SessionLocal() as db:
        cursor = _cursor(db, owner_key, mailbox_key, uidvalidity, lane)
        candidate_count = 0
        uids = [int(item["uid"]) for item in examined]
        existing = {}
        if uids:
            existing = {
                int(row.uid): row
                for row in db.query(ImapMessageLedger)
                .filter(
                    ImapMessageLedger.owner_key == owner_key,
                    ImapMessageLedger.mailbox_key == mailbox_key,
                    ImapMessageLedger.uidvalidity == str(uidvalidity),
                    ImapMessageLedger.uid.in_(uids),
                )
                .all()
            }
        scanned_at = datetime.now(timezone.utc)
        for item in examined:
            uid = int(item["uid"])
            candidate = bool(item.get("candidate"))
            row = existing.get(uid)
            if row is None:
                row = ImapMessageLedger(
                    owner_key=owner_key,
                    mailbox_key=mailbox_key,
                    uidvalidity=str(uidvalidity),
                    uid=uid,
                    lane=lane,
                    account_ref=account_ref,
                )
                db.add(row)
            elif row.state in {"completed", "vanished"} or row.discovery_state in {
                "claimed",
                "download_claimed",
                "downloading",
                "downloaded",
                "retry_wait",
                "download_failed",
            }:
                continue
            row.lane, row.account_ref, row.discovery_state, row.is_candidate = lane, account_ref, "ready", candidate
            row.scanned_at = scanned_at
            if not candidate:
                row.discovery_state = "completed"
                row.state = "completed"
            if candidate:
                candidate_count += 1
        cursor.last_uid = max(int(cursor.last_uid or 0), int(last_uid))
        if highwater_uid is not None and cursor.highwater_uid is None:
            cursor.highwater_uid = int(highwater_uid)
        cursor.initialized = True
        db.commit()
    record_metrics(account_ref, lane, scanned=len(examined), candidates=candidate_count)
    return {"scanned": len(examined), "candidates": candidate_count, "last_uid": int(last_uid)}


def scan_lane_windows(
    mail,
    *,
    account_ref: str,
    owner_key: str,
    mailbox_key: str,
    uidvalidity: str,
    folder: str,
    deadline: float,
    legacy_last_uid: int = 0,
    uidnext: int | None = None,
) -> dict[str, int]:
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
        backlog_end = int(back.highwater_uid if back.highwater_uid is not None else highwater)
        fresh_start = int(fresh.last_uid or 0) + 1
        # Values are copied before the session closes; SQLAlchemy may expire ORM rows on commit.
        fresh_end = highwater
    totals = {"backlog_scanned": 0, "backlog_candidates": 0, "new_scanned": 0, "new_candidates": 0}
    # Fresh lane is intentionally first; backlog remains independently resumable.
    for lane, initial_position, end in ((LANE_NEW, fresh_start, fresh_end), (LANE_BACKLOG, backlog_start, backlog_end)):
        position = initial_position
        while position <= end and time.monotonic() < deadline:
            stop = min(position + settings.imap_pipeline_metadata_batch_size - 1, end)
            status, data = mail.uid("search", None, "UID", f"{position}:{stop}")
            if status != "OK":
                break
            uids = [int(value) for value in (data[0] or b"").split() if position <= int(value) <= stop]
            result = discover_metadata_batch(
                mail,
                account_ref=account_ref,
                owner_key=owner_key,
                mailbox_key=mailbox_key,
                uidvalidity=uidvalidity,
                lane=lane,
                uids=uids,
                last_uid=stop,
            )
            totals[f"{lane}_scanned"] += result["scanned"]
            totals[f"{lane}_candidates"] += result["candidates"]
            position = stop + 1
    return totals


def discover_metadata_batch(
    mail,
    *,
    account_ref: str,
    owner_key: str,
    mailbox_key: str,
    uidvalidity: str,
    lane: str,
    uids: list[int],
    highwater_uid: int | None = None,
    last_uid: int | None = None,
) -> dict[str, int]:
    """Fetch BODYSTRUCTURE for a bounded UID batch and durably classify all UIDs."""
    if not uids:
        return commit_metadata_batch(
            account_ref=account_ref,
            owner_key=owner_key,
            mailbox_key=mailbox_key,
            uidvalidity=uidvalidity,
            lane=lane,
            examined=[],
            last_uid=int(last_uid or 0),
            highwater_uid=highwater_uid,
        )
    status, data = mail.uid("fetch", ",".join(str(uid) for uid in sorted(uids)), "(UID BODYSTRUCTURE)")
    parsed: dict[int, bool] = {}
    if status == "OK":
        for item in data or []:
            parsed_uid, proven = classify_bodystructure(item)
            if parsed_uid is not None:
                parsed[parsed_uid] = proven
    examined: list[dict] = []
    for uid in uids:
        proven = parsed.get(int(uid), False)
        examined.append({"uid": int(uid), "candidate": not proven})
    return commit_metadata_batch(
        account_ref=account_ref,
        owner_key=owner_key,
        mailbox_key=mailbox_key,
        uidvalidity=uidvalidity,
        lane=lane,
        examined=examined,
        last_uid=int(last_uid if last_uid is not None else max(uids or [0])),
        highwater_uid=highwater_uid,
    )


def claim_candidates(*, account_ref: str, lane: str, limit: int | None = None) -> tuple[str, list[int]]:
    """Claim one bounded, identity-homogeneous download batch.

    Claims are durable in the database.  An expired claim is eligible again,
    while terminal rows can never be reactivated.  ``SKIP LOCKED`` lets a
    second publisher make progress without waiting behind a running claim.
    """
    now = datetime.now(timezone.utc)
    token = uuid.uuid4().hex
    batch_limit = min(int(limit or settings.imap_pipeline_download_batch_size), 100)
    max_active = 1 if lane == LANE_NEW else 2
    with SessionLocal() as db:
        # Serialize the active-count check with claims for this account/lane.
        # PostgreSQL's advisory transaction lock scopes the lock to this exact
        # outbox lane. SQLite has no row/advisory locks; BEGIN IMMEDIATE is its
        # equivalent writer serialization. A lock failure propagates: falling
        # through after a failed statement would use an aborted transaction.
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"docuelevate:imap:{account_ref}:{lane}"}
            )
        elif dialect == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        active = (
            db.query(func.count(func.distinct(ImapMessageLedger.download_lease_token)))
            .filter(
                ImapMessageLedger.account_ref == account_ref,
                ImapMessageLedger.lane == lane,
                ImapMessageLedger.discovery_state.in_(("claimed", "downloading", "download_claimed")),
                ImapMessageLedger.download_lease_expires_at > now,
            )
            .scalar()
            or 0
        )
        if int(active) >= max_active:
            return token, []
        eligible = or_(
            ImapMessageLedger.discovery_state == "ready",
            (ImapMessageLedger.discovery_state == "retry_wait") & (ImapMessageLedger.next_download_at <= now),
            (
                (ImapMessageLedger.discovery_state.in_(("claimed", "downloading")))
                & (ImapMessageLedger.download_lease_expires_at <= now)
            ),
        )
        query = (
            db.query(ImapMessageLedger)
            .filter(
                ImapMessageLedger.account_ref == account_ref,
                ImapMessageLedger.lane == lane,
                ImapMessageLedger.is_candidate.is_(True),
                ImapMessageLedger.state.notin_(("completed", "vanished")),
                ImapMessageLedger.discovery_state.in_(("ready", "retry_wait", "claimed", "downloading")),
                eligible,
            )
            .order_by(ImapMessageLedger.uid)
            .with_for_update(skip_locked=True)
        )
        candidates = query.limit(batch_limit).all()
        if not candidates:
            return token, []
        # A task must have one owner/mailbox/UIDVALIDITY identity.  Do not
        # combine rows from two accounts or epochs in one IMAP session.
        identity = (candidates[0].owner_key, candidates[0].mailbox_key, str(candidates[0].uidvalidity))
        rows = [row for row in candidates if (row.owner_key, row.mailbox_key, str(row.uidvalidity)) == identity]
        expires = now + timedelta(seconds=settings.imap_pipeline_lease_seconds)
        task_id = uuid.uuid4().hex
        for row in rows:
            row.discovery_state, row.download_lease_token, row.download_lease_expires_at = "claimed", token, expires
            row.download_task_id = task_id
            row.download_started_at = None
            row.download_attempts = (row.download_attempts or 0) + 1
        db.commit()
        return token, [int(row.id) for row in rows]


@shared_task(name="app.imap_pipeline.publish_candidate_batches")
def publish_candidate_batches(account_ref: str, lane: str = LANE_BACKLOG, limit: int | None = None) -> int:
    max_batches = 1 if lane == LANE_NEW else 2
    if limit is not None:
        max_batches = min(max_batches, max(1, int(limit)))
    published = 0
    for _ in range(max_batches):
        token, ledger_ids = claim_candidates(account_ref=account_ref, lane=lane)
        if not ledger_ids:
            break
        task_id = token
        with SessionLocal() as db:
            row = (
                db.query(ImapMessageLedger)
                .filter(ImapMessageLedger.id == ledger_ids[0], ImapMessageLedger.download_lease_token == token)
                .one()
            )
            task_id = row.download_task_id
        try:
            download_imap_batch.apply_async(
                args=[account_ref, lane, ledger_ids, token],
                task_id=task_id,
                queue=QUEUE_DOWNLOAD_NEW if lane == LANE_NEW else QUEUE_DOWNLOAD_BACKLOG,
                priority=0 if lane == LANE_NEW else 6,
                expires=settings.imap_pipeline_lease_seconds,
                retry=False,
            )
        except Exception as exc:
            logger.warning("IMAP download publish failed account=%s lane=%s: %s", account_ref, lane, type(exc).__name__)
            break
        published += len(ledger_ids)
    return published


def recover_legacy_candidates(
    account_ref: str, owner_key: str, mailbox_key: str, uidvalidity: str, limit: int = 500
) -> int:
    """Adopt old nonterminal ledger rows into the candidate outbox once."""
    with SessionLocal() as db:
        rows = (
            db.query(ImapMessageLedger)
            .filter(
                ImapMessageLedger.owner_key == owner_key,
                ImapMessageLedger.mailbox_key == mailbox_key,
                ImapMessageLedger.uidvalidity == str(uidvalidity),
                ImapMessageLedger.account_ref.is_(None),
                ImapMessageLedger.state.notin_(("completed", "vanished")),
            )
            .limit(limit)
            .with_for_update()
            .all()
        )
        for row in rows:
            row.account_ref, row.lane, row.is_candidate, row.discovery_state = account_ref, LANE_BACKLOG, True, "ready"
            row.next_download_at = None
        db.commit()
        return len(rows)


@shared_task(
    bind=True,
    name="app.imap_pipeline.download_imap_batch",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=240,
    time_limit=270,
)
def download_imap_batch(self, account_ref: str, lane: str, ledger_ids: list[int], claim_token: str) -> dict[str, int]:
    """Thin compatibility wrapper around the dedicated download worker."""
    from app.imap_pipeline_download import download_claimed_batch

    return download_claimed_batch(account_ref, lane, ledger_ids, claim_token)
