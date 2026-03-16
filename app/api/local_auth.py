"""Local user authentication API — signup, email verification, password reset.

Provides the REST endpoints and page routes for the self-registration flow:

- GET  /signup                           — signup page (HTML)
- POST /api/auth/signup                  — create account + send verification email
- GET  /verify-email                     — activate account from email link (redirect)
- GET  /verify-email-sent                — confirmation landing page (HTML)
- POST /api/auth/resend-verification     — re-send verification email
- POST /api/auth/request-password-reset  — start password reset
- POST /api/auth/reset-password          — set new password using token
- GET  /reset-password                   — password reset form page (HTML)
"""

import logging
import pathlib
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.config import settings
from app.database import get_db
from app.models import LocalUser, UserProfile
from app.utils.i18n import translate as _translate
from app.utils.local_auth import (
    build_session_user,
    generate_token,
    hash_password,
    is_token_expired,
    send_forgot_username_email,
    send_password_reset_email,
    send_verification_email,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["local-auth"])

_templates_dir = pathlib.Path(__file__).parents[2] / "frontend" / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))
templates.env.globals["_"] = lambda key, **kwargs: _translate(key, "en", **kwargs)

DbSession = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class SignupBody(BaseModel):
    """Body for the signup endpoint."""

    email: str = Field(..., max_length=255)
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str | None = Field(default=None, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    password_confirm: str


class ResendVerificationBody(BaseModel):
    """Body for the resend-verification endpoint."""

    email: str


class PasswordResetRequestBody(BaseModel):
    """Body for the request-password-reset endpoint."""

    email: str


class PasswordResetBody(BaseModel):
    """Body for the reset-password endpoint."""

    token: str
    new_password: str = Field(..., min_length=8, max_length=128)
    new_password_confirm: str


class ForgotUsernameBody(BaseModel):
    """Body for the forgot-username endpoint."""

    email: str


# ---------------------------------------------------------------------------
# Page routes (return HTML)
# ---------------------------------------------------------------------------


@router.get("/signup", include_in_schema=False)
async def signup_page(request: Request) -> Any:
    """Render the signup page, or redirect to login when multi-user / signup is disabled."""
    if not settings.multi_user_enabled:
        return RedirectResponse(url="/login?error=Multi-user+mode+is+not+enabled", status_code=302)
    if not settings.allow_local_signup:
        return RedirectResponse(url="/login?error=Registration+is+not+enabled", status_code=302)
    return templates.TemplateResponse(
        "signup.html",
        {
            "request": request,
            "csrf_token": getattr(request.state, "csrf_token", ""),
            "app_version": settings.version,
        },
    )


@router.get("/verify-email-sent", include_in_schema=False)
async def verify_email_sent_page(request: Request) -> Any:
    """Render the verify-email-sent confirmation page."""
    return templates.TemplateResponse("verify_email_sent.html", {"request": request})


@router.get("/forgot-username", include_in_schema=False)
async def forgot_username_page(request: Request) -> Any:
    """Render the forgot-username page where users can request a username reminder email."""
    return templates.TemplateResponse(
        "forgot_username.html",
        {
            "request": request,
            "csrf_token": getattr(request.state, "csrf_token", ""),
            "app_version": settings.version,
        },
    )


@router.get("/forgot-password", include_in_schema=False)
async def forgot_password_page(request: Request) -> Any:
    """Render the forgot-password page where users can request a reset email."""
    return templates.TemplateResponse(
        "forgot_password.html",
        {
            "request": request,
            "csrf_token": getattr(request.state, "csrf_token", ""),
            "app_version": settings.version,
        },
    )


@router.get("/reset-password", include_in_schema=False)
async def reset_password_page(request: Request) -> Any:
    """Render the password reset form page."""
    token = request.query_params.get("token", "")
    return templates.TemplateResponse(
        "password_reset_form.html",
        {
            "request": request,
            "token": token,
            "csrf_token": getattr(request.state, "csrf_token", ""),
            "app_version": settings.version,
        },
    )


# ---------------------------------------------------------------------------
# API endpoints (return JSON or redirect)
# ---------------------------------------------------------------------------


@router.post("/api/auth/signup", status_code=status.HTTP_201_CREATED)
async def signup(request: Request, body: SignupBody, db: DbSession) -> dict[str, str | bool]:
    """Create a new local user account.

    When SMTP is configured the account is inactive until the user clicks the
    verification link sent to their email.  When SMTP is **not** configured the
    account is activated immediately so that deployments without email can still
    use the self-registration flow.

    Both ``MULTI_USER_ENABLED`` and ``ALLOW_LOCAL_SIGNUP`` must be ``True``.

    Raises:
        403: Multi-user mode or local signup is disabled.
        422: Passwords do not match.
        409: Email or username already registered.
    """
    if not settings.multi_user_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Multi-user mode is not enabled.")
    if not settings.allow_local_signup:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration is not enabled.")
    if body.password != body.password_confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Passwords do not match.")

    if db.query(LocalUser).filter(LocalUser.email == body.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")
    if db.query(LocalUser).filter(LocalUser.username == body.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken.")

    smtp_configured = bool(settings.email_host)

    if smtp_configured:
        token = generate_token()
        user = LocalUser(
            email=body.email,
            username=body.username,
            display_name=body.display_name,
            hashed_password=hash_password(body.password),
            is_active=False,
            email_verification_token=token,
            email_verification_sent_at=datetime.now(tz=timezone.utc),
        )
    else:
        # No SMTP configured — activate the account immediately.
        token = None
        user = LocalUser(
            email=body.email,
            username=body.username,
            display_name=body.display_name,
            hashed_password=hash_password(body.password),
            is_active=True,
        )

    db.add(user)

    profile = UserProfile(
        user_id=body.email,
        display_name=body.display_name or body.username,
    )
    db.add(profile)

    # Flush to the DB so constraint violations (duplicate key etc.) surface NOW,
    # before we attempt to send the email. We do NOT commit yet — the commit only
    # happens after the email is sent successfully so that a failed email leaves
    # no orphan records in the database.
    try:
        db.flush()
    except Exception:
        db.rollback()
        raise

    if smtp_configured and token:
        base_url = str(request.base_url).rstrip("/")
        try:
            send_verification_email(body.email, body.username, token, base_url)
        except Exception as exc:
            # Email failed — roll back so no unverifiable user row persists.
            # The user can simply try registering again once SMTP is fixed.
            db.rollback()
            logger.warning("Signup email failed for %s: %s", body.email, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Failed to send verification email. Please check that SMTP is correctly configured and try again."
                ),
            ) from exc

    db.commit()
    logger.info("New local user registered: %s", body.email)

    if smtp_configured:
        return {"message": "Verification email sent. Please check your inbox.", "email_verification_required": True}
    return {"message": "Account created successfully. You can now log in.", "email_verification_required": False}


@router.get("/verify-email", include_in_schema=False)
async def verify_email(request: Request, db: DbSession) -> Any:
    """Activate a local user account from the email verification link.

    Redirects to the login page on failure, or to onboarding/upload on success.
    """
    token = request.query_params.get("token", "")
    user = db.query(LocalUser).filter(LocalUser.email_verification_token == token).first()

    if not user:
        return RedirectResponse(
            url="/login?error=Invalid+or+expired+verification+link",
            status_code=302,
        )
    if is_token_expired(user.email_verification_sent_at):
        return RedirectResponse(
            url="/login?error=Verification+link+has+expired.+Please+request+a+new+one",
            status_code=302,
        )

    user.is_active = True
    user.email_verification_token = None
    user.email_verification_sent_at = None

    # Ensure profile exists
    if not db.query(UserProfile).filter(UserProfile.user_id == user.email).first():
        db.add(UserProfile(user_id=user.email, display_name=user.display_name or user.username))

    db.commit()

    request.session["user"] = build_session_user(user)
    logger.info("[SECURITY] EMAIL_VERIFIED user=%s", user.email)

    profile = db.query(UserProfile).filter(UserProfile.user_id == user.email).first()
    if profile and not profile.onboarding_completed:
        post_onboarding = request.session.pop("redirect_after_login", "/upload")
        request.session["post_onboarding_redirect"] = post_onboarding
        return RedirectResponse(url="/onboarding", status_code=302)
    return RedirectResponse(url="/upload", status_code=302)


@router.post("/api/auth/resend-verification")
async def resend_verification(request: Request, body: ResendVerificationBody, db: DbSession) -> dict[str, str]:
    """Re-send the verification email for a pending account.

    Always returns 200 to avoid leaking whether an email is registered.
    """
    user = db.query(LocalUser).filter(LocalUser.email == body.email).first()
    if not user or user.is_active:
        return {"message": "Verification email resent if account exists."}

    token = generate_token()
    user.email_verification_token = token
    user.email_verification_sent_at = datetime.now(tz=timezone.utc)
    db.commit()

    base_url = str(request.base_url).rstrip("/")
    try:
        send_verification_email(user.email, user.username, token, base_url)
    except Exception as exc:
        logger.warning("Failed to resend verification email to %s: %s", user.email, exc)

    return {"message": "Verification email resent if account exists."}


@router.post("/api/auth/request-password-reset")
async def request_password_reset(request: Request, body: PasswordResetRequestBody, db: DbSession) -> dict[str, str]:
    """Send a password reset email.

    Always returns 200 to avoid leaking whether an email is registered.
    """
    user = db.query(LocalUser).filter(LocalUser.email == body.email).first()
    if not user:
        return {"message": "Password reset email sent if account exists."}

    token = generate_token()
    user.password_reset_token = token
    user.password_reset_sent_at = datetime.now(tz=timezone.utc)
    db.commit()

    base_url = str(request.base_url).rstrip("/")
    try:
        send_password_reset_email(user.email, user.username, token, base_url)
    except Exception as exc:
        logger.warning("Failed to send password reset email to %s: %s", user.email, exc)

    return {"message": "Password reset email sent if account exists."}


@router.post("/api/auth/reset-password")
async def reset_password(body: PasswordResetBody, db: DbSession) -> dict[str, str]:
    """Set a new password using a valid reset token.

    Raises:
        400: Token is invalid or expired.
        422: Passwords do not match.
    """
    user = db.query(LocalUser).filter(LocalUser.password_reset_token == body.token).first()
    if not user or is_token_expired(user.password_reset_sent_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )
    if body.new_password != body.new_password_confirm:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Passwords do not match.",
        )

    user.hashed_password = hash_password(body.new_password)
    user.password_reset_token = None
    user.password_reset_sent_at = None
    # Activate the account in case it was still pending email verification.
    # A valid password-reset token proves control of the registered email address.
    user.is_active = True
    db.commit()

    logger.info("[SECURITY] PASSWORD_RESET_SUCCESS user=%s", user.email)
    return {"message": "Password updated successfully."}


@router.post("/api/auth/forgot-username")
async def forgot_username(body: ForgotUsernameBody, db: DbSession) -> dict[str, str]:
    """Send a username reminder email.

    Always returns 200 to avoid leaking whether an email is registered.
    """
    user = db.query(LocalUser).filter(LocalUser.email == body.email).first()
    if user:
        try:
            send_forgot_username_email(user.email, user.username)
        except Exception as exc:
            logger.warning("Failed to send forgot-username email to %s: %s", user.email, exc)

    return {"message": "Username reminder sent if account exists."}
