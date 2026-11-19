import base64
import json
import stat
from pathlib import Path

import pytest

from scripts.reprioritize_document_backlog import (
    IMAP_TASK,
    PRIORITY_QUEUE,
    SOURCE_QUEUE,
    apply_plan,
    main,
    plan_reprioritization,
    snapshot_digest,
)


def _message(
    task="app.tasks.process_document.process_document", *, intake_id=None, priority=0, marker=None, body=b"payload"
):
    if intake_id is not None:
        task = IMAP_TASK
        body = json.dumps([[intake_id], {}, None], separators=(",", ":")).encode()
    encoded = base64.b64encode(body).decode()
    headers = {"task": task, "id": f"task-{intake_id or priority}"}
    if marker is not None:
        headers["imap_backlog"] = marker
    return json.dumps(
        {"body": encoded, "headers": headers, "properties": {"priority": priority, "correlation_id": "x"}},
        separators=(",", ":"),
    ).encode()


def _decode(raw):
    return json.loads(raw)


class FakePipeline:
    def __init__(self, client):
        self.client = client
        self.commands = []

    def watch(self, *keys):
        self.client.watched = keys

    def multi(self):
        return None

    def delete(self, *keys):
        self.commands.append(("delete", keys))

    def rpush(self, key, *values):
        self.commands.append(("rpush", key, values))

    def execute(self):
        for command in self.commands:
            if command[0] == "delete":
                for key in command[1]:
                    self.client.data[key] = []
            else:
                self.client.data[command[1]].extend(command[2])
        return []

    def reset(self):
        return None


class FakeRedis:
    def __init__(self, data):
        self.data = {
            SOURCE_QUEUE: list(data.get(SOURCE_QUEUE, [])),
            PRIORITY_QUEUE: list(data.get(PRIORITY_QUEUE, [])),
        }
        self.watched = ()

    def lrange(self, key, _start, _end):
        return list(self.data.get(key, []))

    def llen(self, key):
        return len(self.data.get(key, []))

    def pipeline(self):
        return FakePipeline(self)


def test_preview_moves_only_allowlisted_jobs_and_preserves_order():
    unknown = b"not-json"
    protected = _message(intake_id=2275)
    eligible_one = _message(intake_id=10)
    eligible_two = _message(intake_id=11)
    existing_priority_six = _message(priority=6, marker=True)
    snapshot = {SOURCE_QUEUE: [unknown, eligible_one, protected, eligible_two], PRIORITY_QUEUE: [existing_priority_six]}

    plan = plan_reprioritization(snapshot, [2275])

    assert plan["moved_count"] == 2
    assert plan["protected_count"] == 1
    assert plan["_result_source"] == [unknown, protected]
    assert plan["_result_destination"][0] == existing_priority_six
    assert [plan["_result_destination"][1], plan["_result_destination"][2]]
    for original, transformed in zip((eligible_one, eligible_two), plan["_result_destination"][1:], strict=True):
        original_envelope = _decode(original)
        envelope = _decode(transformed)
        assert envelope["properties"]["priority"] == 6
        assert envelope["headers"]["imap_backlog"] is True
        assert envelope["body"] == original_envelope["body"]


def test_malformed_and_unrecognized_messages_are_byte_identical():
    malformed = b"{broken"
    unregistered = _message(task="app.tasks.not_registered.task")
    snapshot = {SOURCE_QUEUE: [malformed, unregistered], PRIORITY_QUEUE: []}

    plan = plan_reprioritization(snapshot)

    assert plan["moved_count"] == 0
    assert plan["_result_source"] == snapshot[SOURCE_QUEUE]
    assert plan["unknown_or_unrecognized_count"] == 2


@pytest.mark.parametrize(
    "body",
    [
        [[2275, "dispatch-token"], {}, None],
        [[], {"intake_id": 2275}, None],
    ],
)
def test_protection_recognizes_token_and_keyword_intake_shapes(body):
    raw = json.dumps(
        {
            "body": base64.b64encode(json.dumps(body, separators=(",", ":")).encode()).decode(),
            "headers": {"task": IMAP_TASK},
            "properties": {"priority": 0},
        },
        separators=(",", ":"),
    ).encode()
    plan = plan_reprioritization({SOURCE_QUEUE: [raw], PRIORITY_QUEUE: []}, [2275])
    assert plan["moved_count"] == 0
    assert plan["_result_source"] == [raw]
    assert plan["protected_count"] == 1


def test_existing_priority_six_order_is_preserved():
    existing = [_message(priority=6, marker=True), _message(priority=6, marker=True, body=b"second")]
    source = [_message(intake_id=1), _message(intake_id=2)]
    plan = plan_reprioritization({SOURCE_QUEUE: source, PRIORITY_QUEUE: existing})

    assert plan["_result_destination"][:2] == existing
    assert [_decode(item)["properties"]["priority"] for item in plan["_result_destination"]] == [6, 6, 6, 6]


def test_apply_requires_unchanged_snapshot_and_keeps_exact_backup(tmp_path: Path):
    source = [_message(intake_id=1), b"unknown"]
    destination = [_message(priority=6, marker=True)]
    snapshot = {SOURCE_QUEUE: source, PRIORITY_QUEUE: destination}
    plan = plan_reprioritization(snapshot)
    redis_client = FakeRedis(snapshot)
    backup = tmp_path / "queue-backup.json"

    receipt = apply_plan(redis_client, snapshot, plan, backup, plan["preview_digest"])

    assert receipt["moved_count"] == 1
    assert redis_client.data[SOURCE_QUEUE] == [b"unknown"]
    assert redis_client.data[PRIORITY_QUEUE][0] == destination[0]
    assert backup.stat().st_mode & 0o777 == 0o600
    saved = json.loads(backup.read_text())
    assert [base64.b64decode(v) for v in saved["queues"][SOURCE_QUEUE]] == source
    assert [base64.b64decode(v) for v in saved["queues"][PRIORITY_QUEUE]] == destination


def test_changed_queue_fails_closed_after_backup_without_mutation(tmp_path: Path):
    source = [_message(intake_id=1)]
    snapshot = {SOURCE_QUEUE: source, PRIORITY_QUEUE: []}
    plan = plan_reprioritization(snapshot)
    redis_client = FakeRedis(snapshot)
    redis_client.data[SOURCE_QUEUE].append(b"changed")
    backup = tmp_path / "queue-backup.json"

    with pytest.raises(RuntimeError, match="changed since preview"):
        apply_plan(redis_client, snapshot, plan, backup, plan["preview_digest"])

    assert redis_client.data[SOURCE_QUEUE] == source + [b"changed"]
    assert backup.exists()
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600


def test_apply_rejects_preview_digest_mismatch(tmp_path: Path):
    snapshot = {SOURCE_QUEUE: [_message(intake_id=1)], PRIORITY_QUEUE: []}
    plan = plan_reprioritization(snapshot)
    with pytest.raises(RuntimeError, match="preview digest"):
        apply_plan(FakeRedis(snapshot), snapshot, plan, tmp_path / "backup.json", "wrong")


def test_cli_refuses_apply_without_digest_and_backup():
    with pytest.raises(SystemExit):
        main(["--apply"])


def test_snapshot_digest_changes_for_any_source_or_destination_byte():
    first = {SOURCE_QUEUE: [b"a"], PRIORITY_QUEUE: [b"b"]}
    second = {SOURCE_QUEUE: [b"a"], PRIORITY_QUEUE: [b"c"]}
    assert snapshot_digest(first) != snapshot_digest(second)
