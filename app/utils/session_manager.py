"""Server-side session management utilities.

Provides helpers for creating, validating, and revoking user sessions.
Sessions are tracked in the ``user_sessions`` table and referenced by a
cryptographically random token stored in the browser cookie.  This enables
the "log off everywhere" feature and per-session revocation.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models import ApiToken, QRLoginChallenge, UserSession

logger = logging.getLogger(__name__)


def get_session_lifetime_days() -> int:
    """Return the effective session lifetime in days.

    If ``session_lifetime_custom_days`` is set it takes precedence over
    ``session_lifetime_days``.
    """
    custom = getattr(settings, "session_lifetime_custom_days", None)
    if custom is not None and isinstance(custom, int) and custom > 0:
        return custom
    return max(1, getattr(settings, "session_lifetime_days", 30))


def get_session_max_age_seconds() -> int:
    """Return the session max-age in seconds for the cookie."""
    return get_session_lifetime_days() * 86400


def create_session(
    db: Session,
    user_id: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> UserSession:
    """Create a new server-side session record.

    Args:
        db: Database session.
        user_id: Stable owner identifier.
        ip_address: Client IP address.
        user_agent: Client User-Agent header.

    Returns:
        The newly created ``UserSession`` instance.
    """
    session_token = secrets.token_urlsafe(64)
    now = datetime.now(timezone.utc)
    lifetime_days = get_session_lifetime_days()
    expires_at = now + timedelta(days=lifetime_days)

    device_info = _parse_device_info(user_agent)

    user_session = UserSession(
        session_token=session_token,
        user_id=user_id,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:512],
        device_info=device_info,
        created_at=now,
        last_active_at=now,
        expires_at=expires_at,
    )
    try:
        db.add(user_session)
        db.commit()
        db.refresh(user_session)
    except Exception:
        db.rollback()
        logger.exception("Failed to create session for user_id=%s", user_id)
        raise

    logger.info(
        "[SESSION] Created session id=%s user=%s device=%r expires=%s",
        user_session.id,
        user_id,
        device_info,
        expires_at.isoformat(),
    )
    return user_session


def validate_session(db: Session, session_token: str) -> UserSession | None:
    """Validate a session token and return the session if valid.

    A session is valid when:
    * It exists in the database.
    * ``is_revoked`` is ``False``.
    * ``expires_at`` is in the future.

    Side-effect: updates ``last_active_at`` on valid sessions.

    Returns:
        The ``UserSession`` if valid, else ``None``.
    """
    if not session_token:
        return None

    now = datetime.now(timezone.utc)
    user_session = db.query(UserSession).filter(UserSession.session_token == session_token).first()

    if not user_session:
        logger.debug("[SESSION] Token not found in database")
        return None

    if user_session.is_revoked:
        logger.debug("[SESSION] Session id=%s is revoked", user_session.id)
        return None

    if user_session.expires_at:
        # Ensure timezone-aware comparison (SQLite returns naive datetimes)
        expires = user_session.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < now:
            logger.debug("[SESSION] Session id=%s has expired", user_session.id)
            return None

    # Update last_active_at (throttled to avoid excessive writes)
    last_active = user_session.last_active_at
    if last_active and last_active.tzinfo is None:
        last_active = last_active.replace(tzinfo=timezone.utc)
    if not last_active or (now - last_active).total_seconds() > 60:
        try:
            user_session.last_active_at = now
            db.commit()
        except Exception:
            db.rollback()
            logger.debug("[SESSION] Failed to update last_active_at for session id=%s", user_session.id)

    return user_session


def revoke_session(db: Session, session_id: int, user_id: str) -> bool:
    """Revoke a single session by ID.

    Args:
        db: Database session.
        session_id: The session record ID to revoke.
        user_id: The owner — ensures a user can only revoke their own sessions.

    Returns:
        ``True`` if the session was found and revoked, ``False`` otherwise.
    """
    user_session = db.get(UserSession, session_id)
    if not user_session or user_session.user_id != user_id:
        return False

    now = datetime.now(timezone.utc)
    user_session.is_revoked = True
    user_session.revoked_at = now
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("[SESSION] Revoked session id=%s user=%s", session_id, user_id)
    return True


def revoke_all_sessions(
    db: Session,
    user_id: str,
    *,
    except_session_id: int | None = None,
    revoke_api_tokens: bool = True,
) -> int:
    """Revoke all active sessions for a user ("log off everywhere").

    Args:
        db: Database session.
        user_id: The owner whose sessions should be revoked.
        except_session_id: If provided, keep this session active (the
            current browser session).
        revoke_api_tokens: If ``True``, also revoke all active API tokens.

    Returns:
        Number of sessions revoked.
    """
    now = datetime.now(timezone.utc)
    query = db.query(UserSession).filter(
        UserSession.user_id == user_id,
        UserSession.is_revoked.is_(False),
    )
    if except_session_id is not None:
        query = query.filter(UserSession.id != except_session_id)

    sessions = query.all()
    count = 0
    for s in sessions:
        s.is_revoked = True
        s.revoked_at = now
        count += 1

    if revoke_api_tokens:
        tokens = (
            db.query(ApiToken)
            .filter(
                ApiToken.owner_id == user_id,
                ApiToken.is_active.is_(True),
            )
            .all()
        )
        for t in tokens:
            t.is_active = False
            t.revoked_at = now

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info(
        "[SESSION] Revoked all sessions for user=%s (count=%d, except_session_id=%s, tokens_revoked=%s)",
        user_id,
        count,
        except_session_id,
        revoke_api_tokens,
    )
    return count


def list_user_sessions(db: Session, user_id: str) -> list[UserSession]:
    """Return all non-revoked, non-expired sessions for a user.

    Results are ordered by most recently active first.
    """
    now = datetime.now(timezone.utc)
    sessions = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user_id,
            UserSession.is_revoked.is_(False),
        )
        .order_by(UserSession.last_active_at.desc())
        .all()
    )
    # Filter expired sessions in Python to handle timezone-naive datetimes (SQLite)
    result = []
    for s in sessions:
        expires = s.expires_at
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires and expires > now:
            result.append(s)
    return result


def cleanup_expired_sessions(db: Session) -> int:
    """Delete sessions that expired more than 7 days ago.

    Intended to be called periodically (e.g. via Celery beat) to keep the
    table from growing unbounded.

    Returns:
        Number of rows deleted.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    count = db.query(UserSession).filter(UserSession.expires_at < cutoff).delete(synchronize_session=False)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    if count:
        logger.info("[SESSION] Cleaned up %d expired sessions", count)
    return count


# ---------------------------------------------------------------------------
# QR login helpers
# ---------------------------------------------------------------------------


def create_qr_challenge(db: Session, user_id: str, ip_address: str | None = None) -> QRLoginChallenge:
    """Create a new QR login challenge.

    Args:
        db: Database session.
        user_id: The authenticated web user creating the challenge.
        ip_address: IP address of the web client.

    Returns:
        The newly created ``QRLoginChallenge``.
    """
    token = secrets.token_urlsafe(64)
    ttl = getattr(settings, "qr_login_challenge_ttl_seconds", 120)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ttl)

    challenge = QRLoginChallenge(
        challenge_token=token,
        user_id=user_id,
        created_by_ip=ip_address,
        created_at=now,
        expires_at=expires_at,
    )
    try:
        db.add(challenge)
        db.commit()
        db.refresh(challenge)
    except Exception:
        db.rollback()
        logger.exception("Failed to create QR login challenge for user_id=%s", user_id)
        raise

    logger.info("[QR_AUTH] Challenge created: id=%s user=%s expires=%s", challenge.id, user_id, expires_at.isoformat())
    return challenge


def validate_qr_challenge(db: Session, challenge_token: str) -> QRLoginChallenge | None:
    """Validate a QR challenge token without claiming it.

    Returns the challenge if it exists, is not expired, not claimed,
    and not cancelled.  Returns ``None`` otherwise.
    """
    if not challenge_token:
        return None

    now = datetime.now(timezone.utc)
    challenge = db.query(QRLoginChallenge).filter(QRLoginChallenge.challenge_token == challenge_token).first()

    if not challenge:
        return None
    if challenge.is_claimed or challenge.is_cancelled:
        return None
    if challenge.expires_at < now:
        return None

    return challenge


def claim_qr_challenge(
    db: Session,
    challenge_token: str,
    device_name: str = "Mobile App",
    ip_address: str | None = None,
) -> dict | None:
    """Claim a QR challenge and issue an API token.

    This is the critical security path.  The challenge is validated,
    marked as claimed atomically, and an API token is issued for the
    user who created the challenge.

    Args:
        db: Database session.
        challenge_token: The token from the QR code.
        device_name: Name provided by the mobile app.
        ip_address: IP address of the claiming mobile device.

    Returns:
        Dict with ``token`` (plaintext), ``token_id``, ``name``, ``owner_id``
        and ``created_at`` on success, or ``None`` if the challenge is invalid.
    """
    from app.api.api_tokens import generate_api_token, hash_token

    challenge = validate_qr_challenge(db, challenge_token)
    if not challenge:
        logger.warning("[QR_AUTH] Invalid or expired challenge token attempted")
        return None

    now = datetime.now(timezone.utc)

    # Mark as claimed first to prevent race conditions
    challenge.is_claimed = True
    challenge.claimed_at = now
    challenge.claimed_by_ip = ip_address
    challenge.device_name = device_name

    # Generate API token for the mobile app
    token_name = f"Mobile App (QR) – {device_name}"
    plaintext = generate_api_token()
    token_hash_value = hash_token(plaintext)
    prefix = plaintext[:12]

    db_token = ApiToken(
        owner_id=challenge.user_id,
        name=token_name,
        token_hash=token_hash_value,
        token_prefix=prefix,
    )

    try:
        db.add(db_token)
        db.flush()
        challenge.issued_token_id = db_token.id
        db.commit()
        db.refresh(db_token)
    except Exception:
        db.rollback()
        logger.exception("[QR_AUTH] Failed to issue token for challenge id=%s", challenge.id)
        raise

    logger.info(
        "[QR_AUTH] Challenge claimed: id=%s user=%s device=%r token_id=%s",
        challenge.id,
        challenge.user_id,
        device_name,
        db_token.id,
    )

    return {
        "token": plaintext,
        "token_id": db_token.id,
        "name": token_name,
        "owner_id": challenge.user_id,
        "created_at": db_token.created_at,
    }


def get_challenge_status(db: Session, challenge_id: int, user_id: str) -> dict | None:
    """Get the current status of a QR challenge (for polling from the web UI).

    Returns:
        Dict with ``status`` ("pending", "claimed", "expired", "cancelled")
        and metadata, or ``None`` if the challenge doesn't belong to the user.
    """
    challenge = db.get(QRLoginChallenge, challenge_id)
    if not challenge or challenge.user_id != user_id:
        return None

    now = datetime.now(timezone.utc)
    if challenge.is_claimed:
        status = "claimed"
    elif challenge.is_cancelled:
        status = "cancelled"
    elif challenge.expires_at < now:
        status = "expired"
    else:
        status = "pending"

    return {
        "id": challenge.id,
        "status": status,
        "device_name": challenge.device_name,
        "claimed_at": challenge.claimed_at,
        "expires_at": challenge.expires_at,
    }


def _parse_device_info(user_agent: str | None) -> str | None:
    """Extract a human-readable device description from User-Agent.

    This is a lightweight parser — not a full UA library — that covers
    the most common browsers and platforms.
    """
    if not user_agent:
        return None

    ua = user_agent.lower()

    # Platform detection
    platform = "Unknown"
    if "iphone" in ua:
        platform = "iPhone"
    elif "ipad" in ua:
        platform = "iPad"
    elif "android" in ua:
        platform = "Android"
    elif "macintosh" in ua or "mac os" in ua:
        platform = "macOS"
    elif "windows" in ua:
        platform = "Windows"
    elif "linux" in ua:
        platform = "Linux"
    elif "cros" in ua:
        platform = "ChromeOS"

    # Browser detection
    browser = "Unknown Browser"
    if "edg/" in ua or "edge/" in ua:
        browser = "Edge"
    elif "opr/" in ua or "opera" in ua:
        browser = "Opera"
    elif "chrome/" in ua and "safari/" in ua:
        browser = "Chrome"
    elif "safari/" in ua and "chrome/" not in ua:
        browser = "Safari"
    elif "firefox/" in ua:
        browser = "Firefox"
    elif "docuelevate" in ua:
        browser = "DocuElevate App"

    return f"{browser} on {platform}"
