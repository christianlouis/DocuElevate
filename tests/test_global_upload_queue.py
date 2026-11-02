"""Focused contract tests for the global, owner-scoped upload queue shell."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.views import base


def _request(owner: str | None) -> SimpleNamespace:
    session = {} if owner is None else {"user": {"sub": owner}, "preferred_language": "en"}
    return SimpleNamespace(session=session, state=SimpleNamespace(), headers={})


@pytest.mark.unit
def test_global_upload_queue_owner_is_hashed_and_isolated(monkeypatch):
    """Each authenticated owner gets a stable opaque browser-storage namespace."""
    monkeypatch.setattr(base.settings, "auth_enabled", True)
    monkeypatch.setattr(base.settings, "multi_user_enabled", True)
    monkeypatch.setattr("app.utils.user_scope.get_current_owner_id", lambda request: request.session["user"]["sub"])

    alice, bob = {"request": _request("alice@example.test")}, {"request": _request("bob@example.test")}
    base._inject_global_context(alice)
    base._inject_global_context(bob)

    assert alice["is_logged_in"] is True
    assert alice["upload_queue_owner"] == hashlib.sha256(b"alice@example.test", usedforsecurity=False).hexdigest()
    assert bob["upload_queue_owner"] == hashlib.sha256(b"bob@example.test", usedforsecurity=False).hexdigest()
    assert alice["upload_queue_owner"] != bob["upload_queue_owner"]
    assert "alice@example.test" not in alice["upload_queue_owner"]
    assert "bob@example.test" not in bob["upload_queue_owner"]


@pytest.mark.unit
def test_global_upload_queue_context_is_not_emitted_for_anonymous_request(monkeypatch):
    monkeypatch.setattr(base.settings, "auth_enabled", True)
    monkeypatch.setattr(base.settings, "multi_user_enabled", True)
    context = {"request": _request(None)}

    base._inject_global_context(context)

    assert context["is_logged_in"] is False
    assert "upload_queue_owner" not in context


@pytest.mark.unit
def test_global_queue_template_keeps_diagnostics_and_reselection_action_in_base_layout():
    template = Path("frontend/templates/base.html").read_text(encoding="utf-8")

    assert "globalUploadQueueDiagnosticsButton" in template
    assert "globalUploadQueueDiagnosticsPanel" in template
    assert "globalUploadQueueAddFiles" in template
    assert "globalUploadQueueFileInput" in template
    assert "speichert nur Metadaten" in template
    assert template.index("{% block scripts %}") < template.index("/static/js/upload-bulk.js")
