"""Tests for the Devices page and mobile token filtering (app/api/api_tokens.py mobile endpoint).

These tests validate:
- ``GET /api/api-tokens/mobile`` returns only mobile tokens
- ``GET /api/api-tokens/`` excludes mobile tokens
- ``GET /devices`` renders the devices page
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import ApiToken

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_OWNER = "devices_user@example.com"
_OTHER_OWNER = "other_devices@example.com"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dev_engine():
    """In-memory SQLite engine."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def dev_session(dev_engine):
    """DB session scoped to one test."""
    Session = sessionmaker(bind=dev_engine)
    session = Session()
    yield session
    session.close()


def _make_client(dev_engine, owner_id: str = _OWNER) -> TestClient:
    """Return a TestClient with *owner_id* injected as the authenticated user."""
    from app.api.api_tokens import _get_owner_id
    from app.main import app

    Session = sessionmaker(bind=dev_engine)

    def _override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def _override_owner():
        return owner_id

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_get_owner_id] = _override_owner

    client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
    return client


def _cleanup(app):
    """Remove dependency overrides after test."""
    app.dependency_overrides.clear()


def _seed_tokens(session, owner_id: str = _OWNER):
    """Create a mix of regular and mobile tokens for testing."""
    from app.api.api_tokens import generate_api_token, hash_token

    tokens = []
    # Regular API tokens
    for name in ["CI Pipeline", "Webhook Upload"]:
        pt = generate_api_token()
        t = ApiToken(owner_id=owner_id, name=name, token_hash=hash_token(pt), token_prefix=pt[:12])
        session.add(t)
        tokens.append(t)

    # Mobile tokens (various naming patterns)
    for name in [
        "Mobile App – iPhone 15 Pro",
        "Mobile App (QR) – Christian's iPad",
        "Mobile App",
    ]:
        pt = generate_api_token()
        t = ApiToken(owner_id=owner_id, name=name, token_hash=hash_token(pt), token_prefix=pt[:12])
        session.add(t)
        tokens.append(t)

    session.commit()
    return tokens


# ---------------------------------------------------------------------------
# Tests – Mobile Token Filtering
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMobileTokenFiltering:
    """Tests for GET /api/api-tokens/mobile and filtering from GET /api/api-tokens/."""

    def test_list_mobile_tokens_returns_only_mobile(self, dev_engine, dev_session):
        """GET /api/api-tokens/mobile should only return tokens starting with 'Mobile App'."""
        _seed_tokens(dev_session)
        client = _make_client(dev_engine)
        try:
            res = client.get("/api/api-tokens/mobile")
            assert res.status_code == 200
            data = res.json()
            assert len(data) == 3
            for t in data:
                assert t["name"].startswith("Mobile App")
        finally:
            _cleanup(client.app)

    def test_list_regular_tokens_excludes_mobile(self, dev_engine, dev_session):
        """GET /api/api-tokens/ should NOT return tokens starting with 'Mobile App'."""
        _seed_tokens(dev_session)
        client = _make_client(dev_engine)
        try:
            res = client.get("/api/api-tokens/")
            assert res.status_code == 200
            data = res.json()
            assert len(data) == 2
            for t in data:
                assert not t["name"].startswith("Mobile App")
        finally:
            _cleanup(client.app)

    def test_list_mobile_tokens_empty(self, dev_engine):
        """GET /api/api-tokens/mobile returns [] when no mobile tokens exist."""
        client = _make_client(dev_engine)
        try:
            res = client.get("/api/api-tokens/mobile")
            assert res.status_code == 200
            assert res.json() == []
        finally:
            _cleanup(client.app)

    def test_list_mobile_tokens_isolation(self, dev_engine, dev_session):
        """Mobile tokens for other users should not appear."""
        _seed_tokens(dev_session, owner_id=_OTHER_OWNER)
        client = _make_client(dev_engine, owner_id=_OWNER)
        try:
            res = client.get("/api/api-tokens/mobile")
            assert res.status_code == 200
            assert res.json() == []
        finally:
            _cleanup(client.app)

    def test_mobile_token_revoke_via_api_tokens_endpoint(self, dev_engine, dev_session):
        """Mobile tokens can still be revoked via DELETE /api/api-tokens/{id}."""
        tokens = _seed_tokens(dev_session)
        mobile_token = next(t for t in tokens if t.name.startswith("Mobile App"))
        client = _make_client(dev_engine)
        try:
            res = client.delete(f"/api/api-tokens/{mobile_token.id}")
            assert res.status_code == 200
            # Verify it's gone from mobile list
            res2 = client.get("/api/api-tokens/mobile")
            active_names = [t["name"] for t in res2.json() if t["is_active"]]
            assert mobile_token.name not in active_names
        finally:
            _cleanup(client.app)


# ---------------------------------------------------------------------------
# Tests – Devices Page View
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDevicesPageView:
    """Tests for GET /devices page rendering."""

    def test_devices_page_renders(self, dev_engine):
        """GET /devices should return 200 with the devices template."""
        from app.views.devices import router as _  # noqa: F401  – ensures route is registered

        client = _make_client(dev_engine)
        try:
            res = client.get("/devices")
            assert res.status_code == 200
            assert "devices.heading" in res.text or "Mobile Devices" in res.text
        finally:
            _cleanup(client.app)
