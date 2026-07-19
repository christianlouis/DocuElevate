"""Contract tests for authenticated, idempotent document intake."""

from unittest.mock import patch


def _pdf_request(key: str = "legacy:42:abc") -> dict:
    return {
        "data": {"source": "legacy", "idempotency_key": key, "metadata_json": '{"legacy_id": 42}'},
        "files": {"file": ("invoice.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    }


def test_intake_queues_normal_pipeline_and_is_idempotent(client, db_session, tmp_path):
    with (
        patch("app.api.intake.settings.workdir", str(tmp_path)),
        patch("app.api.intake.process_document.delay") as delay,
    ):
        delay.return_value.id = "task-1"
        request = _pdf_request()
        first = client.post("/api/intake/documents", **request)
        second = client.post("/api/intake/documents", **_pdf_request())

    assert first.status_code == 202
    assert first.json()["state"] == "queued"
    assert first.json()["duplicate"] is False
    assert second.status_code == 202
    assert second.json()["intake_id"] == first.json()["intake_id"]
    assert second.json()["duplicate"] is True
    delay.assert_called_once()
    assert len(list(tmp_path.glob("intake_*.pdf"))) == 1


def test_intake_rejects_unsupported_type(client):
    response = client.post(
        "/api/intake/documents",
        data={"source": "legacy", "idempotency_key": "legacy:43:abc"},
        files={"file": ("malware.exe", b"MZ", "application/octet-stream")},
    )
    assert response.status_code == 415


def test_intake_rejects_disallowed_extension_with_allowed_mime_type(client):
    response = client.post(
        "/api/intake/documents",
        data={"source": "legacy", "idempotency_key": "legacy:43:mime-spoof"},
        files={"file": ("malware.exe", b"MZ", "application/pdf")},
    )
    assert response.status_code == 415


def test_intake_shared_secret_authentication(client, tmp_path):
    with (
        patch("app.api.intake.settings.auth_enabled", True),
        patch("app.api.intake.settings.document_intake_shared_secret", "correct-secret"),
        patch("app.api.intake.settings.workdir", str(tmp_path)),
        patch("app.api.intake.process_document.delay") as delay,
    ):
        delay.return_value.id = "task-2"
        denied = client.post("/api/intake/documents", **_pdf_request("legacy:44:abc"))
        allowed = client.post(
            "/api/intake/documents",
            headers={"X-DocuElevate-Intake-Secret": "correct-secret"},
            **_pdf_request("legacy:45:abc"),
        )

    assert denied.status_code == 401
    assert allowed.status_code == 202


def test_intake_rejects_invalid_metadata_before_writing(client, tmp_path):
    with patch("app.api.intake.settings.workdir", str(tmp_path)):
        response = client.post(
            "/api/intake/documents",
            data={"source": "legacy", "idempotency_key": "legacy:46:abc", "metadata_json": "[]"},
            files={"file": ("invoice.pdf", b"%PDF-1.4", "application/pdf")},
        )
    assert response.status_code == 422
    assert not list(tmp_path.iterdir())


def test_index_only_non_pdf_bypasses_conversion_pipeline():
    with (
        patch("app.api.intake.process_document.apply_async") as process_async,
        patch("app.api.intake.convert_to_pdf.delay") as convert_delay,
    ):
        from app.api.intake import _queue_document

        _queue_document(
            "/workdir/notes.docx",
            "notes.docx",
            None,
            "owner",
            index_only=True,
            task_id="source-task",
        )

    process_async.assert_called_once_with(
        args=["/workdir/notes.docx"],
        kwargs={"original_filename": "notes.docx", "owner_id": "owner", "index_only": True},
        task_id="source-task",
    )
    convert_delay.assert_not_called()
