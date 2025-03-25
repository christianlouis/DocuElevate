# app/auth.py
import os
from functools import wraps

from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from fastapi import APIRouter, Request, status
from starlette.responses import RedirectResponse

config = Config(".env")
oauth = OAuth(config)

oauth.register(
    name="authentik",
    client_id=config("AUTHENTIK_CLIENT_ID"),
    client_secret=config("AUTHENTIK_CLIENT_SECRET"),
    server_metadata_url=config("AUTHENTIK_CONFIG_URL"),
    client_kwargs={
        "scope": "openid profile email",
    },
)

router = APIRouter()

def get_current_user(request: Request):
    return request.session.get("user")

def require_login(func):
    """Decorator to require login for particular endpoints."""
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if not request.session.get("user"):
            # Not logged in => redirect to /login
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        # User is logged in => proceed
        return await func(request, *args, **kwargs)
    return wrapper

@router.get("/login")
async def login(request: Request):
    """
    Initiate Authentik login flow.
    This calls oauth.authentik.authorize_redirect(...)
    The resulting redirect_uri must match what's in Authentik's application config.
    """
    redirect_uri = request.url_for("auth")
    return await oauth.authentik.authorize_redirect(request, redirect_uri)

@router.get("/auth")
async def auth(request: Request):
    """
    Authentik callback endpoint. Exchanges code for token,
    puts user info in session, and redirects to /ui or wherever you want.
    """
    token = await oauth.authentik.authorize_access_token(request)
    userinfo = token.get("userinfo")
    request.session["user"] = dict(userinfo)
    return RedirectResponse(url="/ui")

@router.get("/logout")
async def logout(request: Request):
    """Clears session and redirects home."""
    request.session.pop("user", None)
    return RedirectResponse(url="/")

@router.get("/private")
@require_login
async def private_page(request: Request):
    """A protected endpoint that requires login."""
    user = request.session.get("user")  # e.g. {"email": "...", ...}
    return {"message": f"This is a protected page. Hello {user['email']}!"}
