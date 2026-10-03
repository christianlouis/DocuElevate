"""Regression coverage for the evergreen global-integration backport."""

from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


@pytest.mark.unit
@pytest.mark.parametrize(
    ("module_name", "helper_name"),
    [
        ("app.api.dropbox", "_require_admin"),
        ("app.api.google_drive", "_require_admin"),
        ("app.api.onedrive", "_require_admin"),
    ],
)
def test_global_integration_settings_require_admin(monkeypatch, module_name, helper_name):
    """A normal authenticated session cannot change global provider secrets."""
    module = __import__(module_name, fromlist=[helper_name])
    monkeypatch.setattr(module, "AUTH_ENABLED", True)
    request = SimpleNamespace(session={"user": {"is_admin": False}})

    with pytest.raises(HTTPException) as exc_info:
        getattr(module, helper_name)(request)

    assert exc_info.value.status_code == 403


@pytest.mark.unit
def test_global_integration_routes_require_admin(monkeypatch, client: TestClient):
    """The mounted HTTP routes must enforce the admin dependency, not only helpers."""
    modules = [
        __import__(name, fromlist=["AUTH_ENABLED"])
        for name in ("app.api.dropbox", "app.api.google_drive", "app.api.onedrive")
    ]
    for module in modules:
        monkeypatch.setattr(module, "AUTH_ENABLED", True)

    routes = [
        ("post", "/api/dropbox/update-settings", {"refresh_token": "attacker"}),
        ("post", "/api/dropbox/save-settings", {"refresh_token": "attacker"}),
        ("post", "/api/google-drive/update-settings", {"refresh_token": "attacker"}),
        ("post", "/api/google-drive/save-settings", {"refresh_token": "attacker"}),
        ("post", "/api/onedrive/update-settings", {"refresh_token": "attacker"}),
        ("post", "/api/onedrive/save-settings", {"refresh_token": "attacker"}),
        ("get", "/api/onedrive/get-full-config", None),
    ]

    for method, path, data in routes:
        response = getattr(client, method)(path, data=data) if method == "post" else client.get(path)
        assert response.status_code == 403, (method, path, response.text)


@pytest.mark.unit
def test_global_token_routes_require_admin(monkeypatch, client: TestClient):
    """Provider token checks and token-info cannot mutate or expose global secrets."""
    modules = [
        __import__(name, fromlist=["AUTH_ENABLED"])
        for name in ("app.api.dropbox", "app.api.google_drive", "app.api.onedrive")
    ]
    for module in modules:
        monkeypatch.setattr(module, "AUTH_ENABLED", True)

    for path in (
        "/api/dropbox/test-token",
        "/api/google-drive/test-token",
        "/api/google-drive/get-token-info",
        "/api/onedrive/test-token",
    ):
        response = client.get(path)
        assert response.status_code == 403, (path, response.text)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("module_name", "view_name", "secret_key", "refresh_key"),
    [
        (
            "app.views.google_drive",
            "google_drive_setup_page",
            "google_drive_client_secret",
            "google_drive_refresh_token",
        ),
        ("app.views.dropbox", "dropbox_setup_page", "dropbox_app_secret", "dropbox_refresh_token"),
        ("app.views.onedrive", "onedrive_setup_page", "onedrive_client_secret", "onedrive_refresh_token"),
    ],
)
@pytest.mark.asyncio
async def test_provider_setup_pages_do_not_render_global_tokens(
    monkeypatch, module_name, view_name, secret_key, refresh_key
):
    """Setup HTML must contain status flags, never operator OAuth credentials."""
    module = __import__(module_name, fromlist=[view_name])
    monkeypatch.setattr(module.settings, secret_key, "operator-secret")
    monkeypatch.setattr(module.settings, refresh_key, "operator-refresh")
    captured = {}

    def capture(_template, context):
        captured.update(context)
        return context

    monkeypatch.setattr(module.templates, "TemplateResponse", capture)
    request = Mock()
    result = await getattr(module, view_name)(request)

    assert result == captured
    assert captured.get("client_secret_value", captured.get("app_secret_value")) == ""
    if module_name == "app.views.dropbox":
        assert captured["app_secret"] is True
    if "refresh_token_value" in captured:
        assert captured["refresh_token_value"] == ""


@pytest.mark.unit
def test_oauth_setup_forms_allow_server_configured_secret_without_rendering_it():
    """Configured server secrets permit an empty browser field without exposing the value."""
    for name in ("dropbox", "google_drive", "onedrive"):
        source = Path(f"frontend/templates/{name}.html").read_text(encoding="utf-8")
        assert "&& !secretConfigured" in source
        assert "sessionStorage.removeItem" in source
        assert "secretConfigured = {{" in source
        assert "app_secret_value if" not in source
        assert "client_secret_value if" not in source
