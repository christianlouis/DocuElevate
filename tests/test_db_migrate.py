"""Tests for the SQLite-to-SQL database migration helper."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.utils.db_migrate import _make_engine, _ordered_tables, migrate_data, preview_migration


@pytest.mark.unit
class TestMakeEngine:
    def test_sqlite_engine_is_created(self):
        engine = _make_engine("sqlite:///:memory:")
        assert engine is not None
        engine.dispose()

    def test_non_sqlite_engine_does_not_use_sqlite_connect_args(self):
        engine = _make_engine("postgresql+psycopg://user:pass@localhost:5432/docuelevate")
        assert engine is not None
        engine.dispose()


@pytest.mark.unit
class TestOrderedTables:
    def test_known_tables_are_ordered_before_unknown_tables(self):
        inspector = MagicMock()
        inspector.get_table_names.return_value = ["z_table", "files", "documents", "sqlite_sequence"]

        assert _ordered_tables(inspector) == ["documents", "files", "z_table"]

    def test_unsafe_table_names_are_skipped(self):
        inspector = MagicMock()
        inspector.get_table_names.return_value = ["files", "bad-table"]

        assert _ordered_tables(inspector) == ["files"]


@pytest.mark.unit
class TestPreviewMigration:
    def test_preview_returns_row_counts(self, tmp_path):
        db_path = tmp_path / "source.db"
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE files (id INTEGER PRIMARY KEY, local_filename VARCHAR NOT NULL)"))
            conn.execute(text("INSERT INTO files (local_filename) VALUES ('a.pdf'), ('b.pdf')"))

        result = preview_migration(f"sqlite:///{db_path}")

        assert result["success"] is True
        assert result["total_rows"] == 2
        assert result["tables"] == [{"name": "files", "row_count": 2}]


@pytest.mark.unit
class TestMigrateData:
    def test_migrates_reflected_schema_and_rows(self, tmp_path):
        source_path = tmp_path / "source.db"
        target_path = tmp_path / "target.db"
        source = create_engine(f"sqlite:///{source_path}")

        with source.begin() as conn:
            conn.execute(text("CREATE TABLE files (id INTEGER PRIMARY KEY, local_filename VARCHAR NOT NULL)"))
            conn.execute(text("CREATE TABLE future_table (id INTEGER PRIMARY KEY, value VARCHAR)"))
            conn.execute(text("INSERT INTO files (id, local_filename) VALUES (7, 'stable.pdf')"))
            conn.execute(text("INSERT INTO future_table (id, value) VALUES (1, 'kept')"))

        result = migrate_data(f"sqlite:///{source_path}", f"sqlite:///{target_path}")

        assert result["success"] is True
        assert result["rows_copied"] == 2

        target = create_engine(f"sqlite:///{target_path}")
        inspector = inspect(target)
        assert "files" in inspector.get_table_names()
        assert "future_table" in inspector.get_table_names()
        with target.connect() as conn:
            assert conn.execute(text("SELECT local_filename FROM files WHERE id = 7")).scalar_one() == "stable.pdf"
            assert conn.execute(text("SELECT value FROM future_table WHERE id = 1")).scalar_one() == "kept"

    def test_migration_reports_global_errors(self):
        with patch("app.utils.db_migrate._make_engine", side_effect=RuntimeError("boom")):
            result = migrate_data("sqlite:///:memory:", "sqlite:///:memory:")

        assert result["success"] is False
        assert "boom" in result["errors"][0]

    def test_migration_progress_callback_is_called(self):
        source = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        target = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        with source.begin() as conn:
            conn.execute(text("CREATE TABLE files (id INTEGER PRIMARY KEY, local_filename VARCHAR NOT NULL)"))
            conn.execute(text("INSERT INTO files (id, local_filename) VALUES (1, 'a.pdf'), (2, 'b.pdf')"))

        callback = MagicMock()
        with patch("app.utils.db_migrate._make_engine") as make_engine:
            make_engine.side_effect = [source, target]
            result = migrate_data("sqlite:///:memory:", "sqlite:///:memory:", batch_size=1, progress_callback=callback)

        assert result["success"] is True
        assert callback.call_count == 2
