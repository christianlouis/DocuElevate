"""
Full integration test infrastructure using real services.

This module provides fixtures for spinning up real infrastructure components:
- PostgreSQL database (instead of SQLite in-memory)
- Redis (for Celery broker/backend)
- Gotenberg (for PDF conversion)
- WebDAV server (upload target)
- SFTP server (upload target)
- MinIO (S3-compatible storage)

These tests exercise the full application stack end-to-end.
"""

import os
import time
from typing import Generator

import pytest

# Import testcontainers
pytest.importorskip("testcontainers", reason="testcontainers not installed")
from testcontainers.core.container import DockerContainer
from testcontainers.minio import MinioContainer
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

_TEST_CREDENTIAL = "testpass"  # noqa: S105


@pytest.fixture(scope="session")
def postgres_container() -> Generator:
    """
    Start a real PostgreSQL database container for testing.

    This replaces the in-memory SQLite used in unit tests.
    """
    with PostgresContainer("postgres:15-alpine") as postgres:
        # Wait for PostgreSQL to be ready
        time.sleep(2)
        postgres_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )

        # Set environment variable for the app to use
        os.environ["DATABASE_URL"] = postgres_url

        yield {
            "container": postgres,
            "url": postgres_url,
            "host": postgres.get_container_host_ip(),
            "port": postgres.get_exposed_port(5432),
            "username": postgres.username,
            "password": postgres.password,
            "database": postgres.dbname,
        }


@pytest.fixture(scope="session")
def redis_container() -> Generator:
    """
    Start a real Redis container for Celery broker/backend.

    This provides actual message queueing and task result storage.
    """
    with RedisContainer("redis:7-alpine") as redis:
        # Wait for Redis to be ready
        time.sleep(2)

        # Build Redis URL manually
        host = redis.get_container_host_ip()
        port = redis.get_exposed_port(6379)
        redis_url = f"redis://{host}:{port}/0"

        # Set environment variables for the app
        os.environ["REDIS_URL"] = redis_url
        os.environ["CELERY_BROKER_URL"] = redis_url
        os.environ["CELERY_RESULT_BACKEND"] = redis_url

        yield {
            "container": redis,
            "url": redis_url,
            "host": host,
            "port": port,
        }


@pytest.fixture(scope="session")
def gotenberg_container() -> Generator:
    """
    Start a real Gotenberg container for PDF conversion.

    This provides actual document conversion capabilities.
    """
    external_url = os.getenv("TEST_GOTENBERG_URL")
    if external_url:
        # Local/CI environments may already provide the exact Gotenberg service
        # used by the application.  Reuse it to avoid nesting Chromium when the
        # test runner itself is containerized.
        yield {
            "container": None,
            "url": external_url.rstrip("/"),
            "host": None,
            "port": None,
        }
        return

    container = DockerContainer("gotenberg/gotenberg:8")
    container.with_exposed_ports(3000)

    container.start()
    time.sleep(5)  # Gotenberg takes a bit longer to start

    host = container.get_container_host_ip()
    port = container.get_exposed_port(3000)
    gotenberg_url = f"http://{host}:{port}"

    # Set environment variable
    os.environ["GOTENBERG_URL"] = gotenberg_url

    yield {
        "container": container,
        "url": gotenberg_url,
        "host": host,
        "port": port,
    }

    container.stop()


@pytest.fixture(scope="session")
def webdav_container() -> Generator:
    """
    Start a real WebDAV server for upload testing.
    """
    container = DockerContainer("bytemark/webdav:latest")
    container.with_exposed_ports(80)
    container.with_env("AUTH_TYPE", "Basic")
    container.with_env("USERNAME", "testuser")
    container.with_env("PASSWORD", _TEST_CREDENTIAL)

    container.start()
    time.sleep(2)

    host = container.get_container_host_ip()
    port = container.get_exposed_port(80)

    yield {
        "container": container,
        "url": f"http://{host}:{port}",
        "host": host,
        "port": port,
        "username": "testuser",
        "password": _TEST_CREDENTIAL,
    }

    container.stop()


@pytest.fixture(scope="session")
def sftp_container() -> Generator:
    """
    Start a real SFTP server for upload testing.

    Uses atmoz/sftp which provides a simple SSH/SFTP server.
    """
    container = DockerContainer("atmoz/sftp:latest")
    container.with_exposed_ports(22)
    # Create user: username:password:uid:gid:directory
    container.with_command(f"testuser:{_TEST_CREDENTIAL}:1001:1001:upload")

    container.start()
    time.sleep(3)  # SFTP server needs time to initialize

    host = container.get_container_host_ip()
    port = container.get_exposed_port(22)

    yield {
        "container": container,
        "host": host,
        "port": port,
        "username": "testuser",
        "password": _TEST_CREDENTIAL,
        # atmoz/sftp chroots the user into /home/testuser, so clients see the
        # provisioned upload directory at /upload rather than the host path.
        "folder": "/upload",
    }

    container.stop()


@pytest.fixture(scope="session")
def minio_container() -> Generator:
    """
    Start a real MinIO container (S3-compatible storage).

    MinIO provides S3-compatible API for testing S3 uploads.
    """
    with MinioContainer() as minio:
        time.sleep(2)

        # MinIO uses random credentials, get them
        access_key = minio.access_key
        secret_key = minio.secret_key

        endpoint = minio.get_config()["endpoint"]
        yield {
            "container": minio,
            "url": f"http://{endpoint}",
            "access_key": access_key,
            "secret_key": secret_key,
            "region": "us-east-1",
        }


@pytest.fixture(scope="session")
def ftp_container() -> Generator:
    """
    Start a real FTP server for upload testing.

    Uses stilliard/pure-ftpd which provides a simple FTP server.
    """
    container = DockerContainer("stilliard/pure-ftpd:latest")
    container.with_exposed_ports(21, 30000, 30001, 30002, 30003, 30004)
    container.with_env("PUBLICHOST", "localhost")
    container.with_env("FTP_USER_NAME", "testuser")
    container.with_env("FTP_USER_PASS", _TEST_CREDENTIAL)
    container.with_env("FTP_USER_HOME", "/home/testuser")

    container.start()
    time.sleep(3)

    host = container.get_container_host_ip()
    port = container.get_exposed_port(21)

    yield {
        "container": container,
        "host": host,
        "port": port,
        "username": "testuser",
        "password": _TEST_CREDENTIAL,
        "folder": "/",
    }

    container.stop()


@pytest.fixture(scope="session")
def full_infrastructure(
    postgres_container,
    redis_container,
    gotenberg_container,
    webdav_container,
    sftp_container,
    minio_container,
):
    """
    Combined fixture that provides all infrastructure components.

    Use this fixture when you need the complete application stack.
    """
    return {
        "postgres": postgres_container,
        "redis": redis_container,
        "gotenberg": gotenberg_container,
        "webdav": webdav_container,
        "sftp": sftp_container,
        "minio": minio_container,
    }


@pytest.fixture(scope="session")
def celery_app(redis_container):
    """
    Create a Celery app configured to use the real Redis container.

    This allows testing actual task queueing and execution.
    """
    from app.celery_app import celery
    from app.config import settings

    previous_urls = (
        settings.redis_url,
        settings.celery_broker_url,
        settings.celery_result_backend,
    )

    # The production worker has a startup bootstep that verifies the configured
    # Redis result backend is writable.  Point both Settings and Celery at the
    # ephemeral Redis service; updating Celery alone leaves that safety check on
    # the process-start default and makes an otherwise healthy E2E worker fail.
    settings.redis_url = redis_container["url"]
    settings.celery_broker_url = redis_container["url"]
    settings.celery_result_backend = redis_container["url"]

    # Update Celery configuration to use test Redis
    celery.conf.update(
        broker_url=redis_container["url"],
        result_backend=redis_container["url"],
        task_always_eager=False,  # Actually queue tasks (don't execute immediately)
        task_eager_propagates=True,
        result_expires=3600,
    )
    # Celery caches thread-safe and thread-local backends separately.  Clear
    # both storage locations without invoking the property setter (which only
    # accepts a concrete backend instance).
    celery._backend_cache = None  # noqa: SLF001
    celery._local.__dict__.pop("backend", None)  # noqa: SLF001

    yield celery

    settings.redis_url, settings.celery_broker_url, settings.celery_result_backend = previous_urls
    celery._backend_cache = None  # noqa: SLF001
    celery._local.__dict__.pop("backend", None)  # noqa: SLF001


@pytest.fixture(scope="session")
def celery_worker(celery_app, redis_container):
    """
    Start a real Celery worker for processing tasks.

    This runs tasks asynchronously like in production.
    """
    import gc

    from celery.contrib.testing.worker import start_worker

    # Start worker in test mode
    with start_worker(
        celery_app,
        perform_ping_check=False,
        loglevel="info",
        concurrency=2,
    ) as worker:
        try:
            yield worker
        finally:
            # AsyncResult destructors unsubscribe from Redis.  Collect them and
            # stop the result consumer while the ephemeral backend is still
            # alive; otherwise teardown emits misleading reconnect failures
            # after testcontainers has already removed Redis.
            gc.collect()
            result_consumer = getattr(celery_app.backend, "result_consumer", None)
            if result_consumer is not None:
                result_consumer.stop()
            gc.collect()


@pytest.fixture
def db_session_real(postgres_container):
    """
    Create a database session using the real PostgreSQL container.

    This replaces the in-memory SQLite session for integration tests.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base

    # Create engine using PostgreSQL container
    engine = create_engine(postgres_container["url"])

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create session
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    # Mirror normal ingestion startup: PostgreSQL enforces the tenant/Tribe
    # foreign keys that SQLite unit tests can otherwise hide.
    from app.utils.tribe_scope import ensure_document_scope

    ensure_document_scope(session, owner_id=None)
    session.commit()

    try:
        yield session
    finally:
        session.close()
        # Clean up tables after test
        Base.metadata.drop_all(bind=engine)
