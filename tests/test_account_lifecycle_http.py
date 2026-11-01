"""Concurrent HTTP work must finish before deletion can fence an account."""

import asyncio

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from app.api.api_tokens import hash_token
from app.config import settings
from app.database import Base
from app.middleware.account_lifecycle import AccountLifecycleMiddleware
from app.models import ApiToken
from app.services.account_deletion import delete_account


@pytest.mark.asyncio
async def test_http_requests_coordinate_with_deletion(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr("app.database.SessionLocal", sessions)
    with sessions() as db:
        db.add(ApiToken(owner_id="alice", name="test", token_hash=hash_token("secret"), token_prefix="secret"))
        db.commit()
    app = FastAPI()
    app.add_middleware(AccountLifecycleMiddleware)
    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    entered = 0
    both_entered = asyncio.Event()
    release = asyncio.Event()
    deletion_done = asyncio.Event()

    @app.get("/seed")
    async def seed(request: Request):
        request.session["user"] = {"sub": "alice"}
        return {"ok": True}

    @app.post("/work")
    async def work():
        nonlocal entered
        with sessions() as db:
            if not db.query(ApiToken).filter_by(token_hash=hash_token("secret"), is_active=True).first():
                raise HTTPException(status_code=401)
        entered += 1
        if entered == 2:
            both_entered.set()
        await release.wait()
        return {"ok": True}

    @app.delete("/api/account")
    async def deletion(request: Request):
        def fence():
            with sessions() as db:
                delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=tmp_path)

        await asyncio.to_thread(fence)
        deletion_done.set()
        return {"ok": True}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        headers = {"authorization": "Bearer secret"}
        await client.get("/seed")
        work1 = asyncio.create_task(client.post("/work", headers=headers))
        work2 = asyncio.create_task(client.post("/work", headers=headers))
        await asyncio.wait_for(both_entered.wait(), 2)
        delete = asyncio.create_task(client.delete("/api/account", headers=headers))
        await asyncio.sleep(0.05)
        assert not deletion_done.is_set()
        release.set()
        assert (await work1).status_code == 200
        assert (await work2).status_code == 200
        assert (await asyncio.wait_for(delete, 2)).status_code == 200
        assert (await client.post("/work", headers=headers)).status_code == 403
    engine.dispose()
