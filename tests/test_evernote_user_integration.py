import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

from app.tasks.upload_to_evernote import test_evernote_connection as check_evernote_connection
from app.tasks.upload_to_evernote import upload_to_evernote_integration


class _Types:
    class Data:
        pass

    class Resource:
        pass

    class ResourceAttributes:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class Note:
        pass


class _Store:
    def __init__(self):
        self.calls = []

    def createNote(self, token, note):
        self.calls.append((token, note))
        note.guid = "user-note"
        return note

    def listNotebooks(self, token):
        self.calls.append(("list", token))
        return [SimpleNamespace(guid="notebook-user")]


def test_per_user_upload_does_not_use_global_settings(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")
    pdf.with_suffix(".json").write_text(json.dumps({"tags": ["invoice"]}), encoding="utf-8")
    store = _Store()

    with (
        patch("app.tasks.upload_to_evernote._get_note_store", return_value=(store, _Types)) as get_store,
        patch(
            "app.tasks.upload_to_evernote.settings",
            SimpleNamespace(
                evernote_auth_token="GLOBAL-MUST-NOT-BE-USED",
                evernote_notebook_guid="global-notebook",
                evernote_default_tags="global",
                evernote_include_metadata=False,
                evernote_sandbox=False,
            ),
        ),
    ):
        result = upload_to_evernote_integration(
            str(pdf),
            {"notebook_guid": "user-notebook", "default_tags": "user", "include_metadata": True, "sandbox": True},
            {"auth_token": "USER-TOKEN"},
            "task-1",
        )

    assert result["evernote_note_guid"] == "user-note"
    assert get_store.call_args.kwargs == {"sandbox": True}
    token, note = store.calls[0]
    assert token == "USER-TOKEN"
    assert note.notebookGuid == "user-notebook"
    assert note.tagNames == ["user", "invoice"]


def test_connection_test_reads_notebooks_without_writes():
    store = _Store()
    with patch("app.tasks.upload_to_evernote._get_note_store", return_value=(store, _Types)):
        result = check_evernote_connection(
            {"notebook_guid": "notebook-user", "sandbox": True}, {"auth_token": "USER-TOKEN"}
        )
    assert result["success"] is True
    assert store.calls == [("list", "USER-TOKEN")]


def test_connection_test_redacts_upstream_errors():
    with patch("app.tasks.upload_to_evernote._get_note_store", side_effect=RuntimeError("USER-TOKEN upstream body")):
        result = check_evernote_connection({}, {"auth_token": "USER-TOKEN"})
    assert result["success"] is False
    assert "USER-TOKEN" not in result["message"]
    assert "upstream body" not in result["message"]


def test_upload_error_has_no_raw_exception_chain_or_log(caplog, tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")
    marker = "SDK raw body USER-TOKEN"
    with patch("app.tasks.upload_to_evernote._create_evernote_note", side_effect=RuntimeError(marker)):
        with caplog.at_level(logging.WARNING):
            try:
                upload_to_evernote_integration(str(pdf), {}, {"auth_token": "USER-TOKEN"}, "task-1")
            except RuntimeError as exc:
                assert exc.__cause__ is None
                assert marker not in "".join(__import__("traceback").format_exception(exc))
            else:  # pragma: no cover
                raise AssertionError("expected upload failure")
    assert marker not in caplog.text
    assert "USER-TOKEN" not in caplog.text


def test_user_dispatcher_invokes_evernote_handler(tmp_path):
    from unittest.mock import MagicMock

    from app.models import IntegrationType
    from app.tasks.upload_to_user_integration import upload_to_user_integration

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")
    row = MagicMock(
        id=12,
        integration_type=IntegrationType.EVERNOTE,
        owner_id="owner@example.com",
        name="personal Evernote",
        config=json.dumps({"sandbox": True}),
        credentials=json.dumps({"auth_token": "USER-TOKEN"}),
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [row, row]
    with (
        patch("app.tasks.upload_to_user_integration.SessionLocal") as session_local,
        patch("app.tasks.upload_to_user_integration.log_task_progress"),
        patch(
            "app.tasks.upload_to_evernote._create_evernote_note", return_value=SimpleNamespace(guid="guid")
        ) as create,
    ):
        session_local.return_value.__enter__.return_value = db
        upload_to_user_integration.request.id = "task-1"
        result = upload_to_user_integration.__wrapped__(str(pdf), 12, file_id=4)
    assert result["evernote_note_guid"] == "guid"
    assert create.call_args.kwargs["auth_token"] == "USER-TOKEN"
    assert create.call_args.kwargs["sandbox"] is True
