"""Tests for the per-user IMAP accounts API (app/api/imap_accounts.py)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import SubscriptionPlan, UserImapAccount, UserProfile

# ---------------------------------------------------------------------------
# Test data constants
# ---------------------------------------------------------------------------

_OWNER = "test_user@example.com"
_BASIC_ACCOUNT = {
    "name": "Test Mailbox",
    "host": "imap.example.com",
    "port": 993,
    "username": "user@example.com",
    "password": "s3cr3t",  # noqa: S105
    "use_ssl": True,
    "delete_after_process": False,
    "is_active": True,
}


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def imap_engine():
    """In-memory SQLite engine for IMAP account tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def imap_session(imap_engine):
    """DB session scoped to one test."""
    Session = sessionmaker(bind=imap_engine)
    session = Session()
    yield session
    session.close()


def _make_client(imap_engine, owner_id: str = _OWNER):
    """Return a TestClient that injects *owner_id* as the authenticated user."""
    from app.api.imap_accounts import _get_owner_id
    from app.main import app

    def override_db():
        Session = sessionmaker(bind=imap_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def override_owner():
        return owner_id

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[_get_owner_id] = override_owner
    return app, override_db, override_owner


def _make_anon_client(imap_engine):
    """Return a TestClient without an authenticated user (401 expected)."""
    from app.main import app

    def override_db():
        Session = sessionmaker(bind=imap_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    return app


@pytest.fixture()
def imap_client(imap_engine):
    """TestClient authenticated as _OWNER."""
    from app.api.imap_accounts import _get_owner_id
    from app.main import app

    def override_db():
        Session = sessionmaker(bind=imap_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def override_owner():
        return _OWNER

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[_get_owner_id] = override_owner
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _make_profile(session, owner: str = _OWNER, tier: str = "starter") -> UserProfile:
    """Create a UserProfile."""
    profile = UserProfile(user_id=owner, subscription_tier=tier)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def _make_plan(session, tier: str = "starter", max_mailboxes: int = 1) -> SubscriptionPlan:
    """Create a SubscriptionPlan row."""
    plan = SubscriptionPlan(
        plan_id=tier,
        name=tier.title(),
        price_monthly=2.99,
        price_yearly=28.99,
        max_mailboxes=max_mailboxes,
        is_active=True,
    )
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


# ---------------------------------------------------------------------------
# Unit tests – quota helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetMaxMailboxes:
    """Unit tests for the _get_max_mailboxes helper."""

    def test_free_tier_returns_zero(self):
        from app.api.imap_accounts import _get_max_mailboxes

        assert _get_max_mailboxes({"id": "free", "max_mailboxes": 0}) == 0

    def test_paid_tier_with_explicit_limit(self):
        from app.api.imap_accounts import _get_max_mailboxes

        assert _get_max_mailboxes({"id": "starter", "max_mailboxes": 1}) == 1

    def test_paid_tier_unlimited(self):
        from app.api.imap_accounts import _get_max_mailboxes

        assert _get_max_mailboxes({"id": "business", "max_mailboxes": 0}) is None

    def test_professional_three(self):
        from app.api.imap_accounts import _get_max_mailboxes

        assert _get_max_mailboxes({"id": "professional", "max_mailboxes": 3}) == 3


# ---------------------------------------------------------------------------
# Integration tests – list endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListImapAccounts:
    """Tests for GET /api/imap-accounts/."""

    def test_list_empty(self, imap_client, imap_session):
        """Listing accounts for a user with none returns empty list."""
        _make_profile(imap_session, tier="starter")
        _make_plan(imap_session, tier="starter", max_mailboxes=1)

        resp = imap_client.get("/api/imap-accounts/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_own_accounts_only(self, imap_client, imap_session):
        """Only the current user's accounts are returned."""
        _make_profile(imap_session, tier="starter")
        _make_plan(imap_session, tier="starter", max_mailboxes=2)

        acct = UserImapAccount(owner_id=_OWNER, name="Mine", host="h", port=993, username="u", password="p")
        other = UserImapAccount(
            owner_id="other@example.com",
            name="Theirs",
            host="h2",
            port=993,
            username="u",
            password="p",
        )
        imap_session.add_all([acct, other])
        imap_session.commit()

        resp = imap_client.get("/api/imap-accounts/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Mine"

    def test_list_requires_authentication(self, imap_engine):
        """Unauthenticated requests return 401."""
        from fastapi import HTTPException, status

        from app.api.imap_accounts import _get_owner_id
        from app.main import app

        def raise_401():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

        def override_db():
            from sqlalchemy.orm import sessionmaker

            Session = sessionmaker(bind=imap_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[_get_owner_id] = raise_401
        try:
            with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as c:
                resp = c.get("/api/imap-accounts/")
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Integration tests – create endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCreateImapAccount:
    """Tests for POST /api/imap-accounts/."""

    def test_create_success(self, imap_client, imap_session):
        """A valid create request returns 201 and the new account."""
        _make_profile(imap_session, tier="starter")
        _make_plan(imap_session, tier="starter", max_mailboxes=2)

        resp = imap_client.post("/api/imap-accounts/", json=_BASIC_ACCOUNT)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == _BASIC_ACCOUNT["name"]
        assert data["host"] == _BASIC_ACCOUNT["host"]
        assert "password" not in data

    def test_create_increments_count(self, imap_client, imap_session):
        """After creation, the count in the database increases."""
        _make_profile(imap_session, tier="starter")
        _make_plan(imap_session, tier="starter", max_mailboxes=2)

        imap_client.post("/api/imap-accounts/", json=_BASIC_ACCOUNT)
        count = imap_session.query(UserImapAccount).filter(UserImapAccount.owner_id == _OWNER).count()
        assert count == 1

    def test_create_blocked_on_free_tier(self, imap_client, imap_session):
        """Free-tier users cannot add any IMAP accounts."""
        _make_profile(imap_session, tier="free")
        _make_plan(imap_session, tier="free", max_mailboxes=0)

        resp = imap_client.post("/api/imap-accounts/", json=_BASIC_ACCOUNT)
        assert resp.status_code == 403
        assert "plan" in resp.json()["detail"].lower()

    def test_create_blocked_at_quota_limit(self, imap_client, imap_session):
        """Users at the quota limit receive a 403."""
        _make_profile(imap_session, tier="starter")
        _make_plan(imap_session, tier="starter", max_mailboxes=1)

        existing = UserImapAccount(owner_id=_OWNER, name="Existing", host="h", port=993, username="u", password="p")
        imap_session.add(existing)
        imap_session.commit()

        resp = imap_client.post("/api/imap-accounts/", json=_BASIC_ACCOUNT)
        assert resp.status_code == 403

    def test_create_unlimited_on_power_tier(self, imap_engine, imap_session):
        """Power-tier users can add multiple accounts (unlimited)."""
        from app.api.imap_accounts import _get_owner_id
        from app.main import app

        def override_db():
            from sqlalchemy.orm import sessionmaker

            Session = sessionmaker(bind=imap_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        def override_owner():
            return _OWNER

        _make_profile(imap_session, tier="business")
        _make_plan(imap_session, tier="business", max_mailboxes=0)

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[_get_owner_id] = override_owner
        try:
            with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as c:
                resp1 = c.post("/api/imap-accounts/", json=_BASIC_ACCOUNT)
                resp2 = c.post("/api/imap-accounts/", json={**_BASIC_ACCOUNT, "name": "Second"})
            assert resp1.status_code == 201
            assert resp2.status_code == 201
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Integration tests – update endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestUpdateImapAccount:
    """Tests for PUT /api/imap-accounts/{id}."""

    def _create_account(self, session, owner: str = _OWNER) -> UserImapAccount:
        acct = UserImapAccount(owner_id=owner, name="Original", host="h", port=993, username="u", password="p")
        session.add(acct)
        session.commit()
        session.refresh(acct)
        return acct

    def test_update_name(self, imap_client, imap_session):
        """Updating name only changes the name."""
        _make_profile(imap_session, tier="starter")
        _make_plan(imap_session, tier="starter", max_mailboxes=1)
        acct = self._create_account(imap_session)

        resp = imap_client.put(f"/api/imap-accounts/{acct.id}", json={"name": "Updated"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"
        assert resp.json()["host"] == "h"

    def test_update_not_found(self, imap_client, imap_session):
        """Updating a non-existent account returns 404."""
        resp = imap_client.put("/api/imap-accounts/9999", json={"name": "x"})
        assert resp.status_code == 404

    def test_cannot_update_other_users_account(self, imap_client, imap_session):
        """A user cannot update another user's account."""
        other_acct = self._create_account(imap_session, owner="other@example.com")
        resp = imap_client.put(f"/api/imap-accounts/{other_acct.id}", json={"name": "Hijacked"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Integration tests – delete endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDeleteImapAccount:
    """Tests for DELETE /api/imap-accounts/{id}."""

    def _create_account(self, session) -> UserImapAccount:
        acct = UserImapAccount(owner_id=_OWNER, name="ToDelete", host="h", port=993, username="u", password="p")
        session.add(acct)
        session.commit()
        session.refresh(acct)
        return acct

    def test_delete_success(self, imap_client, imap_session):
        """Deleting an account returns 204 and removes the DB row."""
        acct = self._create_account(imap_session)

        resp = imap_client.delete(f"/api/imap-accounts/{acct.id}")
        assert resp.status_code == 204

        remaining = imap_session.query(UserImapAccount).filter(UserImapAccount.id == acct.id).first()
        assert remaining is None

    def test_delete_not_found(self, imap_client, imap_session):
        """Deleting a non-existent account returns 404."""
        resp = imap_client.delete("/api/imap-accounts/9999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Integration tests – test-connection endpoints
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestImapConnectionTest:
    """Tests for POST /api/imap-accounts/test and /{id}/test."""

    def test_test_connection_success(self, imap_client, imap_session):
        """A successful IMAP login returns success=True."""
        with patch("app.api.imap_accounts._test_imap_connection") as mock_test:
            mock_test.return_value = {"success": True, "message": "Connection successful"}
            resp = imap_client.post(
                "/api/imap-accounts/test",
                json={
                    "host": "imap.example.com",
                    "port": 993,
                    "username": "u@example.com",
                    "password": "pass",  # noqa: S106
                    "use_ssl": True,
                },
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_test_connection_failure(self, imap_client, imap_session):
        """A failed IMAP login returns success=False with a message."""
        with patch("app.api.imap_accounts._test_imap_connection") as mock_test:
            mock_test.return_value = {
                "success": False,
                "message": "IMAP error: authentication failed",
            }
            resp = imap_client.post(
                "/api/imap-accounts/test",
                json={
                    "host": "imap.example.com",
                    "port": 993,
                    "username": "u@example.com",
                    "password": "wrong",  # noqa: S106
                    "use_ssl": True,
                },
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_test_saved_account(self, imap_client, imap_session):
        """Testing a saved account calls the connection helper with stored credentials."""
        acct = UserImapAccount(
            owner_id=_OWNER,
            name="Saved",
            host="imap.test.com",
            port=993,
            username="u",
            password="p",
        )
        imap_session.add(acct)
        imap_session.commit()
        imap_session.refresh(acct)

        with patch("app.api.imap_accounts._test_imap_connection") as mock_test:
            mock_test.return_value = {"success": True, "message": "Connection successful"}
            resp = imap_client.post(f"/api/imap-accounts/{acct.id}/test")

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_test.assert_called_once_with("imap.test.com", 993, "u", "p", True)


# ---------------------------------------------------------------------------
# Integration tests – quota endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestImapQuota:
    """Tests for GET /api/imap-accounts/quota/."""

    def test_quota_free_tier(self, imap_client, imap_session):
        """Free-tier user reports max_mailboxes=0 and can_add=False."""
        _make_profile(imap_session, tier="free")
        _make_plan(imap_session, tier="free", max_mailboxes=0)

        resp = imap_client.get("/api/imap-accounts/quota/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_mailboxes"] == 0
        assert data["can_add"] is False

    def test_quota_starter_tier(self, imap_client, imap_session):
        """Starter-tier user with no accounts reports can_add=True."""
        _make_profile(imap_session, tier="starter")
        _make_plan(imap_session, tier="starter", max_mailboxes=1)

        resp = imap_client.get("/api/imap-accounts/quota/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_mailboxes"] == 1
        assert data["can_add"] is True
        assert data["current_count"] == 0

    def test_quota_unlimited(self, imap_client, imap_session):
        """Power-tier user reports max_mailboxes=None and can_add=True."""
        _make_profile(imap_session, tier="business")
        _make_plan(imap_session, tier="business", max_mailboxes=0)

        resp = imap_client.get("/api/imap-accounts/quota/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_mailboxes"] is None
        assert data["can_add"] is True


# ---------------------------------------------------------------------------
# Unit tests – _test_imap_connection helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTestImapConnection:
    """Unit tests for the _test_imap_connection helper (no network calls)."""

    def test_success(self):
        """Successful login returns success=True."""
        from app.api.imap_accounts import _test_imap_connection

        mock_mail = MagicMock()
        with (
            patch("app.api.imap_accounts.is_private_ip", return_value=False),
            patch("imaplib.IMAP4_SSL", return_value=mock_mail),
        ):
            result = _test_imap_connection(
                "imap.example.com",
                993,
                "user",
                "pass",
                use_ssl=True,  # noqa: S106
            )

        assert result["success"] is True
        mock_mail.login.assert_called_once_with("user", "pass")
        mock_mail.logout.assert_called_once()

    def test_auth_error(self):
        """An exception raised by IMAP4_SSL returns success=False."""
        from app.api.imap_accounts import _test_imap_connection

        with (
            patch("app.api.imap_accounts.is_private_ip", return_value=False),
            patch("imaplib.IMAP4_SSL", side_effect=Exception("auth failed")),
        ):
            result = _test_imap_connection(
                "imap.example.com",
                993,
                "user",
                "badpass",
                use_ssl=True,  # noqa: S106
            )

        assert result["success"] is False
        assert "auth failed" in result["message"]

    def test_network_error(self):
        """An OSError returns success=False with a network error message."""
        from app.api.imap_accounts import _test_imap_connection

        with (
            patch("app.api.imap_accounts.is_private_ip", return_value=False),
            patch("imaplib.IMAP4", side_effect=OSError("connection refused")),
        ):
            result = _test_imap_connection(
                "bad-host",
                143,
                "user",
                "pass",
                use_ssl=False,  # noqa: S106
            )

        assert result["success"] is False
        assert "connection refused" in result["message"].lower()
