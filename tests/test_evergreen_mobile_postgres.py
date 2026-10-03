"""Opt-in PostgreSQL startup and persistence coverage for Evergreen mobile auth."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from app import auth, database, main
from app.api import mobile
from app.models import EvergreenMobileToken, FileRecord


def _postgres_url() -> str:
    raw_url = os.environ.get("MOBILE_TEST_POSTGRES_URL")
    if not raw_url:
        pytest.skip("MOBILE_TEST_POSTGRES_URL is not set")
    parsed = make_url(raw_url)
    if (
        parsed.get_backend_name() != "postgresql"
        or parsed.host not in {"localhost", "127.0.0.1"}
        or parsed.database != "docuelevate_test"
    ):
        pytest.fail("MOBILE_TEST_POSTGRES_URL must point to the local docuelevate_test PostgreSQL database")
    return raw_url


@pytest.fixture
def evergreen_postgres(monkeypatch):
    """Provide a random schema and route all app database access into it."""
    raw_url = _postgres_url()
    schema = f"evergreen_mobile_{uuid.uuid4().hex}"
    admin_engine = create_engine(raw_url)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_engine(raw_url, connect_args={"options": f"-csearch_path={schema}"})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(database, "DB_URL", raw_url)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    monkeypatch.setattr(main, "DB_URL_SOURCE", "test")
    monkeypatch.setattr(main, "init_apprise", lambda: None)
    monkeypatch.setattr(main, "notify_startup", lambda: None)
    monkeypatch.setattr(main, "notify_shutdown", lambda: None)
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth.settings, "admin_username", "admin")
    monkeypatch.setattr(auth.settings, "admin_password", "secret")
    monkeypatch.setattr(auth, "SessionLocal", session_factory)
    monkeypatch.setattr(mobile, "SessionLocal", session_factory)

    try:
        yield engine, session_factory
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.mark.asyncio
async def test_evergreen_mobile_postgres_startup_preserves_legacy_data(evergreen_postgres):
    """Two real startup cycles create the token table and preserve existing rows."""
    engine, session_factory = evergreen_postgres

    # Seed only the legacy table. The first real startup must create the new table.
    FileRecord.__table__.create(bind=engine)
    db = session_factory()
    db.add(
        FileRecord(
            filehash="legacy-file",
            original_filename="legacy.txt",
            local_filename="legacy.txt",
            file_size=1,
        )
    )
    db.commit()
    db.close()

    async with main.lifespan(main.app):
        pass

    assert inspect(engine).has_table("evergreen_mobile_tokens")
    db = session_factory()
    assert db.query(FileRecord).one().original_filename == "legacy.txt"
    token = auth.issue_mobile_token(
        {
            "id": "evergreen-user",
            "name": "Evergreen User",
            "email": "evergreen@example.test",
            "is_admin": True,
        },
        db=db,
    )
    assert db.query(EvergreenMobileToken).count() == 1
    db.close()

    async with main.lifespan(main.app):
        pass

    assert auth._mobile_user_from_token(token)["id"] == "evergreen-user"
    db = session_factory()
    assert db.query(EvergreenMobileToken).one().token_hash != token
    assert db.query(FileRecord).one().original_filename == "legacy.txt"
    db.close()

    client = TestClient(main.app, base_url="http://localhost")
    response = client.get("/api/mobile/whoami", headers={"Authorization": f"Bearer {token}"})
    client.close()
    assert response.status_code == 200
    assert response.json()["owner_id"] == "evergreen-user"
