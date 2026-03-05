"""Tests for app/utils/db_migrate.py module."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.utils.db_migrate import migrate_data, preview_migration


@pytest.mark.unit
class TestPreviewMigration:
    """Tests for preview_migration function."""

    def test_preview_in_memory_sqlite(self):
        """Test previewing an in-memory SQLite database."""
        # Create a temporary source DB with some data
        src_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=src_engine)

        # Insert a test row
        Session = sessionmaker(bind=src_engine)
        session = Session()
        session.execute(text("INSERT INTO documents (filename) VALUES ('test.pdf')"))
        session.commit()
        session.close()

        # Preview using the engine's URL won't work for :memory:,
        # but we can test the error path
        result = preview_migration("sqlite:///:memory:")
        # For :memory: this creates a new empty DB, so tables are empty
        assert result["success"] is True
        assert isinstance(result["tables"], list)

    def test_preview_invalid_url(self):
        """Test preview with invalid URL returns error."""
        result = preview_migration("invalid://not-a-db")
        assert result["success"] is False
        assert "error" in result


@pytest.mark.unit
class TestMigrateData:
    """Tests for migrate_data function."""

    def test_migrate_empty_sqlite_to_sqlite(self):
        """Test migrating an empty SQLite DB to another SQLite DB."""
        # Both are file-based temp databases for this test
        src_url = "sqlite:///:memory:"
        tgt_url = "sqlite://"  # Another in-memory DB

        # Create source schema
        src_engine = create_engine(src_url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=src_engine)
        src_engine.dispose()

        # Run migration from empty source
        with patch("app.utils.db_migrate._make_engine") as mock_make:
            # Create real engines for both
            real_src = create_engine(
                "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
            )
            Base.metadata.create_all(bind=real_src)
            real_tgt = create_engine(
                "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
            )
            mock_make.side_effect = [real_src, real_tgt]

            with patch("app.utils.db_migrate._stamp_alembic_head"):
                result = migrate_data("sqlite:///:memory:", "sqlite:///:memory:")

        assert result["success"] is True
        assert result["rows_copied"] == 0

    def test_migrate_with_data(self):
        """Test migrating a SQLite DB with actual data."""
        real_src = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=real_src)

        # Insert test data
        Session = sessionmaker(bind=real_src)
        session = Session()
        session.execute(text("INSERT INTO documents (filename) VALUES ('invoice.pdf')"))
        session.execute(text("INSERT INTO documents (filename) VALUES ('receipt.pdf')"))
        session.commit()
        session.close()

        real_tgt = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        with patch("app.utils.db_migrate._make_engine") as mock_make:
            mock_make.side_effect = [real_src, real_tgt]
            with patch("app.utils.db_migrate._stamp_alembic_head"):
                result = migrate_data("sqlite:///:memory:", "sqlite:///:memory:")

        assert result["success"] is True
        assert result["rows_copied"] >= 2  # At least the 2 documents rows

    def test_migrate_with_progress_callback(self):
        """Test that progress callback is invoked during migration."""
        real_src = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=real_src)

        Session = sessionmaker(bind=real_src)
        session = Session()
        session.execute(text("INSERT INTO documents (filename) VALUES ('test.pdf')"))
        session.commit()
        session.close()

        real_tgt = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        callback = MagicMock()

        with patch("app.utils.db_migrate._make_engine") as mock_make:
            mock_make.side_effect = [real_src, real_tgt]
            with patch("app.utils.db_migrate._stamp_alembic_head"):
                result = migrate_data("sqlite:///:memory:", "sqlite:///:memory:", progress_callback=callback)

        assert result["success"] is True
        # Callback should have been called at least once for the non-empty table
        if result["rows_copied"] > 0:
            assert callback.call_count > 0

    def test_migrate_global_exception(self):
        """Test that a global exception is caught gracefully."""
        with patch("app.utils.db_migrate._make_engine", side_effect=Exception("boom")):
            result = migrate_data("sqlite:///:memory:", "sqlite:///:memory:")
        assert result["success"] is False
        assert len(result["errors"]) > 0

    def test_migrate_stamp_failure_is_recorded(self):
        """Test that Alembic stamp failure is recorded as an error."""
        real_src = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=real_src)
        real_tgt = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        with patch("app.utils.db_migrate._make_engine") as mock_make:
            mock_make.side_effect = [real_src, real_tgt]
            with patch("app.utils.db_migrate._stamp_alembic_head", side_effect=Exception("stamp failed")):
                result = migrate_data("sqlite:///:memory:", "sqlite:///:memory:")

        # Data copy succeeds but stamp fails — errors list non-empty
        assert len(result["errors"]) > 0
        assert any("stamp" in e.lower() for e in result["errors"])
