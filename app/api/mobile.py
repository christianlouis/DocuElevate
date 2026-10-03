"""Small native-client compatibility endpoints for the Evergreen release line."""

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from app.auth import mobile_user_or_401
from app.database import SessionLocal
from app.models import EvergreenMobileToken

router = APIRouter()


@router.get("/mobile/whoami")
async def mobile_whoami(request: Request):
    """Native profile shape; bearer access is limited to this identity route."""
    user = mobile_user_or_401(request)
    return {
        "id": user.get("id") or user.get("sub"),
        "owner_id": user.get("id") or user.get("sub"),
        "display_name": user.get("name") or user.get("preferred_username") or user.get("email"),
        "email": user.get("email"),
        "avatar_url": user.get("avatar_url") or user.get("picture"),
        "is_admin": bool(user.get("is_admin", False)),
        "preferred_language": user.get("preferred_language"),
    }


@router.post("/i18n/language")
async def set_language(request: Request):
    user = mobile_user_or_401(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid language") from exc
    language = payload.get("language") if isinstance(payload, dict) else None
    if not isinstance(language, str) or len(language) > 16 or not language.strip():
        raise HTTPException(status_code=400, detail="Invalid language")
    language = language.strip()
    db = SessionLocal()
    try:
        token = request.headers.get("authorization", "")[7:].strip()
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        record = (
            db.query(EvergreenMobileToken)
            .filter(
                EvergreenMobileToken.token_hash == token_hash,
                EvergreenMobileToken.revoked_at.is_(None),
            )
            .first()
        )
        if record:
            record.preferred_language = language
            db.commit()
        if request.session.get("user"):
            request.session["user"]["preferred_language"] = language
        return {"language": language, "user_id": user.get("id")}
    finally:
        db.close()


@router.post("/auth/mobile/revoke")
async def revoke_mobile_token(request: Request):
    mobile_user_or_401(request)
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(status_code=400, detail="Bearer token required")
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
            raise HTTPException(status_code=401, detail="Not authenticated")
        record.revoked_at = datetime.now(timezone.utc)
        db.commit()
        return {"revoked": True}
    finally:
        db.close()
