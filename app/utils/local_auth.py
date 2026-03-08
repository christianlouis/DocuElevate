"""Utilities for local (email/password) user authentication.

Provides password hashing (bcrypt), secure token generation, and
synchronous SMTP email helpers for account verification and password
reset flows.  No external dependencies beyond bcrypt (already in
requirements.txt) and Python stdlib.
"""

import logging
import secrets
import smtplib
import socket
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import bcrypt

from app.config import settings

logger = logging.getLogger(__name__)

TOKEN_BYTES = 32  # 256 bits of entropy
TOKEN_EXPIRY_HOURS = 24  # verification + reset tokens expire after 24 h


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*. Stores result as a UTF-8 string."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True when *plain* matches the stored bcrypt *hashed* string."""
    try:
        result = bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        if not result:
            logger.debug("verify_password: mismatch password_provided=%s", bool(plain))
        return result
    except Exception as exc:
        logger.warning("verify_password: exception type=%s msg=%s", type(exc).__name__, exc)
        return False


def generate_token() -> str:
    """Return a 256-bit URL-safe random token string."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def is_token_expired(sent_at: datetime | None) -> bool:
    """Return True when *sent_at* is None or older than TOKEN_EXPIRY_HOURS."""
    if sent_at is None:
        return True
    return datetime.now(tz=timezone.utc) > sent_at.astimezone(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)


def _smtp_send(subject: str, html_body: str, plain_body: str, recipient: str) -> None:
    """Send an HTML email via the configured SMTP server.

    Args:
        subject: Email subject line.
        html_body: HTML version of the email body.
        plain_body: Plain-text version of the email body.
        recipient: Recipient email address.

    Raises:
        RuntimeError: When SMTP is not configured or sending fails.
    """
    if not settings.email_host:
        raise RuntimeError("SMTP is not configured (EMAIL_HOST missing). Cannot send email.")

    sender = settings.email_sender or settings.email_username or "noreply@docuelevate.local"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        socket.gethostbyname(settings.email_host)
    except socket.gaierror as exc:
        raise RuntimeError(f"Cannot resolve SMTP host {settings.email_host!r}: {exc}") from exc

    with smtplib.SMTP(settings.email_host, settings.email_port or 587, timeout=30) as server:
        if settings.email_use_tls:
            server.starttls()
        if settings.email_username and settings.email_password:
            server.login(settings.email_username, settings.email_password)
        server.send_message(msg)

    logger.info("Sent %r to %s", subject, recipient)


def send_verification_email(email: str, username: str, token: str, base_url: str) -> None:
    """Send a double opt-in verification email to *email*.

    Args:
        email: Recipient email address.
        username: The user's chosen username (used in greeting).
        token: The verification token to embed in the link.
        base_url: The base URL of the application (e.g. https://app.example.com).
    """
    verify_url = f"{base_url}/verify-email?token={token}"
    subject = "Verify your DocuElevate account"
    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#f4f4f5;margin:0;padding:32px;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;box-shadow:0 2px 8px rgba(0,0,0,.08);">
    <h1 style="color:#4f46e5;font-size:24px;margin-bottom:8px;">Welcome to DocuElevate, {username}!</h1>
    <p style="color:#374151;">Thanks for signing up. Please confirm your email address to activate your account.</p>
    <div style="text-align:center;margin:32px 0;">
      <a href="{verify_url}"
         style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:14px 32px;border-radius:8px;font-weight:600;font-size:16px;">
        Confirm my email address
      </a>
    </div>
    <p style="color:#6b7280;font-size:13px;">This link expires in 24 hours. If you did not create an account, you can safely ignore this email.</p>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
    <p style="color:#9ca3af;font-size:12px;text-align:center;">DocuElevate &middot; Intelligent Document Processing</p>
  </div>
</body>
</html>"""
    plain_body = (
        f"Welcome to DocuElevate, {username}!\n\n"
        f"Please verify your email address by visiting:\n{verify_url}\n\n"
        "This link expires in 24 hours."
    )
    _smtp_send(subject, html_body, plain_body, email)


def send_password_reset_email(email: str, username: str, token: str, base_url: str) -> None:
    """Send a password reset email to *email*.

    Args:
        email: Recipient email address.
        username: The user's username (used in greeting).
        token: The password reset token to embed in the link.
        base_url: The base URL of the application.
    """
    reset_url = f"{base_url}/reset-password?token={token}"
    subject = "Reset your DocuElevate password"
    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#f4f4f5;margin:0;padding:32px;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;box-shadow:0 2px 8px rgba(0,0,0,.08);">
    <h1 style="color:#4f46e5;font-size:24px;margin-bottom:8px;">Password Reset</h1>
    <p style="color:#374151;">Hi {username}, you requested a password reset for your DocuElevate account.</p>
    <div style="text-align:center;margin:32px 0;">
      <a href="{reset_url}"
         style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:14px 32px;border-radius:8px;font-weight:600;font-size:16px;">
        Reset my password
      </a>
    </div>
    <p style="color:#6b7280;font-size:13px;">This link expires in 24 hours. If you did not request a password reset, you can safely ignore this email.</p>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
    <p style="color:#9ca3af;font-size:12px;text-align:center;">DocuElevate &middot; Intelligent Document Processing</p>
  </div>
</body>
</html>"""
    plain_body = (
        f"Hi {username},\n\n"
        f"You requested a password reset. Visit the link below:\n{reset_url}\n\n"
        "This link expires in 24 hours. If you did not request this, ignore this email."
    )
    _smtp_send(subject, html_body, plain_body, email)


def send_forgot_username_email(email: str, username: str) -> None:
    """Send an email reminding the user of their username.

    Args:
        email: Recipient email address.
        username: The user's username to include in the message.
    """
    subject = "Your DocuElevate username"
    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#f4f4f5;margin:0;padding:32px;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;box-shadow:0 2px 8px rgba(0,0,0,.08);">
    <h1 style="color:#4f46e5;font-size:24px;margin-bottom:8px;">Your Username</h1>
    <p style="color:#374151;">You requested a reminder of your DocuElevate username.</p>
    <div style="text-align:center;margin:32px 0;background:#f3f4f6;border-radius:8px;padding:20px;">
      <p style="color:#6b7280;font-size:13px;margin-bottom:4px;">Your username is:</p>
      <p style="color:#111827;font-size:22px;font-weight:700;font-family:monospace;">{username}</p>
    </div>
    <p style="color:#374151;font-size:14px;">You can sign in using your username <strong>or</strong> your email address.</p>
    <p style="color:#6b7280;font-size:13px;margin-top:16px;">If you did not request this reminder, you can safely ignore this email.</p>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
    <p style="color:#9ca3af;font-size:12px;text-align:center;">DocuElevate &middot; Intelligent Document Processing</p>
  </div>
</body>
</html>"""
    plain_body = (
        f"You requested a reminder of your DocuElevate username.\n\n"
        f"Your username is: {username}\n\n"
        "You can sign in using your username or your email address.\n\n"
        "If you did not request this, please ignore this email."
    )
    _smtp_send(subject, html_body, plain_body, email)


def build_session_user(user: object) -> dict:
    """Build the session user dict for a LocalUser, matching the OAuth session format.

    Args:
        user: A ``LocalUser`` ORM instance.

    Returns:
        Dict suitable for storing in ``request.session["user"]``.
    """
    from app.auth import get_gravatar_url

    return {
        "sub": user.email,  # type: ignore[attr-defined]
        "id": user.email,  # type: ignore[attr-defined]
        "email": user.email,  # type: ignore[attr-defined]
        "preferred_username": user.username,  # type: ignore[attr-defined]
        "name": user.display_name or user.username,  # type: ignore[attr-defined]
        "picture": get_gravatar_url(user.email),  # type: ignore[attr-defined]
        "is_admin": bool(user.is_admin),  # type: ignore[attr-defined]
        "auth_method": "local",
    }
