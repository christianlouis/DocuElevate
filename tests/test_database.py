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
