"""Tests for app/database.py module."""

from unittest.mock import MagicMock, patch

import pytest

from app.database import get_db, init_db


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
        from sqlalchemy import create_engine, text

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

    def test_migration_adds_file_path_columns(self, tmp_path):
        """Test that _run_schema_migrations adds file path columns to files table."""
        from sqlalchemy import create_engine, text

        from app.database import _run_schema_migrations

        # Create a database with the old schema (no file path columns)
        db_path = str(tmp_path / "migration_files_test.db")
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE files ("
                    "id INTEGER PRIMARY KEY, "
                    "filename VARCHAR, "
                    "filehash VARCHAR, "
                    "upload_date DATETIME)"
                )
            )

        # Run migrations
        _run_schema_migrations(engine)

        # Verify columns were added with correct types
        from sqlalchemy import inspect

        inspector = inspect(engine)
        columns = {col["name"]: col for col in inspector.get_columns("files")}

        assert "original_file_path" in columns
        assert columns["original_file_path"]["type"].__class__.__name__ in ("VARCHAR", "String", "TEXT")

        assert "processed_file_path" in columns
        assert columns["processed_file_path"]["type"].__class__.__name__ in ("VARCHAR", "String", "TEXT")

        assert "is_duplicate" in columns
        assert columns["is_duplicate"]["type"].__class__.__name__ in ("BOOLEAN", "Integer")

        assert "duplicate_of_id" in columns
        assert columns["duplicate_of_id"]["type"].__class__.__name__ in ("INTEGER", "Integer")

        engine.dispose()

    def test_migration_drops_unique_filehash_index(self, tmp_path):
        """Test that _run_schema_migrations drops unique index on filehash."""
        from sqlalchemy import create_engine, text

        from app.database import _run_schema_migrations

        # Create a database with unique index on filehash
        db_path = str(tmp_path / "migration_index_test.db")
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE files ("
                    "id INTEGER PRIMARY KEY, "
                    "filename VARCHAR, "
                    "filehash VARCHAR, "
                    "upload_date DATETIME, "
                    "original_file_path VARCHAR, "
                    "processed_file_path VARCHAR, "
                    "is_duplicate BOOLEAN DEFAULT FALSE NOT NULL, "
                    "duplicate_of_id INTEGER)"
                )
            )
            conn.execute(text("CREATE UNIQUE INDEX idx_filehash_unique ON files (filehash)"))

        # Verify unique index exists before migration
        from sqlalchemy import inspect

        inspector = inspect(engine)
        indexes_before = inspector.get_indexes("files")
        unique_indexes_before = [idx for idx in indexes_before if idx.get("unique")]
        assert len(unique_indexes_before) > 0

        # Run migrations
        _run_schema_migrations(engine)

        # Verify unique index was removed
        inspector = inspect(engine)
        indexes_after = inspector.get_indexes("files")
        unique_filehash_indexes_after = [
            idx for idx in indexes_after if idx.get("unique") and "filehash" in idx.get("column_names", [])
        ]
        assert len(unique_filehash_indexes_after) == 0

        engine.dispose()

    def test_migration_handles_missing_tables_gracefully(self, tmp_path):
        """Test that migrations don't fail when tables don't exist."""
        from sqlalchemy import create_engine

        from app.database import _run_schema_migrations

        # Create an empty database
        db_path = str(tmp_path / "empty_db_test.db")
        engine = create_engine(f"sqlite:///{db_path}")

        # Run migrations - should not raise any errors
        _run_schema_migrations(engine)

        engine.dispose()

    def test_migration_is_idempotent(self, tmp_path):
        """Test that running migrations multiple times is safe."""
        from sqlalchemy import create_engine, text

        from app.database import _run_schema_migrations

        # Create a database with old schema
        db_path = str(tmp_path / "idempotent_test.db")
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
            conn.execute(
                text(
                    "CREATE TABLE files ("
                    "id INTEGER PRIMARY KEY, "
                    "filename VARCHAR, "
                    "filehash VARCHAR, "
                    "upload_date DATETIME)"
                )
            )

        # Run migrations multiple times
        _run_schema_migrations(engine)
        _run_schema_migrations(engine)
        _run_schema_migrations(engine)

        # Verify all columns exist and no errors occurred
        from sqlalchemy import inspect

        inspector = inspect(engine)

        processing_log_columns = [col["name"] for col in inspector.get_columns("processing_logs")]
        assert "detail" in processing_log_columns

        files_columns = [col["name"] for col in inspector.get_columns("files")]
        assert "original_file_path" in files_columns
        assert "processed_file_path" in files_columns
        assert "is_duplicate" in files_columns
        assert "duplicate_of_id" in files_columns

        engine.dispose()


@pytest.mark.unit
class TestInitDbErrors:
    """Tests for error handling in init_db function."""

    @patch("app.database.Base")
    @patch("app.database.make_url")
    def test_init_db_handles_sqlalchemy_error(self, mock_make_url, mock_base):
        """Test that init_db properly handles SQLAlchemy errors."""
        from sqlalchemy import exc

        # Mock to raise SQLAlchemy error
        mock_url = MagicMock()
        mock_url.get_backend_name.return_value = "sqlite"
        mock_url.database = ":memory:"
        mock_make_url.return_value = mock_url

        mock_base.metadata.create_all.side_effect = exc.SQLAlchemyError("Database error")

        with pytest.raises(exc.SQLAlchemyError):
            init_db()
