"""Coordinate authenticated requests with account deletion."""

from contextlib import AsyncExitStack

from starlette.requests import Request
from starlette.responses import JSONResponse


class AccountLifecycleMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from app.api.api_tokens import hash_token
        from app.database import SessionLocal
        from app.models import ApiToken
        from app.services.account_deletion import deletion_blocked
        from app.services.account_lifecycle_lock import async_account_lifecycle_lock
        from app.utils.user_scope import _owner_id_from_user

        request = Request(scope, receive=receive)
        path = request.url.path.rstrip("/")
        if (
            (path == "/api/account" and request.method in {"GET", "DELETE"})
            or path in {"/auth", "/oauth-callback", "/api/auth/signup"}
            or path.startswith("/social-callback/")
        ):
            return await self.app(scope, receive, send)
        # Anonymous requests have no owner whose deletion fence can apply.
        # Avoid opening a database session for them; this also keeps optional
        # integrations usable when their own persistence probe is being tested.
        session_user = request.session.get("user")
        auth = request.headers.get("authorization", "")
        if not isinstance(session_user, dict) and not auth.startswith("Bearer "):
            return await self.app(scope, receive, send)

        db = SessionLocal()
        try:
            owner = _owner_id_from_user(session_user) if isinstance(session_user, dict) else None
            owners = {owner} if owner else set()
            if auth.startswith("Bearer "):
                token = db.query(ApiToken).filter_by(token_hash=hash_token(auth[7:]), is_active=True).first()
                if token and token.owner_id:
                    owners.add(token.owner_id)
            if not owners:
                return await self.app(scope, receive, send)
            # Release a token lookup connection before waiting for a lifecycle lock.
            db.rollback()
            async with AsyncExitStack() as stack:
                for owner in sorted(owners):
                    await stack.enter_async_context(async_account_lifecycle_lock(db, owner))
                blocked = any(deletion_blocked(db, owner) for owner in owners)
                db.rollback()
                if blocked:
                    response = JSONResponse({"detail": "Account unavailable"}, status_code=403)
                    return await response(scope, receive, send)
                return await self.app(scope, receive, send)
        finally:
            db.close()
