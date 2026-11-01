"""Provider revocation contract tests for account deletion."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.config import settings
from app.services import account_deletion


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter_by(self, **kwargs):
        return self

    def all(self):
        return self.rows


def _db(grant):
    db = Mock()
    db.query.return_value = _Query([grant])
    return db


def _settings(monkeypatch):
    for name, value in {
        "social_auth_apple_key_id": "key-id",
        "social_auth_apple_team_id": "team-id",
        "social_auth_apple_client_id": "client-id",
        "social_auth_apple_private_key": "private-key",
    }.items():
        monkeypatch.setattr(settings, name, value)


def test_apple_grant_is_decrypted_and_revoked(monkeypatch):
    grant = SimpleNamespace(encrypted_token="enc:test")
    _settings(monkeypatch)
    monkeypatch.setattr("app.utils.encryption.decrypt_value", lambda value: "refresh-token")
    encoded = Mock(return_value=b"signed-secret")
    monkeypatch.setattr("authlib.jose.jwt.encode", encoded)
    response = Mock()
    monkeypatch.setattr("requests.post", Mock(return_value=response))

    account_deletion._revoke_apple_grants(_db(grant), "owner-1")

    encoded.assert_called_once()
    request = __import__("requests").post
    request.assert_called_once_with(
        "https://appleid.apple.com/auth/revoke",
        data={
            "client_id": "client-id",
            "client_secret": "signed-secret",
            "token": "refresh-token",
            "token_type_hint": "refresh_token",
        },
        timeout=15,
    )
    response.raise_for_status.assert_called_once_with()


def test_apple_revoke_propagates_provider_error(monkeypatch):
    grant = SimpleNamespace(encrypted_token="enc:test")
    _settings(monkeypatch)
    monkeypatch.setattr("app.utils.encryption.decrypt_value", lambda value: "refresh-token")
    monkeypatch.setattr("authlib.jose.jwt.encode", lambda *args, **kwargs: b"signed")
    response = Mock()
    response.raise_for_status.side_effect = RuntimeError("provider unavailable")
    monkeypatch.setattr("requests.post", Mock(return_value=response))

    with pytest.raises(RuntimeError, match="provider unavailable"):
        account_deletion._revoke_apple_grants(_db(grant), "owner-1")


def test_apple_revoke_does_not_call_provider_when_decryption_fails(monkeypatch):
    grant = SimpleNamespace(encrypted_token="enc:test")
    _settings(monkeypatch)
    monkeypatch.setattr("app.utils.encryption.decrypt_value", lambda value: "enc:test")
    monkeypatch.setattr("authlib.jose.jwt.encode", lambda *args, **kwargs: b"signed")
    post = Mock()
    monkeypatch.setattr("requests.post", post)

    with pytest.raises(RuntimeError, match="decryption"):
        account_deletion._revoke_apple_grants(_db(grant), "owner-1")
    post.assert_not_called()
