import hashlib
import inspect
import logging
import pathlib
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlencode, urlparse

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.config import settings
from app.database import get_db
from app.middleware.audit_log import get_client_ip

# Conditional imports: only used when multi_user_enabled=True. Imported here at
# module level (not inside auth()) so they don't incur repeated import overhead.
# Guards at call-sites ensure they are never *called* in single-user mode.
from app.models import LocalUser as _LocalUser
from app.models import UserProfile as _UserProfile
from app.utils.i18n import translate as _translate
from app.utils.local_auth import build_session_user as _build_session_user
from app.utils.local_auth import verify_password as _verify_password

logger = logging.getLogger(__name__)

oauth = OAuth()

AUTH_ENABLED = settings.auth_enabled

# Set up templates for authentication
templates_dir = pathlib.Path(__file__).parents[1] / "frontend" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))
templates.env.globals["_"] = lambda key, **kwargs: _translate(key, "en", **kwargs)

# Configure OAuth provider if credentials are provided
OAUTH_CONFIGURED = False
OAUTH_PROVIDER_NAME = "Single Sign-On"

# Social login providers that are enabled and registered
SOCIAL_PROVIDERS: dict[str, dict[str, str]] = {}

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

# --- Social Login Providers ---------------------------------------------------
if AUTH_ENABLED and settings.social_auth_google_enabled:
    if settings.social_auth_google_client_id and settings.social_auth_google_client_secret:
        oauth.register(
            name="google",
            client_id=settings.social_auth_google_client_id,
            client_secret=settings.social_auth_google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid profile email"},
        )
        SOCIAL_PROVIDERS["google"] = {"name": "Google", "icon": "fab fa-google", "color": "red"}
        logger.info("Social login provider registered: Google")
    else:
        logger.warning("SOCIAL_AUTH_GOOGLE_ENABLED=true but client ID/secret not configured")

if AUTH_ENABLED and settings.social_auth_microsoft_enabled:
    if settings.social_auth_microsoft_client_id and settings.social_auth_microsoft_client_secret:
        tenant = settings.social_auth_microsoft_tenant or "common"
        oauth.register(
            name="microsoft",
            client_id=settings.social_auth_microsoft_client_id,
            client_secret=settings.social_auth_microsoft_client_secret,
            server_metadata_url=f"https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration",
            client_kwargs={"scope": "openid profile email"},
        )
        SOCIAL_PROVIDERS["microsoft"] = {"name": "Microsoft", "icon": "fab fa-microsoft", "color": "blue"}
        logger.info("Social login provider registered: Microsoft (tenant=%s)", tenant)
    else:
        logger.warning("SOCIAL_AUTH_MICROSOFT_ENABLED=true but client ID/secret not configured")

if AUTH_ENABLED and settings.social_auth_apple_enabled:
    if settings.social_auth_apple_client_id and settings.social_auth_apple_team_id:
        oauth.register(
            name="apple",
            client_id=settings.social_auth_apple_client_id,
            server_metadata_url="https://appleid.apple.com/.well-known/openid-configuration",
            client_kwargs={
                "scope": "openid name email",
                "response_mode": "form_post",
            },
        )
        SOCIAL_PROVIDERS["apple"] = {"name": "Apple", "icon": "fab fa-apple", "color": "gray"}
        logger.info("Social login provider registered: Apple")
    else:
        logger.warning("SOCIAL_AUTH_APPLE_ENABLED=true but client ID/team ID not configured")

if AUTH_ENABLED and settings.social_auth_dropbox_enabled:
    if settings.social_auth_dropbox_client_id and settings.social_auth_dropbox_client_secret:
        oauth.register(
            name="dropbox",
            client_id=settings.social_auth_dropbox_client_id,
            client_secret=settings.social_auth_dropbox_client_secret,
            authorize_url="https://www.dropbox.com/oauth2/authorize",
            access_token_url="https://api.dropboxapi.com/oauth2/token",
            userinfo_endpoint="https://api.dropboxapi.com/2/users/get_current_account",
            client_kwargs={"token_endpoint_auth_method": "client_secret_post"},
        )
        SOCIAL_PROVIDERS["dropbox"] = {"name": "Dropbox", "icon": "fab fa-dropbox", "color": "blue"}
        logger.info("Social login provider registered: Dropbox")
    else:
        logger.warning("SOCIAL_AUTH_DROPBOX_ENABLED=true but client ID/secret not configured")

router = APIRouter()


def get_current_user(request: Request):
    # Check for Bearer token auth first (API tokens)
    api_user = getattr(request.state, "api_token_user", None)
    if isinstance(api_user, dict):
        logger.debug("[AUTH] get_current_user: resolved from API token (user_id=%s)", api_user.get("id"))
        return api_user
    session_user = request.session.get("user")
    if session_user:
        # Validate server-side session if a session token is present
        session_token = request.session.get("_session_token")
        if session_token:
            try:
                from app.database import SessionLocal
                from app.utils.session_manager import validate_session

                db = SessionLocal()
                try:
                    valid = validate_session(db, session_token)
                    if not valid:
                        logger.debug("[AUTH] get_current_user: server-side session invalid — clearing")
                        request.session.pop("user", None)
                        request.session.pop("_session_token", None)
                        return None
                finally:
                    db.close()
            except Exception:
                logger.debug("[AUTH] get_current_user: session validation error", exc_info=True)
        logger.debug(
            "[AUTH] get_current_user: resolved from session (user=%s)",
            session_user.get("preferred_username") or session_user.get("email") or session_user.get("id"),
        )
    else:
        logger.debug("[AUTH] get_current_user: no user in session or API token")
    return session_user


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
        logger.debug("[AUTH] _resolve_bearer_user: no Bearer token in Authorization header")
        return None

    raw_token = auth_header[7:]
    if not raw_token or not isinstance(raw_token, str):
        logger.debug("[AUTH] _resolve_bearer_user: empty or invalid token after 'Bearer ' prefix")
        return None

    from app.api.api_tokens import hash_token
    from app.models import ApiToken

    token_hash = hash_token(raw_token)
    db_token = db.query(ApiToken).filter(ApiToken.token_hash == token_hash, ApiToken.is_active.is_(True)).first()
    if db_token is None:
        logger.debug("[AUTH] _resolve_bearer_user: no active API token matched the provided hash")
        return None

    logger.debug(
        "[AUTH] _resolve_bearer_user: matched API token id=%s owner=%s",
        db_token.id,
        db_token.owner_id,
    )

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
        url_path = urlparse(str(request.url)).path
        # Check session auth first
        if request.session.get("user"):
            logger.debug("[AUTH] require_login: session auth OK for %s", url_path)
            if inspect.iscoroutinefunction(func):
                return await func(*args, request=request, **kwargs)
            else:
                return func(*args, request=request, **kwargs)

        # Fall back to Bearer token auth for API endpoints
        if url_path.startswith("/api/"):
            logger.debug("[AUTH] require_login: no session, trying Bearer token for %s", url_path)
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
                logger.debug(
                    "[AUTH] require_login: Bearer token auth OK for %s (user=%s)", url_path, api_user.get("id")
                )
                if inspect.iscoroutinefunction(func):
                    return await func(*args, request=request, **kwargs)
                else:
                    return func(*args, request=request, **kwargs)

            logger.debug("[AUTH] require_login: no valid auth for API endpoint %s — returning 401", url_path)
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Not authenticated"},
            )

        # Non-API endpoint with no session — redirect to login
        logger.debug("[AUTH] require_login: no session for %s — redirecting to /login", url_path)
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
    # Persist the mobile deep-link redirect URI in the session so it survives
    # the OAuth provider round-trip and is available when auth completes.
    # Accepted schemes:
    #   • "docuelevate://" — production / EAS builds (custom app scheme)
    #   • "exp://"         — Expo Go development client
    # Only custom (non-HTTP) schemes are accepted to prevent open-redirect abuse.
    _MOBILE_ALLOWED_SCHEMES = ("docuelevate://", "exp://")
    if request.query_params.get("mobile") == "1":
        redirect_uri = request.query_params.get("redirect_uri", "")
        logger.debug(
            "[MOBILE] Login page opened with mobile=1: redirect_uri=%r client_ip=%s",
            redirect_uri,
            get_client_ip(request),
        )
        if any(redirect_uri.startswith(s) for s in _MOBILE_ALLOWED_SCHEMES):
            request.session["mobile_redirect_uri"] = redirect_uri
            logger.info(
                "[MOBILE] Mobile redirect URI stored in session: %r",
                redirect_uri,
            )
        else:
            logger.warning(
                "[MOBILE] Rejected redirect_uri with disallowed scheme: %r (allowed: %s)",
                redirect_uri,
                ", ".join(_MOBILE_ALLOWED_SCHEMES),
            )
    else:
        logger.debug(
            "[MOBILE] Login page opened without mobile=1 (standard browser flow) client_ip=%s",
            get_client_ip(request),
        )

    return templates.TemplateResponse(
        request,
        "login.html",
        context={
            "error": request.query_params.get("error"),
            "message": request.query_params.get("message"),
            "show_oauth": OAUTH_CONFIGURED,
            "oauth_provider_name": OAUTH_PROVIDER_NAME,
            "social_providers": SOCIAL_PROVIDERS,
            "app_version": settings.version,
            "csrf_token": getattr(request.state, "csrf_token", ""),
            # "Create account" link is only shown when multi-user mode AND local signup are both enabled
            "allow_signup": settings.multi_user_enabled and settings.allow_local_signup,
        },
    )


async def oauth_login(request: Request):
    """Handle OAuth login flow"""
    if not OAUTH_CONFIGURED:
        logger.debug("[AUTH] oauth_login: OAuth not configured — redirecting to /login")
        return RedirectResponse(url="/login?error=OAuth+not+configured", status_code=status.HTTP_302_FOUND)

    redirect_uri = request.url_for("oauth_callback")
    logger.debug(
        "[AUTH] oauth_login: initiating Authentik OAuth redirect_uri=%s session_keys=%s",
        redirect_uri,
        list(request.session.keys()),
    )
    return await oauth.authentik.authorize_redirect(request, redirect_uri)


async def social_login(request: Request, provider: str):
    """Initiate a social login flow for the given provider.

    Args:
        request: The current FastAPI request.
        provider: One of the registered social provider keys (google, microsoft, apple, dropbox).

    Returns:
        A redirect to the provider's authorization page, or back to /login on error.
    """
    if provider not in SOCIAL_PROVIDERS:
        logger.debug(
            "[AUTH] social_login: unknown provider=%r (registered=%s)", provider, list(SOCIAL_PROVIDERS.keys())
        )
        return RedirectResponse(url="/login?error=Unknown+social+provider", status_code=status.HTTP_302_FOUND)

    redirect_uri = request.url_for("social_callback", provider=provider)
    oauth_client = getattr(oauth, provider, None)
    if oauth_client is None:
        logger.debug("[AUTH] social_login: provider=%r registered but OAuth client not configured", provider)
        return RedirectResponse(url="/login?error=Provider+not+configured", status_code=status.HTTP_302_FOUND)

    logger.debug(
        "[AUTH] social_login: initiating %s OAuth, redirect_uri=%s session_keys=%s",
        provider,
        redirect_uri,
        list(request.session.keys()),
    )
    return await oauth_client.authorize_redirect(request, redirect_uri)


def _normalize_social_userinfo(provider: str, token: dict, raw_userinfo: dict | None) -> dict:
    """Normalize the userinfo payload from different social providers into a common format.

    Returns a dict with keys: sub, email, name, preferred_username, picture.

    Args:
        provider: The social provider key (google, microsoft, apple, dropbox).
        token: The OAuth token response from the provider. Included for future
            provider-specific claim extraction (e.g. ``id_token`` claims).
        raw_userinfo: The raw userinfo dict (may be None for providers without standard OIDC userinfo).

    Returns:
        A normalized user-data dict compatible with the session user format.
    """
    userinfo: dict = raw_userinfo or {}

    if provider == "dropbox":
        # Dropbox returns a non-standard userinfo response
        email = userinfo.get("email", "")
        name_info = userinfo.get("name", {})
        display_name = name_info.get("display_name", "") if isinstance(name_info, dict) else str(name_info)
        return {
            "sub": userinfo.get("account_id", email),
            "email": email,
            "name": display_name,
            "preferred_username": email,
            "picture": userinfo.get("profile_photo_url", ""),
        }

    # Standard OIDC providers (Google, Microsoft, Apple)
    return {
        "sub": userinfo.get("sub", ""),
        "email": userinfo.get("email", ""),
        "name": userinfo.get("name", ""),
        "preferred_username": userinfo.get("email", ""),
        "picture": userinfo.get("picture", ""),
    }


async def social_callback(request: Request, provider: str, db: Session = Depends(get_db)):
    """Handle the OAuth callback from a social login provider.

    After the user authorizes with the social provider, this endpoint exchanges
    the authorization code for tokens, extracts user information, creates or
    updates the user profile, and establishes a session.

    Args:
        request: The current FastAPI request.
        provider: One of the registered social provider keys.
        db: Database session (injected).

    Returns:
        A redirect to the user's original destination or the upload page.
    """
    if provider not in SOCIAL_PROVIDERS:
        logger.debug("[AUTH] social_callback: unknown provider=%r", provider)
        return RedirectResponse(url="/login?error=Unknown+social+provider", status_code=status.HTTP_302_FOUND)

    oauth_client = getattr(oauth, provider, None)
    if oauth_client is None:
        logger.debug("[AUTH] social_callback: provider=%r not configured", provider)
        return RedirectResponse(url="/login?error=Provider+not+configured", status_code=status.HTTP_302_FOUND)

    try:
        logger.debug("[AUTH] social_callback: exchanging auth code for provider=%s", provider)
        token = await oauth_client.authorize_access_token(request)

        # Try standard OIDC userinfo first, fall back to token-embedded userinfo
        raw_userinfo = token.get("userinfo")
        if not raw_userinfo:
            logger.debug("[AUTH] social_callback: no userinfo in token, fetching from userinfo endpoint")
            try:
                resp = await oauth_client.userinfo(token=token)
                raw_userinfo = resp if isinstance(resp, dict) else resp.json() if hasattr(resp, "json") else {}
            except Exception:
                logger.debug("[AUTH] social_callback: userinfo endpoint failed, using empty dict", exc_info=True)
                raw_userinfo = {}

        user_data = _normalize_social_userinfo(provider, token, raw_userinfo)
        logger.debug(
            "[AUTH] social_callback: normalized user_data email=%s sub=%s provider=%s",
            user_data.get("email"),
            user_data.get("sub"),
            provider,
        )

        if not user_data.get("email"):
            logger.debug("[AUTH] social_callback: no email in user_data — aborting")
            return RedirectResponse(
                url="/login?error=Could+not+retrieve+email+from+provider",
                status_code=status.HTTP_302_FOUND,
            )

        # Add Gravatar if no picture provided
        if not user_data.get("picture") and user_data.get("email"):
            user_data["picture"] = get_gravatar_url(user_data["email"])

        # Tag the login source for audit/debugging
        user_data["auth_provider"] = provider

        # Social login users are never admin by default (admin must be granted
        # via the Authentik/OIDC admin group or manually in the admin panel)
        user_data["is_admin"] = False

        request.session["user"] = user_data

        # Create server-side session for tracking and revocation
        try:
            from app.utils.session_manager import create_session

            _session_user_id = (
                user_data.get("sub")
                or user_data.get("preferred_username")
                or user_data.get("email")
                or user_data.get("id")
            )
            if _session_user_id:
                user_session = create_session(
                    db,
                    user_id=_session_user_id,
                    ip_address=get_client_ip(request),
                    user_agent=request.headers.get("user-agent"),
                )
                request.session["_session_token"] = user_session.session_token
        except Exception:
            logger.debug("[AUTH] Failed to create server-side session for social user", exc_info=True)

        # Auto-create or update UserProfile
        _ensure_user_profile(db, user_data, is_admin=False)

        provider_name = SOCIAL_PROVIDERS[provider]["name"]
        logger.info(
            "[SECURITY] SOCIAL_LOGIN_SUCCESS provider=%s user=%s", provider_name, user_data.get("email", "unknown")
        )

        # Redirect first-time users to onboarding
        user_id = (
            user_data.get("sub") or user_data.get("preferred_username") or user_data.get("email") or user_data.get("id")
        )

        # Mobile app flow: issue an inline API token and redirect back to the app.
        logger.debug(
            "[MOBILE] social_callback: checking for mobile redirect (session has mobile_redirect_uri=%s)",
            "mobile_redirect_uri" in request.session,
        )
        mobile_resp = _create_mobile_redirect(request, db)
        if mobile_resp:
            logger.info("[MOBILE] social_callback: returning mobile redirect response for provider=%s", provider)
            return mobile_resp

        if user_id:
            profile = db.query(_UserProfile).filter(_UserProfile.user_id == user_id).first()
            if profile and not profile.onboarding_completed:
                logger.debug("[AUTH] social_callback: user=%s needs onboarding, redirecting", user_id)
                post_onboarding = request.session.pop("redirect_after_login", "/upload")
                request.session["post_onboarding_redirect"] = post_onboarding
                return RedirectResponse(url="/onboarding", status_code=status.HTTP_302_FOUND)

        redirect_url = request.session.pop("redirect_after_login", "/upload")
        logger.debug("[AUTH] social_callback: login complete, redirecting to %s", redirect_url)
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    except Exception as e:
        logger.warning("[SECURITY] SOCIAL_LOGIN_FAILURE provider=%s error=%s", provider, type(e).__name__)
        logger.debug("[AUTH] social_callback: full exception for provider=%s", provider, exc_info=True)
        return RedirectResponse(
            url="/login?error=Social+login+failed.+Please+try+again.", status_code=status.HTTP_302_FOUND
        )


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
        logger.debug("[AUTH] oauth_callback: exchanging authorization code for token")
        token = await oauth.authentik.authorize_access_token(request)
        userinfo = token.get("userinfo")
        if not userinfo:
            logger.debug("[AUTH] oauth_callback: no userinfo in token response — aborting")
            return RedirectResponse(
                url="/login?error=Failed+to+retrieve+user+information", status_code=status.HTTP_302_FOUND
            )

        # Store user info in session
        user_data = dict(userinfo)
        logger.debug(
            "[AUTH] oauth_callback: received userinfo email=%s sub=%s groups=%s",
            user_data.get("email"),
            user_data.get("sub"),
            user_data.get("groups", []),
        )

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
            logger.debug(
                "[AUTH] oauth_callback: admin group check — looking for %r in %s → is_admin=%s",
                admin_group,
                [g.lower() for g in groups],
                is_admin,
            )

        # Set is_admin flag (defaults to False for OAuth users unless they're in admin group)
        user_data["is_admin"] = is_admin

        request.session["user"] = user_data

        # Create server-side session for tracking and revocation
        try:
            from app.utils.session_manager import create_session

            _session_user_id = (
                user_data.get("sub")
                or user_data.get("preferred_username")
                or user_data.get("email")
                or user_data.get("id")
            )
            if _session_user_id:
                user_session = create_session(
                    db,
                    user_id=_session_user_id,
                    ip_address=get_client_ip(request),
                    user_agent=request.headers.get("user-agent"),
                )
                request.session["_session_token"] = user_session.session_token
        except Exception:
            logger.debug("[AUTH] Failed to create server-side session for OAuth user", exc_info=True)

        # Auto-create or update UserProfile so the user appears in admin user management
        _ensure_user_profile(db, user_data, is_admin=is_admin)

        # Log the successful authentication
        logger.info("[SECURITY] OAUTH_LOGIN_SUCCESS user=%s admin=%s", user_data.get("email", "unknown"), is_admin)
        _record_login_event(
            db,
            request,
            user_data.get("email") or user_data.get("preferred_username") or "unknown",
            success=True,
            method="oauth",
        )

        # Redirect first-time users to onboarding
        user_id = (
            user_data.get("sub") or user_data.get("preferred_username") or user_data.get("email") or user_data.get("id")
        )

        # Mobile app flow: issue an inline API token and redirect back to the app.
        # This check runs before onboarding so native-app users are never sent
        # to the web-based onboarding wizard.
        logger.debug(
            "[MOBILE] oauth_callback: checking for mobile redirect (session has mobile_redirect_uri=%s)",
            "mobile_redirect_uri" in request.session,
        )
        mobile_resp = _create_mobile_redirect(request, db)
        if mobile_resp:
            logger.info("[MOBILE] oauth_callback: returning mobile redirect response")
            return mobile_resp

        if user_id:
            profile = db.query(_UserProfile).filter(_UserProfile.user_id == user_id).first()
            if profile and not profile.onboarding_completed:
                logger.debug("[AUTH] oauth_callback: user=%s needs onboarding, redirecting", user_id)
                post_onboarding = request.session.pop("redirect_after_login", "/upload")
                request.session["post_onboarding_redirect"] = post_onboarding
                return RedirectResponse(url="/onboarding", status_code=status.HTTP_302_FOUND)

        # Redirect to original destination or default
        redirect_url = request.session.pop("redirect_after_login", "/upload")
        logger.debug("[AUTH] oauth_callback: login complete, redirecting to %s", redirect_url)
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    except Exception as e:
        logger.warning(f"[SECURITY] OAUTH_LOGIN_FAILURE error={type(e).__name__}")
        logger.debug("[AUTH] oauth_callback: full exception details", exc_info=True)
        return RedirectResponse(url=f"/login?error=Authentication+failed:+{str(e)}", status_code=status.HTTP_302_FOUND)


def _record_login_event(
    db: Session,
    request: Request,
    username: str,
    *,
    success: bool,
    method: str = "local",
    detail: str | None = None,
) -> None:
    """Write a login or login-failure audit event to the database.

    Failures are silently swallowed so that an audit-service error never
    prevents a legitimate login or surfaces an unrelated 500 error to the user.

    Args:
        db: Active database session.
        request: The current HTTP request (used to extract the client IP).
        username: The username that attempted authentication.
        success: ``True`` for a successful login, ``False`` for a failure.
        method: Authentication method, e.g. ``"local"`` or ``"oauth"``.
        detail: Optional extra context for failures (e.g. ``"wrong_password"``).
    """
    try:
        from app.utils.audit_service import record_event

        action = "login" if success else "login.failure"
        details: dict = {"method": method}
        if detail:
            details["reason"] = detail
        record_event(
            db,
            action=action,
            user=username,
            resource_type="session",
            ip_address=get_client_ip(request),
            details=details,
            severity="info" if success else "warning",
        )
    except Exception:
        logger.debug("Failed to write login audit event for user=%s", username, exc_info=True)


def _create_mobile_redirect(request: Request, db: Session) -> RedirectResponse | None:
    """Generate a mobile API token and return a redirect to the mobile app.

    If ``mobile_redirect_uri`` is stored in the session (set when the login
    page was opened with ``?mobile=1&redirect_uri=docuelevate://...``), this
    function creates a long-lived API token, appends it as a ``?token=``
    query parameter to the redirect URI, and returns the redirect so that
    ``WebBrowser.openAuthSessionAsync`` in the Expo app intercepts the
    deep link and stores the token.

    Returns ``None`` when the request is not part of a mobile SSO flow.

    Args:
        request: The current FastAPI request.  The ``user`` dict must already
            be stored in ``request.session`` before calling this function.
        db: Active database session used to persist the new API token.

    Returns:
        A ``RedirectResponse`` to the deep-link URI with ``?token=<plaintext>``,
        or ``None`` if no mobile redirect URI is pending.
    """
    mobile_redirect_uri = request.session.pop("mobile_redirect_uri", None)
    if not mobile_redirect_uri:
        logger.debug("[MOBILE] _create_mobile_redirect: no mobile_redirect_uri in session — skipping mobile flow")
        return None

    logger.info(
        "[MOBILE] _create_mobile_redirect: mobile flow detected, redirect_uri=%r",
        mobile_redirect_uri,
    )

    user = request.session.get("user") or {}
    owner_id = user.get("sub") or user.get("preferred_username") or user.get("email") or user.get("id")
    logger.debug(
        "[MOBILE] Resolving owner_id from session user: sub=%r preferred_username=%r email=%r id=%r → owner_id=%r",
        user.get("sub"),
        user.get("preferred_username"),
        user.get("email"),
        user.get("id"),
        owner_id,
    )
    if not owner_id:
        logger.warning("Mobile SSO redirect requested but no owner_id could be resolved from session")
        return None

    # Lazy imports to avoid circular dependency via app.api.__init__
    from app.api.api_tokens import generate_api_token, hash_token
    from app.models import ApiToken as _ApiToken

    plaintext = generate_api_token()
    token_hash_value = hash_token(plaintext)
    prefix = plaintext[:12]

    db_token = _ApiToken(
        owner_id=owner_id,
        name="Mobile App",
        token_hash=token_hash_value,
        token_prefix=prefix,
    )
    try:
        db.add(db_token)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to create mobile API token for owner_id=%s", owner_id)
        return None

    # Safely append the token as a query parameter, preserving any existing params.
    separator = "&" if "?" in mobile_redirect_uri else "?"
    redirect_url = f"{mobile_redirect_uri}{separator}{urlencode({'token': plaintext})}"

    # Log the full redirect URL at DEBUG so it's visible when debug logging is enabled.
    # At INFO level, log a sanitised version (scheme + host only, token prefix only)
    # so the plaintext token is never written to persistent info logs.
    parsed = urlparse(redirect_url)
    existing_params = f"&{parsed.query.replace(f'token={plaintext}', '')}" if parsed.query else ""
    sanitised_url = (
        f"{parsed.scheme}://{parsed.netloc}{parsed.path}?token={prefix}…[redacted]{existing_params.rstrip('&')}"
    )
    logger.info(
        "[MOBILE] MOBILE_SSO_TOKEN_ISSUED owner=%s token_id=%s redirect_target=%s",
        owner_id,
        db_token.id,
        sanitised_url,
    )
    logger.debug(
        "[MOBILE] Full redirect URL being sent to client: %s",
        redirect_url,
    )
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


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

        username_lower = username.lower()
        local_user = (
            db.query(_LocalUser)
            .filter(
                (func.lower(_LocalUser.username) == username_lower) | (func.lower(_LocalUser.email) == username_lower)
            )
            .first()
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
                _record_login_event(db, request, username, success=False, detail="account_not_verified")
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
                _record_login_event(db, request, username, success=False, detail="wrong_password")
                return RedirectResponse(url="/login?error=Invalid+username+or+password", status_code=302)
            user_data = _build_session_user(local_user)
            request.session["user"] = user_data
            # Create server-side session for tracking and revocation
            try:
                from app.utils.session_manager import create_session

                user_session = create_session(
                    db,
                    user_id=local_user.email,
                    ip_address=get_client_ip(request),
                    user_agent=request.headers.get("user-agent"),
                )
                request.session["_session_token"] = user_session.session_token
            except Exception:
                logger.debug("[AUTH] Failed to create server-side session", exc_info=True)
            logger.info("[SECURITY] LOCAL_LOGIN_SUCCESS user=%s", local_user.email)
            _record_login_event(db, request, local_user.email, success=True)
            _ensure_user_profile(db, user_data, is_admin=bool(local_user.is_admin))

            # Mobile app flow: issue an inline API token and redirect back to the app.
            logger.debug(
                "[MOBILE] local auth: checking for mobile redirect (session has mobile_redirect_uri=%s)",
                "mobile_redirect_uri" in request.session,
            )
            mobile_resp = _create_mobile_redirect(request, db)
            if mobile_resp:
                logger.info("[MOBILE] local auth: returning mobile redirect response")
                return mobile_resp

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
        (username or "").lower() == settings.admin_username.lower() if admin_configured else False,
        settings.multi_user_enabled,
    )
    if (
        settings.admin_username
        and settings.admin_password
        and (username or "").lower() == settings.admin_username.lower()
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
        # Create server-side session for tracking and revocation
        try:
            from app.utils.session_manager import create_session

            admin_user_id = settings.admin_username or "admin"
            user_session = create_session(
                db,
                user_id=admin_user_id,
                ip_address=get_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
            request.session["_session_token"] = user_session.session_token
        except Exception:
            logger.debug("[AUTH] Failed to create server-side session for admin", exc_info=True)
        logger.info("[SECURITY] LOCAL_LOGIN_SUCCESS user=%s", username)
        _record_login_event(db, request, username, success=True)
        _ensure_user_profile(db, admin_user_data, is_admin=True)

        # Mobile app flow: issue an inline API token and redirect back to the app.
        logger.debug(
            "[MOBILE] admin auth: checking for mobile redirect (session has mobile_redirect_uri=%s)",
            "mobile_redirect_uri" in request.session,
        )
        mobile_resp = _create_mobile_redirect(request, db)
        if mobile_resp:
            logger.info("[MOBILE] admin auth: returning mobile redirect response")
            return mobile_resp

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
        _record_login_event(db, request, username or "anonymous", success=False, detail="invalid_credentials")
        return RedirectResponse(url="/login?error=Invalid+username+or+password", status_code=302)


async def logout(request: Request, db: Session = Depends(get_db)):
    """Handle user logout"""
    user = request.session.get("user")
    username = "unknown"
    if isinstance(user, dict):
        username = user.get("preferred_username") or user.get("email") or "unknown"
    logger.debug("[AUTH] logout: clearing session for user=%s client_ip=%s", username, get_client_ip(request))
    logger.info(f"[SECURITY] LOGOUT user={username}")
    try:
        from app.utils.audit_service import record_event

        record_event(
            db,
            action="logout",
            user=username,
            resource_type="session",
            ip_address=get_client_ip(request),
            severity="info",
        )
    except Exception:
        logger.debug("Failed to write logout audit event for user=%s", username, exc_info=True)
    # Revoke server-side session
    session_token = request.session.get("_session_token")
    if session_token:
        try:
            from app.utils.session_manager import validate_session

            user_session = validate_session(db, session_token)
            if user_session:
                user_session.is_revoked = True
                user_session.revoked_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            logger.debug("[AUTH] Failed to revoke server-side session", exc_info=True)
    request.session.pop("_session_token", None)
    request.session.pop("user", None)
    return RedirectResponse(url="/login?message=You+have+been+logged+out+successfully", status_code=302)


if AUTH_ENABLED:
    router.add_api_route("/login", login, methods=["GET"])
    router.add_api_route("/oauth-login", oauth_login, methods=["GET"])
    router.add_api_route("/oauth-callback", oauth_callback, methods=["GET"])
    router.add_api_route("/social-login/{provider}", social_login, methods=["GET"])
    router.add_api_route("/social-callback/{provider}", social_callback, methods=["GET"])
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
