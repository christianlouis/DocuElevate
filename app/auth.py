# app/auth.py
import os
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from starlette.middleware.sessions import SessionMiddleware
from fastapi import APIRouter, Request
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
    async def wrapper(request: Request, *args, **kwargs):
        if not request.session.get("user"):
            return RedirectResponse(url="/login")
        return await func(request, *args, **kwargs)
    return wrapper

@router.get("/login")
async def login(request: Request):
    redirect_uri = request.url_for("auth")
    return await oauth.authentik.authorize_redirect(request, redirect_uri)

@router.get("/auth")
async def auth(request: Request):
    token = await oauth.authentik.authorize_access_token(request)
    userinfo = token.get("userinfo")
    request.session["user"] = dict(userinfo)
    return RedirectResponse(url="/ui")

@router.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/")

@router.get("/private")
@require_login
async def private_page(request: Request):
    user = request.session.get("user")
    return {"message": f"This is a protected page. Hello {user['email']}!"}
