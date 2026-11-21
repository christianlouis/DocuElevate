from contextlib import contextmanager

import pytest

from app.imap_pipeline import LANE_BACKLOG, LANE_NEW, commit_metadata_batch, scan_lane_windows
from app.models import ImapMessageLedger, ImapPipelineCursor


@pytest.fixture
def pipeline_session(db_session, monkeypatch):
    ImapPipelineCursor.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    ImapMessageLedger.__table__.create(bind=db_session.get_bind(), checkfirst=True)

    @contextmanager
    def factory():
        yield db_session

    import app.imap_pipeline as pipeline

    monkeypatch.setattr(pipeline, "SessionLocal", factory)
    return db_session


class FakeMail:
    def __init__(self, present):
        self.present = present
        self.searches = []
        self.fetches = []

    def uid(self, command, uid_set, *args):
        if command == "search":
            uid_set = args[-1]
            self.searches.append(uid_set)
            start, end = (int(x) for x in uid_set.split(":", 1))
            return "OK", [b" ".join(str(uid).encode() for uid in self.present if start <= uid <= end)]
        self.fetches.append(uid_set)
        rows = []
        for raw in uid_set.split(","):
            uid = int(raw)
            # UID 2 has a named attachment; all other fixtures are plain text.
            structure = (
                b'("APPLICATION" "PDF" NIL NIL NIL "BASE64" 12)'
                if uid == 2
                else b'("TEXT" "PLAIN" NIL NIL NIL "7BIT" 12 1)'
            )
            rows.append(f"{uid} FETCH (UID {uid} BODYSTRUCTURE ".encode() + structure + b")")
        return "OK", rows


@pytest.mark.unit
def test_initial_backlog_then_new_arrival_uses_fixed_boundary(pipeline_session):
    db_session = pipeline_session
    mail = FakeMail([1, 2, 3])
    first = scan_lane_windows(
        mail,
        account_ref="a",
        owner_key="o",
        mailbox_key="m",
        uidvalidity="7",
        folder="INBOX",
        deadline=10**9,
        uidnext=4,
    )
    assert first["backlog_scanned"] == 3
    assert mail.searches == ["1:3"]

    mail.present.append(4)
    second = scan_lane_windows(
        mail,
        account_ref="a",
        owner_key="o",
        mailbox_key="m",
        uidvalidity="7",
        folder="INBOX",
        deadline=10**9,
        uidnext=5,
    )
    assert second["new_scanned"] == 1
    assert mail.searches[-1] == "4:4"
    assert "4:4" not in mail.searches[:-1]
    cursors = db_session.query(ImapPipelineCursor).all()
    assert {c.lane: c.highwater_uid for c in cursors} == {LANE_BACKLOG: 3, LANE_NEW: 3}


@pytest.mark.unit
def test_empty_initial_mailbox_keeps_zero_boundary_and_new_mail_stays_fresh(pipeline_session):
    db_session = pipeline_session
    mail = FakeMail([])
    initial = scan_lane_windows(
        mail,
        account_ref="a",
        owner_key="o",
        mailbox_key="m",
        uidvalidity="7",
        folder="INBOX",
        deadline=10**9,
        uidnext=1,
    )
    assert initial == {"backlog_scanned": 0, "backlog_candidates": 0, "new_scanned": 0, "new_candidates": 0}

    mail.present.append(1)
    next_run = scan_lane_windows(
        mail,
        account_ref="a",
        owner_key="o",
        mailbox_key="m",
        uidvalidity="7",
        folder="INBOX",
        deadline=10**9,
        uidnext=2,
    )
    assert next_run["new_scanned"] == 1
    assert next_run["backlog_scanned"] == 0
    assert mail.searches == ["1:1"]
    assert db_session.query(ImapMessageLedger).one().lane == LANE_NEW


@pytest.mark.unit
def test_metadata_windows_preserve_every_uid_and_cursor(pipeline_session, monkeypatch):
    db_session = pipeline_session
    monkeypatch.setattr("app.imap_pipeline.settings.imap_pipeline_metadata_batch_size", 100)
    mail = FakeMail(list(range(1, 1002)))
    result = scan_lane_windows(
        mail,
        account_ref="a",
        owner_key="o",
        mailbox_key="m",
        uidvalidity="7",
        folder="INBOX",
        deadline=10**9,
        uidnext=1002,
    )
    assert result["backlog_scanned"] == 1001
    assert result["new_scanned"] == 0
    assert db_session.query(ImapMessageLedger).count() == 1001
    cursor = db_session.query(ImapPipelineCursor).filter_by(lane=LANE_BACKLOG).one()
    assert cursor.last_uid == 1001


@pytest.mark.unit
def test_metadata_commit_failure_rolls_back_cursor_and_ledger(pipeline_session, monkeypatch):
    db_session = pipeline_session

    class FailingCommitSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def __getattr__(self, name):
            return getattr(db_session, name)

        def commit(self):
            db_session.rollback()
            raise RuntimeError("injected commit failure")

    monkeypatch.setattr("app.imap_pipeline.SessionLocal", FailingCommitSession)
    with pytest.raises(RuntimeError, match="injected commit failure"):
        commit_metadata_batch(
            account_ref="a",
            owner_key="o",
            mailbox_key="m",
            uidvalidity="7",
            lane=LANE_BACKLOG,
            examined=[{"uid": 1, "candidate": True}],
            last_uid=1,
        )
    assert db_session.query(ImapMessageLedger).count() == 0
    assert db_session.query(ImapPipelineCursor).count() == 0


@pytest.mark.unit
def test_no_document_is_terminal_and_candidate_has_no_raw_structure(pipeline_session):
    db_session = pipeline_session
    commit_metadata_batch(
        account_ref="a",
        owner_key="o",
        mailbox_key="m",
        uidvalidity="7",
        lane=LANE_BACKLOG,
        examined=[{"uid": 1, "candidate": False}, {"uid": 2, "candidate": True}],
        last_uid=2,
        highwater_uid=2,
    )
    rows = {row.uid: row for row in db_session.query(ImapMessageLedger).all()}
    assert rows[1].state == "completed"
    assert rows[1].is_candidate is False
    assert rows[2].discovery_state == "ready"
    assert rows[2].state == "pending"
    assert rows[2].metadata_json is None
    assert rows[1].scanned_at is not None


@pytest.mark.unit
def test_commit_preserves_inflight_claim_and_cursor_rollback(pipeline_session):
    db_session = pipeline_session
    db_session.add(
        ImapMessageLedger(
            owner_key="o",
            mailbox_key="m",
            uidvalidity="7",
            uid=9,
            state="pending",
            lane=LANE_BACKLOG,
            account_ref="a",
            discovery_state="downloading",
            is_candidate=True,
            download_lease_token="keep",
        )
    )
    db_session.commit()
    commit_metadata_batch(
        account_ref="a",
        owner_key="o",
        mailbox_key="m",
        uidvalidity="7",
        lane=LANE_BACKLOG,
        examined=[{"uid": 9, "candidate": False}],
        last_uid=9,
    )
    row = db_session.query(ImapMessageLedger).one()
    assert row.discovery_state == "downloading"
    assert row.download_lease_token == "keep"
