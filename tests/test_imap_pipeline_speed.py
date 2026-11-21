from types import SimpleNamespace

import pytest

from app import imap_pipeline
from app import imap_pipeline_download as downloader
from app.config import settings


def test_backlog_publisher_fills_four_slots_but_new_lane_stays_single(monkeypatch):
    claims = iter([(f"token-{n}", [n]) for n in range(1, 6)])
    published = []

    monkeypatch.setattr(imap_pipeline, "claim_candidates", lambda **_: next(claims))
    monkeypatch.setattr(
        imap_pipeline,
        "download_imap_batch",
        SimpleNamespace(apply_async=lambda **kwargs: published.append(kwargs)),
    )

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def query(self, *_args):
            return self

        def filter(self, *_args):
            return self

        def one(self):
            return SimpleNamespace(download_task_id="task")

    monkeypatch.setattr(imap_pipeline, "SessionLocal", FakeSession)
    monkeypatch.setattr(settings, "imap_pipeline_backlog_active_batches", 4)

    assert imap_pipeline.publish_candidate_batches.run("acct", "backlog") == 4
    assert len(published) == 4

    claims = iter([("new-token", [99]), ("should-not-publish", [100])])
    published.clear()
    assert imap_pipeline.publish_candidate_batches.run("acct", "new") == 1
    assert len(published) == 1


def test_connection_cache_reuses_with_noop_and_invalidates_credentials(monkeypatch):
    downloader._close_all_cached_connections()
    created = []

    class Mail:
        def __init__(self):
            self.noops = 0
            self.closed = 0

        def login(self, *_args):
            pass

        def noop(self):
            self.noops += 1

        def response(self, _name):
            return (_name, [None])

        def select(self, *_args, **_kwargs):
            return "OK", {"UIDVALIDITY": [b"7"]}

        def shutdown(self):
            self.closed += 1

    def make_mail(*_args, **_kwargs):
        mail = Mail()
        created.append(mail)
        return mail

    monkeypatch.setattr(downloader.imaplib, "IMAP4_SSL", make_mail)
    monkeypatch.setattr(downloader, "find_all_mail_folder", lambda _mail: "INBOX")
    monkeypatch.setattr(downloader, "_extract_uidvalidity", lambda *_args: "7")
    account = {"host": "imap.example", "port": 993, "username": "user", "password": "secret", "use_ssl": True}
    first = downloader._open_or_reuse_connection("acct", account, True)
    second = downloader._open_or_reuse_connection("acct", account, True)
    assert first[0] is second[0]
    assert second[4] is True
    assert len(created) == 1 and created[0].noops == 1
    changed = {**account, "password": "rotated"}
    third = downloader._open_or_reuse_connection("acct", changed, True)
    assert third[0] is not first[0]
    assert len(created) == 2 and created[0].closed == 1
    downloader._close_all_cached_connections()


def test_connection_cache_idle_cleanup_skips_borrowed_and_closes_idle(monkeypatch):
    downloader._close_all_cached_connections()
    closed = []

    class Mail:
        def login(self, *_args):
            pass

        def select(self, *_args, **_kwargs):
            return "OK", {"UIDVALIDITY": [b"7"]}

        def shutdown(self):
            closed.append(self)

    monkeypatch.setattr(downloader.imaplib, "IMAP4_SSL", lambda *_args, **_kwargs: Mail())
    monkeypatch.setattr(downloader, "find_all_mail_folder", lambda _mail: "INBOX")
    monkeypatch.setattr(downloader, "_extract_uidvalidity", lambda *_args: "7")
    account = {"host": "imap.example", "port": 993, "username": "u", "password": "p", "use_ssl": True}
    mail = downloader._open_or_reuse_connection("idle", account, True)[0]
    entry = downloader._CONNECTION_CACHE["idle"]
    entry.created_at = entry.last_used_at = 0
    entry.in_use = True
    downloader._expire_idle_connections(now=10_000)
    assert "idle" in downloader._CONNECTION_CACHE
    entry.in_use = False
    downloader._expire_idle_connections(now=10_000)
    assert "idle" not in downloader._CONNECTION_CACHE
    assert closed == [mail]


@pytest.mark.parametrize("noop_result", [("NO", [b"not ready"]), ("BAD", [b"closed"])])
def test_connection_cache_reconnects_when_noop_rejects(monkeypatch, noop_result):
    downloader._close_all_cached_connections()
    created = []

    class Mail:
        state = "SELECTED"

        def login(self, *_args):
            pass

        def noop(self):
            return noop_result if len(created) == 1 else ("OK", [b"done"])

        def response(self, _name):
            return "OK", [b"7"]

        def select(self, *_args, **_kwargs):
            return "OK", {"UIDVALIDITY": [b"7"]}

        def shutdown(self):
            pass

    def make_mail(*_args, **_kwargs):
        mail = Mail()
        created.append(mail)
        return mail

    monkeypatch.setattr(downloader.imaplib, "IMAP4_SSL", make_mail)
    monkeypatch.setattr(downloader, "find_all_mail_folder", lambda _mail: "INBOX")
    monkeypatch.setattr(downloader, "_extract_uidvalidity", lambda *_args: "7")
    account = {"host": "imap.example", "port": 993, "username": "u", "password": "p", "use_ssl": True}
    downloader._open_or_reuse_connection("noop", account, True)
    second = downloader._open_or_reuse_connection("noop", account, True)
    assert second[0] is created[1]


def test_connection_cache_reconnects_on_malformed_or_changed_uidvalidity(monkeypatch):
    downloader._close_all_cached_connections()
    created = []

    class Mail:
        def login(self, *_args):
            pass

        def noop(self):
            return "OK", []

        def response(self, _name):
            return "OK", [b"not-a-uid"] if len(created) == 1 else [b"8"]

        def select(self, *_args, **_kwargs):
            return "OK", {"UIDVALIDITY": [b"7"]}

        def shutdown(self):
            pass

    def make_mail(*_args, **_kwargs):
        mail = Mail()
        created.append(mail)
        return mail

    monkeypatch.setattr(downloader.imaplib, "IMAP4_SSL", make_mail)
    monkeypatch.setattr(downloader, "find_all_mail_folder", lambda _mail: "INBOX")
    monkeypatch.setattr(downloader, "_extract_uidvalidity", lambda *_args: "7")
    account = {"host": "imap.example", "port": 993, "username": "u", "password": "p", "use_ssl": True}
    downloader._open_or_reuse_connection("uid", account, True)
    second = downloader._open_or_reuse_connection("uid", account, True)
    assert second[0] is created[1]
