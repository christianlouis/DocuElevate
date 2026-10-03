"""HTTP regression coverage for the Evergreen native mobile compatibility slice."""

import hashlib
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy.orm import sessionmaker

from app import auth
from app.models import EvergreenMobileToken, FileRecord


@pytest.fixture
def mobile_client(client, db_session, monkeypatch, tmp_path):
    """Use the real HTTP app with auth routes enabled and a test-local token DB."""
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth.settings, "admin_username", "admin")
    monkeypatch.setattr(auth.settings, "admin_password", "secret")
    token_session = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    monkeypatch.setattr(auth, "SessionLocal", token_session)
    monkeypatch.setattr("app.api.mobile.SessionLocal", token_session)
    monkeypatch.setattr(auth.settings, "workdir", str(tmp_path))
    routes = {route.path for route in client.app.routes}
    added_routes = []
    if "/login" not in routes:
        for path, endpoint, methods, name in [
            ("/login", auth.login, ["GET"], None),
            ("/auth", auth.auth, ["POST"], None),
            ("/oauth-login", auth.oauth_login, ["GET"], None),
            ("/oauth-callback", auth.oauth_callback, ["GET"], "oauth_callback"),
            ("/logout", auth.logout, ["GET"], None),
        ]:
            client.app.add_api_route(path, endpoint, methods=methods, name=name)
            added_routes.append(next(route for route in reversed(client.app.routes) if route.path == path))
    try:
        yield client, db_session
    finally:
        for route in added_routes:
            if route in client.app.routes:
                client.app.routes.remove(route)


def _local_token(mobile_client):
    client, _ = mobile_client
    response = client.get("/login?mobile=1&redirect_uri=docuelevate://callback")
    assert response.status_code == 200
    response = client.post(
        "/auth",
        data={"username": "admin", "password": "secret", "mobile": "1", "redirect_uri": "docuelevate://callback"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    return response.headers["location"].split("?token=", 1)[1]


@pytest.mark.parametrize(
    "callback",
    [
        "https://evil.example/callback",
        "docuelevate://other",
        "docuelevate://callback?token=evil",
        "docuelevate://callback#fragment",
        "docuelevate://user@callback",
        "exp://localhost:bad/callback",
        "exp://[broken/callback",
        "",
    ],
)
def test_invalid_callback_is_json_error(mobile_client, callback):
    client, _ = mobile_client
    response = client.get("/login", params={"mobile": "1", "redirect_uri": callback})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid mobile callback"


def test_mobile_marker_survives_bad_local_login(mobile_client):
    client, _ = mobile_client
    client.get("/login?mobile=1&redirect_uri=docuelevate://callback")
    failed = client.post("/auth", data={"username": "admin", "password": "wrong"}, follow_redirects=False)
    assert failed.status_code == 302
    retry = client.get(failed.headers["location"])
    assert retry.status_code == 200
    assert 'name="mobile"' in retry.text
    success = client.post(
        "/auth",
        data={"username": "admin", "password": "secret", "mobile": "1", "redirect_uri": "docuelevate://callback"},
        follow_redirects=False,
    )
    assert success.status_code == 302
    assert "docuelevate://callback?token=" in success.headers["location"]


def test_mocked_oauth_callback_issues_native_token(mobile_client, monkeypatch):
    client, _ = mobile_client
    client.get("/login?mobile=1&redirect_uri=docuelevate://callback")
    from starlette.responses import RedirectResponse

    mocked_client = SimpleNamespace(
        authorize_redirect=AsyncMock(return_value=RedirectResponse("https://idp.example/authorize", status_code=302)),
        authorize_access_token=AsyncMock(
            return_value={"userinfo": {"sub": "oidc-1", "email": "user@example.test", "name": "Native User"}}
        ),
    )
    monkeypatch.setattr(auth, "OAUTH_CONFIGURED", True)
    monkeypatch.setattr(auth, "oauth", SimpleNamespace(authentik=mocked_client))
    start = client.get("/oauth-login", follow_redirects=False)
    assert start.status_code == 302
    assert start.headers["location"] == "https://idp.example/authorize"
    mocked_client.authorize_redirect.assert_awaited_once()
    response = client.get("/oauth-callback?code=mock", follow_redirects=False)
    assert response.status_code == 302
    assert "docuelevate://callback?token=" in response.headers["location"]
    token = parse_qs(urlsplit(response.headers["location"]).query)["token"][0]
    client.cookies.clear()
    profile = client.get("/api/mobile/whoami", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200
    assert profile.json()["owner_id"] == "oidc-1"
    assert profile.json()["email"] == "user@example.test"
    assert profile.json()["is_admin"] is False


def test_local_login_token_identity_files_upload_and_revoke(mobile_client, monkeypatch):
    client, db = mobile_client
    token = _local_token(mobile_client)
    record = db.query(EvergreenMobileToken).one()
    assert record.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert record.token_hash != token
    remaining = record.expires_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(days=29) < remaining <= timedelta(days=30)

    client.cookies.clear()
    assert client.get("/api/mobile/whoami").status_code == 401
    headers = {"Authorization": f"Bearer {token}"}
    profile = client.get("/api/mobile/whoami", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["owner_id"] == "admin"
    assert profile.json()["is_admin"] is True

    assert client.get("/api/files", headers=headers).status_code == 200
    document = FileRecord(
        filehash="existing-document",
        original_filename="existing.txt",
        local_filename="existing.txt",
        file_size=1,
    )
    db.add(document)
    db.commit()
    detail = client.get(f"/api/files/{document.id}", headers=headers)
    assert detail.status_code == 200
    assert {"file", "processing_status", "logs", "files_on_disk"} <= detail.json().keys()

    class FakeTask:
        id = "mobile-test-task"

    monkeypatch.setattr("app.api.files.process_document", FakeTask())
    monkeypatch.setattr("app.api.files.convert_to_pdf", FakeTask())
    FakeTask.delay = lambda *args, **kwargs: FakeTask()
    upload = client.post("/api/ui-upload", headers=headers, files={"file": ("a.txt", BytesIO(b"hello"), "text/plain")})
    assert upload.status_code in {200, 202}
    assert client.post("/api/i18n/language", headers=headers, json={"language": "de"}).status_code == 200
    assert client.post("/api/i18n/language", headers=headers, content="broken JSON").status_code == 400
    assert client.get("/api/mobile/whoami", headers=headers).json()["preferred_language"] == "de"
    assert client.post("/api/auth/mobile/revoke", headers=headers).status_code == 200
    assert client.get("/api/mobile/whoami", headers=headers).status_code == 401


def test_expired_and_wrong_tokens_are_rejected(mobile_client):
    client, db = mobile_client
    token = _local_token(mobile_client)
    client.cookies.clear()
    row = db.query(EvergreenMobileToken).first()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/mobile/whoami", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get("/api/mobile/whoami", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_mobile_bearer_does_not_unlock_admin_api(mobile_client):
    client, _ = mobile_client
    token = _local_token(mobile_client)
    client.cookies.clear()
    response = client.get("/api/settings", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code in {401, 403}


def test_create_all_is_idempotent_and_preserves_token_rows(mobile_client):
    client, db = mobile_client
    token = _local_token(mobile_client)
    from app.database import Base

    db.add(FileRecord(filehash="legacy", original_filename="legacy.txt", local_filename="legacy.txt", file_size=1))
    db.commit()
    Base.metadata.create_all(bind=db.get_bind())
    Base.metadata.create_all(bind=db.get_bind())
    assert db.query(EvergreenMobileToken).count() == 1
    assert db.query(FileRecord).one().original_filename == "legacy.txt"
    client.cookies.clear()
    assert client.get("/api/mobile/whoami", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_fresh_web_login_discards_abandoned_mobile_callback(mobile_client):
    client, db = mobile_client
    client.get("/login?mobile=1&redirect_uri=docuelevate://callback")
    client.get("/login")
    response = client.post("/auth", data={"username": "admin", "password": "secret"}, follow_redirects=False)
    assert response.headers["location"] == "/upload"
    assert db.query(EvergreenMobileToken).count() == 0


@pytest.mark.parametrize("login_method", ["local", "oauth"])
def test_mobile_token_failure_returns_safe_callback(mobile_client, monkeypatch, login_method):
    client, _ = mobile_client
    client.get("/login?mobile=1&redirect_uri=docuelevate://callback")

    def failed_issue(_user):
        raise RuntimeError("private database diagnostics")

    monkeypatch.setattr(auth, "issue_mobile_token", failed_issue)
    if login_method == "local":
        response = client.post("/auth", data={"username": "admin", "password": "secret"}, follow_redirects=False)
    else:
        mocked_client = SimpleNamespace(
            authorize_access_token=AsyncMock(return_value={"userinfo": {"sub": "oidc-1", "email": "user@example.test"}})
        )
        monkeypatch.setattr(auth, "oauth", SimpleNamespace(authentik=mocked_client))
        response = client.get("/oauth-callback?code=mock", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "docuelevate://callback?error=mobile_token_failed"
    assert "private database diagnostics" not in response.text


def test_oauth_state_failure_never_issues_mobile_token(mobile_client, monkeypatch):
    from authlib.integrations.base_client.errors import MismatchingStateError

    client, db = mobile_client
    client.get("/login?mobile=1&redirect_uri=docuelevate://callback")
    mocked_client = SimpleNamespace(authorize_access_token=AsyncMock(side_effect=MismatchingStateError()))
    monkeypatch.setattr(auth, "oauth", SimpleNamespace(authentik=mocked_client))
    response = client.get("/oauth-callback?code=mock&state=wrong", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("/login?error=")
    assert db.query(EvergreenMobileToken).count() == 0
    assert client.get("/api/mobile/whoami").status_code == 401
