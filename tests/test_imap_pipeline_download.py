from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import imap_pipeline_download as downloader


class FakeDB:
    def commit(self):
        pass

    def close(self):
        pass


def row(**overrides):
    values = dict(
        id=1,
        owner_key="owner",
        mailbox_key="mailbox",
        uidvalidity="7",
        uid=42,
        state="pending",
        is_candidate=True,
        download_lease_token="token",
        download_lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        message_id=None,
        last_error=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_stale_or_duplicate_claim_has_no_network_side_effect(monkeypatch):
    calls = []
    monkeypatch.setattr(downloader, "SessionLocal", FakeDB)
    monkeypatch.setattr(downloader, "_claim_rows", lambda *args: [])
    monkeypatch.setattr(downloader.imaplib, "IMAP4_SSL", lambda *args, **kwargs: calls.append(args))

    result = downloader.download_claimed_batch("imap1", "new-mail", [1], "stale")

    assert result["deferred"] == 1
    assert calls == []


def test_disk_pause_releases_claim_without_network(monkeypatch):
    candidate = row()
    monkeypatch.setattr(downloader, "SessionLocal", FakeDB)
    monkeypatch.setattr(downloader, "_claim_rows", lambda *args: [candidate])
    monkeypatch.setattr(downloader, "_free_space_ok", lambda: False)
    monkeypatch.setattr(downloader.imaplib, "IMAP4_SSL", lambda *args, **kwargs: pytest.fail("network"))

    result = downloader.download_claimed_batch("imap1", "backlog", [1], "token")

    assert result["deferred"] == 1
    assert candidate.state == "pending"
    assert candidate.download_lease_token is None


def test_inactive_source_is_deferred_before_connect(monkeypatch):
    candidate = row()
    monkeypatch.setattr(downloader, "SessionLocal", FakeDB)
    monkeypatch.setattr(downloader, "_claim_rows", lambda *args: [candidate])
    monkeypatch.setattr(downloader, "_free_space_ok", lambda: True)
    monkeypatch.setattr(downloader, "_account_from_ref", lambda *args: None)
    monkeypatch.setattr(downloader.imaplib, "IMAP4_SSL", lambda *args, **kwargs: pytest.fail("network"))

    result = downloader.download_claimed_batch("user_owner_9", "new-mail", [1], "token")

    assert result["deferred"] == 1
    assert candidate.state == "deferred"


def test_uidvalidity_mismatch_does_not_fetch_payload(monkeypatch):
    candidate = row(mailbox_key="expected", uidvalidity="8")
    monkeypatch.setattr(downloader, "SessionLocal", FakeDB)
    monkeypatch.setattr(downloader, "_claim_rows", lambda *args: [candidate])
    monkeypatch.setattr(downloader, "_free_space_ok", lambda: True)
    monkeypatch.setattr(
        downloader,
        "_account_from_ref",
        lambda *args: {"owner_id": "owner", "host": "imap.example", "port": 993, "username": "u", "password": "p", "use_ssl": True, "profile_id": None},
    )

    class Mail:
        def login(self, *_):
            pass

        def select(self, *_args, **_kwargs):
            return "OK", {"UIDVALIDITY": [b"7"]}

        def uid(self, *_args):
            pytest.fail("payload fetch must not occur")

    monkeypatch.setattr(downloader, "is_private_ip", lambda _: False)
    monkeypatch.setattr(downloader.imaplib, "IMAP4_SSL", lambda *args, **kwargs: Mail())
    monkeypatch.setattr(downloader, "find_all_mail_folder", lambda _mail: "INBOX")

    result = downloader.download_claimed_batch("imap1", "new-mail", [1], "token")

    assert result["deferred"] == 1


def test_ingestion_prefix_preserves_full_identity(monkeypatch):
    assert downloader._mailbox_key("owner", "imap.example", 993, "user", "INBOX")
    assert "owner:mailbox:7:42" == ":".join(("owner", "mailbox", "7", "42"))


def test_timeout_rows_remain_retryable(monkeypatch):
    candidate = row()
    monkeypatch.setattr(downloader, "SessionLocal", FakeDB)
    monkeypatch.setattr(downloader, "_claim_rows", lambda *args: [candidate])
    monkeypatch.setattr(downloader, "_free_space_ok", lambda: True)
    monkeypatch.setattr(downloader, "_account_from_ref", lambda *args: None)
    result = downloader.download_claimed_batch("imap1", "backlog", [1], "token")
    assert candidate.download_lease_token is None
    assert result["deferred"] == 1
