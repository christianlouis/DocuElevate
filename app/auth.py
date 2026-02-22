import hashlib
import inspect
import logging
import pathlib
from functools import wraps

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request, status
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse

from app.config import settings

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
    """Show login page with appropriate authentication options"""
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": request.query_params.get("error"),
            "message": request.query_params.get("message"),
            "show_oauth": OAUTH_CONFIGURED,
            "oauth_provider_name": OAUTH_PROVIDER_NAME,
            "app_version": settings.version,  # Changed from app_version to version
        },
    )


async def oauth_login(request: Request):
    """Handle OAuth login flow"""
    if not OAUTH_CONFIGURED:
        return RedirectResponse(url="/login?error=OAuth+not+configured", status_code=status.HTTP_302_FOUND)

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

        # Log the successful authentication
        logger.info(f"[SECURITY] OAUTH_LOGIN_SUCCESS user={user_data.get('email', 'unknown')} admin={is_admin}")

        # Redirect to original destination or default
        redirect_url = request.session.pop("redirect_after_login", "/upload")
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    except Exception as e:
        logger.warning(f"[SECURITY] OAUTH_LOGIN_FAILURE error={type(e).__name__}")
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
        logger.info(f"[SECURITY] LOCAL_LOGIN_SUCCESS user={username}")
        # Redirect to original destination or default
        redirect_url = request.session.pop("redirect_after_login", "/upload")
        return RedirectResponse(url=redirect_url, status_code=302)
    else:
        logger.warning(f"[SECURITY] LOCAL_LOGIN_FAILURE user={username}")
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
