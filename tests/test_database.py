"""Tests for app/database.py module."""

import warnings
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

    def test_deprecated_run_schema_migrations_warns(self, tmp_path):
        """Test that _run_schema_migrations emits a DeprecationWarning."""
        from sqlalchemy import create_engine

        from app.database import _run_schema_migrations

        db_path = str(tmp_path / "deprecation_test.db")
        engine = create_engine(f"sqlite:///{db_path}")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _run_schema_migrations(engine)

            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()
            assert "Alembic" in str(w[0].message)

        engine.dispose()

    def test_deprecated_migration_still_adds_detail_column(self, tmp_path):
        """Test that deprecated _run_schema_migrations still works for legacy callers."""
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

        # Run deprecated migrations (suppress warning for test clarity)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            _run_schema_migrations(engine)

        # Verify detail column was added
        from sqlalchemy import inspect

        inspector = inspect(engine)
        columns = [col["name"] for col in inspector.get_columns("processing_logs")]
        assert "detail" in columns

        engine.dispose()

    def test_deprecated_migration_adds_file_path_columns(self, tmp_path):
        """Test that deprecated _run_schema_migrations adds file path columns to files table."""
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

        # Run deprecated migrations
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
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

        assert "ocr_text" in columns
        assert "ai_metadata" in columns
        assert "document_title" in columns

        engine.dispose()

    def test_deprecated_migration_handles_missing_tables_gracefully(self, tmp_path):
        """Test that deprecated migrations don't fail when tables don't exist."""
        from sqlalchemy import create_engine

        from app.database import _run_schema_migrations

        # Create an empty database
        db_path = str(tmp_path / "empty_db_test.db")
        engine = create_engine(f"sqlite:///{db_path}")

        # Run migrations - should not raise any errors
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            _run_schema_migrations(engine)

        engine.dispose()

    def test_deprecated_migration_is_idempotent(self, tmp_path):
        """Test that running deprecated migrations multiple times is safe."""
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

        # Run deprecated migrations multiple times
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
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
        assert "ocr_text" in files_columns
        assert "ai_metadata" in files_columns
        assert "document_title" in files_columns

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


@pytest.mark.unit
class TestMultiVersionMigrations:
    """Test deprecated migration scenarios from various database versions.

    These tests verify the deprecated _run_schema_migrations function still
    works for legacy callers. New schema changes should use Alembic exclusively.
    """

    def test_migration_from_v1_to_v2_processing_logs(self, tmp_path):
        """Test migration from v1 (no detail column) to v2 (with detail)."""
        from sqlalchemy import create_engine, inspect, text

        from app.database import _run_schema_migrations

        # Create v1 database (without detail column)
        db_path = str(tmp_path / "v1_to_v2.db")
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
            # Insert test data
            conn.execute(
                text(
                    "INSERT INTO processing_logs (task_id, step_name, status, message) "
                    "VALUES ('test-1', 'test_step', 'success', 'Test message')"
                )
            )

        # Run migration to v2
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            _run_schema_migrations(engine)

        # Verify detail column exists and old data is preserved
        inspector = inspect(engine)
        columns = [col["name"] for col in inspector.get_columns("processing_logs")]
        assert "detail" in columns

        # Verify old data still accessible
        with engine.connect() as conn:
            result = conn.execute(text("SELECT task_id, message, detail FROM processing_logs WHERE task_id = 'test-1'"))
            row = result.fetchone()
            assert row[0] == "test-1"
            assert row[1] == "Test message"
            assert row[2] is None  # detail should be NULL for old records

        engine.dispose()

    def test_migration_from_v1_to_v3_files_table(self, tmp_path):
        """Test migration from v1 (basic) to v3 (with dedup columns)."""
        from sqlalchemy import create_engine, inspect, text

        from app.database import _run_schema_migrations

        # Create v1 database (minimal files table)
        db_path = str(tmp_path / "v1_to_v3.db")
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
            # Insert test data
            conn.execute(text("INSERT INTO files (filename, filehash) VALUES ('test.pdf', 'abc123')"))

        # Run migration to v3 (adds path columns and dedup columns)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            _run_schema_migrations(engine)

        # Verify all new columns exist
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("files")}
        assert "original_file_path" in columns
        assert "processed_file_path" in columns
        assert "is_duplicate" in columns
        assert "duplicate_of_id" in columns

        # Verify old data preserved with default values
        with engine.connect() as conn:
            result = conn.execute(text("SELECT filename, is_duplicate FROM files WHERE filename = 'test.pdf'"))
            row = result.fetchone()
            assert row[0] == "test.pdf"
            # is_duplicate should be False (0) by default
            assert row[1] in (0, False)

        engine.dispose()

    def test_migration_with_unique_index_already_dropped(self, tmp_path):
        """Test that migration handles case where unique index was already dropped."""
        from sqlalchemy import create_engine, text

        from app.database import _run_schema_migrations

        # Create database without unique index
        db_path = str(tmp_path / "no_index.db")
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE files ("
                    "id INTEGER PRIMARY KEY, "
                    "filename VARCHAR, "
                    "filehash VARCHAR, "
                    "original_file_path VARCHAR, "
                    "processed_file_path VARCHAR, "
                    "is_duplicate BOOLEAN DEFAULT FALSE NOT NULL, "
                    "duplicate_of_id INTEGER)"
                )
            )

        # Run migration - should not error even though there's no index to drop
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            _run_schema_migrations(engine)

        # Should complete without error
        engine.dispose()

    def test_migration_partial_state(self, tmp_path):
        """Test migration from partial state (some columns added, some missing)."""
        from sqlalchemy import create_engine, inspect, text

        from app.database import _run_schema_migrations

        # Create database with only some of the new columns
        db_path = str(tmp_path / "partial.db")
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            # Files table with only original_file_path, missing processed_file_path and dedup columns
            conn.execute(
                text(
                    "CREATE TABLE files ("
                    "id INTEGER PRIMARY KEY, "
                    "filename VARCHAR, "
                    "filehash VARCHAR, "
                    "original_file_path VARCHAR)"
                )
            )
            # Processing logs with detail column already present
            conn.execute(
                text(
                    "CREATE TABLE processing_logs ("
                    "id INTEGER PRIMARY KEY, "
                    "task_id VARCHAR, "
                    "step_name VARCHAR, "
                    "status VARCHAR, "
                    "message VARCHAR, "
                    "detail TEXT, "
                    "timestamp DATETIME)"
                )
            )

        # Run migration - should add missing columns only
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            _run_schema_migrations(engine)

        # Verify all columns exist now
        inspector = inspect(engine)
        files_columns = {col["name"] for col in inspector.get_columns("files")}
        assert "original_file_path" in files_columns
        assert "processed_file_path" in files_columns
        assert "is_duplicate" in files_columns
        assert "duplicate_of_id" in files_columns

        logs_columns = {col["name"] for col in inspector.get_columns("processing_logs")}
        assert "detail" in logs_columns

        engine.dispose()

    def test_migration_exception_handling(self, tmp_path):
        """Test that migration handles exceptions gracefully for index operations."""
        from sqlalchemy import create_engine, text

        from app.database import _run_schema_migrations

        # Create database with all columns but trigger exception path
        db_path = str(tmp_path / "exception_test.db")
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE files ("
                    "id INTEGER PRIMARY KEY, "
                    "filename VARCHAR, "
                    "filehash VARCHAR, "
                    "original_file_path VARCHAR, "
                    "processed_file_path VARCHAR, "
                    "is_duplicate BOOLEAN DEFAULT FALSE NOT NULL, "
                    "duplicate_of_id INTEGER)"
                )
            )

        # Run migration - should handle the exception path for index operations
        # (when get_indexes might have issues)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                _run_schema_migrations(engine)
            # Should complete without raising
        except Exception as e:
            pytest.fail(f"Migration should handle exceptions gracefully: {e}")

        engine.dispose()


@pytest.mark.unit
class TestAlembicUpgrade:
    """Tests for Alembic-based migration management."""

    def test_alembic_upgrade_stamps_fresh_database(self, tmp_path):
        """Test that _run_alembic_upgrade stamps a fresh database to head."""
        from pathlib import Path

        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine, inspect, text

        from app.database import Base, _run_alembic_upgrade

        # Determine the expected head revision dynamically
        migrations_dir = str(Path(__file__).resolve().parent.parent / "migrations")
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", migrations_dir)
        script = ScriptDirectory.from_config(alembic_cfg)
        expected_head = script.get_heads()[0]

        db_path = str(tmp_path / "fresh_alembic.db")
        engine = create_engine(f"sqlite:///{db_path}")

        # Create all tables (simulates Base.metadata.create_all)
        Base.metadata.create_all(bind=engine)

        # Run Alembic upgrade — should stamp to head (not run migrations)
        _run_alembic_upgrade(engine)

        # Verify alembic_version table exists and has a revision
        inspector = inspect(engine)
        assert "alembic_version" in inspector.get_table_names()

        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            assert row is not None
            # Should be stamped to the latest revision
            assert row[0] == expected_head

        engine.dispose()

    def test_alembic_upgrade_applies_pending_migrations(self, tmp_path):
        """Test that _run_alembic_upgrade applies pending migrations to a tracked DB."""
        from pathlib import Path

        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine, inspect, text

        from app.database import _run_alembic_upgrade

        # Determine the expected head revision dynamically
        migrations_dir = str(Path(__file__).resolve().parent.parent / "migrations")
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", migrations_dir)
        script = ScriptDirectory.from_config(alembic_cfg)
        expected_head = script.get_heads()[0]

        db_path = str(tmp_path / "tracked_alembic.db")
        engine = create_engine(f"sqlite:///{db_path}")

        # Create a database that represents the schema at revision 006:
        # - files table WITH detail, file_paths, dedup, search fields, but WITHOUT ocr_quality_score
        # - processing_logs WITH detail column
        # - alembic_version table pointing to 006
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE files ("
                    "id INTEGER PRIMARY KEY, "
                    "filehash VARCHAR NOT NULL, "
                    "original_filename VARCHAR, "
                    "local_filename VARCHAR NOT NULL, "
                    "original_file_path VARCHAR, "
                    "processed_file_path VARCHAR, "
                    "file_size INTEGER NOT NULL, "
                    "mime_type VARCHAR, "
                    "is_duplicate BOOLEAN DEFAULT 0 NOT NULL, "
                    "duplicate_of_id INTEGER, "
                    "ocr_text TEXT, "
                    "ai_metadata TEXT, "
                    "document_title VARCHAR, "
                    "created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE processing_logs ("
                    "id INTEGER PRIMARY KEY, "
                    "file_id INTEGER, "
                    "task_id VARCHAR, "
                    "step_name VARCHAR, "
                    "status VARCHAR, "
                    "message VARCHAR, "
                    "detail TEXT, "
                    "timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE file_processing_steps ("
                    "id INTEGER PRIMARY KEY, "
                    "file_id INTEGER NOT NULL, "
                    "step_name VARCHAR NOT NULL, "
                    "status VARCHAR NOT NULL, "
                    "started_at DATETIME, "
                    "completed_at DATETIME, "
                    "error_message TEXT, "
                    "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
                    "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
                )
            )
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('006_add_detail_column')"))

        # Verify ocr_quality_score does NOT exist yet
        inspector = inspect(engine)
        columns_before = {col["name"] for col in inspector.get_columns("files")}
        assert "ocr_quality_score" not in columns_before

        # Run Alembic upgrade — should apply 007 (adds ocr_quality_score) and 008 (indexes)
        _run_alembic_upgrade(engine)

        # Verify ocr_quality_score was added by migration 007
        inspector = inspect(engine)
        columns_after = {col["name"] for col in inspector.get_columns("files")}
        assert "ocr_quality_score" in columns_after

        # Verify alembic_version was updated to head
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            assert row is not None
            assert row[0] == expected_head

        engine.dispose()

    def test_alembic_upgrade_idempotent(self, tmp_path):
        """Test that calling _run_alembic_upgrade multiple times is safe."""
        from pathlib import Path

        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine, text

        from app.database import Base, _run_alembic_upgrade

        # Determine the expected head revision dynamically
        migrations_dir = str(Path(__file__).resolve().parent.parent / "migrations")
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", migrations_dir)
        script = ScriptDirectory.from_config(alembic_cfg)
        expected_head = script.get_heads()[0]

        db_path = str(tmp_path / "idempotent_alembic.db")
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(bind=engine)

        # Run multiple times — should not raise
        _run_alembic_upgrade(engine)
        _run_alembic_upgrade(engine)
        _run_alembic_upgrade(engine)

        # Verify revision is still head
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            assert row is not None
            assert row[0] == expected_head

        engine.dispose()

    def test_all_migration_revisions_exist(self):
        """Test that all expected Alembic migration revisions are present."""
        from pathlib import Path

        migrations_dir = Path(__file__).resolve().parent.parent / "migrations" / "versions"
        migration_files = sorted(migrations_dir.glob("*.py"))

        expected_prefixes = [
            "001_file_processing_steps",
            "002_add_file_paths",
            "003_add_deduplication_support",
            "004_add_search_fields",
            "005_add_saved_searches",
            "006_add_detail_column",
            "007_add_ocr_quality_drop_filehash_unique",
            "008_add_performance_indexes",
        ]

        migration_names = [f.stem for f in migration_files]
        for prefix in expected_prefixes:
            assert prefix in migration_names, f"Missing Alembic migration: {prefix}"

    def test_migration_chain_is_connected(self):
        """Test that the Alembic migration chain is properly connected."""
        from pathlib import Path

        from alembic.config import Config
        from alembic.script import ScriptDirectory

        migrations_dir = str(Path(__file__).resolve().parent.parent / "migrations")
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", migrations_dir)

        script = ScriptDirectory.from_config(alembic_cfg)

        # Walk the chain from base to head — should not raise
        revisions = list(script.walk_revisions())
        # At least 8 migrations should exist (001 through 008)
        assert len(revisions) >= 8

        # Count migration files to verify consistency
        versions_dir = Path(migrations_dir) / "versions"
        migration_files = [f for f in versions_dir.glob("*.py") if not f.name.startswith("__")]
        assert len(revisions) == len(migration_files)

        # Verify head is reachable
        heads = script.get_heads()
        assert len(heads) == 1  # Should be a single linear chain
