"""
Tests for the backup/restore functionality.

Covers:
- BackupRecord model creation
- backup_tasks: create_backup, cleanup_old_backups, retention helpers
- app/api/backup.py endpoints: list, create, download, restore, delete, cleanup
- app/views/backup.py dashboard view
"""

import gzip
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import BackupRecord

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def bk_engine():
    """In-memory SQLite engine with all tables for backup tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture()
def admin_client(bk_engine):
    """TestClient with admin override for backup routes."""
    from app.api.backup import _require_admin

    def override_db():
        Session = sessionmaker(bind=bk_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def override_require_admin():
        return {"email": "admin@test.com", "is_admin": True}

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[_require_admin] = override_require_admin
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def non_admin_client(bk_engine):
    """TestClient without admin override - _require_admin will raise 403."""

    def override_db():
        Session = sessionmaker(bind=bk_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def db_session(bk_engine):
    """SQLAlchemy session against the in-memory engine."""
    Session = sessionmaker(bind=bk_engine)
    session = Session()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBackupRecordModel:
    """Test the BackupRecord SQLAlchemy model."""

    def test_create_backup_record(self, db_session):
        """Test creating a BackupRecord persists correctly."""
        rec = BackupRecord(
            filename="backup_daily_2026-01-01T02-30-00.db.gz",
            local_path="/tmp/test.db.gz",
            backup_type="daily",
            size_bytes=2048,
            checksum="deadbeef",
            status="ok",
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)

        assert rec.id is not None
        assert rec.filename == "backup_daily_2026-01-01T02-30-00.db.gz"
        assert rec.backup_type == "daily"
        assert rec.size_bytes == 2048

    def test_backup_record_defaults(self, db_session):
        """Test default values for BackupRecord fields."""
        rec = BackupRecord(
            filename="backup_weekly_2026-01-01T03-00-00.db.gz",
            backup_type="weekly",
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)

        assert rec.status == "ok"
        assert rec.size_bytes == 0
        assert rec.remote_destination is None
        assert rec.remote_path is None

    def test_backup_record_remote_fields(self, db_session):
        """Test remote destination fields on BackupRecord."""
        rec = BackupRecord(
            filename="backup_hourly_remote.db.gz",
            backup_type="hourly",
            remote_destination="s3",
            remote_path="backups/backup_hourly_remote.db.gz",
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)

        assert rec.remote_destination == "s3"
        assert rec.remote_path == "backups/backup_hourly_remote.db.gz"


# ---------------------------------------------------------------------------
# Task helper unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBackupTaskHelpers:
    """Unit tests for backup_tasks helper functions."""

    def test_backup_dir_creation(self, tmp_path):
        """_backup_dir() creates the directory if it does not exist."""
        from app.tasks.backup_tasks import _backup_dir

        with patch("app.tasks.backup_tasks.settings") as mock_settings:
            mock_settings.backup_dir = str(tmp_path / "mybkp")
            d = _backup_dir()
            assert d.exists()

    def test_backup_dir_default(self, tmp_path):
        """_backup_dir() defaults to <workdir>/backups."""
        from app.tasks.backup_tasks import _backup_dir

        with patch("app.tasks.backup_tasks.settings") as mock_settings:
            mock_settings.backup_dir = None
            mock_settings.workdir = str(tmp_path)
            d = _backup_dir()
            assert d == tmp_path / "backups"

    def test_sha256(self, tmp_path):
        """_sha256() returns a 64-char hex string."""
        from app.tasks.backup_tasks import _sha256

        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        digest = _sha256(f)
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_dump_sqlite(self, tmp_path):
        """_dump_sqlite() writes a gzip-compressed SQL dump."""
        from app.tasks.backup_tasks import _dump_sqlite

        src = tmp_path / "src.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
        conn.execute("INSERT INTO t VALUES (1, 'hello')")
        conn.commit()
        conn.close()

        dest = tmp_path / "dump.db.gz"
        _dump_sqlite(src, dest)

        assert dest.exists()
        with gzip.open(str(dest), "rt") as gz:
            content = gz.read()
        assert "CREATE TABLE t" in content
        assert "hello" in content

    def test_db_path_sqlite(self):
        """_db_path() returns path for sqlite:/// URLs."""
        from app.tasks.backup_tasks import _db_path

        with patch("app.tasks.backup_tasks.settings") as mock_settings:
            mock_settings.database_url = "sqlite:////tmp/test.db"
            result = _db_path()
            assert result == Path("/tmp/test.db")

    def test_db_path_memory(self):
        """_db_path() returns None for in-memory sqlite."""
        from app.tasks.backup_tasks import _db_path

        with patch("app.tasks.backup_tasks.settings") as mock_settings:
            mock_settings.database_url = "sqlite:///:memory:"
            result = _db_path()
            assert result is None

    def test_db_path_postgres(self):
        """_db_path() returns None for non-SQLite databases."""
        from app.tasks.backup_tasks import _db_path

        with patch("app.tasks.backup_tasks.settings") as mock_settings:
            mock_settings.database_url = "postgresql://user:pass@localhost/db"
            result = _db_path()
            assert result is None

    def test_db_backend_sqlite(self):
        """_db_backend() returns 'sqlite' for SQLite URLs."""
        from app.tasks.backup_tasks import _db_backend

        with patch("app.tasks.backup_tasks.settings") as mock_settings:
            mock_settings.database_url = "sqlite:////tmp/test.db"
            assert _db_backend() == "sqlite"

    def test_db_backend_postgresql(self):
        """_db_backend() returns 'postgresql' for PostgreSQL URLs."""
        from app.tasks.backup_tasks import _db_backend

        with patch("app.tasks.backup_tasks.settings") as mock_settings:
            mock_settings.database_url = "postgresql://user:pass@localhost/db"
            assert _db_backend() == "postgresql"

    def test_db_backend_mysql(self):
        """_db_backend() returns 'mysql' for MySQL URLs."""
        from app.tasks.backup_tasks import _db_backend

        with patch("app.tasks.backup_tasks.settings") as mock_settings:
            mock_settings.database_url = "mysql+pymysql://user:pass@localhost/db"
            assert _db_backend() == "mysql"

    def test_archive_ext_sqlite(self):
        """_archive_ext_for_backend() returns '.db.gz' for sqlite."""
        from app.tasks.backup_tasks import _archive_ext_for_backend

        assert _archive_ext_for_backend("sqlite") == ".db.gz"

    def test_archive_ext_postgresql(self):
        """_archive_ext_for_backend() returns '.pgsql.gz' for postgresql."""
        from app.tasks.backup_tasks import _archive_ext_for_backend

        assert _archive_ext_for_backend("postgresql") == ".pgsql.gz"

    def test_archive_ext_mysql(self):
        """_archive_ext_for_backend() returns '.mysql.gz' for mysql."""
        from app.tasks.backup_tasks import _archive_ext_for_backend

        assert _archive_ext_for_backend("mysql") == ".mysql.gz"

    def test_archive_ext_unknown(self):
        """_archive_ext_for_backend() falls back to '.sql.gz' for unknown backends."""
        from app.tasks.backup_tasks import _archive_ext_for_backend

        assert _archive_ext_for_backend("mssql") == ".sql.gz"

    def test_dump_postgresql_success(self, tmp_path):
        """_dump_postgresql() streams pg_dump output into a gzip archive."""
        from unittest.mock import MagicMock

        from app.tasks.backup_tasks import _dump_postgresql

        dest = tmp_path / "dump.pgsql.gz"
        fake_sql = b"-- PostgreSQL database dump\nSELECT 1;\n"

        mock_proc = MagicMock()
        mock_proc.stdout.read.side_effect = [fake_sql, b""]
        mock_proc.stderr.read.return_value = b""
        mock_proc.returncode = 0

        with patch("app.tasks.backup_tasks.subprocess.Popen", return_value=mock_proc):
            _dump_postgresql("postgresql://user:pass@localhost/testdb", dest)

        assert dest.exists()
        with gzip.open(str(dest), "rb") as gz:
            assert gz.read() == fake_sql

    def test_dump_postgresql_failure(self, tmp_path):
        """_dump_postgresql() raises RuntimeError when pg_dump fails."""
        from unittest.mock import MagicMock

        from app.tasks.backup_tasks import _dump_postgresql

        dest = tmp_path / "dump.pgsql.gz"

        mock_proc = MagicMock()
        mock_proc.stdout.read.side_effect = [b""]
        mock_proc.stderr.read.return_value = b"FATAL: connection refused"
        mock_proc.returncode = 1

        with patch("app.tasks.backup_tasks.subprocess.Popen", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="pg_dump exited with code 1"):
                _dump_postgresql("postgresql://user:pass@localhost/testdb", dest)

    def test_dump_mysql_success(self, tmp_path):
        """_dump_mysql() streams mysqldump output into a gzip archive."""
        from unittest.mock import MagicMock

        from app.tasks.backup_tasks import _dump_mysql

        dest = tmp_path / "dump.mysql.gz"
        fake_sql = b"-- MySQL dump\nCREATE TABLE t (id INT);\n"

        mock_proc = MagicMock()
        mock_proc.stdout.read.side_effect = [fake_sql, b""]
        mock_proc.stderr.read.return_value = b""
        mock_proc.returncode = 0

        with patch("app.tasks.backup_tasks.subprocess.Popen", return_value=mock_proc):
            _dump_mysql("mysql+pymysql://user:pass@localhost/testdb", dest)

        assert dest.exists()
        with gzip.open(str(dest), "rb") as gz:
            assert gz.read() == fake_sql

    def test_dump_mysql_failure(self, tmp_path):
        """_dump_mysql() raises RuntimeError when mysqldump fails."""
        from unittest.mock import MagicMock

        from app.tasks.backup_tasks import _dump_mysql

        dest = tmp_path / "dump.mysql.gz"

        mock_proc = MagicMock()
        mock_proc.stdout.read.side_effect = [b""]
        mock_proc.stderr.read.return_value = b"ERROR: Access denied"
        mock_proc.returncode = 1

        with patch("app.tasks.backup_tasks.subprocess.Popen", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="mysqldump exited with code 1"):
                _dump_mysql("mysql+pymysql://user:pass@localhost/testdb", dest)

    def test_restore_sqlite_success(self, tmp_path):
        """_restore_sqlite() applies a valid SQL dump to a SQLite file."""
        from app.tasks.backup_tasks import _restore_sqlite

        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE old (id INTEGER)")
        conn.commit()
        conn.close()

        # Create a valid dump archive
        sql = "BEGIN TRANSACTION;\nCREATE TABLE new_tbl (x TEXT);\nCOMMIT;\n"
        archive = tmp_path / "dump.db.gz"
        with gzip.open(str(archive), "wt") as gz:
            gz.write(sql)

        _restore_sqlite(db_file, archive)

        conn2 = sqlite3.connect(str(db_file))
        tables = [r[0] for r in conn2.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        conn2.close()
        assert "new_tbl" in tables

    def test_restore_sqlite_invalid_gz(self, tmp_path):
        """_restore_sqlite() raises ValueError for corrupt gzip content."""
        from app.tasks.backup_tasks import _restore_sqlite

        db_file = tmp_path / "test.db"
        db_file.write_bytes(b"")
        archive = tmp_path / "bad.db.gz"
        archive.write_bytes(b"not gzip data")

        with pytest.raises(ValueError, match="Failed to decompress"):
            _restore_sqlite(db_file, archive)

    def test_restore_sqlite_invalid_sql(self, tmp_path):
        """_restore_sqlite() raises ValueError for invalid SQL content."""
        from app.tasks.backup_tasks import _restore_sqlite

        db_file = tmp_path / "test.db"
        db_file.write_bytes(b"")
        archive = tmp_path / "bad.db.gz"
        with gzip.open(str(archive), "wt") as gz:
            gz.write("THIS IS NOT VALID SQL!!!;\n")

        with pytest.raises(ValueError, match="invalid SQL"):
            _restore_sqlite(db_file, archive)

    def test_restore_postgresql_success(self, tmp_path):
        """_restore_postgresql() pipes the archive to psql."""
        from unittest.mock import MagicMock

        from app.tasks.backup_tasks import _restore_postgresql

        fake_sql = b"-- PostgreSQL dump\nSELECT 1;\n"
        archive = tmp_path / "dump.pgsql.gz"
        with gzip.open(str(archive), "wb") as gz:
            gz.write(fake_sql)

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0

        with patch("app.tasks.backup_tasks.subprocess.Popen", return_value=mock_proc):
            _restore_postgresql("postgresql://user:pass@localhost/testdb", archive)

        mock_proc.communicate.assert_called_once_with(input=fake_sql)

    def test_restore_postgresql_failure(self, tmp_path):
        """_restore_postgresql() raises RuntimeError when psql fails."""
        from unittest.mock import MagicMock

        from app.tasks.backup_tasks import _restore_postgresql

        archive = tmp_path / "dump.pgsql.gz"
        with gzip.open(str(archive), "wb") as gz:
            gz.write(b"SELECT 1;")

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"", b"ERROR: invalid input")
        mock_proc.returncode = 1

        with patch("app.tasks.backup_tasks.subprocess.Popen", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="psql exited with code 1"):
                _restore_postgresql("postgresql://user:pass@localhost/testdb", archive)

    def test_restore_mysql_success(self, tmp_path):
        """_restore_mysql() pipes the archive to mysql."""
        from unittest.mock import MagicMock

        from app.tasks.backup_tasks import _restore_mysql

        fake_sql = b"-- MySQL dump\nSELECT 1;\n"
        archive = tmp_path / "dump.mysql.gz"
        with gzip.open(str(archive), "wb") as gz:
            gz.write(fake_sql)

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0

        with patch("app.tasks.backup_tasks.subprocess.Popen", return_value=mock_proc):
            _restore_mysql("mysql+pymysql://user:pass@localhost/testdb", archive)

        mock_proc.communicate.assert_called_once_with(input=fake_sql)

    def test_restore_mysql_failure(self, tmp_path):
        """_restore_mysql() raises RuntimeError when mysql fails."""
        from unittest.mock import MagicMock

        from app.tasks.backup_tasks import _restore_mysql

        archive = tmp_path / "dump.mysql.gz"
        with gzip.open(str(archive), "wb") as gz:
            gz.write(b"SELECT 1;")

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"", b"ERROR: Access denied")
        mock_proc.returncode = 1

        with patch("app.tasks.backup_tasks.subprocess.Popen", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="mysql exited with code 1"):
                _restore_mysql("mysql+pymysql://user:pass@localhost/testdb", archive)

    def test_apply_retention_prunes_old(self, tmp_path, db_session):
        """_apply_retention() deletes backups beyond the retention limit."""
        from app.tasks.backup_tasks import _apply_retention

        for i in range(5):
            f = tmp_path / f"backup_hourly_{i:04d}.db.gz"
            f.write_bytes(b"x")
            rec = BackupRecord(
                filename=f"backup_hourly_{i:04d}.db.gz",
                local_path=str(f),
                backup_type="hourly",
                size_bytes=1,
                status="ok",
                created_at=datetime(2026, 1, 1, i, 0, 0, tzinfo=timezone.utc),
            )
            db_session.add(rec)
        db_session.commit()

        with patch("app.tasks.backup_tasks.settings") as mock_settings:
            mock_settings.backup_retain_hourly = 3
            _apply_retention("hourly", db_session)

        remaining = db_session.query(BackupRecord).filter_by(backup_type="hourly").all()
        remaining_paths = [r.local_path for r in remaining if r.local_path is not None]
        assert len(remaining_paths) <= 3

    def test_apply_retention_removes_record_no_remote(self, tmp_path, db_session):
        """_apply_retention() deletes the DB record when no local file or remote copy remain."""
        from app.tasks.backup_tasks import _apply_retention

        # Old record – local file doesn't exist, no remote
        old_rec = BackupRecord(
            filename="backup_hourly_old.db.gz",
            local_path=str(tmp_path / "nonexistent.db.gz"),
            backup_type="hourly",
            size_bytes=1,
            status="ok",
            created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        )
        db_session.add(old_rec)
        # Two newer records so the old one falls outside retention window
        for i, dt in enumerate([datetime(2026, 1, 1), datetime(2026, 1, 2)]):
            db_session.add(
                BackupRecord(
                    filename=f"backup_hourly_new_{i}.db.gz",
                    backup_type="hourly",
                    size_bytes=1,
                    status="ok",
                    created_at=dt.replace(tzinfo=timezone.utc),
                )
            )
        db_session.commit()

        with patch("app.tasks.backup_tasks.settings") as mock_settings:
            mock_settings.backup_retain_hourly = 2
            _apply_retention("hourly", db_session)

        remaining = db_session.query(BackupRecord).filter_by(filename="backup_hourly_old.db.gz").first()
        assert remaining is None

    def test_upload_remote_no_destination(self, tmp_path):
        """_upload_remote() returns None when no destination is configured."""
        from app.tasks.backup_tasks import _upload_remote

        f = tmp_path / "bkp.db.gz"
        f.write_bytes(b"data")

        with patch("app.tasks.backup_tasks.settings") as mock_settings:
            mock_settings.backup_remote_destination = None
            result = _upload_remote(f, "bkp.db.gz")
        assert result is None

    def test_upload_remote_unknown_dest(self, tmp_path):
        """_upload_remote() returns None for an unimplemented destination."""
        from app.tasks.backup_tasks import _upload_remote

        f = tmp_path / "bkp.db.gz"
        f.write_bytes(b"data")

        with patch("app.tasks.backup_tasks.settings") as mock_settings:
            mock_settings.backup_remote_destination = "unknown_provider"
            mock_settings.backup_remote_folder = "backups"
            result = _upload_remote(f, "bkp.db.gz")
        assert result is None

    def test_delete_remote_copy_no_dest(self):
        """_delete_remote_copy() does nothing when rec has no destination."""
        from app.tasks.backup_tasks import _delete_remote_copy

        rec = BackupRecord(
            filename="x.db.gz",
            backup_type="hourly",
            remote_destination=None,
            remote_path=None,
        )
        _delete_remote_copy(rec)


# ---------------------------------------------------------------------------
# Task integration tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateBackupTask:
    """Tests for the create_backup Celery task."""

    def test_backup_disabled(self):
        """create_backup returns early when backup_enabled is False."""
        from app.tasks.backup_tasks import create_backup

        with patch("app.tasks.backup_tasks.settings") as mock_settings:
            mock_settings.backup_enabled = False
            result = create_backup("hourly")
        assert result["status"] == "disabled"

    def test_unsupported_db_backend(self):
        """create_backup returns unsupported_db for backends other than sqlite/postgresql/mysql."""
        from app.tasks.backup_tasks import create_backup

        with patch("app.tasks.backup_tasks.settings") as mock_settings:
            mock_settings.backup_enabled = True
            mock_settings.database_url = "mssql+pyodbc://user:pass@server/db"
            result = create_backup("hourly")
        assert result["status"] == "unsupported_db"

    def test_in_memory_sqlite_unsupported(self):
        """create_backup returns unsupported_db for in-memory SQLite."""
        from app.tasks.backup_tasks import create_backup

        with patch("app.tasks.backup_tasks.settings") as mock_settings:
            mock_settings.backup_enabled = True
            mock_settings.database_url = "sqlite:///:memory:"
            result = create_backup("hourly")
        assert result["status"] == "unsupported_db"

    def test_missing_db_file(self, tmp_path):
        """create_backup returns error when the SQLite DB file does not exist."""
        from app.tasks.backup_tasks import create_backup

        missing = tmp_path / "does_not_exist.db"

        with (
            patch("app.tasks.backup_tasks.settings") as mock_settings,
            patch("app.tasks.backup_tasks._db_path", return_value=missing),
        ):
            mock_settings.backup_enabled = True
            mock_settings.database_url = f"sqlite:///{missing}"
            result = create_backup("hourly")
        assert result["status"] == "error"

    def test_successful_backup(self, tmp_path):
        """create_backup creates a .db.gz archive and a BackupRecord."""
        from app.tasks.backup_tasks import create_backup

        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        conn.close()

        backup_dir = tmp_path / "backups"

        with (
            patch("app.tasks.backup_tasks.settings") as mock_settings,
            patch("app.tasks.backup_tasks._db_path", return_value=db_file),
            patch("app.tasks.backup_tasks._backup_dir", return_value=backup_dir),
            patch("app.tasks.backup_tasks._upload_remote", return_value=None),
            patch("app.tasks.backup_tasks._apply_retention"),
            patch("app.tasks.backup_tasks._prune_remote_backups"),
            patch("app.tasks.backup_tasks.SessionLocal") as mock_sl,
        ):
            backup_dir.mkdir(parents=True, exist_ok=True)
            mock_settings.backup_enabled = True
            mock_settings.database_url = f"sqlite:///{db_file}"
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = create_backup("hourly")

        assert result["status"] == "ok"
        assert "filename" in result
        assert result["filename"].startswith("backup_hourly_")
        assert result["filename"].endswith(".db.gz")

    def test_successful_backup_postgresql(self, tmp_path):
        """create_backup creates a .pgsql.gz archive for PostgreSQL databases."""
        from app.tasks.backup_tasks import create_backup

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        def fake_pg_dump(db_url: str, dest: Path) -> None:
            with gzip.open(str(dest), "wb") as gz:
                gz.write(b"-- PostgreSQL dump\n")

        with (
            patch("app.tasks.backup_tasks.settings") as mock_settings,
            patch("app.tasks.backup_tasks._backup_dir", return_value=backup_dir),
            patch("app.tasks.backup_tasks._dump_postgresql", side_effect=fake_pg_dump),
            patch("app.tasks.backup_tasks._upload_remote", return_value=None),
            patch("app.tasks.backup_tasks._apply_retention"),
            patch("app.tasks.backup_tasks._prune_remote_backups"),
            patch("app.tasks.backup_tasks.SessionLocal") as mock_sl,
        ):
            mock_settings.backup_enabled = True
            mock_settings.database_url = "postgresql://user:pass@localhost/testdb"
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = create_backup("daily")

        assert result["status"] == "ok"
        assert result["filename"].endswith(".pgsql.gz")
        assert "daily" in result["filename"]

    def test_successful_backup_mysql(self, tmp_path):
        """create_backup creates a .mysql.gz archive for MySQL databases."""
        from app.tasks.backup_tasks import create_backup

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        def fake_mysql_dump(db_url: str, dest: Path) -> None:
            with gzip.open(str(dest), "wb") as gz:
                gz.write(b"-- MySQL dump\n")

        with (
            patch("app.tasks.backup_tasks.settings") as mock_settings,
            patch("app.tasks.backup_tasks._backup_dir", return_value=backup_dir),
            patch("app.tasks.backup_tasks._dump_mysql", side_effect=fake_mysql_dump),
            patch("app.tasks.backup_tasks._upload_remote", return_value=None),
            patch("app.tasks.backup_tasks._apply_retention"),
            patch("app.tasks.backup_tasks._prune_remote_backups"),
            patch("app.tasks.backup_tasks.SessionLocal") as mock_sl,
        ):
            mock_settings.backup_enabled = True
            mock_settings.database_url = "mysql+pymysql://user:pass@localhost/testdb"
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = create_backup("weekly")

        assert result["status"] == "ok"
        assert result["filename"].endswith(".mysql.gz")
        assert "weekly" in result["filename"]

    def test_invalid_backup_type_defaults_to_hourly(self, tmp_path):
        """create_backup normalises unknown backup_type to 'hourly'."""
        from app.tasks.backup_tasks import create_backup

        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        conn.close()

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        with (
            patch("app.tasks.backup_tasks.settings") as mock_settings,
            patch("app.tasks.backup_tasks._db_path", return_value=db_file),
            patch("app.tasks.backup_tasks._backup_dir", return_value=backup_dir),
            patch("app.tasks.backup_tasks._upload_remote", return_value=None),
            patch("app.tasks.backup_tasks._apply_retention"),
            patch("app.tasks.backup_tasks._prune_remote_backups"),
            patch("app.tasks.backup_tasks.SessionLocal") as mock_sl,
        ):
            mock_settings.backup_enabled = True
            mock_settings.database_url = f"sqlite:///{db_file}"
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = create_backup("invalid_type")

        assert result.get("status") == "ok"
        assert "hourly" in result["filename"]


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestBackupAPIEndpoints:
    """Tests for /api/admin/backup/* endpoints."""

    def test_list_backups_admin(self, admin_client):
        """GET /api/admin/backup/ returns a list for admin users."""
        resp = admin_client.get("/api/admin/backup/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_backups_non_admin(self, non_admin_client):
        """GET /api/admin/backup/ returns 403 for non-admin users."""
        resp = non_admin_client.get("/api/admin/backup/")
        assert resp.status_code == 403

    def test_trigger_backup_admin(self, admin_client):
        """POST /api/admin/backup/create queues a backup task."""
        with patch("app.tasks.backup_tasks.create_backup") as mock_task:
            mock_result = MagicMock()
            mock_result.id = "fake-task-id"
            mock_task.delay.return_value = mock_result
            resp = admin_client.post("/api/admin/backup/create?backup_type=hourly")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["backup_type"] == "hourly"

    def test_trigger_backup_invalid_type(self, admin_client):
        """POST /api/admin/backup/create returns 400 for invalid type."""
        resp = admin_client.post("/api/admin/backup/create?backup_type=invalid")
        assert resp.status_code == 400

    def test_trigger_backup_non_admin(self, non_admin_client):
        """POST /api/admin/backup/create returns 403 for non-admin."""
        resp = non_admin_client.post("/api/admin/backup/create")
        assert resp.status_code == 403

    def test_download_backup_not_found(self, admin_client):
        """GET /api/admin/backup/99999/download returns 404 for unknown ID."""
        resp = admin_client.get("/api/admin/backup/99999/download")
        assert resp.status_code == 404

    def test_download_backup_no_local_file(self, admin_client, bk_engine):
        """GET /api/admin/backup/{id}/download returns 404 when file was pruned."""
        Session = sessionmaker(bind=bk_engine)
        with Session() as db:
            rec = BackupRecord(
                filename="backup_hourly_pruned.db.gz",
                local_path="/nonexistent/path/file.db.gz",
                backup_type="hourly",
                size_bytes=0,
                status="ok",
            )
            db.add(rec)
            db.commit()
            rid = rec.id

        resp = admin_client.get(f"/api/admin/backup/{rid}/download")
        assert resp.status_code == 404

    def test_delete_backup_admin(self, admin_client, bk_engine):
        """DELETE /api/admin/backup/{id} removes the record."""
        Session = sessionmaker(bind=bk_engine)
        with Session() as db:
            rec = BackupRecord(
                filename="backup_hourly_to_delete.db.gz",
                backup_type="hourly",
                size_bytes=0,
                status="ok",
            )
            db.add(rec)
            db.commit()
            rid = rec.id

        resp = admin_client.delete(f"/api/admin/backup/{rid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_backup_not_found(self, admin_client):
        """DELETE /api/admin/backup/99999 returns 404."""
        resp = admin_client.delete("/api/admin/backup/99999")
        assert resp.status_code == 404

    def test_delete_backup_non_admin(self, non_admin_client):
        """DELETE /api/admin/backup/1 returns 403 for non-admin."""
        resp = non_admin_client.delete("/api/admin/backup/1")
        assert resp.status_code == 403

    def test_cleanup_endpoint_admin(self, admin_client):
        """POST /api/admin/backup/cleanup queues cleanup task."""
        with patch("app.tasks.backup_tasks.cleanup_old_backups") as mock_task:
            mock_result = MagicMock()
            mock_result.id = "fake-cleanup-id"
            mock_task.delay.return_value = mock_result
            resp = admin_client.post("/api/admin/backup/cleanup")
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    def test_cleanup_endpoint_non_admin(self, non_admin_client):
        """POST /api/admin/backup/cleanup returns 403 for non-admin."""
        resp = non_admin_client.post("/api/admin/backup/cleanup")
        assert resp.status_code == 403

    def test_restore_wrong_extension(self, admin_client):
        """POST /api/admin/backup/restore rejects files with wrong extension for current backend."""
        # Default test env uses sqlite:///:memory: → expects .db.gz
        resp = admin_client.post(
            "/api/admin/backup/restore",
            files={"file": ("backup.zip", b"data", "application/zip")},
        )
        assert resp.status_code == 400

    def test_restore_invalid_gz_content(self, admin_client, tmp_path):
        """POST /api/admin/backup/restore rejects corrupt gzip data."""
        db_file = tmp_path / "test.db"
        db_file.write_bytes(b"")

        with patch("app.tasks.backup_tasks._db_path", return_value=db_file):
            resp = admin_client.post(
                "/api/admin/backup/restore",
                files={"file": ("backup.db.gz", b"not gzip data at all", "application/gzip")},
            )
        assert resp.status_code == 400

    def test_restore_valid_archive(self, admin_client, tmp_path):
        """POST /api/admin/backup/restore succeeds with a valid gzip SQL dump."""
        sql = "BEGIN TRANSACTION;\nCOMMIT;\n"
        gz_data = gzip.compress(sql.encode())

        db_file = tmp_path / "restore_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.close()

        with patch("app.tasks.backup_tasks._db_path", return_value=db_file):
            resp = admin_client.post(
                "/api/admin/backup/restore",
                files={"file": ("backup.db.gz", gz_data, "application/gzip")},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "restored"

    def test_restore_in_memory_sqlite(self, admin_client):
        """POST /api/admin/backup/restore returns 400 for in-memory SQLite (no file to restore to)."""
        gz_data = gzip.compress(b"BEGIN TRANSACTION;\nCOMMIT;\n")

        # _db_path() returns None for :memory: URLs → 400
        with patch("app.tasks.backup_tasks._db_path", return_value=None):
            resp = admin_client.post(
                "/api/admin/backup/restore",
                files={"file": ("backup.db.gz", gz_data, "application/gzip")},
            )
        assert resp.status_code == 400

    def test_restore_wrong_extension_for_postgresql(self, admin_client):
        """POST /api/admin/backup/restore returns 400 when uploading .db.gz for PostgreSQL backend."""
        gz_data = gzip.compress(b"-- PostgreSQL dump")

        with patch("app.config.settings") as mock_settings:
            mock_settings.database_url = "postgresql://user:pass@localhost/testdb"
            resp = admin_client.post(
                "/api/admin/backup/restore",
                files={"file": ("backup.db.gz", gz_data, "application/gzip")},
            )
        assert resp.status_code == 400

    def test_restore_wrong_extension_for_mysql(self, admin_client):
        """POST /api/admin/backup/restore returns 400 when uploading .db.gz for MySQL backend."""
        gz_data = gzip.compress(b"-- MySQL dump")

        with patch("app.config.settings") as mock_settings:
            mock_settings.database_url = "mysql+pymysql://user:pass@localhost/testdb"
            resp = admin_client.post(
                "/api/admin/backup/restore",
                files={"file": ("backup.db.gz", gz_data, "application/gzip")},
            )
        assert resp.status_code == 400

    def test_restore_postgresql_success(self, admin_client):
        """POST /api/admin/backup/restore succeeds for PostgreSQL database."""
        gz_data = gzip.compress(b"-- PostgreSQL dump\n")

        with (
            patch("app.config.settings") as mock_settings,
            patch("app.tasks.backup_tasks._restore_postgresql") as mock_restore,
        ):
            mock_settings.database_url = "postgresql://user:pass@localhost/testdb"
            resp = admin_client.post(
                "/api/admin/backup/restore",
                files={"file": ("backup.pgsql.gz", gz_data, "application/gzip")},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "restored"
        mock_restore.assert_called_once()

    def test_restore_mysql_success(self, admin_client):
        """POST /api/admin/backup/restore succeeds for MySQL database."""
        gz_data = gzip.compress(b"-- MySQL dump\n")

        with (
            patch("app.config.settings") as mock_settings,
            patch("app.tasks.backup_tasks._restore_mysql") as mock_restore,
        ):
            mock_settings.database_url = "mysql+pymysql://user:pass@localhost/testdb"
            resp = admin_client.post(
                "/api/admin/backup/restore",
                files={"file": ("backup.mysql.gz", gz_data, "application/gzip")},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "restored"
        mock_restore.assert_called_once()

    def test_restore_postgresql_runtime_error(self, admin_client):
        """POST /api/admin/backup/restore returns 500 when psql command fails."""
        gz_data = gzip.compress(b"-- PostgreSQL dump\n")

        with (
            patch("app.config.settings") as mock_settings,
            patch("app.tasks.backup_tasks._restore_postgresql", side_effect=RuntimeError("psql failed")),
        ):
            mock_settings.database_url = "postgresql://user:pass@localhost/testdb"
            resp = admin_client.post(
                "/api/admin/backup/restore",
                files={"file": ("backup.pgsql.gz", gz_data, "application/gzip")},
            )
        assert resp.status_code == 500

    def test_restore_postgresql_missing_binary(self, admin_client):
        """POST /api/admin/backup/restore returns 500 when psql binary is missing."""
        gz_data = gzip.compress(b"-- PostgreSQL dump\n")

        with (
            patch("app.config.settings") as mock_settings,
            patch("app.tasks.backup_tasks._restore_postgresql", side_effect=FileNotFoundError("psql not found")),
        ):
            mock_settings.database_url = "postgresql://user:pass@localhost/testdb"
            resp = admin_client.post(
                "/api/admin/backup/restore",
                files={"file": ("backup.pgsql.gz", gz_data, "application/gzip")},
            )
        assert resp.status_code == 500

    def test_restore_unsupported_backend(self, admin_client):
        """POST /api/admin/backup/restore returns 400 for an unsupported database backend."""
        gz_data = gzip.compress(b"-- some dump\n")

        with patch("app.config.settings") as mock_settings:
            mock_settings.database_url = "mssql+pyodbc://user:pass@server/db"
            resp = admin_client.post(
                "/api/admin/backup/restore",
                files={"file": ("backup.sql.gz", gz_data, "application/gzip")},
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# View tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestBackupView:
    """Tests for the /admin/backup dashboard view."""

    def test_backup_dashboard_admin(self, admin_client):
        """GET /admin/backup returns 200 for admin users."""
        resp = admin_client.get("/admin/backup")
        assert resp.status_code == 200
        assert b"Backup" in resp.content

    def test_backup_dashboard_non_admin_redirect(self, non_admin_client):
        """GET /admin/backup redirects non-admin users."""
        resp = non_admin_client.get("/admin/backup", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_backup_dashboard_unauthenticated(self):
        """GET /admin/backup redirects unauthenticated users."""
        with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
            resp = client.get("/admin/backup", follow_redirects=False)
        assert resp.status_code in (302, 303)
