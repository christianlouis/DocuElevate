"""
Database configuration wizard utilities.

Provides helpers for building, validating, and testing database connection
strings.  Used by both the interactive wizard UI and the REST API.
"""

import logging
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

logger = logging.getLogger(__name__)

# Supported database backends with human-readable labels and defaults.
SUPPORTED_BACKENDS: list[dict[str, Any]] = [
    {
        "id": "sqlite",
        "label": "SQLite (Development)",
        "driver": "",
        "default_port": None,
        "description": "File-based database. Best for development and single-user setups.",
        "requires_host": False,
    },
    {
        "id": "postgresql",
        "label": "PostgreSQL (Recommended for Production)",
        "driver": "",
        "default_port": 5432,
        "description": "Robust, full-featured database. Recommended for production.",
        "requires_host": True,
    },
    {
        "id": "mysql",
        "label": "MySQL / MariaDB",
        "driver": "pymysql",
        "default_port": 3306,
        "description": "Popular open-source database. Requires pymysql driver.",
        "requires_host": True,
    },
]


def get_supported_backends() -> list[dict[str, Any]]:
    """Return the list of supported database backends with metadata.

    Returns:
        List of backend descriptor dicts.
    """
    return SUPPORTED_BACKENDS


def build_connection_string(
    backend: str,
    host: str = "",
    port: int | None = None,
    database: str = "",
    username: str = "",
    password: str = "",
    ssl_mode: str = "",
    extra_options: str = "",
    sqlite_path: str = "",
) -> str:
    """Build a SQLAlchemy connection string from individual components.

    Args:
        backend: Database backend identifier (``sqlite``, ``postgresql``, ``mysql``).
        host: Database server hostname or IP.
        port: Database server port (uses backend default when ``None``).
        database: Database / schema name.
        username: Authentication username.
        password: Authentication password.
        ssl_mode: SSL mode (e.g. ``require``, ``verify-full``).  PostgreSQL only.
        extra_options: Additional query-string options appended to the URL.
        sqlite_path: File path for SQLite databases.

    Returns:
        A SQLAlchemy-compatible connection URL string.

    Raises:
        ValueError: If required fields are missing for the chosen backend.
    """
    if backend == "sqlite":
        path = sqlite_path.strip() if sqlite_path else "./app/database.db"
        return f"sqlite:///{path}"

    # Resolve driver prefix
    backend_info = next((b for b in SUPPORTED_BACKENDS if b["id"] == backend), None)
    if backend_info is None:
        raise ValueError(f"Unsupported backend: {backend}")

    if not host:
        raise ValueError("Host is required for non-SQLite backends")
    if not database:
        raise ValueError("Database name is required for non-SQLite backends")
    if not username:
        raise ValueError("Username is required for non-SQLite backends")

    driver_suffix = f"+{backend_info['driver']}" if backend_info["driver"] else ""
    scheme = f"{backend}{driver_suffix}"

    resolved_port = port if port else backend_info["default_port"]

    # Build query parameters
    params: list[str] = []
    if ssl_mode:
        params.append(f"sslmode={ssl_mode}")
    if extra_options:
        params.append(extra_options)
    if backend == "mysql" and "charset=" not in extra_options:
        params.append("charset=utf8mb4")

    query_string = "&".join(params)

    # Construct URL
    auth = username
    if password:
        auth = f"{username}:{password}"

    url = f"{scheme}://{auth}@{host}:{resolved_port}/{database}"
    if query_string:
        url = f"{url}?{query_string}"

    return url


def parse_connection_string(url: str) -> dict[str, Any]:
    """Parse a SQLAlchemy connection string into its components.

    Args:
        url: A SQLAlchemy database URL string.

    Returns:
        Dict with keys: ``backend``, ``host``, ``port``, ``database``,
        ``username``, ``password``, ``ssl_mode``, ``is_sqlite``.
    """
    try:
        parsed = make_url(url)
        backend_name = parsed.get_backend_name()
        return {
            "backend": backend_name,
            "host": parsed.host or "",
            "port": parsed.port,
            "database": parsed.database or "",
            "username": parsed.username or "",
            "password": parsed.password or "",
            "ssl_mode": "",
            "is_sqlite": backend_name == "sqlite",
            "valid": True,
        }
    except Exception as exc:
        logger.warning(f"Failed to parse connection string: {exc}")
        return {"valid": False, "error": str(exc)}


def test_connection(url: str, timeout: int = 10) -> dict[str, Any]:
    """Attempt to connect to a database and return status information.

    The function creates a short-lived engine, executes a simple ``SELECT 1``
    query, and disposes the engine.  It does **not** modify any global state.

    Args:
        url: SQLAlchemy database URL to test.
        timeout: Connection timeout in seconds.

    Returns:
        Dict with ``success`` (bool), ``message`` (str), and optional
        ``server_version`` (str).
    """
    try:
        parsed = make_url(url)
        backend = parsed.get_backend_name()

        connect_args: dict[str, Any] = {}
        kwargs: dict[str, Any] = {"pool_pre_ping": True}

        if backend == "sqlite":
            connect_args["check_same_thread"] = False
        else:
            kwargs["pool_timeout"] = timeout

        test_engine = create_engine(
            url,
            connect_args=connect_args,
            **kwargs,
        )

        with test_engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()

            # Try to fetch server version for informational display
            server_version = _get_server_version(conn, backend)

        test_engine.dispose()

        return {
            "success": True,
            "message": "Connection successful",
            "backend": backend,
            "server_version": server_version,
        }
    except Exception as exc:
        logger.warning(f"Connection test failed: {exc}")
        return {
            "success": False,
            "message": str(exc),
            "backend": "",
            "server_version": "",
        }


def _get_server_version(conn: Any, backend: str) -> str:
    """Retrieve a human-readable server version string.

    Args:
        conn: An active SQLAlchemy connection.
        backend: Backend identifier (``sqlite``, ``postgresql``, ``mysql``).

    Returns:
        Server version string, or empty string on failure.
    """
    try:
        if backend == "postgresql":
            row = conn.execute(text("SELECT version()")).fetchone()
            return str(row[0]) if row else ""
        elif backend == "mysql":
            row = conn.execute(text("SELECT version()")).fetchone()
            return str(row[0]) if row else ""
        elif backend == "sqlite":
            row = conn.execute(text("SELECT sqlite_version()")).fetchone()
            return f"SQLite {row[0]}" if row else ""
    except Exception:
        logger.debug("Could not retrieve server version")
    return ""


def validate_url_format(url: str) -> dict[str, Any]:
    """Validate that a connection string is syntactically correct.

    Args:
        url: The connection string to validate.

    Returns:
        Dict with ``valid`` (bool) and optional ``error`` (str).
    """
    try:
        parsed = make_url(url)
        backend = parsed.get_backend_name()
        if backend not in ("sqlite", "postgresql", "mysql"):
            return {"valid": False, "error": f"Unsupported backend: {backend}"}
        return {"valid": True, "backend": backend}
    except Exception as exc:
        return {"valid": False, "error": str(exc)}
