import hashlib
import inspect
import logging
import pathlib
from functools import wraps

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Request, status
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.config import settings
from app.database import get_db

oauth = OAuth()

logger = logging.getLogger(__name__)

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
    return request.session.get("user")


def require_login(func):
    if not AUTH_ENABLED:
        return func  # no-op

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if not request.session.get("user"):
            request.session["redirect_after_login"] = str(request.url)
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        # Check if the wrapped function is a coroutine function
        if inspect.iscoroutinefunction(func):
            return await func(request, *args, **kwargs)
        else:
            return func(request, *args, **kwargs)

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
            "allow_signup": settings.allow_local_signup,
        },
    )


async def oauth_login(request: Request):
    """Handle OAuth login flow"""
    if not OAUTH_CONFIGURED:
        return RedirectResponse(url="/login?error=OAuth+not+configured", status_code=status.HTTP_302_FOUND)

    redirect_uri = request.url_for("oauth_callback")
    return await oauth.authentik.authorize_redirect(request, redirect_uri)


def _ensure_user_profile(db: Session, user_data: dict) -> None:
    """Create a UserProfile row for *user_data* if one does not yet exist.

    Uses the same identifier priority as ``get_current_owner_id`` (sub →
    preferred_username → email → id) so that the profile's ``user_id`` matches
    ``FileRecord.owner_id`` for every document the user uploads.

    If a profile already exists it is left unchanged; only missing profiles
    are created so that admin-managed settings (tier, limits, etc.) are
    preserved across logins.
    """
    from app.models import UserProfile

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
            profile = UserProfile(user_id=user_id, display_name=display_name)
            db.add(profile)
            db.commit()
            logger.info("Auto-created UserProfile for user_id=%s", user_id)
    except Exception:
        db.rollback()
        logger.exception("Failed to auto-create UserProfile for user_id=%s", user_id)


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
        _ensure_user_profile(db, user_data)

        # Log the successful authentication
        logger.info("[SECURITY] OAUTH_LOGIN_SUCCESS user=%s admin=%s", user_data.get("email", "unknown"), is_admin)

        # Redirect first-time users to onboarding
        user_id = (
            user_data.get("sub") or user_data.get("preferred_username") or user_data.get("email") or user_data.get("id")
        )
        if user_id:
            from app.models import UserProfile as _UserProfile

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

    Checks LocalUser accounts first, then falls back to admin credentials.
    """
    form_data = await request.form()
    username = form_data.get("username")
    password = form_data.get("password")

    # --- LocalUser check ---
    from app.models import LocalUser as _LocalUser
    from app.models import UserProfile as _UserProfile
    from app.utils.local_auth import build_session_user as _build_session_user
    from app.utils.local_auth import verify_password as _verify_password

    local_user = db.query(_LocalUser).filter((_LocalUser.username == username) | (_LocalUser.email == username)).first()
    if local_user is not None:
        if not _verify_password(password or "", local_user.hashed_password):
            logger.warning("[SECURITY] LOCAL_LOGIN_FAILURE user=%s", username)
            return RedirectResponse(url="/login?error=Invalid+username+or+password", status_code=302)
        if not local_user.is_active:
            logger.warning("[SECURITY] LOCAL_LOGIN_UNVERIFIED user=%s", username)
            return RedirectResponse(
                url="/login?error=Please+verify+your+email+address+before+logging+in",
                status_code=302,
            )
        user_data = _build_session_user(local_user)
        request.session["user"] = user_data
        logger.info("[SECURITY] LOCAL_LOGIN_SUCCESS user=%s", local_user.email)
        profile = db.query(_UserProfile).filter(_UserProfile.user_id == local_user.email).first()
        if profile and not profile.onboarding_completed:
            post_onboarding = request.session.pop("redirect_after_login", "/upload")
            request.session["post_onboarding_redirect"] = post_onboarding
            return RedirectResponse(url="/onboarding", status_code=302)
        redirect_url = request.session.pop("redirect_after_login", "/upload")
        return RedirectResponse(url=redirect_url, status_code=302)

    # --- Admin credentials fallback ---
    if username == settings.admin_username and password == settings.admin_password:
        request.session["user"] = {
            "id": "admin",
            "name": "Administrator",
            "email": f"{username}@local.docuelevate",
            "preferred_username": username,
            "picture": "/static/images/default-avatar.svg",
            "is_admin": True,
        }
        logger.info("[SECURITY] LOCAL_LOGIN_SUCCESS user=%s", username)
        redirect_url = request.session.pop("redirect_after_login", "/upload")
        return RedirectResponse(url=redirect_url, status_code=302)
    else:
        logger.warning("[SECURITY] LOCAL_LOGIN_FAILURE user=%s", username)
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
    user = request.session.get("user")
    return user or {"error": "Not authenticated"}


@router.get("/private")
@require_login
async def private_page(request: Request):
    """A protected endpoint that requires login."""
    user = request.session.get("user")
    return {"message": "This is a protected page.", "user": user}
