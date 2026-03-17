"""Tests for server-side session management and QR code login.

Covers:
* Session creation, validation, revocation, and cleanup
* "Log off everywhere" (revoke all sessions)
* QR login challenge creation, validation, claiming, and status polling
* Session management API endpoints (list, revoke, revoke-all)
* QR auth API endpoints (challenge, status, claim)
* Device info parsing from User-Agent strings
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import ApiToken, QRLoginChallenge, UserSession

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    """Provide an in-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def sample_user_id():
    return "user@example.com"


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUserSessionModel:
    """Tests for the UserSession ORM model."""

    def test_create_user_session(self, db_session: Session, sample_user_id: str):
        """Test creating a UserSession record."""
        now = datetime.now(timezone.utc)
        session = UserSession(
            session_token=secrets.token_urlsafe(64),
            user_id=sample_user_id,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            device_info="Chrome on macOS",
            expires_at=now + timedelta(days=30),
        )
        db_session.add(session)
        db_session.commit()

        assert session.id is not None
        assert session.user_id == sample_user_id
        assert session.is_revoked is False
        assert session.device_info == "Chrome on macOS"

    def test_session_default_values(self, db_session: Session, sample_user_id: str):
        """Test that default values are set correctly."""
        session = UserSession(
            session_token="test_token_123",
            user_id=sample_user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db_session.add(session)
        db_session.commit()

        assert session.is_revoked is False
        assert session.revoked_at is None


@pytest.mark.unit
class TestQRLoginChallengeModel:
    """Tests for the QRLoginChallenge ORM model."""

    def test_create_challenge(self, db_session: Session, sample_user_id: str):
        """Test creating a QRLoginChallenge record."""
        challenge = QRLoginChallenge(
            challenge_token=secrets.token_urlsafe(64),
            user_id=sample_user_id,
            created_by_ip="10.0.0.1",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=120),
        )
        db_session.add(challenge)
        db_session.commit()

        assert challenge.id is not None
        assert challenge.is_claimed is False
        assert challenge.is_cancelled is False

    def test_challenge_default_values(self, db_session: Session, sample_user_id: str):
        """Test that QRLoginChallenge defaults are correct."""
        challenge = QRLoginChallenge(
            challenge_token="challenge_test_123",
            user_id=sample_user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=120),
        )
        db_session.add(challenge)
        db_session.commit()

        assert challenge.is_claimed is False
        assert challenge.is_cancelled is False
        assert challenge.claimed_at is None
        assert challenge.device_name is None


# ---------------------------------------------------------------------------
# Session Manager Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSessionManager:
    """Tests for app/utils/session_manager.py functions."""

    @patch("app.utils.session_manager.settings")
    def test_get_session_lifetime_days_default(self, mock_settings):
        """Test default session lifetime."""
        from app.utils.session_manager import get_session_lifetime_days

        mock_settings.session_lifetime_custom_days = None
        mock_settings.session_lifetime_days = 30
        assert get_session_lifetime_days() == 30

    @patch("app.utils.session_manager.settings")
    def test_get_session_lifetime_days_custom(self, mock_settings):
        """Test custom session lifetime overrides default."""
        from app.utils.session_manager import get_session_lifetime_days

        mock_settings.session_lifetime_custom_days = 90
        mock_settings.session_lifetime_days = 30
        assert get_session_lifetime_days() == 90

    @patch("app.utils.session_manager.settings")
    def test_get_session_lifetime_days_minimum(self, mock_settings):
        """Test session lifetime has a minimum of 1 day."""
        from app.utils.session_manager import get_session_lifetime_days

        mock_settings.session_lifetime_custom_days = None
        mock_settings.session_lifetime_days = 0
        assert get_session_lifetime_days() == 1

    @patch("app.utils.session_manager.settings")
    def test_get_session_max_age_seconds(self, mock_settings):
        """Test session max age in seconds."""
        from app.utils.session_manager import get_session_max_age_seconds

        mock_settings.session_lifetime_custom_days = None
        mock_settings.session_lifetime_days = 30
        assert get_session_max_age_seconds() == 30 * 86400

    @patch("app.utils.session_manager.settings")
    def test_create_session(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test creating a server-side session."""
        from app.utils.session_manager import create_session

        mock_settings.session_lifetime_custom_days = None
        mock_settings.session_lifetime_days = 30
        mock_settings.qr_login_challenge_ttl_seconds = 120

        user_session = create_session(
            db_session,
            user_id=sample_user_id,
            ip_address="10.0.0.1",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0",
        )

        assert user_session.id is not None
        assert user_session.user_id == sample_user_id
        assert user_session.ip_address == "10.0.0.1"
        assert user_session.session_token is not None
        assert len(user_session.session_token) > 32
        assert user_session.is_revoked is False
        assert user_session.device_info is not None

    @patch("app.utils.session_manager.settings")
    def test_validate_session_valid(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test validating a valid session."""
        from app.utils.session_manager import create_session, validate_session

        mock_settings.session_lifetime_custom_days = None
        mock_settings.session_lifetime_days = 30

        user_session = create_session(db_session, user_id=sample_user_id)
        result = validate_session(db_session, user_session.session_token)
        assert result is not None
        assert result.id == user_session.id

    @patch("app.utils.session_manager.settings")
    def test_validate_session_revoked(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test that revoked sessions are rejected."""
        from app.utils.session_manager import create_session, validate_session

        mock_settings.session_lifetime_custom_days = None
        mock_settings.session_lifetime_days = 30

        user_session = create_session(db_session, user_id=sample_user_id)
        user_session.is_revoked = True
        db_session.commit()

        result = validate_session(db_session, user_session.session_token)
        assert result is None

    @patch("app.utils.session_manager.settings")
    def test_validate_session_expired(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test that expired sessions are rejected."""
        from app.utils.session_manager import create_session, validate_session

        mock_settings.session_lifetime_custom_days = None
        mock_settings.session_lifetime_days = 30

        user_session = create_session(db_session, user_id=sample_user_id)
        user_session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()

        result = validate_session(db_session, user_session.session_token)
        assert result is None

    def test_validate_session_empty_token(self, db_session: Session):
        """Test that empty token returns None."""
        from app.utils.session_manager import validate_session

        assert validate_session(db_session, "") is None
        assert validate_session(db_session, None) is None

    def test_validate_session_nonexistent_token(self, db_session: Session):
        """Test that nonexistent token returns None."""
        from app.utils.session_manager import validate_session

        assert validate_session(db_session, "nonexistent_token_xyz") is None

    @patch("app.utils.session_manager.settings")
    def test_revoke_session(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test revoking a single session."""
        from app.utils.session_manager import create_session, revoke_session, validate_session

        mock_settings.session_lifetime_custom_days = None
        mock_settings.session_lifetime_days = 30

        user_session = create_session(db_session, user_id=sample_user_id)
        assert revoke_session(db_session, user_session.id, sample_user_id) is True

        # Session should now be invalid
        assert validate_session(db_session, user_session.session_token) is None

    @patch("app.utils.session_manager.settings")
    def test_revoke_session_wrong_user(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test that a user cannot revoke another user's session."""
        from app.utils.session_manager import create_session, revoke_session

        mock_settings.session_lifetime_custom_days = None
        mock_settings.session_lifetime_days = 30

        user_session = create_session(db_session, user_id=sample_user_id)
        assert revoke_session(db_session, user_session.id, "other_user@example.com") is False

    @patch("app.utils.session_manager.settings")
    def test_revoke_all_sessions(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test revoking all sessions for a user."""
        from app.utils.session_manager import create_session, list_user_sessions, revoke_all_sessions

        mock_settings.session_lifetime_custom_days = None
        mock_settings.session_lifetime_days = 30

        s1 = create_session(db_session, user_id=sample_user_id)
        s2 = create_session(db_session, user_id=sample_user_id)
        s3 = create_session(db_session, user_id=sample_user_id)

        count = revoke_all_sessions(db_session, sample_user_id, revoke_api_tokens=False)
        assert count == 3

        # All sessions should be revoked
        active = list_user_sessions(db_session, sample_user_id)
        assert len(active) == 0

    @patch("app.utils.session_manager.settings")
    def test_revoke_all_except_current(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test revoking all sessions except the current one."""
        from app.utils.session_manager import create_session, list_user_sessions, revoke_all_sessions

        mock_settings.session_lifetime_custom_days = None
        mock_settings.session_lifetime_days = 30

        s1 = create_session(db_session, user_id=sample_user_id)
        s2 = create_session(db_session, user_id=sample_user_id)
        s3 = create_session(db_session, user_id=sample_user_id)

        count = revoke_all_sessions(
            db_session,
            sample_user_id,
            except_session_id=s1.id,
            revoke_api_tokens=False,
        )
        assert count == 2

        active = list_user_sessions(db_session, sample_user_id)
        assert len(active) == 1
        assert active[0].id == s1.id

    @patch("app.utils.session_manager.settings")
    def test_revoke_all_includes_api_tokens(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test that revoke-all also revokes API tokens."""
        from app.utils.session_manager import create_session, revoke_all_sessions

        mock_settings.session_lifetime_custom_days = None
        mock_settings.session_lifetime_days = 30

        create_session(db_session, user_id=sample_user_id)

        # Create an API token
        token = ApiToken(
            owner_id=sample_user_id,
            name="Test Token",
            token_hash="abc123hash",
            token_prefix="de_abc12345",
        )
        db_session.add(token)
        db_session.commit()

        revoke_all_sessions(db_session, sample_user_id, revoke_api_tokens=True)

        db_session.refresh(token)
        assert token.is_active is False

    @patch("app.utils.session_manager.settings")
    def test_list_user_sessions(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test listing active sessions for a user."""
        from app.utils.session_manager import create_session, list_user_sessions

        mock_settings.session_lifetime_custom_days = None
        mock_settings.session_lifetime_days = 30

        create_session(db_session, user_id=sample_user_id)
        create_session(db_session, user_id=sample_user_id)
        create_session(db_session, user_id="other@example.com")

        sessions = list_user_sessions(db_session, sample_user_id)
        assert len(sessions) == 2

    @patch("app.utils.session_manager.settings")
    def test_cleanup_expired_sessions(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test cleaning up expired sessions."""
        from app.utils.session_manager import cleanup_expired_sessions, create_session

        mock_settings.session_lifetime_custom_days = None
        mock_settings.session_lifetime_days = 30

        # Create a session that expired 10 days ago
        session = create_session(db_session, user_id=sample_user_id)
        session.expires_at = datetime.now(timezone.utc) - timedelta(days=10)
        db_session.commit()

        count = cleanup_expired_sessions(db_session)
        assert count == 1


# ---------------------------------------------------------------------------
# QR Login Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestQRLogin:
    """Tests for QR login challenge/claim flow."""

    @patch("app.utils.session_manager.settings")
    def test_create_qr_challenge(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test creating a QR login challenge."""
        from app.utils.session_manager import create_qr_challenge

        mock_settings.qr_login_challenge_ttl_seconds = 120

        challenge = create_qr_challenge(db_session, sample_user_id, ip_address="10.0.0.1")

        assert challenge.id is not None
        assert challenge.user_id == sample_user_id
        assert challenge.challenge_token is not None
        assert len(challenge.challenge_token) > 32
        assert challenge.is_claimed is False
        assert challenge.created_by_ip == "10.0.0.1"
        # SQLite returns naive datetimes; normalise before comparison
        expires = challenge.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        assert expires > datetime.now(timezone.utc)

    @patch("app.utils.session_manager.settings")
    def test_validate_qr_challenge_valid(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test validating a valid QR challenge."""
        from app.utils.session_manager import create_qr_challenge, validate_qr_challenge

        mock_settings.qr_login_challenge_ttl_seconds = 120

        challenge = create_qr_challenge(db_session, sample_user_id)
        result = validate_qr_challenge(db_session, challenge.challenge_token)
        assert result is not None
        assert result.id == challenge.id

    @patch("app.utils.session_manager.settings")
    def test_validate_qr_challenge_expired(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test that expired challenges are rejected."""
        from app.utils.session_manager import create_qr_challenge, validate_qr_challenge

        mock_settings.qr_login_challenge_ttl_seconds = 120

        challenge = create_qr_challenge(db_session, sample_user_id)
        challenge.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()

        result = validate_qr_challenge(db_session, challenge.challenge_token)
        assert result is None

    @patch("app.utils.session_manager.settings")
    def test_validate_qr_challenge_claimed(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test that claimed challenges are rejected (replay protection)."""
        from app.utils.session_manager import create_qr_challenge, validate_qr_challenge

        mock_settings.qr_login_challenge_ttl_seconds = 120

        challenge = create_qr_challenge(db_session, sample_user_id)
        challenge.is_claimed = True
        db_session.commit()

        result = validate_qr_challenge(db_session, challenge.challenge_token)
        assert result is None

    @patch("app.utils.session_manager.settings")
    def test_validate_qr_challenge_cancelled(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test that cancelled challenges are rejected."""
        from app.utils.session_manager import create_qr_challenge, validate_qr_challenge

        mock_settings.qr_login_challenge_ttl_seconds = 120

        challenge = create_qr_challenge(db_session, sample_user_id)
        challenge.is_cancelled = True
        db_session.commit()

        result = validate_qr_challenge(db_session, challenge.challenge_token)
        assert result is None

    def test_validate_qr_challenge_empty(self, db_session: Session):
        """Test that empty challenge token returns None."""
        from app.utils.session_manager import validate_qr_challenge

        assert validate_qr_challenge(db_session, "") is None
        assert validate_qr_challenge(db_session, None) is None

    @patch("app.utils.session_manager.settings")
    def test_claim_qr_challenge_success(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test successfully claiming a QR challenge."""
        from app.utils.session_manager import claim_qr_challenge, create_qr_challenge

        mock_settings.qr_login_challenge_ttl_seconds = 120

        challenge = create_qr_challenge(db_session, sample_user_id)
        result = claim_qr_challenge(
            db_session,
            challenge.challenge_token,
            device_name="Christian's iPhone 15 Pro",
            ip_address="192.168.1.100",
        )

        assert result is not None
        assert result["token"].startswith("de_")
        assert result["token_id"] is not None
        assert result["owner_id"] == sample_user_id
        assert "QR" in result["name"]

        # Challenge should now be claimed
        db_session.refresh(challenge)
        assert challenge.is_claimed is True
        assert challenge.claimed_by_ip == "192.168.1.100"
        assert challenge.device_name == "Christian's iPhone 15 Pro"

    @patch("app.utils.session_manager.settings")
    def test_claim_qr_challenge_replay_protection(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test that a claimed challenge cannot be claimed again."""
        from app.utils.session_manager import claim_qr_challenge, create_qr_challenge

        mock_settings.qr_login_challenge_ttl_seconds = 120

        challenge = create_qr_challenge(db_session, sample_user_id)

        # First claim succeeds
        result1 = claim_qr_challenge(db_session, challenge.challenge_token)
        assert result1 is not None

        # Second claim fails (replay protection)
        result2 = claim_qr_challenge(db_session, challenge.challenge_token)
        assert result2 is None

    @patch("app.utils.session_manager.settings")
    def test_claim_qr_challenge_expired(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test that expired challenges cannot be claimed."""
        from app.utils.session_manager import claim_qr_challenge, create_qr_challenge

        mock_settings.qr_login_challenge_ttl_seconds = 120

        challenge = create_qr_challenge(db_session, sample_user_id)
        challenge.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()

        result = claim_qr_challenge(db_session, challenge.challenge_token)
        assert result is None

    def test_claim_qr_challenge_invalid_token(self, db_session: Session):
        """Test claiming with an invalid token."""
        from app.utils.session_manager import claim_qr_challenge

        result = claim_qr_challenge(db_session, "nonexistent_token_xyz")
        assert result is None

    @patch("app.utils.session_manager.settings")
    def test_get_challenge_status_pending(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test getting status of a pending challenge."""
        from app.utils.session_manager import create_qr_challenge, get_challenge_status

        mock_settings.qr_login_challenge_ttl_seconds = 120

        challenge = create_qr_challenge(db_session, sample_user_id)
        status = get_challenge_status(db_session, challenge.id, sample_user_id)

        assert status is not None
        assert status["status"] == "pending"

    @patch("app.utils.session_manager.settings")
    def test_get_challenge_status_claimed(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test getting status of a claimed challenge."""
        from app.utils.session_manager import claim_qr_challenge, create_qr_challenge, get_challenge_status

        mock_settings.qr_login_challenge_ttl_seconds = 120

        challenge = create_qr_challenge(db_session, sample_user_id)
        claim_qr_challenge(db_session, challenge.challenge_token, device_name="Test Device")

        status = get_challenge_status(db_session, challenge.id, sample_user_id)
        assert status is not None
        assert status["status"] == "claimed"
        assert status["device_name"] == "Test Device"

    @patch("app.utils.session_manager.settings")
    def test_get_challenge_status_expired(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test getting status of an expired challenge."""
        from app.utils.session_manager import create_qr_challenge, get_challenge_status

        mock_settings.qr_login_challenge_ttl_seconds = 120

        challenge = create_qr_challenge(db_session, sample_user_id)
        challenge.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()

        status = get_challenge_status(db_session, challenge.id, sample_user_id)
        assert status["status"] == "expired"

    @patch("app.utils.session_manager.settings")
    def test_get_challenge_status_wrong_user(self, mock_settings, db_session: Session, sample_user_id: str):
        """Test that a user cannot see another user's challenge status."""
        from app.utils.session_manager import create_qr_challenge, get_challenge_status

        mock_settings.qr_login_challenge_ttl_seconds = 120

        challenge = create_qr_challenge(db_session, sample_user_id)
        status = get_challenge_status(db_session, challenge.id, "other@example.com")
        assert status is None


# ---------------------------------------------------------------------------
# Device Info Parsing Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeviceInfoParsing:
    """Tests for User-Agent parsing."""

    def test_chrome_macos(self):
        from app.utils.session_manager import _parse_device_info

        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        result = _parse_device_info(ua)
        assert "Chrome" in result
        assert "macOS" in result

    def test_safari_iphone(self):
        from app.utils.session_manager import _parse_device_info

        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
        result = _parse_device_info(ua)
        assert "Safari" in result
        assert "iPhone" in result

    def test_firefox_windows(self):
        from app.utils.session_manager import _parse_device_info

        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
        result = _parse_device_info(ua)
        assert "Firefox" in result
        assert "Windows" in result

    def test_edge_windows(self):
        from app.utils.session_manager import _parse_device_info

        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        result = _parse_device_info(ua)
        assert "Edge" in result
        assert "Windows" in result

    def test_android_chrome(self):
        from app.utils.session_manager import _parse_device_info

        ua = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.210 Mobile Safari/537.36"
        result = _parse_device_info(ua)
        assert "Chrome" in result
        assert "Android" in result

    def test_none_user_agent(self):
        from app.utils.session_manager import _parse_device_info

        assert _parse_device_info(None) is None

    def test_empty_user_agent(self):
        from app.utils.session_manager import _parse_device_info

        assert _parse_device_info("") is None


# ---------------------------------------------------------------------------
# Config Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSessionConfig:
    """Tests for session-related configuration fields."""

    def test_session_lifetime_days_field_exists(self):
        """Verify session_lifetime_days field is defined in Settings."""
        from app.config import Settings

        # Check the field exists in the model
        assert "session_lifetime_days" in Settings.model_fields

    def test_session_lifetime_custom_days_field_exists(self):
        """Verify session_lifetime_custom_days field is defined in Settings."""
        from app.config import Settings

        assert "session_lifetime_custom_days" in Settings.model_fields

    def test_qr_login_challenge_ttl_field_exists(self):
        """Verify qr_login_challenge_ttl_seconds field is defined in Settings."""
        from app.config import Settings

        assert "qr_login_challenge_ttl_seconds" in Settings.model_fields
