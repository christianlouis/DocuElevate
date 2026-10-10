"""Focused coverage for newly added security boundary branches."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request


def _request(*, scheme="https"):
    return Request(
        {
            "type": "http",
            "scheme": scheme,
            "server": ("example.test", 443 if scheme == "https" else 80),
            "path": "/",
            "headers": [],
        }
    )


def test_audit_admin_helper_returns_verified_user():
    from app.api import audit_logs

    with patch.object(audit_logs, "get_current_user", return_value={"is_admin": True}) as current_user:
        assert audit_logs._require_admin(_request()) == {"is_admin": True}
    current_user.assert_called_once()


def test_automation_target_validation_rejects_invalid_and_private_urls():
    from app.api import automation

    with pytest.raises(HTTPException, match="public HTTP"):
        automation._validate_target_url("file:///etc/passwd")
    with patch.object(automation, "is_private_ip", return_value=True):
        with pytest.raises(HTTPException, match="Private or local"):
            automation._validate_target_url("https://internal.example.test/hook")


def test_automation_hook_response_handles_malformed_events():
    from app.api.automation import _hook_to_response

    hook = MagicMock(id=7, target_url="https://hooks.example.test", events="not-json", is_active=True)
    assert _hook_to_response(hook)["events"] == []


def test_automation_mutations_require_stable_owner():
    from app.api import automation

    body = automation.HookSubscribe(target_url="https://hooks.example.test", events=["document.uploaded"])
    db = MagicMock()
    with (
        patch.object(automation, "get_event_owner_id", return_value=None),
        patch.object(automation, "is_private_ip", return_value=False),
    ):
        for call in (
            lambda: automation.subscribe_hook(body, db, {}),
            lambda: automation.unsubscribe_hook(1, db, {}),
            lambda: automation.list_hooks(db, {}),
        ):
            with pytest.raises(HTTPException, match="stable owner"):
                call()


@pytest.mark.asyncio
async def test_onedrive_exchange_rejects_invalid_state_before_consuming_transaction():
    from app.api import onedrive

    request = _request()
    request.scope["session"] = {}
    request.session["onedrive_oauth"] = {"state": "expected", "owner_id": "owner", "integration_id": None}
    with patch.object(onedrive, "get_current_owner_id", return_value="owner"):
        with pytest.raises(HTTPException, match="Invalid or expired"):
            await onedrive.exchange_onedrive_token(request, state="wrong", integration_id=None, db=MagicMock())


def test_onedrive_tenant_validation_rejects_injection():
    from app.api.onedrive import _valid_tenant_id

    assert _valid_tenant_id("common")
    assert not _valid_tenant_id("common/../../admin")


@pytest.mark.asyncio
async def test_qr_challenge_requires_https_origin():
    from app.api import qr_auth

    with patch.object(qr_auth.settings, "qr_login_enabled", True):
        with pytest.raises(HTTPException, match="HTTPS server origin"):
            await qr_auth.create_challenge(_request(scheme="http"), "owner", MagicMock())


def test_backfill_budget_fails_closed_for_invalid_values():
    from app.tasks import dropbox_corpus_import as importer

    integration = MagicMock()
    with patch.object(importer.settings, "corpus_backfill_daily_llm_token_budget", "invalid"):
        with pytest.raises(importer.CorpusDailyBudgetUnavailable, match="invalid"):
            importer._configured_backfill_token_budget(integration)
    with patch.object(importer.settings, "corpus_backfill_daily_llm_token_budget", -1):
        with pytest.raises(importer.CorpusDailyBudgetUnavailable, match="Negative"):
            importer._configured_backfill_token_budget(integration)
