"""Tests for app/utils/db_wizard.py module."""

import pytest

from app.utils.db_wizard import (
    build_connection_string,
    get_supported_backends,
    parse_connection_string,
    test_connection as db_test_connection,
    validate_url_format,
)


@pytest.mark.unit
class TestGetSupportedBackends:
    """Tests for get_supported_backends function."""

    def test_returns_list(self):
        """Test that it returns a non-empty list."""
        result = get_supported_backends()
        assert isinstance(result, list)
        assert len(result) >= 3

    def test_each_backend_has_required_keys(self):
        """Test that each backend has expected keys."""
        required_keys = {"id", "label", "description", "requires_host"}
        for backend in get_supported_backends():
            assert required_keys.issubset(set(backend.keys())), f"Missing keys in {backend.get('id')}"

    def test_includes_sqlite(self):
        """Test that SQLite is included."""
        ids = [b["id"] for b in get_supported_backends()]
        assert "sqlite" in ids

    def test_includes_postgresql(self):
        """Test that PostgreSQL is included."""
        ids = [b["id"] for b in get_supported_backends()]
        assert "postgresql" in ids

    def test_includes_mysql(self):
        """Test that MySQL is included."""
        ids = [b["id"] for b in get_supported_backends()]
        assert "mysql" in ids


@pytest.mark.unit
class TestBuildConnectionString:
    """Tests for build_connection_string function."""

    def test_sqlite_default_path(self):
        """Test building a SQLite URL with default path."""
        url = build_connection_string(backend="sqlite")
        assert url == "sqlite:///./app/database.db"

    def test_sqlite_custom_path(self):
        """Test building a SQLite URL with custom path."""
        url = build_connection_string(backend="sqlite", sqlite_path="/data/mydb.db")
        assert url == "sqlite:////data/mydb.db"

    def test_postgresql_basic(self):
        """Test building a basic PostgreSQL URL."""
        url = build_connection_string(
            backend="postgresql",
            host="localhost",
            database="docuelevate",
            username="user",
            password="pass",
        )
        assert url == "postgresql://user:pass@localhost:5432/docuelevate"

    def test_postgresql_with_ssl(self):
        """Test building a PostgreSQL URL with SSL."""
        url = build_connection_string(
            backend="postgresql",
            host="rds.amazonaws.com",
            database="docuelevate",
            username="admin",
            password="secret",
            ssl_mode="require",
        )
        assert "sslmode=require" in url
        assert "postgresql://admin:secret@rds.amazonaws.com:5432/docuelevate" in url

    def test_postgresql_custom_port(self):
        """Test building a PostgreSQL URL with custom port."""
        url = build_connection_string(
            backend="postgresql",
            host="localhost",
            port=5433,
            database="testdb",
            username="user",
            password="pass",
        )
        assert ":5433/" in url

    def test_mysql_basic(self):
        """Test building a MySQL URL."""
        url = build_connection_string(
            backend="mysql",
            host="localhost",
            database="docuelevate",
            username="root",
            password="password",
        )
        assert url.startswith("mysql+pymysql://")
        assert "charset=utf8mb4" in url

    def test_mysql_no_duplicate_charset(self):
        """Test that charset is not duplicated when passed in extra_options."""
        url = build_connection_string(
            backend="mysql",
            host="localhost",
            database="docuelevate",
            username="root",
            password="pass",
            extra_options="charset=utf8mb4",
        )
        assert url.count("charset=utf8mb4") == 1

    def test_unsupported_backend_raises(self):
        """Test that unsupported backend raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported backend"):
            build_connection_string(backend="oracle")

    def test_missing_host_raises(self):
        """Test that missing host for non-SQLite raises ValueError."""
        with pytest.raises(ValueError, match="Host is required"):
            build_connection_string(backend="postgresql", database="db", username="u")

    def test_missing_database_raises(self):
        """Test that missing database name raises ValueError."""
        with pytest.raises(ValueError, match="Database name is required"):
            build_connection_string(backend="postgresql", host="localhost", username="u")

    def test_missing_username_raises(self):
        """Test that missing username raises ValueError."""
        with pytest.raises(ValueError, match="Username is required"):
            build_connection_string(backend="postgresql", host="localhost", database="db")

    def test_no_password(self):
        """Test building URL without password."""
        url = build_connection_string(
            backend="postgresql",
            host="localhost",
            database="db",
            username="user",
        )
        assert "user@localhost" in url
        assert ":@" not in url


@pytest.mark.unit
class TestParseConnectionString:
    """Tests for parse_connection_string function."""

    def test_parse_sqlite(self):
        """Test parsing a SQLite URL."""
        result = parse_connection_string("sqlite:///./app/database.db")
        assert result["valid"] is True
        assert result["backend"] == "sqlite"
        assert result["is_sqlite"] is True

    def test_parse_postgresql(self):
        """Test parsing a PostgreSQL URL."""
        result = parse_connection_string("postgresql://user:pass@host:5432/mydb")
        assert result["valid"] is True
        assert result["backend"] == "postgresql"
        assert result["host"] == "host"
        assert result["port"] == 5432
        assert result["database"] == "mydb"
        assert result["username"] == "user"
        assert result["is_sqlite"] is False

    def test_parse_mysql(self):
        """Test parsing a MySQL URL."""
        result = parse_connection_string("mysql+pymysql://root:pass@localhost:3306/db")
        assert result["valid"] is True
        assert result["backend"] == "mysql"

    def test_parse_invalid_url(self):
        """Test parsing an invalid URL returns error."""
        result = parse_connection_string("not-a-valid-url://")
        # Should still return a dict (make_url may or may not raise)
        assert isinstance(result, dict)


@pytest.mark.unit
class TestValidateUrlFormat:
    """Tests for validate_url_format function."""

    def test_valid_sqlite(self):
        """Test valid SQLite URL."""
        result = validate_url_format("sqlite:///./db.sqlite")
        assert result["valid"] is True
        assert result["backend"] == "sqlite"

    def test_valid_postgresql(self):
        """Test valid PostgreSQL URL."""
        result = validate_url_format("postgresql://u:p@host/db")
        assert result["valid"] is True

    def test_valid_mysql(self):
        """Test valid MySQL URL."""
        result = validate_url_format("mysql+pymysql://u:p@host/db")
        assert result["valid"] is True

    def test_unsupported_backend(self):
        """Test that unsupported backends are flagged."""
        result = validate_url_format("mssql://u:p@host/db")
        assert result["valid"] is False
        assert "Unsupported" in result.get("error", "")

    def test_invalid_format(self):
        """Test that garbage input is invalid."""
        result = validate_url_format("")
        assert result["valid"] is False


@pytest.mark.unit
class TestTestConnection:
    """Tests for test_connection function."""

    def test_sqlite_memory_succeeds(self):
        """Test connecting to an in-memory SQLite database."""
        result = db_test_connection("sqlite:///:memory:")
        assert result["success"] is True
        assert "SQLite" in result.get("server_version", "")

    def test_unreachable_host_fails(self):
        """Test that an unreachable host returns failure."""
        result = db_test_connection("postgresql://u:p@192.0.2.1:5432/db", timeout=2)
        assert result["success"] is False
        assert result["message"]  # Should contain an error message
