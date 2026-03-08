import hashlib
import inspect
import logging
import pathlib
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlparse

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.config import settings
from app.database import get_db

# Conditional imports: only used when multi_user_enabled=True. Imported here at
# module level (not inside auth()) so they don't incur repeated import overhead.
# Guards at call-sites ensure they are never *called* in single-user mode.
from app.models import LocalUser as _LocalUser
from app.models import UserProfile as _UserProfile
from app.utils.local_auth import build_session_user as _build_session_user
from app.utils.local_auth import verify_password as _verify_password

logger = logging.getLogger(__name__)

oauth = OAuth()

AUTH_ENABLED = settings.auth_enabled

# Set up templates for authentication
templates_dir = pathlib.Path(__file__).parents[1] / "frontend" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Configure OAuth provider if credentials are provided
OAUTH_CONFIGURED = False
OAUTH_PROVIDER_NAME = "Single Sign-On"

if AUTH_ENABLED and settings.authentik_client_id and settings.authentik_client_secret:
    oauth.register(
        name="authentik",
        client_id=settings.authentik_client_id,
        client_secret=settings.authentik_client_secret,
        server_metadata_url=settings.authentik_config_url,
        client_kwargs={"scope": "openid profile email"},
    )
    OAUTH_CONFIGURED = True
    OAUTH_PROVIDER_NAME = settings.oauth_provider_name or "Authentik SSO"

router = APIRouter()


def get_current_user(request: Request):
    # Check for Bearer token auth first (API tokens)
    api_user = getattr(request.state, "api_token_user", None)
    if isinstance(api_user, dict):
        return api_user
    return request.session.get("user")


def _resolve_bearer_user(request: Request, db: Session) -> dict | None:
    """Resolve a user from a Bearer API token in the Authorization header.

    If the header is present and the token is valid, updates usage tracking
    (last_used_at, last_used_ip) and returns a synthetic user dict compatible
    with the session user format.

    Returns:
        A user dict or ``None`` if no valid Bearer token is present.
    """
    auth_header = request.headers.get("authorization", "")
    if not isinstance(auth_header, str) or not auth_header.startswith("Bearer "):
        return None

    raw_token = auth_header[7:]
    if not raw_token or not isinstance(raw_token, str):
        return None

    from app.api.api_tokens import hash_token
    from app.models import ApiToken

    token_hash = hash_token(raw_token)
    db_token = db.query(ApiToken).filter(ApiToken.token_hash == token_hash, ApiToken.is_active.is_(True)).first()
    if db_token is None:
        return None

    # Update usage tracking
    try:
        db_token.last_used_at = datetime.now(timezone.utc)
        # Extract client IP (respect X-Forwarded-For from reverse proxy)
        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not client_ip and request.client:
            client_ip = request.client.host
        db_token.last_used_ip = client_ip or None
        db.commit()
    except Exception:
        db.rollback()
        logger.debug("Failed to update API token usage tracking for token_id=%s", db_token.id)

    # Build a synthetic user dict that mimics the session user format
    return {
        "id": db_token.owner_id,
        "email": db_token.owner_id,
        "preferred_username": db_token.owner_id,
        "is_admin": False,
        "_api_token_id": db_token.id,
    }


def get_current_user_id(request: Request) -> str:
    """Return a stable string identifier for the authenticated user.

    Falls back to ``"anonymous"`` when no user is in the session (e.g. when
    AUTH_ENABLED=False in single-user mode).  The returned value is consistent
    with how pipeline and file ownership is stored in the database.

    Priority order: ``preferred_username`` → ``email`` → ``id`` → ``"anonymous"``.

    Args:
        request: The current FastAPI request.

    Returns:
        A non-empty string identifying the current user.
    """
    user = get_current_user(request)
    if not user or not isinstance(user, dict):
        return "anonymous"
    return user.get("preferred_username") or user.get("email") or user.get("id") or "anonymous"


def require_login(func):
    if not AUTH_ENABLED:
        return func  # no-op

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        # Check session auth first
        if request.session.get("user"):
            if inspect.iscoroutinefunction(func):
                return await func(*args, request=request, **kwargs)
            else:
                return func(*args, request=request, **kwargs)

        # Fall back to Bearer token auth for API endpoints
        url_path = urlparse(str(request.url)).path
        if url_path.startswith("/api/"):
            try:
                from app.database import SessionLocal

                db = SessionLocal()
                try:
                    api_user = _resolve_bearer_user(request, db)
                finally:
                    db.close()
            except Exception:
                api_user = None

            if api_user:
                request.state.api_token_user = api_user
                if inspect.iscoroutinefunction(func):
                    return await func(*args, request=request, **kwargs)
                else:
                    return func(*args, request=request, **kwargs)

            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Not authenticated"},
            )

        # Non-API endpoint with no session — redirect to login
        request.session["redirect_after_login"] = str(request.url)
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    return wrapper


def get_gravatar_url(email):
    """Generate a Gravatar URL for the given email"""
    email = email.lower().strip()
    # MD5 is used here for Gravatar's URL generation (not for security), so usedforsecurity=False
    email_hash = hashlib.md5(email.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"https://www.gravatar.com/avatar/{email_hash}?d=identicon"


async def login(request: Request):
    """Show login page with appropriate authentication options."""
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": request.query_params.get("error"),
            "message": request.query_params.get("message"),
            "show_oauth": OAUTH_CONFIGURED,
            "oauth_provider_name": OAUTH_PROVIDER_NAME,
            "app_version": settings.version,
            "csrf_token": getattr(request.state, "csrf_token", ""),
            # "Create account" link is only shown when multi-user mode AND local signup are both enabled
            "allow_signup": settings.multi_user_enabled and settings.allow_local_signup,
        },
    )


async def oauth_login(request: Request):
    """Handle OAuth login flow"""
    if not OAUTH_CONFIGURED:
        return RedirectResponse(url="/login?error=OAuth+not+configured", status_code=status.HTTP_302_FOUND)

    redirect_uri = request.url_for("oauth_callback")
    return await oauth.authentik.authorize_redirect(request, redirect_uri)


def _ensure_user_profile(db: Session, user_data: dict, is_admin: bool = False) -> None:
    """Create or update a UserProfile row for *user_data*.

    Uses the same identifier priority as ``get_current_owner_id`` (sub →
    preferred_username → email → id) so that the profile's ``user_id`` matches
    ``FileRecord.owner_id`` for every document the user uploads.

    For regular users, an existing profile is left unchanged so that
    admin-managed settings (tier, limits, etc.) are preserved across logins.

    For admin users (*is_admin=True*) the following rules apply:
    - If no profile exists: one is created with the highest subscription tier,
      ``is_complimentary=True``, and ``onboarding_completed=True`` so that
      admins skip the first-time setup wizard.
    - If a profile already exists: ``is_complimentary`` is set to ``True``
      and, when the current tier is ``"free"``, the tier is upgraded to the
      highest available plan.  Other admin-managed settings are left intact.

    Args:
        db: Active database session.
        user_data: Mapping of user attributes as returned by the OAuth provider
            or built by :func:`app.utils.local_auth.build_session_user`.
        is_admin: When ``True``, apply admin-specific defaults on first login
            and ensure the complimentary flag is always set.
    """
    from app.models import UserProfile
    from app.utils.subscription import TIER_ORDER

    highest_tier = TIER_ORDER[-1]

    user_id = (
        user_data.get("sub") or user_data.get("preferred_username") or user_data.get("email") or user_data.get("id")
    )
    if not user_id:
        logger.warning("Cannot create UserProfile: no stable user identifier in OAuth userinfo")
        return

    try:
        existing = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if existing is None:
            display_name = user_data.get("name") or user_data.get("preferred_username") or user_data.get("email")
            email = user_data.get("email")
            profile = UserProfile(
                user_id=user_id,
                display_name=display_name,
                subscription_tier=highest_tier if is_admin else "free",
                is_complimentary=is_admin,
                onboarding_completed=is_admin,
            )
            db.add(profile)
            db.commit()
            logger.info(
                "Auto-created UserProfile for user_id=%s (admin=%s, tier=%s)",
                user_id,
                is_admin,
                highest_tier if is_admin else "free",
            )
            # Notify admins and fire webhook for new (non-admin) user signup
            if not is_admin:
                try:
                    from app.utils.notification import notify_user_signup
                    from app.utils.webhook import dispatch_webhook_event

                    notify_user_signup(user_id, display_name=display_name, email=email)
                    dispatch_webhook_event(
                        "user.signup",
                        {
                            "user_id": user_id,
                            "display_name": display_name,
                            "email": email,
                        },
                    )
                except Exception:
                    logger.exception("Failed to send signup notification/webhook for user_id=%s", user_id)
        elif is_admin:
            # Ensure existing admin profiles always have complimentary flag set.
            # Also upgrade from free tier to highest if still on default.
            changed = False
            if not existing.is_complimentary:
                existing.is_complimentary = True
                changed = True
            if (existing.subscription_tier or "free") == "free":
                existing.subscription_tier = highest_tier
                changed = True
            if changed:
                db.commit()
                logger.info(
                    "Updated admin UserProfile for user_id=%s (complimentary=True, tier=%s)",
                    user_id,
                    existing.subscription_tier,
                )
    except Exception:
        db.rollback()
        logger.exception("Failed to auto-create/update UserProfile for user_id=%s", user_id)


async def oauth_callback(request: Request, db: Session = Depends(get_db)):
    """Handle OAuth callback from provider"""
    try:
        token = await oauth.authentik.authorize_access_token(request)
        userinfo = token.get("userinfo")
        if not userinfo:
            return RedirectResponse(
                url="/login?error=Failed+to+retrieve+user+information", status_code=status.HTTP_302_FOUND
            )

        # Store user info in session
        user_data = dict(userinfo)

        # Add Gravatar picture if no picture is provided
        if not user_data.get("picture") and user_data.get("email"):
            user_data["picture"] = get_gravatar_url(user_data["email"])

        # Check if user is admin based on OAuth groups or specific email
        # You can customize this logic based on your OAuth provider's attributes
        # For example, check if user has an "admin" group or specific email domain
        is_admin = False
        if "groups" in user_data:
            # Check if user is in admin group
            groups = user_data.get("groups", [])
            admin_group = (settings.admin_group_name or "admin").strip().lower()
            is_admin = admin_group in [group.lower() for group in groups]

        # Set is_admin flag (defaults to False for OAuth users unless they're in admin group)
        user_data["is_admin"] = is_admin

        request.session["user"] = user_data

        # Auto-create or update UserProfile so the user appears in admin user management
        _ensure_user_profile(db, user_data, is_admin=is_admin)

        # Log the successful authentication
        logger.info("[SECURITY] OAUTH_LOGIN_SUCCESS user=%s admin=%s", user_data.get("email", "unknown"), is_admin)

        # Redirect first-time users to onboarding
        user_id = (
            user_data.get("sub") or user_data.get("preferred_username") or user_data.get("email") or user_data.get("id")
        )
        if user_id:
            profile = db.query(_UserProfile).filter(_UserProfile.user_id == user_id).first()
            if profile and not profile.onboarding_completed:
                post_onboarding = request.session.pop("redirect_after_login", "/upload")
                request.session["post_onboarding_redirect"] = post_onboarding
                return RedirectResponse(url="/onboarding", status_code=status.HTTP_302_FOUND)

        # Redirect to original destination or default
        redirect_url = request.session.pop("redirect_after_login", "/upload")
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    except Exception as e:
        logger.warning(f"[SECURITY] OAUTH_LOGIN_FAILURE error={type(e).__name__}")
        return RedirectResponse(url=f"/login?error=Authentication+failed:+{str(e)}", status_code=status.HTTP_302_FOUND)


async def auth(request: Request, db: Session = Depends(get_db)):
    """Handle local username/password authentication.

    In multi-user mode (``MULTI_USER_ENABLED=True``) local registered users are
    checked first; if no matching LocalUser is found the request falls through to
    the single admin-credential check so that single-user deployments continue to
    work without any database involvement.

    In single-user mode (``MULTI_USER_ENABLED=False``, the default) the LocalUser
    table is never queried — only the configured ADMIN_USERNAME / ADMIN_PASSWORD
    are accepted, preserving full backward compatibility.
    """
    form_data = await request.form()
    username = form_data.get("username")
    password = form_data.get("password")

    logger.debug(
        "[AUTH] Login attempt: username=%r password_provided=%s multi_user_enabled=%s",
        username,
        bool(password),
        settings.multi_user_enabled,
    )

    # --- LocalUser check (multi-user mode only) ---
    if settings.multi_user_enabled:
        if not username:
            logger.warning(
                "[AUTH] LOGIN_FAILURE reason=empty_username multi_user_enabled=%s form_keys=%s content_type=%s",
                settings.multi_user_enabled,
                list(form_data.keys()),
                request.headers.get("content-type", "<missing>"),
            )
            return RedirectResponse(url="/login?error=Invalid+username+or+password", status_code=302)

        local_user = (
            db.query(_LocalUser).filter((_LocalUser.username == username) | (_LocalUser.email == username)).first()
        )
        logger.debug(
            "[AUTH] LocalUser lookup: username=%r found=%s",
            username,
            local_user is not None,
        )
        if local_user is not None:
            if not local_user.is_active:
                logger.warning(
                    "[SECURITY] LOCAL_LOGIN_UNVERIFIED user=%s is_active=%s",
                    username,
                    local_user.is_active,
                )
                return RedirectResponse(
                    url="/login?error=Please+verify+your+email+address+before+logging+in",
                    status_code=302,
                )
            pw_ok = _verify_password(password or "", local_user.hashed_password)
            logger.debug(
                "[AUTH] Password verification: user=%s ok=%s",
                username,
                pw_ok,
            )
            if not pw_ok:
                logger.warning("[SECURITY] LOCAL_LOGIN_FAILURE reason=wrong_password user=%s", username)
                return RedirectResponse(url="/login?error=Invalid+username+or+password", status_code=302)
            user_data = _build_session_user(local_user)
            request.session["user"] = user_data
            logger.info("[SECURITY] LOCAL_LOGIN_SUCCESS user=%s", local_user.email)
            _ensure_user_profile(db, user_data, is_admin=bool(local_user.is_admin))
            profile = db.query(_UserProfile).filter(_UserProfile.user_id == local_user.email).first()
            if profile and not profile.onboarding_completed:
                post_onboarding = request.session.pop("redirect_after_login", "/upload")
                request.session["post_onboarding_redirect"] = post_onboarding
                return RedirectResponse(url="/onboarding", status_code=302)
            redirect_url = request.session.pop("redirect_after_login", "/upload")
            return RedirectResponse(url=redirect_url, status_code=302)

        # Local user not found; fall through to admin credential check below.
        logger.debug(
            "[AUTH] No LocalUser matched username=%r; falling through to admin credential check",
            username,
        )

    # --- Admin credentials (always available as a fallback / single-user mode) ---
    # Guard: only attempt the match when credentials are actually configured.
    # Without this guard, Python's `None == None` would be True when neither
    # ADMIN_USERNAME nor ADMIN_PASSWORD is set, allowing any request that omits
    # those form fields to be authenticated as an admin — creating a phantom
    # "None@local.docuelevate" admin profile with full privileges.
    admin_configured = bool(settings.admin_username and settings.admin_password)
    logger.debug(
        "[AUTH] Admin credential check: admin_configured=%s username_match=%s multi_user_enabled=%s",
        admin_configured,
        username == settings.admin_username if admin_configured else False,
        settings.multi_user_enabled,
    )
    if (
        settings.admin_username
        and settings.admin_password
        and username == settings.admin_username
        and password == settings.admin_password
    ):
        admin_user_data = {
            "id": "admin",
            "name": "Administrator",
            "email": f"{username}@local.docuelevate",
            "preferred_username": username,
            "picture": "/static/images/default-avatar.svg",
            "is_admin": True,
        }
        request.session["user"] = admin_user_data
        logger.info("[SECURITY] LOCAL_LOGIN_SUCCESS user=%s", username)
        _ensure_user_profile(db, admin_user_data, is_admin=True)
        redirect_url = request.session.pop("redirect_after_login", "/upload")
        return RedirectResponse(url=redirect_url, status_code=302)
    else:
        logger.warning(
            "[SECURITY] LOCAL_LOGIN_FAILURE reason=no_match user=%r "
            "multi_user_enabled=%s admin_configured=%s form_empty=%s",
            username,
            settings.multi_user_enabled,
            admin_configured,
            not username and not password,
        )
        return RedirectResponse(url="/login?error=Invalid+username+or+password", status_code=302)


async def logout(request: Request):
    """Handle user logout"""
    user = request.session.get("user")
    username = "unknown"
    if isinstance(user, dict):
        username = user.get("preferred_username") or user.get("email") or "unknown"
    logger.info(f"[SECURITY] LOGOUT user={username}")
    request.session.pop("user", None)
    return RedirectResponse(url="/login?message=You+have+been+logged+out+successfully", status_code=302)


if AUTH_ENABLED:
    router.add_api_route("/login", login, methods=["GET"])
    router.add_api_route("/oauth-login", oauth_login, methods=["GET"])
    router.add_api_route("/oauth-callback", oauth_callback, methods=["GET"])
    router.add_api_route("/auth", auth, methods=["POST"])
    router.add_api_route("/logout", logout, methods=["GET"])


@router.get("/api/auth/whoami")
@require_login
async def whoami(request: Request):
    """API endpoint to get current user information"""
    user = get_current_user(request)
    return user or {"error": "Not authenticated"}


@router.get("/private")
@require_login
async def private_page(request: Request):
    """A protected endpoint that requires login."""
    user = request.session.get("user")
    return {"message": "This is a protected page.", "user": user}
