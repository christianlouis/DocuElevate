import base64
import json
from pathlib import Path

import pytest


def _envelope(intake_id, *, token="a", kwargs=None, task="app.tasks.imap_intake.process_imap_intake"):
    body = base64.b64encode(json.dumps([[intake_id], kwargs or {}, None], separators=(",", ":")).encode()).decode()
    return json.dumps({"body": body, "headers": {"task": task, "dispatch_token": token}}, separators=(",", ":")).encode()


@pytest.fixture
def tool():
    from scripts.compact_imap_queue import intake_id, plan_compaction

    return intake_id, plan_compaction


def test_plan_removes_only_exact_duplicates_and_keeps_one_unfinished(tool):
    _, plan = tool
    duplicate = _envelope(10)
    different_token = _envelope(10, token="b")
    completed = _envelope(11)
    malformed = b"not-json"
    snapshot = {"document_processor": [duplicate, different_token, duplicate, completed, completed, malformed]}

    result = plan(snapshot, {10: "dispatched", 11: "completed"})

    assert result["remove_count"] == 3
    assert {(item["intake_id"], item["index"]) for item in result["removals"]} == {(10, 2), (11, 3), (11, 4)}
    assert result["malformed_or_other_messages"] == 1


def test_unique_unfinished_and_unknown_messages_are_retained(tool):
    _, plan = tool
    known = _envelope(12)
    other = _envelope(12, task="app.tasks.process_document.process_document")
    result = plan({"document_processor": [known, other, b"garbage"]}, {12: "failed"})
    assert result["remove_count"] == 0


def test_priority_lists_are_isolated_and_digest_is_stable(tool):
    _, plan = tool
    message = _envelope(13)
    snapshot = {"document_processor": [message, message], "document_processor\x06\x160": [message]}
    result = plan(snapshot, {13: "completed"})
    assert result["remove_count"] == 2
    assert result["removals"][0]["key"] == "document_processor"
    assert result["snapshot_digest"] == plan(snapshot, {13: "completed"})["snapshot_digest"]


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.commands = []

    def watch(self, *keys):
        self.keys = keys

    def multi(self):
        return None

    def lrem(self, key, count, value):
        self.commands.append((key, count, value))

    def execute(self):
        for key, count, value in self.commands:
            remaining = count
            out = []
            for item in self.redis.data[key]:
                if item == value and remaining:
                    remaining -= 1
                else:
                    out.append(item)
            self.redis.data[key] = out
        return [1]

    def reset(self):
        return None


class FakeRedis:
    def __init__(self, data):
        self.data = data

    def pipeline(self):
        return FakePipeline(self)

    def lrange(self, key, _start, _end):
        return list(self.data[key])


def test_apply_writes_backup_and_preserves_remaining_order(tmp_path: Path, tool):
    _, plan_compaction = tool
    message = _envelope(20)
    snapshot = {"document_processor": [b"other", message, message, b"tail"]}
    plan = plan_compaction(snapshot, {20: "completed"})
    from scripts.compact_imap_queue import apply_plan

    fake = FakeRedis({key: list(value) for key, value in snapshot.items()})
    result = apply_plan(fake, snapshot, plan, tmp_path / "backup.json", plan["snapshot_digest"])
    assert result["removed"] == 2
    assert fake.data["document_processor"] == [b"other", b"tail"]
    payload = json.loads((tmp_path / "backup.json").read_text())
    assert payload["manifest"]["snapshot_digest"] == plan["snapshot_digest"]
    assert (tmp_path / "backup.json").stat().st_mode & 0o777 == 0o600


class RacingRedis(FakeRedis):
    def __init__(self, data):
        super().__init__(data)
        self.reads = 0

    def lrange(self, key, _start, _end):
        self.reads += 1
        result = super().lrange(key, _start, _end)
        if self.reads == 1:
            self.data[key].append(b"changed-after-preview")
        return result


def test_apply_fails_closed_when_queue_changes_since_preview(tmp_path: Path, tool):
    _, plan_compaction = tool
    message = _envelope(21)
    snapshot = {"document_processor": [message, message]}
    plan = plan_compaction(snapshot, {21: "completed"})
    from scripts.compact_imap_queue import apply_plan

    racing = RacingRedis({key: list(value) for key, value in snapshot.items()})
    with pytest.raises(RuntimeError, match="queue changed since preview"):
        apply_plan(racing, snapshot, plan, tmp_path / "backup.json", plan["snapshot_digest"])
    assert racing.data["document_processor"] == [message, message, b"changed-after-preview"]

