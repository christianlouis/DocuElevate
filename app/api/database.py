"""
API endpoints for the database configuration wizard and migration tool.

Provides REST endpoints for:
- Testing database connections
- Building connection strings from form components
- Previewing and executing data migrations between databases
"""

import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.utils.db_migrate import migrate_data, preview_migration
from app.utils.db_wizard import (
    build_connection_string,
    get_supported_backends,
    parse_connection_string,
    test_connection,
    validate_url_format,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/database", tags=["database"])


def _require_admin(request: Request) -> dict:
    """Ensure the caller is an admin.  Raises 403 otherwise."""
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ConnectionStringRequest(BaseModel):
    """Request body for building a connection string."""

    backend: str = Field(..., description="Database backend: sqlite, postgresql, mysql")
    host: str = Field("", description="Database server hostname")
    port: int | None = Field(None, description="Database server port")
    database: str = Field("", description="Database name")
    username: str = Field("", description="Authentication username")
    password: str = Field("", description="Authentication password")
    ssl_mode: str = Field("", description="SSL mode (e.g. require, verify-full)")
    extra_options: str = Field("", description="Additional query-string options")
    sqlite_path: str = Field("", description="File path for SQLite databases")


class TestConnectionRequest(BaseModel):
    """Request body for testing a database connection."""

    url: str = Field(..., description="Full SQLAlchemy connection URL to test")


class MigrateRequest(BaseModel):
    """Request body for data migration."""

    source_url: str = Field(..., description="Source database connection URL")
    target_url: str = Field(..., description="Target database connection URL")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/backends")
async def list_backends() -> list[dict]:
    """List all supported database backends with metadata."""
    return get_supported_backends()


@router.post("/build-url")
async def build_url(body: ConnectionStringRequest, request: Request) -> dict:
    """Build a SQLAlchemy connection string from individual components.

    Returns the assembled URL string.
    """
    _require_admin(request)
    try:
        url = build_connection_string(
            backend=body.backend,
            host=body.host,
            port=body.port,
            database=body.database,
            username=body.username,
            password=body.password,
            ssl_mode=body.ssl_mode,
            extra_options=body.extra_options,
            sqlite_path=body.sqlite_path,
        )
        return {"url": url}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/parse-url")
async def parse_url(body: TestConnectionRequest, request: Request) -> dict:
    """Parse a connection string into its components."""
    _require_admin(request)
    return parse_connection_string(body.url)


@router.post("/validate-url")
async def validate_url(body: TestConnectionRequest, request: Request) -> dict:
    """Validate a connection string format without connecting."""
    _require_admin(request)
    return validate_url_format(body.url)


@router.post("/test-connection")
async def test_db_connection(body: TestConnectionRequest, request: Request) -> dict:
    """Test connectivity to a database and return status info.

    This creates a temporary engine, executes ``SELECT 1``, and disposes
    of the engine.  It does **not** modify any global application state.
    """
    _require_admin(request)
    return test_connection(body.url)


@router.post("/preview-migration")
async def preview_db_migration(body: TestConnectionRequest, request: Request) -> dict:
    """Preview what a migration from the given source would include.

    Returns a table-by-table row count without actually copying data.
    """
    _require_admin(request)
    return preview_migration(body.url)


@router.post("/migrate")
async def execute_migration(body: MigrateRequest, request: Request) -> dict:
    """Execute a full data migration from source to target database.

    **Warning:** This copies all data from the source database into the
    target.  The target schema is created from the current application
    models.  Existing data in the target is **not** deleted first — use
    on an empty target database.
    """
    _require_admin(request)

    # Validate both URLs first
    src_check = validate_url_format(body.source_url)
    if not src_check.get("valid"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid source URL: {src_check.get('error', 'unknown')}",
        )
    tgt_check = validate_url_format(body.target_url)
    if not tgt_check.get("valid"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid target URL: {tgt_check.get('error', 'unknown')}",
        )

    result = migrate_data(body.source_url, body.target_url)
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Migration completed with errors", **result},
        )
    return result
