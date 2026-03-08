"""Tests for document sharing via expiring links (app/api/shared_links.py)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import FileRecord, SharedLink

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_OWNER = "shareuser@example.com"
_OTHER_OWNER = "other@example.com"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sl_engine():
    """In-memory SQLite engine with all tables created."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def sl_session(sl_engine):
    """DB session scoped to one test."""
    Session = sessionmaker(bind=sl_engine)
    session = Session()
    yield session
    session.close()


def _make_file(session, owner_id: str = _OWNER, filename: str = "test.pdf") -> FileRecord:
    """Insert a minimal FileRecord and return it."""
    record = FileRecord(
        owner_id=owner_id,
        filehash="abc123",
        original_filename=filename,
        local_filename="/tmp/test.pdf",
        file_size=1024,
        mime_type="application/pdf",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _make_client(sl_engine, owner_id: str = _OWNER) -> TestClient:
    """Return a TestClient with *owner_id* injected as the authenticated user."""
    from app.api.shared_links import _get_owner_id
    from app.main import app

    Session = sessionmaker(bind=sl_engine)

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


# ---------------------------------------------------------------------------
# Tests – Link CRUD (authenticated)
# ---------------------------------------------------------------------------


class TestCreateSharedLink:
    """Tests for POST /api/shared-links/."""

    @pytest.mark.unit
    def test_create_link_basic(self, sl_engine, sl_session):
        """Creating a link returns the token and share URL."""
        from app.main import app

        file_record = _make_file(sl_session)
        client = _make_client(sl_engine)
        try:
            resp = client.post("/api/shared-links/", json={"file_id": file_record.id})
            assert resp.status_code == 201, resp.text
            data = resp.json()
            assert "token" in data
            assert data["share_url"].startswith("http")
            assert data["token"] in data["share_url"]
            assert data["is_active"] is True
            assert data["has_password"] is False
            assert data["expires_at"] is None
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_create_link_with_expiry(self, sl_engine, sl_session):
        """Creating a link with expires_in_hours sets expires_at."""
        from app.main import app

        file_record = _make_file(sl_session)
        client = _make_client(sl_engine)
        try:
            resp = client.post("/api/shared-links/", json={"file_id": file_record.id, "expires_in_hours": 24})
            assert resp.status_code == 201
            data = resp.json()
            assert data["expires_at"] is not None
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_create_link_with_password(self, sl_engine, sl_session):
        """Creating a link with a password stores a hash (not plaintext)."""
        from app.main import app

        file_record = _make_file(sl_session)
        client = _make_client(sl_engine)
        try:
            resp = client.post("/api/shared-links/", json={"file_id": file_record.id, "password": "secret"})
            assert resp.status_code == 201
            data = resp.json()
            assert data["has_password"] is True
            # Verify plaintext is not stored.
            from app.models import SharedLink

            Session = sessionmaker(bind=sl_engine)
            with Session() as sess:
                db_link = sess.query(SharedLink).filter(SharedLink.token == data["token"]).first()
                assert db_link is not None
                assert db_link.password_hash != "secret"
                assert len(db_link.password_hash) == 64  # hex digest length
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_create_link_with_max_views(self, sl_engine, sl_session):
        """Creating a link with max_views stores the limit."""
        from app.main import app

        file_record = _make_file(sl_session)
        client = _make_client(sl_engine)
        try:
            resp = client.post("/api/shared-links/", json={"file_id": file_record.id, "max_views": 5})
            assert resp.status_code == 201
            assert resp.json()["max_views"] == 5
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_create_link_wrong_file_returns_404(self, sl_engine, sl_session):
        """Creating a link for a non-existent file returns 404."""
        from app.main import app

        client = _make_client(sl_engine)
        try:
            resp = client.post("/api/shared-links/", json={"file_id": 99999})
            assert resp.status_code == 404
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_create_link_other_users_file_returns_404(self, sl_engine, sl_session):
        """Creating a link for another user's file returns 404."""
        from app.main import app

        other_file = _make_file(sl_session, owner_id=_OTHER_OWNER)
        client = _make_client(sl_engine, _OWNER)
        try:
            from app.config import settings

            original = settings.multi_user_enabled
            settings.multi_user_enabled = True
            try:
                resp = client.post("/api/shared-links/", json={"file_id": other_file.id})
                assert resp.status_code == 404
            finally:
                settings.multi_user_enabled = original
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_create_link_with_label(self, sl_engine, sl_session):
        """A label is returned when provided."""
        from app.main import app

        file_record = _make_file(sl_session)
        client = _make_client(sl_engine)
        try:
            resp = client.post("/api/shared-links/", json={"file_id": file_record.id, "label": "For Alice"})
            assert resp.status_code == 201
            assert resp.json()["label"] == "For Alice"
        finally:
            _cleanup(app)


class TestListSharedLinks:
    """Tests for GET /api/shared-links/."""

    @pytest.mark.unit
    def test_list_empty(self, sl_engine):
        """Listing when no links exist returns an empty list."""
        from app.main import app

        client = _make_client(sl_engine)
        try:
            resp = client.get("/api/shared-links/")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_list_returns_own_links(self, sl_engine, sl_session):
        """Listing returns all links created by the current user."""
        from app.main import app

        file_record = _make_file(sl_session)
        client = _make_client(sl_engine)
        try:
            client.post("/api/shared-links/", json={"file_id": file_record.id, "label": "Link A"})
            client.post("/api/shared-links/", json={"file_id": file_record.id, "label": "Link B"})
            resp = client.get("/api/shared-links/")
            assert resp.status_code == 200
            assert len(resp.json()) == 2
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_list_isolation(self, sl_engine, sl_session):
        """Users can only list their own links."""
        from app.main import app

        file_a = _make_file(sl_session, owner_id=_OWNER)
        client_a = _make_client(sl_engine, _OWNER)
        try:
            client_a.post("/api/shared-links/", json={"file_id": file_a.id})
        finally:
            _cleanup(app)

        file_b = _make_file(sl_session, owner_id=_OTHER_OWNER)
        client_b = _make_client(sl_engine, _OTHER_OWNER)
        try:
            resp = client_b.get("/api/shared-links/")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _cleanup(app)


class TestRevokeSharedLink:
    """Tests for DELETE /api/shared-links/{id}."""

    @pytest.mark.unit
    def test_revoke_link(self, sl_engine, sl_session):
        """Revoking a link marks it inactive."""
        from app.main import app

        file_record = _make_file(sl_session)
        client = _make_client(sl_engine)
        try:
            create_resp = client.post("/api/shared-links/", json={"file_id": file_record.id})
            link_id = create_resp.json()["id"]

            resp = client.delete(f"/api/shared-links/{link_id}")
            assert resp.status_code == 200

            list_resp = client.get("/api/shared-links/")
            revoked = [link for link in list_resp.json() if link["id"] == link_id][0]
            assert revoked["is_active"] is False
            assert revoked["revoked_at"] is not None
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_revoke_already_revoked(self, sl_engine, sl_session):
        """Revoking an already-revoked link returns 400."""
        from app.main import app

        file_record = _make_file(sl_session)
        client = _make_client(sl_engine)
        try:
            create_resp = client.post("/api/shared-links/", json={"file_id": file_record.id})
            link_id = create_resp.json()["id"]
            client.delete(f"/api/shared-links/{link_id}")
            resp = client.delete(f"/api/shared-links/{link_id}")
            assert resp.status_code == 400
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_revoke_nonexistent(self, sl_engine):
        """Revoking a non-existent link returns 404."""
        from app.main import app

        client = _make_client(sl_engine)
        try:
            resp = client.delete("/api/shared-links/99999")
            assert resp.status_code == 404
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_revoke_other_users_link(self, sl_engine, sl_session):
        """A user cannot revoke another user's link."""
        from app.main import app

        file_a = _make_file(sl_session, owner_id=_OWNER)
        client_a = _make_client(sl_engine, _OWNER)
        try:
            create_resp = client_a.post("/api/shared-links/", json={"file_id": file_a.id})
            link_id = create_resp.json()["id"]
        finally:
            _cleanup(app)

        client_b = _make_client(sl_engine, _OTHER_OWNER)
        try:
            resp = client_b.delete(f"/api/shared-links/{link_id}")
            assert resp.status_code == 404
        finally:
            _cleanup(app)


# ---------------------------------------------------------------------------
# Tests – Public endpoints
# ---------------------------------------------------------------------------


class TestPublicInfo:
    """Tests for GET /api/share/{token}/info."""

    @pytest.mark.unit
    def test_info_for_valid_link(self, sl_engine, sl_session):
        """Public info endpoint returns metadata for a valid link."""
        from app.main import app

        file_record = _make_file(sl_session, filename="report.pdf")
        client = _make_client(sl_engine)
        try:
            create_resp = client.post(
                "/api/shared-links/",
                json={"file_id": file_record.id, "label": "For Bob"},
            )
            token = create_resp.json()["token"]
        finally:
            _cleanup(app)

        # Public client (no auth override)
        from app.main import app as main_app

        Session = sessionmaker(bind=sl_engine)

        def _override_db():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        main_app.dependency_overrides[get_db] = _override_db
        pub_client = TestClient(main_app, base_url="http://localhost", raise_server_exceptions=False)
        try:
            resp = pub_client.get(f"/api/share/{token}/info")
            assert resp.status_code == 200
            data = resp.json()
            assert data["token"] == token
            assert data["is_valid"] is True
            assert data["original_filename"] == "report.pdf"
            assert data["label"] == "For Bob"
            assert data["has_password"] is False
        finally:
            main_app.dependency_overrides.clear()

    @pytest.mark.unit
    def test_info_for_unknown_token(self, sl_engine):
        """Unknown token returns 404."""
        from app.main import app

        Session = sessionmaker(bind=sl_engine)

        def _override_db():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
        try:
            resp = client.get("/api/share/nonexistenttoken/info")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.unit
    def test_info_shows_has_password(self, sl_engine, sl_session):
        """Info for a password-protected link shows has_password=True."""
        from app.main import app

        file_record = _make_file(sl_session)
        client = _make_client(sl_engine)
        try:
            create_resp = client.post(
                "/api/shared-links/",
                json={"file_id": file_record.id, "password": "hunter2"},
            )
            token = create_resp.json()["token"]
        finally:
            _cleanup(app)

        Session = sessionmaker(bind=sl_engine)

        def _override_db():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _override_db
        pub_client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
        try:
            resp = pub_client.get(f"/api/share/{token}/info")
            assert resp.status_code == 200
            assert resp.json()["has_password"] is True
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.unit
    def test_expired_link_shows_invalid(self, sl_engine, sl_session):
        """An expired link reports is_valid=False in info response."""
        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=1)
        link = SharedLink(
            token="expiredtoken123",
            file_id=_make_file(sl_session).id,
            owner_id=_OWNER,
            expires_at=past,
            view_count=0,
            is_active=True,
        )
        sl_session.add(link)
        sl_session.commit()

        from app.main import app

        Session = sessionmaker(bind=sl_engine)

        def _override_db():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
        try:
            resp = client.get("/api/share/expiredtoken123/info")
            assert resp.status_code == 200
            assert resp.json()["is_valid"] is False
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.unit
    def test_view_limit_reached_shows_invalid(self, sl_engine, sl_session):
        """A link that has reached its view limit reports is_valid=False."""
        link = SharedLink(
            token="limitedtoken456",
            file_id=_make_file(sl_session).id,
            owner_id=_OWNER,
            max_views=3,
            view_count=3,
            is_active=True,
        )
        sl_session.add(link)
        sl_session.commit()

        from app.main import app

        Session = sessionmaker(bind=sl_engine)

        def _override_db():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
        try:
            resp = client.get("/api/share/limitedtoken456/info")
            assert resp.status_code == 200
            assert resp.json()["is_valid"] is False
        finally:
            app.dependency_overrides.clear()


class TestPublicDownload:
    """Tests for GET /api/share/{token}/download."""

    @pytest.mark.unit
    def test_download_no_file_on_disk_returns_404(self, sl_engine, sl_session):
        """Download endpoint returns 404 when file not on disk."""
        link = SharedLink(
            token="dltoken001",
            file_id=_make_file(sl_session, filename="missing.pdf").id,
            owner_id=_OWNER,
            view_count=0,
            is_active=True,
        )
        sl_session.add(link)
        sl_session.commit()

        from app.main import app

        Session = sessionmaker(bind=sl_engine)

        def _override_db():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
        try:
            resp = client.get("/api/share/dltoken001/download")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.unit
    def test_download_expired_returns_410(self, sl_engine, sl_session):
        """Download endpoint returns 410 when link has expired."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        link = SharedLink(
            token="expiredlink999",
            file_id=_make_file(sl_session).id,
            owner_id=_OWNER,
            expires_at=past,
            view_count=0,
            is_active=True,
        )
        sl_session.add(link)
        sl_session.commit()

        from app.main import app

        Session = sessionmaker(bind=sl_engine)

        def _override_db():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
        try:
            resp = client.get("/api/share/expiredlink999/download")
            assert resp.status_code == 410
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.unit
    def test_download_revoked_returns_410(self, sl_engine, sl_session):
        """Download endpoint returns 410 when link has been revoked."""
        link = SharedLink(
            token="revokedlink777",
            file_id=_make_file(sl_session).id,
            owner_id=_OWNER,
            view_count=0,
            is_active=False,
            revoked_at=datetime.now(timezone.utc),
        )
        sl_session.add(link)
        sl_session.commit()

        from app.main import app

        Session = sessionmaker(bind=sl_engine)

        def _override_db():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
        try:
            resp = client.get("/api/share/revokedlink777/download")
            assert resp.status_code == 410
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.unit
    def test_download_password_required(self, sl_engine, sl_session):
        """Download endpoint returns 401 when password is required but not supplied."""
        from app.api.shared_links import _hash_password

        link = SharedLink(
            token="pwdlink111",
            file_id=_make_file(sl_session).id,
            owner_id=_OWNER,
            password_hash=_hash_password("correct"),
            view_count=0,
            is_active=True,
        )
        sl_session.add(link)
        sl_session.commit()

        from app.main import app

        Session = sessionmaker(bind=sl_engine)

        def _override_db():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
        try:
            resp = client.get("/api/share/pwdlink111/download")
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.unit
    def test_download_wrong_password(self, sl_engine, sl_session):
        """Download endpoint returns 403 for wrong password."""
        from app.api.shared_links import _hash_password

        link = SharedLink(
            token="pwdlink222",
            file_id=_make_file(sl_session).id,
            owner_id=_OWNER,
            password_hash=_hash_password("correct"),
            view_count=0,
            is_active=True,
        )
        sl_session.add(link)
        sl_session.commit()

        from app.main import app

        Session = sessionmaker(bind=sl_engine)

        def _override_db():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
        try:
            resp = client.get("/api/share/pwdlink222/download?password=wrong")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.unit
    def test_download_view_limit_reached(self, sl_engine, sl_session):
        """Download endpoint returns 410 when view limit is already reached."""
        link = SharedLink(
            token="limitedlink333",
            file_id=_make_file(sl_session).id,
            owner_id=_OWNER,
            max_views=2,
            view_count=2,
            is_active=True,
        )
        sl_session.add(link)
        sl_session.commit()

        from app.main import app

        Session = sessionmaker(bind=sl_engine)

        def _override_db():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
        try:
            resp = client.get("/api/share/limitedlink333/download")
            assert resp.status_code == 410
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests – Helper utilities
# ---------------------------------------------------------------------------


class TestHelpers:
    """Tests for internal helper functions."""

    @pytest.mark.unit
    def test_generate_token_unique(self):
        """Generated tokens should be unique."""
        from app.api.shared_links import _generate_token

        tokens = {_generate_token() for _ in range(100)}
        assert len(tokens) == 100

    @pytest.mark.unit
    def test_hash_password_deterministic(self):
        """Hashing the same password always produces the same hex digest."""
        from app.api.shared_links import _hash_password

        h = _hash_password("mysecret")
        assert h == _hash_password("mysecret")
        assert len(h) == 64

    @pytest.mark.unit
    def test_verify_password_correct(self):
        """_verify_password returns True for a matching password."""
        from app.api.shared_links import _hash_password, _verify_password

        h = _hash_password("correct")
        assert _verify_password("correct", h) is True

    @pytest.mark.unit
    def test_verify_password_wrong(self):
        """_verify_password returns False for a wrong password."""
        from app.api.shared_links import _hash_password, _verify_password

        h = _hash_password("correct")
        assert _verify_password("wrong", h) is False

    @pytest.mark.unit
    def test_is_link_valid_active(self):
        """_is_link_valid returns True for a basic active link."""
        from app.api.shared_links import _is_link_valid

        link = SharedLink(is_active=True, view_count=0)
        assert _is_link_valid(link) is True

    @pytest.mark.unit
    def test_is_link_valid_revoked(self):
        """_is_link_valid returns False for a revoked link."""
        from app.api.shared_links import _is_link_valid

        link = SharedLink(is_active=False, view_count=0)
        assert _is_link_valid(link) is False

    @pytest.mark.unit
    def test_is_link_valid_expired(self):
        """_is_link_valid returns False when expires_at is in the past."""
        from app.api.shared_links import _is_link_valid

        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        link = SharedLink(is_active=True, expires_at=past, view_count=0)
        assert _is_link_valid(link) is False

    @pytest.mark.unit
    def test_is_link_valid_not_yet_expired(self):
        """_is_link_valid returns True when expires_at is in the future."""
        from app.api.shared_links import _is_link_valid

        future = datetime.now(timezone.utc) + timedelta(hours=1)
        link = SharedLink(is_active=True, expires_at=future, view_count=0)
        assert _is_link_valid(link) is True

    @pytest.mark.unit
    def test_is_link_valid_view_limit_hit(self):
        """_is_link_valid returns False when view_count >= max_views."""
        from app.api.shared_links import _is_link_valid

        link = SharedLink(is_active=True, max_views=3, view_count=3)
        assert _is_link_valid(link) is False

    @pytest.mark.unit
    def test_is_link_valid_view_limit_not_hit(self):
        """_is_link_valid returns True when view_count < max_views."""
        from app.api.shared_links import _is_link_valid

        link = SharedLink(is_active=True, max_views=3, view_count=2)
        assert _is_link_valid(link) is True
