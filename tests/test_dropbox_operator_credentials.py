"""Dropbox user grants can reuse operator app credentials without copying secrets."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.utils.dropbox_credentials import resolve_dropbox_oauth_credentials


def test_resolves_operator_app_credentials(monkeypatch):
    monkeypatch.setattr(
        "app.utils.dropbox_credentials.settings.dropbox_allow_global_credentials_for_integrations", True
    )
    monkeypatch.setattr("app.utils.dropbox_credentials.settings.dropbox_app_key", "operator-key")
    monkeypatch.setattr("app.utils.dropbox_credentials.settings.dropbox_app_secret", "operator-secret")

    resolved = resolve_dropbox_oauth_credentials({"refresh_token": "user-grant", "use_global_app_secret": True})

    assert resolved == ("operator-key", "operator-secret", "user-grant")


def test_rejects_operator_mode_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.utils.dropbox_credentials.settings.dropbox_allow_global_credentials_for_integrations", False
    )

    with pytest.raises(ValueError, match="not enabled"):
        resolve_dropbox_oauth_credentials({"refresh_token": "user-grant", "use_global_app_secret": True})


def test_corpus_client_uses_operator_app_credentials(monkeypatch):
    monkeypatch.setattr(
        "app.utils.dropbox_credentials.settings.dropbox_allow_global_credentials_for_integrations", True
    )
    monkeypatch.setattr("app.utils.dropbox_credentials.settings.dropbox_app_key", "operator-key")
    monkeypatch.setattr("app.utils.dropbox_credentials.settings.dropbox_app_secret", "operator-secret")
    integration = SimpleNamespace(credentials="encrypted")
    client = MagicMock()

    with (
        patch(
            "app.tasks.dropbox_corpus_import._decode",
            return_value={"refresh_token": "grant", "use_global_app_secret": True},
        ),
        patch("dropbox.Dropbox", return_value=client) as dropbox_client,
    ):
        from app.tasks.dropbox_corpus_import import _dropbox_client

        assert _dropbox_client(integration) is client

    dropbox_client.assert_called_once_with(
        oauth2_refresh_token="grant",
        app_key="operator-key",
        app_secret="operator-secret",
    )
