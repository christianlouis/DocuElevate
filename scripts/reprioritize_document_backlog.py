#!/usr/bin/env python3
"""Preview and safely move eligible document jobs to Redis priority six.

The default mode is read-only.  This tool changes Celery envelopes only; it
does not touch documents, mail, or database rows.  Apply requires an exact
preview digest, a new ``--backup`` path, and a quiescent broker.  Unknown,
malformed, unregistered, and explicitly protected messages remain byte-for-
byte in their original list and order.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

SOURCE_QUEUE = "document_processor"
PRIORITY_QUEUE = f"{SOURCE_QUEUE}\x06\x166"
PRIORITY = 6
MAX_MESSAGES = 100_000
MAX_BYTES = 256 * 1024 * 1024
IMAP_TASK = "app.tasks.imap_intake.process_imap_intake"

# Explicitly bounded to task names observed in the inventory.  Bare names are
# included because Celery task registration can preserve a short name.
KNOWN_TASKS = frozenset(
    {
        "app.tasks.backup_tasks.create_backup",
        "app.tasks.batch_tasks.backfill_missing_metadata",
        "app.tasks.batch_tasks.cleanup_temp_files",
        "app.tasks.batch_tasks.expire_shared_links",
        "app.tasks.batch_tasks.process_new_documents",
        "app.tasks.batch_tasks.reprocess_failed_documents",
        "app.tasks.check_credentials.check_credentials",
        "app.tasks.embed_metadata_into_pdf.embed_metadata_into_pdf",
        "app.tasks.extract_metadata_with_gpt.extract_metadata_with_gpt",
        "app.tasks.finalize_document_storage.finalize_document_storage",
        IMAP_TASK,
        "app.tasks.knowledge_research.cleanup_knowledge_research_jobs",
        "app.tasks.monitor_stalled_steps.monitor_stalled_steps",
        "app.tasks.process_document.process_document",
        "app.tasks.process_with_ocr.process_with_ocr",
        "app.tasks.rotate_pdf_pages.rotate_pdf_pages",
        "app.tasks.send_to_all.send_to_user_destinations",
        "app.tasks.subscription_tasks.apply_pending_subscription_changes_all",
        "app.tasks.translate_to_default_language.translate_to_default_language",
        "app.tasks.upload_to_user_integration.upload_to_user_integration",
        "app.tasks.uptime_kuma_tasks.ping_uptime_kuma",
        "app.tasks.watch_folder_tasks.scan_all_watch_folders",
        "backfill_missing_embeddings",
        "compute_document_embedding",
    }
)


def _body_is_valid(envelope: Mapping[str, Any]) -> bool:
    body = envelope.get("body")
    if not isinstance(body, str):
        return False
    try:
        decoded = base64.b64decode(body, validate=True)
        value = json.loads(decoded)
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(value, list) and len(value) >= 2 and isinstance(value[0], list) and isinstance(value[1], dict)


def _envelope(raw: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    headers = value.get("headers")
    properties = value.get("properties")
    if not isinstance(headers, dict) or headers.get("task") not in KNOWN_TASKS:
        return None
    if not isinstance(properties, dict) or not _body_is_valid(value):
        return None
    return value


def _intake_id(envelope: Mapping[str, Any]) -> int | None:
    if not isinstance(envelope, Mapping):
        return None
    headers = envelope.get("headers")
    if not isinstance(headers, dict) or headers.get("task") != IMAP_TASK:
        return None
    try:
        body = base64.b64decode(envelope["body"], validate=True)
        decoded = json.loads(body)
    except (KeyError, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, list) or len(decoded) < 2 or not isinstance(decoded[0], list):
        return None
    args = decoded[0]
    if args and isinstance(args[0], int) and not isinstance(args[0], bool) and args[0] >= 1:
        return args[0]
    kwargs = decoded[1]
    intake_id = kwargs.get("intake_id")
    if isinstance(intake_id, int) and not isinstance(intake_id, bool) and intake_id >= 1:
        return intake_id
    return None


def transform_message(raw: bytes, protected_intakes: frozenset[int]) -> tuple[bytes, str] | None:
    """Return transformed raw envelope and task name, or ``None`` if untouched."""
    envelope = _envelope(raw)
    if envelope is None:
        return None
    intake = _intake_id(envelope)
    if intake is not None and intake in protected_intakes:
        return None
    headers = envelope["headers"]
    properties = envelope["properties"]
    headers["imap_backlog"] = True
    properties["priority"] = PRIORITY
    # The body string, including any binary attachment encoding, is copied
    # unchanged.  Only the two explicitly permitted envelope fields differ.
    transformed = json.dumps(envelope, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return transformed, headers["task"]


def list_digest(messages: Iterable[bytes]) -> str:
    digest = hashlib.sha256()
    for message in messages:
        digest.update(len(message).to_bytes(8, "big"))
        digest.update(message)
    return digest.hexdigest()


def snapshot_digest(snapshot: Mapping[str, list[bytes]]) -> str:
    digest = hashlib.sha256()
    for key in (SOURCE_QUEUE, PRIORITY_QUEUE):
        digest.update(key.encode())
        digest.update(b"\0")
        for message in snapshot.get(key, []):
            digest.update(len(message).to_bytes(8, "big"))
            digest.update(message)
    return digest.hexdigest()


def _preview_digest(snapshot: Mapping[str, list[bytes]], protected_intakes: frozenset[int], moved: list[bytes]) -> str:
    payload = {
        "snapshot": snapshot_digest(snapshot),
        "protected_intakes": sorted(protected_intakes),
        "moved": [hashlib.sha256(message).hexdigest() for message in moved],
    }
    return hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def plan_reprioritization(snapshot: Mapping[str, list[bytes]], protected_intakes: Iterable[int] = ()) -> dict[str, Any]:
    """Create a deterministic plan without mutating the supplied snapshot."""
    protected = frozenset(protected_intakes)
    source = list(snapshot.get(SOURCE_QUEUE, []))
    destination = list(snapshot.get(PRIORITY_QUEUE, []))
    remaining: list[bytes] = []
    moved: list[bytes] = []
    moved_tasks: dict[str, int] = {}
    protected_count = 0
    unknown_count = 0
    for raw in source:
        transformed = transform_message(raw, protected)
        if transformed is None:
            remaining.append(raw)
            envelope = None
            try:
                envelope = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            if envelope and _intake_id(envelope) in protected:
                protected_count += 1
            else:
                unknown_count += 1
            continue
        message, task = transformed
        moved.append(message)
        moved_tasks[task] = moved_tasks.get(task, 0) + 1
    resulting = {SOURCE_QUEUE: remaining, PRIORITY_QUEUE: destination + moved}
    digest = _preview_digest(snapshot, protected, moved)
    return {
        "source_queue": SOURCE_QUEUE,
        "destination_queue": PRIORITY_QUEUE,
        "snapshot_digest": snapshot_digest(snapshot),
        "preview_digest": digest,
        "source_count": len(source),
        "destination_count": len(destination),
        "moved_count": len(moved),
        "moved_tasks": dict(sorted(moved_tasks.items())),
        "protected_count": protected_count,
        "unknown_or_unrecognized_count": unknown_count,
        "result_source_digest": list_digest(resulting[SOURCE_QUEUE]),
        "result_destination_digest": list_digest(resulting[PRIORITY_QUEUE]),
        "protected_intakes": sorted(protected),
        "_result_source": remaining,
        "_result_destination": destination + moved,
    }


def backup_snapshot(path: Path, snapshot: Mapping[str, list[bytes]], manifest: Mapping[str, Any]) -> None:
    """Persist exact raw queue bytes with mode 0600 and fsync before mutation."""
    if path.exists():
        raise RuntimeError(f"backup path already exists; choose a unique path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "manifest": {key: value for key, value in manifest.items() if not key.startswith("_")},
        "queues": {
            key: [base64.b64encode(message).decode("ascii") for message in snapshot.get(key, [])]
            for key in (SOURCE_QUEUE, PRIORITY_QUEUE)
        },
    }
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


def _read_snapshot(
    redis_client: Any, *, max_messages: int = MAX_MESSAGES, max_bytes: int = MAX_BYTES
) -> dict[str, list[bytes]]:
    """Read both lists in bounded chunks, refusing oversized queues early."""
    snapshot: dict[str, list[bytes]] = {}
    message_count = 0
    byte_count = 0
    for key in (SOURCE_QUEUE, PRIORITY_QUEUE):
        queue_count = int(redis_client.llen(key))
        message_count += queue_count
        if message_count > max_messages:
            raise RuntimeError("refusing snapshot over configured message bound")
        values: list[bytes] = []
        for start in range(0, queue_count, 1000):
            chunk = list(redis_client.lrange(key, start, min(start + 999, queue_count - 1)))
            values.extend(chunk)
            byte_count += sum(len(message) for message in chunk)
            if byte_count > max_bytes:
                raise RuntimeError("refusing snapshot over configured byte bound")
        if len(values) != queue_count:
            raise RuntimeError("queue changed while snapshot was being read")
        snapshot[key] = values
    return snapshot


def apply_plan(
    redis_client: Any,
    snapshot: Mapping[str, list[bytes]],
    plan: Mapping[str, Any],
    backup: Path,
    preview_digest: str,
) -> dict[str, Any]:
    """CAS-apply a plan, replacing only the two watched Redis lists."""
    if plan["preview_digest"] != preview_digest:
        raise RuntimeError("preview digest does not match the plan")
    backup_snapshot(backup, snapshot, plan)
    pipe = redis_client.pipeline()
    try:
        pipe.watch(SOURCE_QUEUE, PRIORITY_QUEUE)
        current = _read_snapshot(redis_client)
        if snapshot_digest(current) != plan["snapshot_digest"]:
            raise RuntimeError("queue changed since preview; no mutation applied")
        pipe.multi()
        pipe.delete(SOURCE_QUEUE, PRIORITY_QUEUE)
        if plan["_result_source"]:
            pipe.rpush(SOURCE_QUEUE, *plan["_result_source"])
        if plan["_result_destination"]:
            pipe.rpush(PRIORITY_QUEUE, *plan["_result_destination"])
        pipe.execute()
    finally:
        pipe.reset()
    actual = _read_snapshot(redis_client)
    expected = {SOURCE_QUEUE: plan["_result_source"], PRIORITY_QUEUE: plan["_result_destination"]}
    if actual != expected:
        raise RuntimeError("post-apply queue invariant failed; inspect backup before retry")
    return {
        "status": "applied",
        "backup": str(backup),
        "preview_digest": preview_digest,
        "moved_count": plan["moved_count"],
        "source_digest": list_digest(actual[SOURCE_QUEUE]),
        "destination_digest": list_digest(actual[PRIORITY_QUEUE]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="apply only the unchanged preview")
    parser.add_argument("--preview-digest", help="digest printed by the preceding preview")
    parser.add_argument("--backup", type=Path, help="new mode-0600 backup path; required with --apply")
    parser.add_argument(
        "--protect-intake", action="append", type=int, default=[], help="intake ID to leave at priority 0"
    )
    parser.add_argument("--max-messages", type=int, default=MAX_MESSAGES)
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    args = parser.parse_args(argv)
    if args.apply and (not args.preview_digest or args.backup is None):
        parser.error("--apply requires --preview-digest and a new --backup path")

    import redis

    from app.config import settings

    client = redis.Redis.from_url(settings.effective_celery_broker_url, socket_connect_timeout=5, socket_timeout=10)
    snapshot = _read_snapshot(client, max_messages=args.max_messages, max_bytes=args.max_bytes)
    # _read_snapshot enforces bounds while reading, before materializing any
    # unbounded Redis list in memory.
    plan = plan_reprioritization(snapshot, args.protect_intake)
    public_plan = {key: value for key, value in plan.items() if not key.startswith("_")}
    print(json.dumps(public_plan, sort_keys=True))
    if not args.apply:
        return 0
    if args.preview_digest != plan["preview_digest"]:
        raise SystemExit("queue or preview inputs changed; rerun a read-only preview")
    print(json.dumps(apply_plan(client, snapshot, plan, args.backup, args.preview_digest), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
