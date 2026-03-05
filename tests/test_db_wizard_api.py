"""Tests for app/api/database.py and app/views/db_wizard.py modules."""

from unittest.mock import patch

import pytest


@pytest.mark.integration
class TestDatabaseApiEndpoints:
    """Tests for the database API endpoints."""

    def test_list_backends(self, client):
        """Test GET /api/database/backends returns supported backends."""
        response = client.get("/api/database/backends")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3
        ids = [b["id"] for b in data]
        assert "sqlite" in ids
        assert "postgresql" in ids

    def test_build_url_requires_admin(self, client):
        """Test POST /api/database/build-url requires admin."""
        response = client.post(
            "/api/database/build-url",
            json={"backend": "sqlite"},
        )
        assert response.status_code == 403

    def test_build_url_sqlite(self, client):
        """Test building a SQLite URL as admin."""
        # Simulate admin session
        with client.session_transaction() if hasattr(client, "session_transaction") else _NoOpContextManager():
            pass
        # Use the session cookie approach
        client.cookies.set("session", "test")
        with patch("app.api.database._require_admin", return_value={"is_admin": True}):
            response = client.post(
                "/api/database/build-url",
                json={"backend": "sqlite", "sqlite_path": "/data/test.db"},
            )
        assert response.status_code == 200
        assert "sqlite:////data/test.db" in response.json().get("url", "")

    def test_build_url_missing_host(self, client):
        """Test building URL with missing host returns 400."""
        with patch("app.api.database._require_admin", return_value={"is_admin": True}):
            response = client.post(
                "/api/database/build-url",
                json={"backend": "postgresql", "database": "db", "username": "u"},
            )
        assert response.status_code == 400

    def test_test_connection_sqlite(self, client):
        """Test connection to in-memory SQLite."""
        with patch("app.api.database._require_admin", return_value={"is_admin": True}):
            response = client.post(
                "/api/database/test-connection",
                json={"url": "sqlite:///:memory:"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_validate_url_valid(self, client):
        """Test validate-url with valid SQLite URL."""
        with patch("app.api.database._require_admin", return_value={"is_admin": True}):
            response = client.post(
                "/api/database/validate-url",
                json={"url": "sqlite:///test.db"},
            )
        assert response.status_code == 200
        assert response.json()["valid"] is True

    def test_validate_url_invalid(self, client):
        """Test validate-url with unsupported backend."""
        with patch("app.api.database._require_admin", return_value={"is_admin": True}):
            response = client.post(
                "/api/database/validate-url",
                json={"url": "mssql://u:p@h/d"},
            )
        assert response.status_code == 200
        assert response.json()["valid"] is False

    def test_parse_url(self, client):
        """Test parse-url endpoint."""
        with patch("app.api.database._require_admin", return_value={"is_admin": True}):
            response = client.post(
                "/api/database/parse-url",
                json={"url": "postgresql://user:pass@host:5432/db"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["backend"] == "postgresql"
        assert data["host"] == "host"

    def test_preview_migration(self, client):
        """Test preview-migration endpoint."""
        with patch("app.api.database._require_admin", return_value={"is_admin": True}):
            response = client.post(
                "/api/database/preview-migration",
                json={"url": "sqlite:///:memory:"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "tables" in data

    def test_migrate_invalid_source(self, client):
        """Test migrate endpoint with invalid source URL."""
        with patch("app.api.database._require_admin", return_value={"is_admin": True}):
            response = client.post(
                "/api/database/migrate",
                json={"source_url": "mssql://bad", "target_url": "sqlite:///:memory:"},
            )
        assert response.status_code == 400

    def test_migrate_invalid_target(self, client):
        """Test migrate endpoint with invalid target URL."""
        with patch("app.api.database._require_admin", return_value={"is_admin": True}):
            response = client.post(
                "/api/database/migrate",
                json={"source_url": "sqlite:///:memory:", "target_url": "mssql://bad"},
            )
        assert response.status_code == 400


@pytest.mark.integration
class TestDatabaseWizardView:
    """Tests for the database wizard view."""

    def test_database_wizard_page_loads(self, client):
        """Test GET /database-wizard returns 200."""
        response = client.get("/database-wizard")
        assert response.status_code == 200

    def test_database_wizard_contains_title(self, client):
        """Test that the wizard page contains expected content."""
        response = client.get("/database-wizard")
        assert response.status_code == 200
        assert "Database Configuration Wizard" in response.text

    def test_database_wizard_contains_tabs(self, client):
        """Test that the wizard page contains configure and migrate tabs."""
        response = client.get("/database-wizard")
        assert "Configure Database" in response.text
        assert "Migrate Data" in response.text


# Context manager helper for tests that don't need session_transaction
class _NoOpContextManager:
    """Dummy context manager for tests that don't need session_transaction."""

    def __enter__(self):
        return None

    def __exit__(self, *args):
        pass
