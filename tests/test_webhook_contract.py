"""Tests for the versioned outbound webhook contract."""

import json

import pytest


@pytest.mark.unit
def test_build_payload_includes_contract_version(mocker):
    """Outbound payloads include an explicit envelope version."""
    mocker.patch("app.utils.webhook.time.time", return_value=123.5)

    from app.utils.webhook import WEBHOOK_PAYLOAD_VERSION, build_payload

    payload = build_payload("document.processed", {"file_id": 42})

    assert payload == {
        "version": WEBHOOK_PAYLOAD_VERSION,
        "event": "document.processed",
        "timestamp": 123.5,
        "data": {"file_id": 42},
    }


@pytest.mark.unit
def test_deliver_webhook_sends_signature_and_contract_headers(mocker):
    """Delivery includes signature, event, and payload-version headers."""
    send = mocker.patch("app.utils.webhook._send_pinned_post", return_value=(True, 204))
    mocker.patch("app.utils.webhook._resolve_public_address", return_value="203.0.113.10")

    from app.utils.webhook import compute_signature, deliver_webhook

    payload = {
        "version": "1.0",
        "event": "document.processed",
        "timestamp": 123.5,
        "data": {"file_id": 42},
    }

    assert deliver_webhook("https://hooks.example.com/docuelevate", payload, "secret") is True

    _, _, body_bytes, headers = send.call_args.args
    expected_body = json.dumps(payload, default=str, sort_keys=True).encode("utf-8")
    assert body_bytes == expected_body
    assert headers["Content-Type"] == "application/json"
    assert headers["X-DocuElevate-Event"] == "document.processed"
    assert headers["X-DocuElevate-Webhook-Version"] == "1.0"
    assert headers["X-Webhook-Signature"] == compute_signature(expected_body, "secret")
