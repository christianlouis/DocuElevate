"""Tests for app/database.py module."""
import os
import pytest
from unittest.mock import patch, MagicMock

from app.database import init_db, get_db


@pytest.mark.unit
class TestInitDb:
    """Tests for init_db function."""

    def test_init_db_creates_tables(self):
        """Test that init_db creates tables without error."""
        # In test environment, DATABASE_URL is sqlite:///:memory:
        init_db()

    @patch("app.database.make_url")
    @patch("app.database.Base")
    def test_init_db_with_sqlite_file(self, mock_base, mock_make_url, tmp_path):
        """Test init_db with a file-based SQLite database."""
        db_path = str(tmp_path / "test_db" / "test.db")
        mock_url = MagicMock()
        mock_url.get_backend_name.return_value = "sqlite"
        mock_url.database = db_path
        mock_make_url.return_value = mock_url

        init_db()

    @patch("app.database.make_url")
    @patch("app.database.Base")
    def test_init_db_with_memory_db(self, mock_base, mock_make_url):
        """Test init_db with in-memory database."""
        mock_url = MagicMock()
        mock_url.get_backend_name.return_value = "sqlite"
        mock_url.database = ":memory:"
        mock_make_url.return_value = mock_url

        init_db()

    @patch("app.database.make_url")
    @patch("app.database.Base")
    def test_init_db_with_non_sqlite(self, mock_base, mock_make_url):
        """Test init_db with non-SQLite database."""
        mock_url = MagicMock()
        mock_url.get_backend_name.return_value = "postgresql"
        mock_make_url.return_value = mock_url

        init_db()


@pytest.mark.unit
class TestGetDb:
    """Tests for get_db function."""

    def test_get_db_yields_session(self):
        """Test that get_db yields a session and closes it."""
        gen = get_db()
        session = next(gen)
        assert session is not None
        # Clean up
        try:
            next(gen)
        except StopIteration:
            pass

    def test_get_db_closes_session_on_exit(self):
        """Test that the session is closed when exiting the generator."""
        gen = get_db()
        session = next(gen)
        # Force the generator to close
        gen.close()


@pytest.mark.unit
class TestSchemaMigrations:
    """Tests for schema migration logic."""

    def test_processing_log_detail_column_exists(self, db_session):
        """Test that ProcessingLog has the detail column."""
        from app.models import ProcessingLog

        log = ProcessingLog(
            task_id="test-task",
            step_name="test_step",
            status="success",
            message="Short message",
            detail="Verbose worker log output\nWith multiple lines",
        )
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)

        assert log.detail == "Verbose worker log output\nWith multiple lines"

    def test_processing_log_detail_nullable(self, db_session):
        """Test that detail column is nullable (backward compatible)."""
        from app.models import ProcessingLog

        log = ProcessingLog(
            task_id="test-task-2",
            step_name="test_step",
            status="success",
            message="Short message",
        )
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)

        assert log.detail is None

    def test_migration_adds_detail_column(self, tmp_path):
        """Test that _run_schema_migrations adds detail column to existing tables."""
        from sqlalchemy import Column, Integer, String, create_engine, text
        from sqlalchemy.orm import sessionmaker

        from app.database import _run_schema_migrations

        # Create a database with the old schema (no detail column)
        db_path = str(tmp_path / "migration_test.db")
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE processing_logs ("
                    "id INTEGER PRIMARY KEY, "
                    "file_id INTEGER, "
                    "task_id VARCHAR, "
                    "step_name VARCHAR, "
                    "status VARCHAR, "
                    "message VARCHAR, "
                    "timestamp DATETIME)"
                )
            )

        # Run migrations
        _run_schema_migrations(engine)

        # Verify detail column was added
        from sqlalchemy import inspect

        inspector = inspect(engine)
        columns = [col["name"] for col in inspector.get_columns("processing_logs")]
        assert "detail" in columns

        engine.dispose()
