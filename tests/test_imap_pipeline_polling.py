"""Contract tests for the IMAP pipeline polling hooks."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker


def _mail():
    mail = MagicMock()
    mail.login.return_value = ("OK", [])
    mail.select.return_value = ("OK", [b"1 (UIDVALIDITY 11)"])
    mail.response.side_effect = lambda key: (key, [b"2"] if key == "UIDNEXT" else [b"11"])
    return mail


@pytest.mark.unit
@pytest.mark.parametrize("scan_result", [{"new": 0, "backlog": 0}, RuntimeError("scan failed")])
def test_pipeline_scan_always_publishes_both_lanes_and_keeps_scan_readonly(db_session, scan_result):
    from app.tasks import imap_tasks

    mail = _mail()
    factory = sessionmaker(bind=db_session.get_bind())
    scan = MagicMock()
    if isinstance(scan_result, Exception):
        scan.side_effect = scan_result
    else:
        scan.return_value = scan_result
    publish = MagicMock()

    with (
        patch.object(imap_tasks, "_get_db_session", factory),
        patch.object(imap_tasks.imaplib, "IMAP4_SSL", return_value=mail),
        patch.object(imap_tasks, "is_private_ip", return_value=False),
        patch.object(imap_tasks, "find_all_mail_folder", return_value="INBOX"),
        patch.object(imap_tasks.settings, "imap_pipeline_enabled", True),
        patch.object(imap_tasks.settings, "imap_readonly_mode", False),
        patch("app.imap_pipeline.scan_lane_windows", scan),
        patch("app.imap_pipeline.recover_legacy_candidates", return_value=0),
        patch("app.imap_pipeline.publish_candidate_batches", publish),
    ):
        if isinstance(scan_result, Exception):
            assert not imap_tasks.pull_inbox("account", "imap.example", 993, "user", "pw", True, True)
        else:
            assert imap_tasks.pull_inbox("account", "imap.example", 993, "user", "pw", True, True)

    mail.select.assert_called_once_with("INBOX", readonly=True)
    assert [call.args for call in publish.call_args_list] == [("account", "new"), ("account", "backlog")]
    assert not any(call.args and call.args[0] in {"store", "expunge"} for call in mail.uid.call_args_list)


@pytest.mark.unit
def test_pipeline_connection_failure_does_not_mutate_mailbox(db_session):
    from app.tasks import imap_tasks

    mail = _mail()
    mail.login.side_effect = OSError("connection failed")
    with (
        patch.object(imap_tasks, "_get_db_session", sessionmaker(bind=db_session.get_bind())),
        patch.object(imap_tasks.imaplib, "IMAP4_SSL", return_value=mail),
        patch.object(imap_tasks, "is_private_ip", return_value=False),
        patch.object(imap_tasks.settings, "imap_pipeline_enabled", True),
        patch.object(imap_tasks.settings, "imap_readonly_mode", False),
    ):
        assert not imap_tasks.pull_inbox("account", "imap.example", 993, "user", "pw", True, True)
    mail.expunge.assert_not_called()
    assert not any(call.args and call.args[0] == "store" for call in mail.uid.call_args_list)
