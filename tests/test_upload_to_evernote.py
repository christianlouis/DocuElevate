import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.tasks.upload_to_evernote import _build_enml, upload_to_evernote


class _FakeTypes:
    class Data:
        pass

    class Resource:
        pass

    class ResourceAttributes:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    class Note:
        pass


class _FakeNoteStore:
    def __init__(self):
        self.calls = []

    def createNote(self, auth_token, note):
        self.calls.append((auth_token, note))
        note.guid = "note-guid-123"
        return note


_fake_note_store = _FakeNoteStore()


@pytest.fixture(autouse=True)
def reset_fake_store():
    global _fake_note_store
    _fake_note_store = _FakeNoteStore()


def test_build_enml_escapes_metadata():
    enml = _build_enml({"sender": "A&B <Corp>"}, "abc123", "application/pdf", include_metadata=True)

    assert "A&amp;B &lt;Corp&gt;" in enml
    assert '<en-media type="application/pdf" hash="abc123"/>' in enml


@pytest.mark.unit
def test_upload_to_evernote_creates_note_with_metadata_and_pdf(tmp_path):
    pdf_path = tmp_path / "invoice.pdf"
    pdf_bytes = b"%PDF-1.4 test content"
    pdf_path.write_bytes(pdf_bytes)
    pdf_path.with_suffix(".json").write_text(
        json.dumps(
            {
                "title": "Invoice May",
                "absender": "Example GmbH",
                "tags": ["invoice", "finance"],
                "empty": "Unknown",
            }
        ),
        encoding="utf-8",
    )

    with (
        patch("app.tasks.upload_to_evernote._get_note_store", return_value=(_fake_note_store, _FakeTypes)),
        patch("app.tasks.upload_to_evernote.log_task_progress"),
        patch("app.tasks.upload_to_evernote.settings") as mock_settings,
    ):
        mock_settings.evernote_auth_token = "auth-token"
        mock_settings.evernote_sandbox = True
        mock_settings.evernote_notebook_guid = "notebook-guid"
        mock_settings.evernote_default_tags = "docuelevate,archive"
        mock_settings.evernote_include_metadata = True

        result = upload_to_evernote.apply(args=[str(pdf_path)], kwargs={"file_id": 7}).get()

    created_note = _fake_note_store.calls[0][1]
    resource = created_note.resources[0]

    assert result["status"] == "Completed"
    assert result["evernote_note_guid"] == "note-guid-123"
    assert created_note.title == "Invoice May"
    assert created_note.notebookGuid == "notebook-guid"
    assert created_note.tagNames == ["docuelevate", "archive", "invoice", "finance"]
    assert "Example GmbH" in created_note.content
    assert "empty" not in created_note.content
    assert f'hash="{hashlib.md5(pdf_bytes).hexdigest()}"' in created_note.content  # noqa: S324
    assert resource.mime == "application/pdf"
    assert resource.attributes.fileName == "invoice.pdf"
    assert resource.data.body == pdf_bytes
    assert resource.data.bodyHash == hashlib.md5(pdf_bytes).digest()  # noqa: S324


@pytest.mark.unit
def test_upload_to_evernote_requires_token(tmp_path):
    pdf_path = tmp_path / "document.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    with (
        patch("app.tasks.upload_to_evernote.log_task_progress"),
        patch("app.tasks.upload_to_evernote.settings", SimpleNamespace(evernote_auth_token=None)),
    ):
        result = upload_to_evernote.apply(args=[str(pdf_path)])

    assert result.failed()
    assert isinstance(result.result, ValueError)
    assert "EVERNOTE_AUTH_TOKEN" in str(result.result)
