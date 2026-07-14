"""Contract tests for the optional Evergreen-to-preprod document bridge."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch


def _record() -> SimpleNamespace:
    return SimpleNamespace(
        id=42,
        filehash="abc123",
        owner_id=None,
        original_filename="invoice.pdf",
        document_title="Invoice",
        mime_type="application/pdf",
        created_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )


def test_bridge_sends_intake_contract_with_bearer_token(tmp_path):
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"%PDF-1.4")

    with (
        patch("app.utils.document_bridge.settings.document_bridge_url", "https://preprod.example/api/intake/documents"),
        patch("app.utils.document_bridge.settings.document_bridge_bearer_token", "secret-token"),
        patch("app.utils.document_bridge.settings.document_bridge_shared_secret", None),
        patch("app.utils.document_bridge.settings.document_bridge_source", "legacy-prod"),
        patch("app.utils.document_bridge._resolve_public_address", return_value="203.0.113.10"),
        patch("app.utils.document_bridge._send_pinned_post", return_value=(True, 202)) as send,
    ):
        from app.utils.document_bridge import deliver_document

        assert deliver_document(_record(), str(source)) == 202

    _parsed, _address, body, headers = send.call_args.args
    assert headers["Authorization"] == "Bearer secret-token"
    assert b'name="source"' in body
    assert b"legacy-prod" in body
    assert b'name="idempotency_key"' in body
    assert b"legacy-prod:42:abc123" in body
    assert b'filename="invoice.pdf"' in body
    assert body.count(b"%PDF-1.4") == 1


def test_bridge_uses_shared_secret_when_token_absent(tmp_path):
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"%PDF")
    with (
        patch("app.utils.document_bridge.settings.document_bridge_url", "https://preprod.example/intake"),
        patch("app.utils.document_bridge.settings.document_bridge_bearer_token", None),
        patch("app.utils.document_bridge.settings.document_bridge_shared_secret", "bridge-secret"),
        patch("app.utils.document_bridge._resolve_public_address", return_value="203.0.113.10"),
        patch("app.utils.document_bridge._send_pinned_post", return_value=(True, 202)) as send,
    ):
        from app.utils.document_bridge import deliver_document

        deliver_document(_record(), str(source))

    assert send.call_args.args[3]["X-DocuElevate-Intake-Secret"] == "bridge-secret"


def test_bridge_rejects_non_https_target(tmp_path):
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"%PDF")
    with patch("app.utils.document_bridge.settings.document_bridge_url", "http://preprod.example/intake"):
        from app.utils.document_bridge import DocumentBridgeError, deliver_document

        try:
            deliver_document(_record(), str(source))
        except DocumentBridgeError as exc:
            assert "HTTPS" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("Expected insecure bridge URL to be rejected")
