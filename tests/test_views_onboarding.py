"""Tests for app/views/onboarding.py covering _get_configured_destinations() and onboarding_page() route."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import UserProfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine():
    """Return an in-memory SQLite engine with all tables created."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


def _make_session(engine):
    """Return a plain session for *engine*."""
    return sessionmaker(bind=engine)()


def _make_profile(session, user_id: str, **kwargs) -> UserProfile:
    """Insert a UserProfile row and return it."""
    kwargs.setdefault("is_blocked", False)
    kwargs.setdefault("onboarding_completed", False)
    profile = UserProfile(user_id=user_id, **kwargs)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def _make_mock_request(session_user: dict | None = None) -> MagicMock:
    """Build a minimal mock FastAPI Request with a controllable session."""
    mock_req = MagicMock()
    if session_user is None:
        mock_req.session = {}
    else:
        mock_req.session = {"user": session_user}
    return mock_req


# ---------------------------------------------------------------------------
# Tests for _get_configured_destinations
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetConfiguredDestinations:
    """Unit tests for the _get_configured_destinations helper."""

    def test_returns_empty_when_nothing_configured(self):
        """No credentials set → empty list."""
        from app.views.onboarding import _get_configured_destinations

        cfg = MagicMock()
        cfg.dropbox_refresh_token = None
        cfg.dropbox_app_key = None
        cfg.google_drive_credentials_json = None
        cfg.google_drive_refresh_token = None
        cfg.onedrive_refresh_token = None
        cfg.onedrive_client_id = None
        cfg.aws_access_key_id = None
        cfg.s3_bucket_name = None
        cfg.nextcloud_upload_url = None
        cfg.nextcloud_username = None
        cfg.webdav_url = None
        cfg.webdav_username = None
        cfg.sftp_host = None
        cfg.sftp_username = None
        cfg.ftp_host = None
        cfg.ftp_username = None

        result = _get_configured_destinations(cfg)
        assert result == []

    def test_returns_dropbox_when_configured(self):
        """Dropbox credentials set → Dropbox included."""
        from app.views.onboarding import _get_configured_destinations

        cfg = MagicMock()
        cfg.dropbox_refresh_token = "token"
        cfg.dropbox_app_key = "key"
        cfg.google_drive_credentials_json = None
        cfg.google_drive_refresh_token = None
        cfg.onedrive_refresh_token = None
        cfg.onedrive_client_id = None
        cfg.aws_access_key_id = None
        cfg.s3_bucket_name = None
        cfg.nextcloud_upload_url = None
        cfg.nextcloud_username = None
        cfg.webdav_url = None
        cfg.webdav_username = None
        cfg.sftp_host = None
        cfg.sftp_username = None
        cfg.ftp_host = None
        cfg.ftp_username = None

        result = _get_configured_destinations(cfg)
        ids = [d["id"] for d in result]
        assert "dropbox" in ids

    def test_returns_gdrive_when_credentials_json_configured(self):
        """Google Drive credentials_json set → gdrive included."""
        from app.views.onboarding import _get_configured_destinations

        cfg = MagicMock()
        cfg.dropbox_refresh_token = None
        cfg.dropbox_app_key = None
        cfg.google_drive_credentials_json = '{"type": "service_account"}'
        cfg.google_drive_refresh_token = None
        cfg.onedrive_refresh_token = None
        cfg.onedrive_client_id = None
        cfg.aws_access_key_id = None
        cfg.s3_bucket_name = None
        cfg.nextcloud_upload_url = None
        cfg.nextcloud_username = None
        cfg.webdav_url = None
        cfg.webdav_username = None
        cfg.sftp_host = None
        cfg.sftp_username = None
        cfg.ftp_host = None
        cfg.ftp_username = None

        result = _get_configured_destinations(cfg)
        ids = [d["id"] for d in result]
        assert "gdrive" in ids

    def test_returns_gdrive_when_refresh_token_configured(self):
        """Google Drive refresh_token set (without credentials_json) → gdrive included."""
        from app.views.onboarding import _get_configured_destinations

        cfg = MagicMock()
        cfg.dropbox_refresh_token = None
        cfg.dropbox_app_key = None
        cfg.google_drive_credentials_json = None
        cfg.google_drive_refresh_token = "refresh-token"
        cfg.onedrive_refresh_token = None
        cfg.onedrive_client_id = None
        cfg.aws_access_key_id = None
        cfg.s3_bucket_name = None
        cfg.nextcloud_upload_url = None
        cfg.nextcloud_username = None
        cfg.webdav_url = None
        cfg.webdav_username = None
        cfg.sftp_host = None
        cfg.sftp_username = None
        cfg.ftp_host = None
        cfg.ftp_username = None

        result = _get_configured_destinations(cfg)
        ids = [d["id"] for d in result]
        assert "gdrive" in ids

    def test_returns_onedrive_when_configured(self):
        """OneDrive credentials set → onedrive included."""
        from app.views.onboarding import _get_configured_destinations

        cfg = MagicMock()
        cfg.dropbox_refresh_token = None
        cfg.dropbox_app_key = None
        cfg.google_drive_credentials_json = None
        cfg.google_drive_refresh_token = None
        cfg.onedrive_refresh_token = "token"
        cfg.onedrive_client_id = "client-id"
        cfg.aws_access_key_id = None
        cfg.s3_bucket_name = None
        cfg.nextcloud_upload_url = None
        cfg.nextcloud_username = None
        cfg.webdav_url = None
        cfg.webdav_username = None
        cfg.sftp_host = None
        cfg.sftp_username = None
        cfg.ftp_host = None
        cfg.ftp_username = None

        result = _get_configured_destinations(cfg)
        ids = [d["id"] for d in result]
        assert "onedrive" in ids

    def test_returns_s3_when_configured(self):
        """S3 credentials set → s3 included."""
        from app.views.onboarding import _get_configured_destinations

        cfg = MagicMock()
        cfg.dropbox_refresh_token = None
        cfg.dropbox_app_key = None
        cfg.google_drive_credentials_json = None
        cfg.google_drive_refresh_token = None
        cfg.onedrive_refresh_token = None
        cfg.onedrive_client_id = None
        cfg.aws_access_key_id = "AKIAIOSFODNN7EXAMPLE"
        cfg.s3_bucket_name = "my-bucket"
        cfg.nextcloud_upload_url = None
        cfg.nextcloud_username = None
        cfg.webdav_url = None
        cfg.webdav_username = None
        cfg.sftp_host = None
        cfg.sftp_username = None
        cfg.ftp_host = None
        cfg.ftp_username = None

        result = _get_configured_destinations(cfg)
        ids = [d["id"] for d in result]
        assert "s3" in ids

    def test_returns_nextcloud_when_configured(self):
        """Nextcloud credentials set → nextcloud included."""
        from app.views.onboarding import _get_configured_destinations

        cfg = MagicMock()
        cfg.dropbox_refresh_token = None
        cfg.dropbox_app_key = None
        cfg.google_drive_credentials_json = None
        cfg.google_drive_refresh_token = None
        cfg.onedrive_refresh_token = None
        cfg.onedrive_client_id = None
        cfg.aws_access_key_id = None
        cfg.s3_bucket_name = None
        cfg.nextcloud_upload_url = "https://cloud.example.com"
        cfg.nextcloud_username = "admin"
        cfg.webdav_url = None
        cfg.webdav_username = None
        cfg.sftp_host = None
        cfg.sftp_username = None
        cfg.ftp_host = None
        cfg.ftp_username = None

        result = _get_configured_destinations(cfg)
        ids = [d["id"] for d in result]
        assert "nextcloud" in ids

    def test_returns_webdav_when_configured(self):
        """WebDAV credentials set → webdav included."""
        from app.views.onboarding import _get_configured_destinations

        cfg = MagicMock()
        cfg.dropbox_refresh_token = None
        cfg.dropbox_app_key = None
        cfg.google_drive_credentials_json = None
        cfg.google_drive_refresh_token = None
        cfg.onedrive_refresh_token = None
        cfg.onedrive_client_id = None
        cfg.aws_access_key_id = None
        cfg.s3_bucket_name = None
        cfg.nextcloud_upload_url = None
        cfg.nextcloud_username = None
        cfg.webdav_url = "https://dav.example.com"
        cfg.webdav_username = "user"
        cfg.sftp_host = None
        cfg.sftp_username = None
        cfg.ftp_host = None
        cfg.ftp_username = None

        result = _get_configured_destinations(cfg)
        ids = [d["id"] for d in result]
        assert "webdav" in ids

    def test_returns_sftp_when_configured(self):
        """SFTP credentials set → sftp included."""
        from app.views.onboarding import _get_configured_destinations

        cfg = MagicMock()
        cfg.dropbox_refresh_token = None
        cfg.dropbox_app_key = None
        cfg.google_drive_credentials_json = None
        cfg.google_drive_refresh_token = None
        cfg.onedrive_refresh_token = None
        cfg.onedrive_client_id = None
        cfg.aws_access_key_id = None
        cfg.s3_bucket_name = None
        cfg.nextcloud_upload_url = None
        cfg.nextcloud_username = None
        cfg.webdav_url = None
        cfg.webdav_username = None
        cfg.sftp_host = "sftp.example.com"
        cfg.sftp_username = "user"
        cfg.ftp_host = None
        cfg.ftp_username = None

        result = _get_configured_destinations(cfg)
        ids = [d["id"] for d in result]
        assert "sftp" in ids

    def test_returns_ftp_when_configured(self):
        """FTP credentials set → ftp included."""
        from app.views.onboarding import _get_configured_destinations

        cfg = MagicMock()
        cfg.dropbox_refresh_token = None
        cfg.dropbox_app_key = None
        cfg.google_drive_credentials_json = None
        cfg.google_drive_refresh_token = None
        cfg.onedrive_refresh_token = None
        cfg.onedrive_client_id = None
        cfg.aws_access_key_id = None
        cfg.s3_bucket_name = None
        cfg.nextcloud_upload_url = None
        cfg.nextcloud_username = None
        cfg.webdav_url = None
        cfg.webdav_username = None
        cfg.sftp_host = None
        cfg.sftp_username = None
        cfg.ftp_host = "ftp.example.com"
        cfg.ftp_username = "user"

        result = _get_configured_destinations(cfg)
        ids = [d["id"] for d in result]
        assert "ftp" in ids

    def test_returns_multiple_when_all_configured(self):
        """All credentials set → all eight destinations returned in order."""
        from app.views.onboarding import _DESTINATION_META, _get_configured_destinations

        cfg = MagicMock()
        cfg.dropbox_refresh_token = "token"
        cfg.dropbox_app_key = "key"
        cfg.google_drive_credentials_json = '{"type": "service_account"}'
        cfg.google_drive_refresh_token = "token"
        cfg.onedrive_refresh_token = "token"
        cfg.onedrive_client_id = "client-id"
        cfg.aws_access_key_id = "key"
        cfg.s3_bucket_name = "bucket"
        cfg.nextcloud_upload_url = "https://nc.example.com"
        cfg.nextcloud_username = "admin"
        cfg.webdav_url = "https://dav.example.com"
        cfg.webdav_username = "user"
        cfg.sftp_host = "sftp.example.com"
        cfg.sftp_username = "sftpuser"
        cfg.ftp_host = "ftp.example.com"
        cfg.ftp_username = "ftpuser"

        result = _get_configured_destinations(cfg)
        assert len(result) == len(_DESTINATION_META)

    def test_result_contains_required_keys(self):
        """Each destination dict must have id, name, and icon keys."""
        from app.views.onboarding import _get_configured_destinations

        cfg = MagicMock()
        cfg.dropbox_refresh_token = "token"
        cfg.dropbox_app_key = "key"
        cfg.google_drive_credentials_json = None
        cfg.google_drive_refresh_token = None
        cfg.onedrive_refresh_token = None
        cfg.onedrive_client_id = None
        cfg.aws_access_key_id = None
        cfg.s3_bucket_name = None
        cfg.nextcloud_upload_url = None
        cfg.nextcloud_username = None
        cfg.webdav_url = None
        cfg.webdav_username = None
        cfg.sftp_host = None
        cfg.sftp_username = None
        cfg.ftp_host = None
        cfg.ftp_username = None

        result = _get_configured_destinations(cfg)
        assert len(result) == 1
        assert set(result[0].keys()) == {"id", "name", "icon"}

    def test_partial_credentials_not_included(self):
        """Only one of a required credential pair set → destination not included."""
        from app.views.onboarding import _get_configured_destinations

        cfg = MagicMock()
        # Dropbox needs both refresh_token AND app_key; only token provided
        cfg.dropbox_refresh_token = "token"
        cfg.dropbox_app_key = None
        cfg.google_drive_credentials_json = None
        cfg.google_drive_refresh_token = None
        cfg.onedrive_refresh_token = None
        cfg.onedrive_client_id = None
        cfg.aws_access_key_id = None
        cfg.s3_bucket_name = None
        cfg.nextcloud_upload_url = None
        cfg.nextcloud_username = None
        cfg.webdav_url = None
        cfg.webdav_username = None
        cfg.sftp_host = None
        cfg.sftp_username = None
        cfg.ftp_host = None
        cfg.ftp_username = None

        result = _get_configured_destinations(cfg)
        ids = [d["id"] for d in result]
        assert "dropbox" not in ids


# ---------------------------------------------------------------------------
# Tests for onboarding_page view
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOnboardingPage:
    """Unit tests for the onboarding_page view handler."""

    @pytest.mark.asyncio
    async def test_no_user_renders_template(self):
        """No user in session → template is rendered (no redirect)."""
        from starlette.responses import RedirectResponse

        from app.views.onboarding import onboarding_page

        engine = _make_engine()
        db = _make_session(engine)
        mock_req = _make_mock_request(session_user=None)
        mock_template_response = MagicMock()

        try:
            with (
                patch("app.views.onboarding.templates") as mock_templates,
                patch("app.views.onboarding.get_all_tiers", return_value=[]),
                patch("app.views.onboarding._get_configured_destinations", return_value=[]),
            ):
                mock_templates.TemplateResponse.return_value = mock_template_response
                result = await onboarding_page(mock_req, db)

            assert not isinstance(result, RedirectResponse)
            mock_templates.TemplateResponse.assert_called_once()
            call_args = mock_templates.TemplateResponse.call_args
            assert call_args[0][0] == "onboarding.html"
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)

    @pytest.mark.asyncio
    async def test_user_without_profile_renders_template(self):
        """User in session but no UserProfile row → template is rendered."""
        from starlette.responses import RedirectResponse

        from app.views.onboarding import onboarding_page

        engine = _make_engine()
        db = _make_session(engine)
        mock_req = _make_mock_request(session_user={"sub": "user-no-profile"})
        mock_template_response = MagicMock()

        try:
            with (
                patch("app.views.onboarding.templates") as mock_templates,
                patch("app.views.onboarding.get_all_tiers", return_value=[]),
                patch("app.views.onboarding._get_configured_destinations", return_value=[]),
            ):
                mock_templates.TemplateResponse.return_value = mock_template_response
                result = await onboarding_page(mock_req, db)

            assert not isinstance(result, RedirectResponse)
            mock_templates.TemplateResponse.assert_called_once()
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)

    @pytest.mark.asyncio
    async def test_incomplete_onboarding_renders_template(self):
        """User has a profile with onboarding_completed=False → template rendered."""
        from starlette.responses import RedirectResponse

        from app.views.onboarding import onboarding_page

        engine = _make_engine()
        db = _make_session(engine)
        _make_profile(db, "user-incomplete", onboarding_completed=False)
        mock_req = _make_mock_request(session_user={"sub": "user-incomplete"})
        mock_template_response = MagicMock()

        try:
            with (
                patch("app.views.onboarding.templates") as mock_templates,
                patch("app.views.onboarding.get_all_tiers", return_value=[]),
                patch("app.views.onboarding._get_configured_destinations", return_value=[]),
            ):
                mock_templates.TemplateResponse.return_value = mock_template_response
                result = await onboarding_page(mock_req, db)

            assert not isinstance(result, RedirectResponse)
            mock_templates.TemplateResponse.assert_called_once()
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)

    @pytest.mark.asyncio
    async def test_completed_onboarding_redirects_via_sub(self):
        """User (identified by 'sub') with onboarding_completed=True → redirected to /upload."""
        from starlette.responses import RedirectResponse

        from app.views.onboarding import onboarding_page

        engine = _make_engine()
        db = _make_session(engine)
        _make_profile(db, "user-done-sub", onboarding_completed=True)
        mock_req = _make_mock_request(session_user={"sub": "user-done-sub"})

        try:
            result = await onboarding_page(mock_req, db)

            assert isinstance(result, RedirectResponse)
            assert result.status_code == 302
            assert result.headers["location"] == "/upload"
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)

    @pytest.mark.asyncio
    async def test_completed_onboarding_redirects_via_preferred_username(self):
        """User identified by 'preferred_username' with onboarding_completed=True → redirect."""
        from starlette.responses import RedirectResponse

        from app.views.onboarding import onboarding_page

        engine = _make_engine()
        db = _make_session(engine)
        _make_profile(db, "user-done-username", onboarding_completed=True)
        # sub is absent; preferred_username is used instead
        mock_req = _make_mock_request(session_user={"preferred_username": "user-done-username"})

        try:
            result = await onboarding_page(mock_req, db)

            assert isinstance(result, RedirectResponse)
            assert result.status_code == 302
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)

    @pytest.mark.asyncio
    async def test_completed_onboarding_redirects_via_email(self):
        """User identified by 'email' with onboarding_completed=True → redirect."""
        from starlette.responses import RedirectResponse

        from app.views.onboarding import onboarding_page

        engine = _make_engine()
        db = _make_session(engine)
        _make_profile(db, "done@example.com", onboarding_completed=True)
        mock_req = _make_mock_request(session_user={"email": "done@example.com"})

        try:
            result = await onboarding_page(mock_req, db)

            assert isinstance(result, RedirectResponse)
            assert result.status_code == 302
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)

    @pytest.mark.asyncio
    async def test_completed_onboarding_redirects_via_id(self):
        """User identified by 'id' with onboarding_completed=True → redirect."""
        from starlette.responses import RedirectResponse

        from app.views.onboarding import onboarding_page

        engine = _make_engine()
        db = _make_session(engine)
        _make_profile(db, "user-id-42", onboarding_completed=True)
        mock_req = _make_mock_request(session_user={"id": "user-id-42"})

        try:
            result = await onboarding_page(mock_req, db)

            assert isinstance(result, RedirectResponse)
            assert result.status_code == 302
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)

    @pytest.mark.asyncio
    async def test_template_context_contains_required_keys(self):
        """The template context passed to TemplateResponse has the correct keys."""
        from app.views.onboarding import onboarding_page

        engine = _make_engine()
        db = _make_session(engine)
        user = {"sub": "ctx-user", "name": "Context User"}
        mock_req = _make_mock_request(session_user=user)
        mock_template_response = MagicMock()

        try:
            with (
                patch("app.views.onboarding.templates") as mock_templates,
                patch("app.views.onboarding.get_all_tiers", return_value=["free"]),
                patch("app.views.onboarding._get_configured_destinations", return_value=[{"id": "s3"}]),
            ):
                mock_templates.TemplateResponse.return_value = mock_template_response
                await onboarding_page(mock_req, db)

            call_args = mock_templates.TemplateResponse.call_args
            context = call_args[0][1]
            assert context["request"] is mock_req
            assert context["user"] == user
            assert context["configured_destinations"] == [{"id": "s3"}]
            assert context["tiers"] == ["free"]
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)
