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

    def test_migrate_success(self, client):
        """Test migrate endpoint with successful migration."""
        mock_result = {"success": True, "tables_copied": 5, "rows_copied": 100, "errors": []}
        with patch("app.api.database._require_admin", return_value={"is_admin": True}):
            with patch("app.api.database.migrate_data", return_value=mock_result):
                response = client.post(
                    "/api/database/migrate",
                    json={
                        "source_url": "sqlite:///:memory:",
                        "target_url": "sqlite:///:memory:",
                    },
                )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["rows_copied"] == 100

    def test_migrate_failure_returns_500(self, client):
        """Test migrate endpoint returns 500 on migration failure."""
        mock_result = {
            "success": False,
            "tables_copied": 2,
            "rows_copied": 50,
            "errors": ["Table X failed", "Stamp failed"],
        }
        with patch("app.api.database._require_admin", return_value={"is_admin": True}):
            with patch("app.api.database.migrate_data", return_value=mock_result):
                response = client.post(
                    "/api/database/migrate",
                    json={
                        "source_url": "sqlite:///:memory:",
                        "target_url": "sqlite:///:memory:",
                    },
                )
        assert response.status_code == 500
        assert "Table X failed" in response.json()["detail"]

    def test_test_connection_requires_admin(self, client):
        """Test POST /api/database/test-connection requires admin."""
        response = client.post(
            "/api/database/test-connection",
            json={"url": "sqlite:///:memory:"},
        )
        assert response.status_code == 403

    def test_parse_url_requires_admin(self, client):
        """Test POST /api/database/parse-url requires admin."""
        response = client.post(
            "/api/database/parse-url",
            json={"url": "sqlite:///:memory:"},
        )
        assert response.status_code == 403

    def test_validate_url_requires_admin(self, client):
        """Test POST /api/database/validate-url requires admin."""
        response = client.post(
            "/api/database/validate-url",
            json={"url": "sqlite:///:memory:"},
        )
        assert response.status_code == 403

    def test_preview_migration_requires_admin(self, client):
        """Test POST /api/database/preview-migration requires admin."""
        response = client.post(
            "/api/database/preview-migration",
            json={"url": "sqlite:///:memory:"},
        )
        assert response.status_code == 403

    def test_migrate_requires_admin(self, client):
        """Test POST /api/database/migrate requires admin."""
        response = client.post(
            "/api/database/migrate",
            json={"source_url": "sqlite:///:memory:", "target_url": "sqlite:///:memory:"},
        )
        assert response.status_code == 403

    def test_build_url_postgresql(self, client):
        """Test building a PostgreSQL URL."""
        with patch("app.api.database._require_admin", return_value={"is_admin": True}):
            response = client.post(
                "/api/database/build-url",
                json={
                    "backend": "postgresql",
                    "host": "localhost",
                    "port": 5432,
                    "database": "mydb",
                    "username": "admin",
                    "password": "secret",
                },
            )
        assert response.status_code == 200
        url = response.json()["url"]
        assert "postgresql://admin:secret@localhost:5432/mydb" in url


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

    def test_database_wizard_has_skip_link(self, client):
        """Test that the wizard page includes a skip-to-content link."""
        response = client.get("/database-wizard")
        assert "Skip to main content" in response.text

    def test_database_wizard_has_main_landmark(self, client):
        """Test that the wizard page has a main landmark."""
        response = client.get("/database-wizard")
        assert 'id="main-content"' in response.text

    def test_database_wizard_has_tablist_role(self, client):
        """Test that the tab navigation has proper ARIA tablist role."""
        response = client.get("/database-wizard")
        assert 'role="tablist"' in response.text
        assert 'role="tab"' in response.text
        assert 'role="tabpanel"' in response.text

    def test_database_wizard_has_aria_labels_on_backend_buttons(self, client):
        """Test that backend selection buttons have aria-label attributes."""
        response = client.get("/database-wizard")
        assert 'aria-label="Select SQLite"' in response.text
        assert 'aria-label="Select PostgreSQL"' in response.text
        assert 'aria-label="Select MySQL / MariaDB"' in response.text

    def test_database_wizard_has_form_labels(self, client):
        """Test that form inputs have associated labels."""
        response = client.get("/database-wizard")
        assert 'for="sqlite_path"' in response.text
        assert 'for="db_host"' in response.text
        assert 'for="db_port"' in response.text
        assert 'for="db_name"' in response.text
        assert 'for="db_user"' in response.text
        assert 'for="db_pass"' in response.text
        assert 'for="ssl_mode"' in response.text

    def test_database_wizard_has_aria_describedby(self, client):
        """Test that inputs have aria-describedby pointing to help text."""
        response = client.get("/database-wizard")
        assert 'aria-describedby="sqlite_path_help"' in response.text
        assert 'id="sqlite_path_help"' in response.text
        assert 'aria-describedby="ssl_mode_help"' in response.text
        assert 'id="ssl_mode_help"' in response.text
        assert 'aria-describedby="mig_source_help"' in response.text
        assert 'aria-describedby="mig_target_help"' in response.text

    def test_database_wizard_has_status_roles(self, client):
        """Test that dynamic feedback areas have role=status or role=alert."""
        response = client.get("/database-wizard")
        assert 'role="status"' in response.text
        assert 'role="alert"' in response.text

    def test_database_wizard_has_aria_live(self, client):
        """Test that dynamic areas have aria-live for screen reader announcements."""
        response = client.get("/database-wizard")
        assert 'aria-live="polite"' in response.text

    def test_database_wizard_has_progressbar(self, client):
        """Test that the migration progress indicator has role=progressbar."""
        response = client.get("/database-wizard")
        assert 'role="progressbar"' in response.text

    def test_database_wizard_has_focus_ring_styles(self, client):
        """Test that interactive elements have focus ring styling."""
        response = client.get("/database-wizard")
        assert "focus:ring-2" in response.text
        assert "focus:outline-none" in response.text

    def test_database_wizard_has_table_scope_headers(self, client):
        """Test that migration preview table has proper scope attributes."""
        response = client.get("/database-wizard")
        assert 'scope="col"' in response.text

    def test_database_wizard_has_dark_mode_styles(self, client):
        """Test that the wizard includes dark mode CSS overrides."""
        response = client.get("/database-wizard")
        assert "html.dark" in response.text

    def test_database_wizard_copy_button_has_aria_label(self, client):
        """Test that the copy-to-clipboard button has an aria-label."""
        response = client.get("/database-wizard")
        assert 'aria-label="Copy to clipboard"' in response.text

    def test_database_wizard_decorative_icons_hidden(self, client):
        """Test that decorative icons have aria-hidden=true."""
        response = client.get("/database-wizard")
        assert 'aria-hidden="true"' in response.text

    def test_database_wizard_reduced_motion(self, client):
        """Test that wizard respects prefers-reduced-motion media query."""
        response = client.get("/database-wizard")
        assert "prefers-reduced-motion" in response.text


@pytest.mark.unit
class TestSettingsPageWizardLink:
    """Tests for the database wizard link on the settings page."""

    def test_settings_template_has_db_wizard_link(self):
        """Test that the settings template contains a link to the database wizard."""
        from pathlib import Path

        template_path = Path(__file__).resolve().parent.parent / "frontend" / "templates" / "settings.html"
        content = template_path.read_text()
        assert "/database-wizard" in content
        assert "DB Wizard" in content

    def test_settings_template_has_help_link_rendering(self):
        """Test that the settings template renders help_link metadata."""
        from pathlib import Path

        template_path = Path(__file__).resolve().parent.parent / "frontend" / "templates" / "settings.html"
        content = template_path.read_text()
        assert "setting.metadata.get('help_link')" in content
        assert "help_link_label" in content

    def test_database_url_metadata_has_help_link(self):
        """Test that database_url SETTING_METADATA includes help_link to wizard."""
        from app.utils.settings_service import SETTING_METADATA

        meta = SETTING_METADATA["database_url"]
        assert "help_link" in meta
        assert meta["help_link"] == "/database-wizard"
        assert "help_link_label" in meta


# Context manager helper for tests that don't need session_transaction
class _NoOpContextManager:
    """Dummy context manager for tests that don't need session_transaction."""

    def __enter__(self):
        return None

    def __exit__(self, *args):
        pass
