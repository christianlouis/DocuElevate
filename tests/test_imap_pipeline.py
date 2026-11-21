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
            structure = b'("APPLICATION" "PDF" NIL NIL NIL "BASE64" 12)' if uid == 2 else b'("TEXT" "PLAIN" NIL NIL NIL "7BIT" 12 1)'
            rows.append(f"{uid} FETCH (UID {uid} BODYSTRUCTURE ".encode() + structure + b")")
        return "OK", rows


@pytest.mark.unit
def test_initial_backlog_then_new_arrival_uses_fixed_boundary(pipeline_session):
    db_session = pipeline_session
    mail = FakeMail([1, 2, 3])
    first = scan_lane_windows(mail, account_ref="a", owner_key="o", mailbox_key="m", uidvalidity="7", folder="INBOX", deadline=10**9, uidnext=4)
    assert first["backlog_scanned"] == 3
    assert mail.searches == ["1:3"]

    mail.present.append(4)
    second = scan_lane_windows(mail, account_ref="a", owner_key="o", mailbox_key="m", uidvalidity="7", folder="INBOX", deadline=10**9, uidnext=5)
    assert second["new_scanned"] == 1
    assert mail.searches[-1] == "4:4"
    assert "4:4" not in mail.searches[:-1]
    cursors = db_session.query(ImapPipelineCursor).all()
    assert {c.lane: c.highwater_uid for c in cursors} == {LANE_BACKLOG: 3, LANE_NEW: 3}


@pytest.mark.unit
def test_no_document_is_terminal_and_candidate_has_no_raw_structure(pipeline_session):
    db_session = pipeline_session
    commit_metadata_batch(account_ref="a", owner_key="o", mailbox_key="m", uidvalidity="7", lane=LANE_BACKLOG, examined=[{"uid": 1, "candidate": False}, {"uid": 2, "candidate": True}], last_uid=2, highwater_uid=2)
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
    db_session.add(ImapMessageLedger(owner_key="o", mailbox_key="m", uidvalidity="7", uid=9, state="pending", lane=LANE_BACKLOG, account_ref="a", discovery_state="downloading", is_candidate=True, download_lease_token="keep"))
    db_session.commit()
    commit_metadata_batch(account_ref="a", owner_key="o", mailbox_key="m", uidvalidity="7", lane=LANE_BACKLOG, examined=[{"uid": 9, "candidate": False}], last_uid=9)
    row = db_session.query(ImapMessageLedger).one()
    assert row.discovery_state == "downloading"
    assert row.download_lease_token == "keep"

