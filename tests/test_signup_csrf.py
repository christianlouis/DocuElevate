"""End-to-end CSRF contract for public signup clients."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.api import local_auth
from app.config import settings
from app.middleware.csrf import CSRFMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(local_auth.router)
    # Session must wrap CSRF so the token survives the capability request.
    app.add_middleware(CSRFMiddleware, config=settings)
    app.add_middleware(SessionMiddleware, secret_key="signup-csrf-test-secret")
    return app


def _payload(**overrides: object) -> dict[str, object]:
    value = {
        "email": "new@example.com",
        "username": "new-user",
        "password": "long-password-123",
        "password_confirm": "long-password-123",
        "accept_terms": True,
        "accept_privacy": True,
        "terms_version": local_auth.CURRENT_TERMS_VERSION,
        "privacy_version": local_auth.CURRENT_PRIVACY_VERSION,
    }
    value.update(overrides)
    return value


def test_public_signup_uses_capability_cookie_csrf_roundtrip(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "multi_user_enabled", True)
    monkeypatch.setattr(settings, "allow_local_signup", True)
    monkeypatch.setattr(settings, "email_host", "smtp.example.com")

    with TestClient(_app()) as client:
        capabilities = client.get("/api/auth/capabilities")
        assert capabilities.status_code == 200
        token = capabilities.json()["csrf_token"]
        assert token
        assert client.cookies

        missing = client.post("/api/auth/signup", json=_payload())
        assert missing.status_code == 403
        wrong = client.post("/api/auth/signup", json=_payload(), headers={"X-CSRF-Token": "wrong"})
        assert wrong.status_code == 403

        # A valid token passes middleware and reaches endpoint validation.
        valid = client.post("/api/auth/signup", json=_payload(accept_terms=False), headers={"X-CSRF-Token": token})
        assert valid.status_code == 422
        assert "terms" in valid.json()["detail"].lower()
