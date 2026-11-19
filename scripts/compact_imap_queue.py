#!/usr/bin/env python3
"""Preview and, explicitly, compact safe duplicate IMAP Celery envelopes.

The default is a read-only preview.  This tool never removes mail, staged
files, database rows, or unknown Celery messages.  It only removes byte-for-
byte duplicate ``process_imap_intake(intake_id)`` envelopes, keeping at least
one copy while an unfinished durable intake exists.  Completed intakes may
have all duplicate copies removed.  Different headers/kwargs remain intact.
Run it from a worker pod (or another environment with the same Redis and DB
configuration) and keep producers/consumers quiescent while applying.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

QUEUE = "document_processor"
PRIORITY_SEP = "\x06\x16"
TASK = "app.tasks.imap_intake.process_imap_intake"
UNFINISHED = {"pending", "processing", "dispatched", "failed"}
MAX_SNAPSHOT_MESSAGES = 100_000


def queue_keys(existing: Iterable[str]) -> list[str]:
    """Return only the known document queue and its ten Redis priority lists."""
    wanted = {QUEUE, *(f"{QUEUE}{PRIORITY_SEP}{n}" for n in range(10))}
    return sorted(set(existing) & wanted, key=lambda k: (k != QUEUE, k))


def _json_body(envelope: Mapping[str, Any]) -> tuple[list[Any], dict[str, Any]] | None:
    body = envelope.get("body")
    if not isinstance(body, str):
        return None
    try:
        decoded = base64.b64decode(body, validate=True)
        value = json.loads(decoded)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(value, list) or len(value) < 2 or not isinstance(value[0], list) or not isinstance(value[1], dict):
        return None
    return value[0], value[1]


def intake_id(raw: bytes) -> int | None:
    """Extract an intake ID only from a valid Celery JSON envelope."""
    try:
        envelope = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(envelope, dict):
        return None
    headers = envelope.get("headers")
    task = headers.get("task") if isinstance(headers, dict) else None
    if task != TASK:
        return None
    parsed = _json_body(envelope)
    if parsed is None:
        return None
    args, kwargs = parsed
    if len(args) != 1 or kwargs or not isinstance(args[0], int) or isinstance(args[0], bool) or args[0] < 1:
        return None
    return args[0]


def snapshot_digest(snapshot: Mapping[str, list[bytes]]) -> str:
    digest = hashlib.sha256()
    for key in sorted(snapshot):
        digest.update(key.encode())
        digest.update(b"\0")
        for item in snapshot[key]:
            digest.update(len(item).to_bytes(8, "big"))
            digest.update(item)
    return digest.hexdigest()


def plan_compaction(snapshot: Mapping[str, list[bytes]], states: Mapping[int, str]) -> dict[str, Any]:
    """Build a deterministic removal plan without mutating its input."""
    occurrences: dict[tuple[str, bytes], list[int]] = {}
    malformed = 0
    eligible = 0
    for key, messages in snapshot.items():
        for index, raw in enumerate(messages):
            iid = intake_id(raw)
            if iid is None:
                malformed += 1
                continue
            eligible += 1
            occurrences.setdefault((key, raw), []).append(index)

    removals: list[dict[str, Any]] = []
    for (key, raw), indices in occurrences.items():
        if len(indices) < 2:
            continue
        iid = intake_id(raw)
        state = states.get(iid)
        if state not in UNFINISHED and state != "completed":
            continue
        keep = 1 if state in UNFINISHED else 0
        for index in indices[keep:]:
            removals.append({"key": key, "index": index, "intake_id": iid, "sha256": hashlib.sha256(raw).hexdigest()})
    removals.sort(key=lambda item: (item["key"], item["index"]))
    return {
        "queue": QUEUE,
        "snapshot_digest": snapshot_digest(snapshot),
        "message_count": sum(len(v) for v in snapshot.values()),
        "eligible_imap_messages": eligible,
        "malformed_or_other_messages": malformed,
        "remove_count": len(removals),
        "removals": removals,
    }


def backup_snapshot(path: Path, snapshot: Mapping[str, list[bytes]], manifest: Mapping[str, Any]) -> None:
    """Write an fsynced mode-0600 JSON backup before any broker mutation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"manifest": manifest, "messages": {key: [base64.b64encode(v).decode("ascii") for v in values] for key, values in snapshot.items()}}
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8", closefd=True) as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def apply_plan(redis_client: Any, snapshot: Mapping[str, list[bytes]], plan: Mapping[str, Any], backup: Path, preview_digest: str) -> dict[str, Any]:
    """Apply one watched Redis transaction; a changed queue fails closed."""
    if plan["snapshot_digest"] != preview_digest:
        raise RuntimeError("preview digest does not match the plan")
    backup_snapshot(backup, snapshot, plan)
    by_value: dict[str, dict[bytes, int]] = {}
    for item in plan["removals"]:
        key = item["key"]
        raw = snapshot[key][item["index"]]
        by_value.setdefault(key, {})[raw] = by_value.setdefault(key, {}).get(raw, 0) + 1
    keys = list(snapshot)
    pipe = redis_client.pipeline()
    try:
        pipe.watch(*keys)
        current = {key: list(redis_client.lrange(key, 0, -1)) for key in keys}
        if snapshot_digest(current) != preview_digest:
            raise RuntimeError("queue changed since preview; no mutation applied")
        pipe.multi()
        for key, values in by_value.items():
            for raw, count in values.items():
                pipe.lrem(key, count, raw)
        result = pipe.execute()
    except Exception:
        pipe.reset()
        raise
    finally:
        try:
            pipe.reset()
        except Exception:
            pass
    expected = {key: list(values) for key, values in snapshot.items()}
    for key, values in by_value.items():
        for raw, count in values.items():
            remaining = count
            filtered = []
            for item in expected[key]:
                if item == raw and remaining:
                    remaining -= 1
                else:
                    filtered.append(item)
            if remaining:
                raise RuntimeError("queue changed during apply; post-apply invariant failed")
            expected[key] = filtered
    actual = {key: list(redis_client.lrange(key, 0, -1)) for key in snapshot}
    if actual != expected:
        raise RuntimeError("post-apply queue invariant failed; inspect the backup before any retry")
    removed = sum(by_value[key][raw] for key in by_value for raw in by_value[key])
    return {"removed": removed, "redis_results": result, "post_apply_digest": snapshot_digest(actual)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="apply the exact preview after --preview-digest")
    parser.add_argument("--preview-digest")
    parser.add_argument("--backup", type=Path, default=Path("/workdir/imap-queue-backups/latest.json"))
    args = parser.parse_args(argv)
    if args.apply and not args.preview_digest:
        parser.error("--apply requires --preview-digest from an unchanged preview")

    import redis
    from app.database import SessionLocal
    from app.models import DocumentIntake
    from app.config import settings

    client = redis.Redis.from_url(settings.effective_celery_broker_url, socket_connect_timeout=5, socket_timeout=10)
    # Do not use Redis KEYS here: the known queue names are bounded and this
    # command must remain safe while the broker contains a large backlog.
    keys = queue_keys(
        key for key in [QUEUE, *(f"{QUEUE}{PRIORITY_SEP}{n}" for n in range(10))] if client.exists(key)
    )
    total = sum(int(client.llen(key)) for key in keys)
    if total > MAX_SNAPSHOT_MESSAGES:
        raise SystemExit(f"refusing snapshot of {total} messages; limit is {MAX_SNAPSHOT_MESSAGES}")
    snapshot = {key: list(client.lrange(key, 0, -1)) for key in keys}
    with SessionLocal() as db:
        states = {row.id: row.state for row in db.query(DocumentIntake.id, DocumentIntake.state).filter(DocumentIntake.source == "imap")}
    plan = plan_compaction(snapshot, states)
    print(json.dumps(plan, sort_keys=True))
    if not args.apply:
        return 0
    if args.preview_digest != plan["snapshot_digest"]:
        raise SystemExit("queue changed or digest mismatch; rerun a read-only preview")
    apply_plan(client, snapshot, plan, args.backup, args.preview_digest)
    print(json.dumps({"status": "applied", "backup": str(args.backup), "digest": args.preview_digest}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
