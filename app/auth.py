import hashlib
import inspect
import pathlib
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlsplit

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, RedirectResponse

from app.config import settings
from app.database import SessionLocal
from app.models import EvergreenMobileToken

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
    mobile_user = getattr(request.state, "mobile_user", None)
    return (mobile_user if isinstance(mobile_user, dict) else None) or request.session.get("user")


def validate_mobile_redirect_uri(value: str | None) -> str | None:
    """Accept only the native production callback (or local Expo callback)."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return None
        if value == "docuelevate://callback":
            return value
        if parsed.scheme == "exp" and parsed.hostname in {"localhost", "127.0.0.1"}:
            if parsed.port and parsed.port not in {19000, 19001, 19002, 8081}:
                return None
            if parsed.path in {"/--/callback", "/callback"}:
                return value
    except ValueError:
        return None
    return None


def _profile_from_user(user: dict) -> dict:
    email = str(user.get("email") or "").strip()
    if not email:
        raise ValueError("Authenticated user has no email")
    return {
        "user_id": str(user.get("id") or user.get("sub") or email),
        "email": email,
        "display_name": str(user.get("name") or user.get("preferred_username") or email),
        "avatar_url": user.get("picture") or user.get("avatar_url"),
        "is_admin": bool(user.get("is_admin", False)),
        "preferred_language": user.get("preferred_language"),
    }


def issue_mobile_token(user: dict, db: Session | None = None) -> str:
    """Persist only a SHA-256 token hash; return the opaque token once."""
    profile = _profile_from_user(user)
    token = secrets.token_urlsafe(32)
    owns_session = db is None
    db = db or SessionLocal()
    try:
        db.add(
            EvergreenMobileToken(
                token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                **profile,
            )
        )
        db.commit()
        return token
    finally:
        if owns_session:
            db.close()


def _mobile_user_from_token(token: str) -> dict | None:
    if not isinstance(token, str) or not token or len(token) > 256:
        return None
    db = SessionLocal()
    try:
        record = (
            db.query(EvergreenMobileToken)
            .filter(
                EvergreenMobileToken.token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest(),
                EvergreenMobileToken.revoked_at.is_(None),
            )
            .first()
        )
        if not record:
            return None
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = expires_at.astimezone(timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            return None
        return {
            "id": record.user_id,
            "sub": record.user_id,
            "email": record.email,
            "name": record.display_name,
            "picture": record.avatar_url,
            "avatar_url": record.avatar_url,
            "is_admin": bool(record.is_admin),
            "preferred_language": record.preferred_language,
        }
    finally:
        db.close()


def mobile_or_web_login(func):
    """Allow an existing browser session or bearer token on scoped mobile routes."""

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if request.session.get("user") or not AUTH_ENABLED:
            return (
                await func(request, *args, **kwargs)
                if inspect.iscoroutinefunction(func)
                else func(request, *args, **kwargs)
            )
        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
        user = _mobile_user_from_token(token)
        if user:
            request.state.mobile_user = user
            return (
                await func(request, *args, **kwargs)
                if inspect.iscoroutinefunction(func)
                else func(request, *args, **kwargs)
            )
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        request.session["redirect_after_login"] = str(request.url)
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    return wrapper


def mobile_user_or_401(request: Request) -> dict:
    state_user = getattr(request.state, "mobile_user", None)
    user = (state_user if isinstance(state_user, dict) else None) or request.session.get("user")
    if not user:
        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
        user = _mobile_user_from_token(token)
        if user:
            request.state.mobile_user = user
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


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
    """Show login page with appropriate authentication options"""
    if request.query_params.get("mobile") == "1":
        mobile_redirect_uri = validate_mobile_redirect_uri(request.query_params.get("redirect_uri"))
        if not mobile_redirect_uri:
            return JSONResponse({"detail": "Invalid mobile callback"}, status_code=400)
        request.session["mobile_redirect_uri"] = mobile_redirect_uri
    elif not request.query_params.get("error"):
        # A fresh browser login must not inherit an abandoned native login.
        request.session.pop("mobile_redirect_uri", None)
    mobile_redirect_uri = validate_mobile_redirect_uri(request.session.get("mobile_redirect_uri"))
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": request.query_params.get("error"),
            "message": request.query_params.get("message"),
            "show_oauth": OAUTH_CONFIGURED,
            "oauth_provider_name": OAUTH_PROVIDER_NAME,
            "app_version": settings.version,  # Changed from app_version to version
            "mobile": mobile_redirect_uri is not None,
            "mobile_redirect_uri": mobile_redirect_uri,
        },
    )


async def oauth_login(request: Request):
    """Handle OAuth login flow"""
    if not OAUTH_CONFIGURED:
        return RedirectResponse(url="/login?error=OAuth+not+configured", status_code=status.HTTP_302_FOUND)

    mobile_redirect_uri = validate_mobile_redirect_uri(
        request.query_params.get("redirect_uri")
    ) or validate_mobile_redirect_uri(request.session.get("mobile_redirect_uri"))
    if request.query_params.get("mobile") == "1" or mobile_redirect_uri:
        if not mobile_redirect_uri:
            return JSONResponse({"detail": "Invalid mobile callback"}, status_code=400)
        request.session["mobile_redirect_uri"] = mobile_redirect_uri
    redirect_uri = request.url_for("oauth_callback")
    return await oauth.authentik.authorize_redirect(request, redirect_uri)


async def oauth_callback(request: Request):
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

        mobile_redirect_uri = validate_mobile_redirect_uri(request.session.pop("mobile_redirect_uri", None))
        if mobile_redirect_uri:
            try:
                token_value = issue_mobile_token(user_data)
            except Exception:
                return RedirectResponse(url=f"{mobile_redirect_uri}?error=mobile_token_failed", status_code=302)
            return RedirectResponse(url=f"{mobile_redirect_uri}?token={token_value}", status_code=302)

        # Log the successful authentication
        print(f"User authenticated via OAuth: {user_data.get('email', 'No email')} (admin: {is_admin})")

        # Redirect to original destination or default
        redirect_url = request.session.pop("redirect_after_login", "/upload")
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"OAuth authentication error: {str(e)}")
        return RedirectResponse(url=f"/login?error=Authentication+failed:+{str(e)}", status_code=status.HTTP_302_FOUND)


async def auth(request: Request):
    """Handle local username/password authentication"""
    form_data = await request.form()
    username = form_data.get("username")
    password = form_data.get("password")

    if username == settings.admin_username and password == settings.admin_password:
        # Create user session
        request.session["user"] = {
            "id": "admin",
            "name": "Administrator",
            "email": f"{username}@local.docuelevate",
            "preferred_username": username,
            "picture": "/static/images/default-avatar.svg",
            "is_admin": True,
        }
        mobile_redirect_uri = validate_mobile_redirect_uri(request.session.pop("mobile_redirect_uri", None))
        if form_data.get("mobile") == "1":
            mobile_redirect_uri = validate_mobile_redirect_uri(form_data.get("redirect_uri"))
        if mobile_redirect_uri:
            try:
                token_value = issue_mobile_token(request.session["user"])
            except Exception:
                return RedirectResponse(url=f"{mobile_redirect_uri}?error=mobile_token_failed", status_code=302)
            return RedirectResponse(url=f"{mobile_redirect_uri}?token={token_value}", status_code=302)
        # Redirect to original destination or default
        redirect_url = request.session.pop("redirect_after_login", "/upload")
        return RedirectResponse(url=redirect_url, status_code=302)
    else:
        return RedirectResponse(url="/login?error=Invalid+username+or+password", status_code=302)


async def logout(request: Request):
    """Handle user logout"""
    request.session.pop("user", None)
    request.session.pop("mobile_redirect_uri", None)
    return RedirectResponse(url="/login?message=You+have+been+logged+out+successfully", status_code=302)


if AUTH_ENABLED:
    router.add_api_route("/login", login, methods=["GET"])
    router.add_api_route("/oauth-login", oauth_login, methods=["GET"])
    router.add_api_route("/oauth-callback", oauth_callback, methods=["GET"])
    router.add_api_route("/auth", auth, methods=["POST"])
    router.add_api_route("/logout", logout, methods=["GET"])


@router.get("/api/auth/whoami")
@mobile_or_web_login
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
