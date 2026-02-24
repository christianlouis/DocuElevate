"""
Tests for app/views/filemanager.py module.

Tests all helper functions and route handlers for the admin file manager.
"""

import base64
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from itsdangerous import TimestampSigner

from app.models import FileRecord

TEST_SESSION_SECRET = "test_secret_key_for_testing_must_be_at_least_32_characters_long"


def _make_admin_session_cookie() -> str:
    """Create a properly signed admin session cookie for tests."""
    session_data = {"user": {"id": "admin", "is_admin": True}}
    signer = TimestampSigner(TEST_SESSION_SECRET)
    data = base64.b64encode(json.dumps(session_data).encode()).decode("utf-8")
    return signer.sign(data).decode("utf-8")


@pytest.mark.unit
class TestFormatSize:
    """Tests for _format_size helper function."""

    def test_formats_bytes(self):
        """Test formatting bytes."""
        from app.views.filemanager import _format_size

        assert _format_size(512) == "512.0 B"

    def test_formats_kilobytes(self):
        """Test formatting kilobytes."""
        from app.views.filemanager import _format_size

        assert _format_size(1024) == "1.0 KB"

    def test_formats_megabytes(self):
        """Test formatting megabytes."""
        from app.views.filemanager import _format_size

        result = _format_size(1024 * 1024)
        assert result == "1.0 MB"

    def test_formats_gigabytes(self):
        """Test formatting gigabytes."""
        from app.views.filemanager import _format_size

        result = _format_size(1024 * 1024 * 1024)
        assert result == "1.0 GB"

    def test_formats_terabytes(self):
        """Test formatting terabytes."""
        from app.views.filemanager import _format_size

        result = _format_size(1024 * 1024 * 1024 * 1024)
        assert result == "1.0 TB"

    def test_formats_zero_bytes(self):
        """Test formatting zero bytes."""
        from app.views.filemanager import _format_size

        assert _format_size(0) == "0.0 B"

    def test_formats_partial_kilobytes(self):
        """Test formatting partial kilobytes."""
        from app.views.filemanager import _format_size

        result = _format_size(1500)
        assert "KB" in result


@pytest.mark.unit
class TestSafePath:
    """Tests for _safe_path helper function."""

    def test_valid_empty_rel_path(self, tmp_path):
        """Test valid empty relative path returns workdir."""
        from app.views.filemanager import _safe_path

        result = _safe_path(str(tmp_path), "")
        assert result == tmp_path.resolve()

    def test_valid_nested_path(self, tmp_path):
        """Test valid nested relative path."""
        from app.views.filemanager import _safe_path

        subdir = tmp_path / "subdir"
        subdir.mkdir()
        result = _safe_path(str(tmp_path), "subdir")
        assert result == subdir.resolve()

    def test_traversal_attempt_raises(self, tmp_path):
        """Test that path traversal raises ValueError."""
        from app.views.filemanager import _safe_path

        with pytest.raises(ValueError, match="Path traversal detected"):
            _safe_path(str(tmp_path), "../../etc/passwd")

    def test_traversal_with_dots_raises(self, tmp_path):
        """Test that .. in path raises ValueError when escaping workdir."""
        from app.views.filemanager import _safe_path

        with pytest.raises(ValueError, match="Path traversal detected"):
            _safe_path(str(tmp_path), "../outside")

    def test_valid_deep_nested_path(self, tmp_path):
        """Test valid deeply nested path."""
        from app.views.filemanager import _safe_path

        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        result = _safe_path(str(tmp_path), "a/b/c")
        assert result == deep.resolve()


@pytest.mark.unit
class TestFileIcon:
    """Tests for _file_icon helper function."""

    def test_directory_icon(self):
        """Test directory returns folder icon."""
        from app.views.filemanager import _file_icon

        result = _file_icon("", True)
        assert "fa-folder" in result

    def test_image_icon(self):
        """Test image MIME type returns image icon."""
        from app.views.filemanager import _file_icon

        result = _file_icon("image/jpeg", False)
        assert "fa-file-image" in result

    def test_pdf_icon(self):
        """Test PDF MIME type returns PDF icon."""
        from app.views.filemanager import _file_icon

        result = _file_icon("application/pdf", False)
        assert "fa-file-pdf" in result

    def test_text_icon(self):
        """Test text MIME type returns text icon."""
        from app.views.filemanager import _file_icon

        result = _file_icon("text/plain", False)
        assert "fa-file-alt" in result

    def test_json_icon(self):
        """Test JSON MIME type returns code icon."""
        from app.views.filemanager import _file_icon

        result = _file_icon("application/json", False)
        assert "fa-file-code" in result

    def test_default_icon(self):
        """Test unknown MIME type returns default file icon."""
        from app.views.filemanager import _file_icon

        result = _file_icon("application/octet-stream", False)
        assert "fa-file" in result

    def test_html_text_icon(self):
        """Test HTML (text/) MIME type returns text icon."""
        from app.views.filemanager import _file_icon

        result = _file_icon("text/html", False)
        assert "fa-file-alt" in result


@pytest.mark.unit
class TestDbPathSet:
    """Tests for _db_path_set helper function."""

    def test_empty_database(self, db_session):
        """Test with empty database returns empty set."""
        from app.views.filemanager import _db_path_set

        result = _db_path_set(db_session)
        assert isinstance(result, set)
        assert len(result) == 0

    def test_with_file_records(self, db_session, tmp_path):
        """Test with file records returns their paths."""
        from app.views.filemanager import _db_path_set

        test_file = tmp_path / "test.pdf"
        test_file.touch()

        record = FileRecord(
            filehash="abc123",
            original_filename="test.pdf",
            local_filename=str(test_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(record)
        db_session.commit()

        result = _db_path_set(db_session)
        assert str(test_file.resolve()) in result

    def test_with_null_paths(self, db_session):
        """Test that null paths are skipped (uses empty strings instead of None)."""
        from app.views.filemanager import _db_path_set

        # Use a real file path but with empty original and processed paths
        record = FileRecord(
            filehash="def456",
            original_filename="test.pdf",
            local_filename="/tmp/test_def456.pdf",
            original_file_path=None,
            processed_file_path=None,
            file_size=0,
            mime_type="application/pdf",
        )
        db_session.add(record)
        db_session.commit()

        result = _db_path_set(db_session)
        # Only local_filename (non-null) should be in the set
        assert len(result) == 1


@pytest.mark.unit
class TestScanDir:
    """Tests for _scan_dir helper function."""

    def test_empty_directory(self, tmp_path):
        """Test scanning empty directory."""
        from app.views.filemanager import _scan_dir

        result = _scan_dir(tmp_path, tmp_path, set())
        assert result == []

    def test_directory_with_file(self, tmp_path):
        """Test scanning directory with a file."""
        from app.views.filemanager import _scan_dir

        test_file = tmp_path / "test.pdf"
        test_file.write_text("content")

        result = _scan_dir(tmp_path, tmp_path, set())
        assert len(result) == 1
        assert result[0]["name"] == "test.pdf"
        assert result[0]["is_dir"] is False
        assert result[0]["db_status"] == "orphan"

    def test_file_in_db(self, tmp_path):
        """Test that file in DB set gets in_db status."""
        from app.views.filemanager import _scan_dir

        test_file = tmp_path / "tracked.pdf"
        test_file.write_text("content")

        db_paths = {str(test_file.resolve())}
        result = _scan_dir(tmp_path, tmp_path, db_paths)
        assert len(result) == 1
        assert result[0]["db_status"] == "in_db"

    def test_directory_entry(self, tmp_path):
        """Test that subdirectory has empty db_status."""
        from app.views.filemanager import _scan_dir

        subdir = tmp_path / "subdir"
        subdir.mkdir()

        result = _scan_dir(tmp_path, tmp_path, set())
        dirs = [e for e in result if e["is_dir"]]
        assert len(dirs) == 1
        assert dirs[0]["db_status"] == ""
        assert dirs[0]["size"] == ""

    def test_directories_sorted_first(self, tmp_path):
        """Test that directories come before files."""
        from app.views.filemanager import _scan_dir

        (tmp_path / "zfile.txt").write_text("content")
        (tmp_path / "adir").mkdir()

        result = _scan_dir(tmp_path, tmp_path, set())
        assert result[0]["is_dir"] is True
        assert result[1]["is_dir"] is False

    def test_includes_mime_type_and_icon(self, tmp_path):
        """Test that mime type and icon are set."""
        from app.views.filemanager import _scan_dir

        (tmp_path / "doc.pdf").write_text("pdf content")

        result = _scan_dir(tmp_path, tmp_path, set())
        assert result[0]["mime_type"] == "application/pdf"
        assert "fa-file-pdf" in result[0]["icon"]


@pytest.mark.unit
class TestWalkAllFiles:
    """Tests for _walk_all_files helper function."""

    def test_empty_directory(self, tmp_path):
        """Test walking empty directory."""
        from app.views.filemanager import _walk_all_files

        result = _walk_all_files(tmp_path, set())
        assert result == []

    def test_with_files(self, tmp_path):
        """Test walking directory with files."""
        from app.views.filemanager import _walk_all_files

        (tmp_path / "file1.txt").write_text("content")
        (tmp_path / "file2.pdf").write_text("content")

        result = _walk_all_files(tmp_path, set())
        assert len(result) == 2
        names = {e["name"] for e in result}
        assert "file1.txt" in names
        assert "file2.pdf" in names

    def test_with_subdirectories(self, tmp_path):
        """Test that subdirectory entries are skipped (only files)."""
        from app.views.filemanager import _walk_all_files

        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.pdf").write_text("content")
        (tmp_path / "root.pdf").write_text("content")

        result = _walk_all_files(tmp_path, set())
        # Only files, not directories
        assert all(not e["is_dir"] for e in result)
        assert len(result) == 2

    def test_db_status_in_db(self, tmp_path):
        """Test that tracked files get in_db status."""
        from app.views.filemanager import _walk_all_files

        test_file = tmp_path / "tracked.pdf"
        test_file.write_text("content")

        db_paths = {str(test_file.resolve())}
        result = _walk_all_files(tmp_path, db_paths)
        assert result[0]["db_status"] == "in_db"

    def test_db_status_orphan(self, tmp_path):
        """Test that untracked files get orphan status."""
        from app.views.filemanager import _walk_all_files

        (tmp_path / "orphan.pdf").write_text("content")

        result = _walk_all_files(tmp_path, set())
        assert result[0]["db_status"] == "orphan"


@pytest.mark.unit
class TestDbRecords:
    """Tests for _db_records helper function."""

    def test_empty_database(self, db_session, tmp_path):
        """Test with empty database."""
        from app.views.filemanager import _db_records

        result = _db_records(db_session, tmp_path)
        assert result == []

    def test_with_file_record(self, db_session, tmp_path):
        """Test with file record in database."""
        from app.views.filemanager import _db_records

        test_file = tmp_path / "test.pdf"
        test_file.write_text("content")

        record = FileRecord(
            filehash="abc123",
            original_filename="test.pdf",
            local_filename=str(test_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(record)
        db_session.commit()

        result = _db_records(db_session, tmp_path)
        assert len(result) == 1
        assert result[0]["original_filename"] == "test.pdf"
        assert result[0]["health"] == "ok"

    def test_missing_file_marked_as_missing(self, db_session, tmp_path):
        """Test that files not on disk are marked as missing."""
        from app.views.filemanager import _db_records

        record = FileRecord(
            filehash="def456",
            original_filename="missing.pdf",
            local_filename="/nonexistent/path/missing.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(record)
        db_session.commit()

        result = _db_records(db_session, tmp_path)
        assert len(result) == 1
        assert result[0]["health"] == "missing"

    def test_null_file_size_shows_dash(self, db_session, tmp_path):
        """Test that zero file size and null mime_type show dashes."""
        from app.views.filemanager import _db_records

        # file_size=0 is falsy → shows "—"; mime_type=None also shows "—"
        record = FileRecord(
            filehash="ghi789",
            original_filename="test.pdf",
            local_filename="/tmp/test_ghi789.pdf",
            file_size=0,
            mime_type=None,
        )
        db_session.add(record)
        db_session.commit()

        result = _db_records(db_session, tmp_path)
        assert result[0]["file_size"] == "—"
        assert result[0]["mime_type"] == "—"

    def test_file_outside_workdir(self, db_session, tmp_path):
        """Test handling of file path outside workdir."""
        from app.views.filemanager import _db_records

        record = FileRecord(
            filehash="jkl012",
            original_filename="outside.pdf",
            local_filename="/completely/different/path/outside.pdf",
            file_size=512,
            mime_type="application/pdf",
        )
        db_session.add(record)
        db_session.commit()

        result = _db_records(db_session, tmp_path)
        assert len(result) == 1
        # Path outside workdir should use full path as rel
        assert result[0]["local"]["rel"] is not None
        assert result[0]["local"]["exists"] is False


@pytest.mark.integration
class TestFilemanagerRoute:
    """Integration tests for filemanager route."""

    def test_redirects_non_admin(self, client):
        """Test that non-admin users are redirected."""
        response = client.get("/admin/files", follow_redirects=False)
        # Without admin session, require_admin_access redirects to home
        assert response.status_code == 302

    def test_filesystem_view_with_admin_session(self, client):
        """Test filesystem view with admin session cookie."""
        client.cookies.set("session", _make_admin_session_cookie())
        response = client.get("/admin/files?view=filesystem", follow_redirects=False)
        assert response.status_code == 200

    def test_database_view_with_admin_session(self, client):
        """Test database view with admin session."""
        client.cookies.set("session", _make_admin_session_cookie())
        response = client.get("/admin/files?view=database", follow_redirects=False)
        assert response.status_code == 200

    def test_reconcile_view_with_admin_session(self, client):
        """Test reconcile view with admin session."""
        client.cookies.set("session", _make_admin_session_cookie())
        response = client.get("/admin/files?view=reconcile", follow_redirects=False)
        assert response.status_code == 200

    def test_path_traversal_blocked(self, client):
        """Test that path traversal is blocked."""
        client.cookies.set("session", _make_admin_session_cookie())
        response = client.get("/admin/files?view=filesystem&path=../../etc", follow_redirects=False)
        # Should still return 200 (blocked silently, falls back to workdir root)
        assert response.status_code == 200

    def test_nonexistent_path_falls_back_to_root(self, client):
        """Test that nonexistent path falls back to workdir root."""
        client.cookies.set("session", _make_admin_session_cookie())
        response = client.get("/admin/files?path=nonexistent_dir_xyz", follow_redirects=False)
        assert response.status_code == 200

    def test_with_breadcrumbs(self, client, tmp_path):
        """Test that breadcrumbs are generated for nested paths."""
        client.cookies.set("session", _make_admin_session_cookie())

        # Create a subdirectory in the actual workdir
        workdir = os.environ.get("WORKDIR", "/tmp")
        subdir = Path(workdir) / "testsubdir"
        subdir.mkdir(exist_ok=True)
        try:
            response = client.get("/admin/files?path=testsubdir", follow_redirects=False)
            assert response.status_code == 200
        finally:
            subdir.rmdir()


@pytest.mark.integration
class TestFilemanagerDownloadRoute:
    """Integration tests for filemanager download route."""

    def test_redirects_non_admin(self, client):
        """Test that non-admin users are redirected."""
        response = client.get("/admin/files/download?path=test.pdf", follow_redirects=False)
        assert response.status_code == 302

    def test_download_invalid_path_returns_400(self, client):
        """Test that invalid (traversal) path returns 400."""
        client.cookies.set("session", _make_admin_session_cookie())
        response = client.get("/admin/files/download?path=../../etc/passwd", follow_redirects=False)
        assert response.status_code == 400

    def test_download_nonexistent_file_returns_404(self, client):
        """Test that nonexistent file returns 404."""
        client.cookies.set("session", _make_admin_session_cookie())
        response = client.get("/admin/files/download?path=nonexistent_file_xyz.pdf", follow_redirects=False)
        assert response.status_code == 404

    def test_download_existing_file(self, client, tmp_path):
        """Test downloading an existing file."""
        client.cookies.set("session", _make_admin_session_cookie())

        # Create a file in the workdir
        workdir = os.environ.get("WORKDIR", "/tmp")
        test_file = Path(workdir) / "test_download_xyz.txt"
        test_file.write_text("test content")
        try:
            response = client.get("/admin/files/download?path=test_download_xyz.txt", follow_redirects=False)
            assert response.status_code == 200
        finally:
            test_file.unlink(missing_ok=True)


@pytest.mark.unit
class TestFilemanagerRouteUnit:
    """Unit tests for filemanager route handler."""

    @patch("app.views.filemanager.templates")
    @patch("app.views.filemanager.settings")
    @pytest.mark.asyncio
    async def test_filesystem_view_calls_scan_dir(self, mock_settings, mock_templates):
        """Test filesystem view calls _scan_dir."""
        from app.views.filemanager import filemanager

        mock_settings.workdir = "/tmp"
        mock_templates.TemplateResponse = MagicMock()

        mock_request = MagicMock()
        mock_request.query_params.get = MagicMock(
            side_effect=lambda key, default=None: "filesystem" if key == "view" else ""
        )
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}

        mock_db = MagicMock()
        mock_db.query.return_value.order_by.return_value.all.return_value = []
        mock_db.query.return_value.count.return_value = 0
        mock_db.query.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.all.return_value = []

        await filemanager(mock_request, mock_db)
        mock_templates.TemplateResponse.assert_called_once()

    @patch("app.views.filemanager.templates")
    @patch("app.views.filemanager.settings")
    @pytest.mark.asyncio
    async def test_database_view_calls_db_records(self, mock_settings, mock_templates):
        """Test database view calls _db_records."""
        from app.views.filemanager import filemanager

        mock_settings.workdir = "/tmp"
        mock_templates.TemplateResponse = MagicMock()

        mock_request = MagicMock()
        mock_request.query_params.get = MagicMock(
            side_effect=lambda key, default=None: "database" if key == "view" else ""
        )
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}

        mock_db = MagicMock()
        mock_db.query.return_value.order_by.return_value.all.return_value = []
        mock_db.query.return_value.count.return_value = 0
        mock_db.query.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.all.return_value = []

        await filemanager(mock_request, mock_db)
        mock_templates.TemplateResponse.assert_called_once()

    @patch("app.views.filemanager.templates")
    @patch("app.views.filemanager.settings")
    @pytest.mark.asyncio
    async def test_reconcile_view(self, mock_settings, mock_templates):
        """Test reconcile view builds orphan and ghost lists."""
        from app.views.filemanager import filemanager

        mock_settings.workdir = "/tmp"
        mock_templates.TemplateResponse = MagicMock()

        mock_request = MagicMock()
        mock_request.query_params.get = MagicMock(
            side_effect=lambda key, default=None: "reconcile" if key == "view" else ""
        )
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}

        mock_db = MagicMock()
        mock_db.query.return_value.order_by.return_value.all.return_value = []
        mock_db.query.return_value.count.return_value = 0
        mock_db.query.return_value.all.return_value = []

        await filemanager(mock_request, mock_db)
        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert "orphan_files" in context
        assert "ghost_records" in context

    @patch("app.views.filemanager.templates")
    @patch("app.views.filemanager.settings")
    @pytest.mark.asyncio
    async def test_path_traversal_falls_back_to_root(self, mock_settings, mock_templates):
        """Test that path traversal attempt falls back to workdir root."""
        from app.views.filemanager import filemanager

        mock_settings.workdir = "/tmp"
        mock_templates.TemplateResponse = MagicMock()

        mock_request = MagicMock()
        mock_request.query_params.get = MagicMock(
            side_effect=lambda key, default=None: "filesystem" if key == "view" else "../../etc"
        )
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}

        mock_db = MagicMock()
        mock_db.query.return_value.order_by.return_value.all.return_value = []
        mock_db.query.return_value.count.return_value = 0
        mock_db.query.return_value.all.return_value = []

        # Should not raise, falls back to workdir root
        await filemanager(mock_request, mock_db)
        mock_templates.TemplateResponse.assert_called_once()

    @patch("app.views.filemanager.templates")
    @patch("app.views.filemanager.settings")
    @pytest.mark.asyncio
    async def test_breadcrumbs_generated_for_nested_path(self, mock_settings, mock_templates, tmp_path):
        """Test that breadcrumbs are generated for nested paths."""
        from app.views.filemanager import filemanager

        # Create nested dir for a valid path
        nested = tmp_path / "level1" / "level2"
        nested.mkdir(parents=True)

        mock_settings.workdir = str(tmp_path)
        mock_templates.TemplateResponse = MagicMock()

        mock_request = MagicMock()
        mock_request.query_params.get = MagicMock(
            side_effect=lambda key, default=None: "filesystem" if key == "view" else "level1/level2"
        )
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}

        mock_db = MagicMock()
        mock_db.query.return_value.order_by.return_value.all.return_value = []
        mock_db.query.return_value.count.return_value = 0
        mock_db.query.return_value.all.return_value = []

        await filemanager(mock_request, mock_db)
        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert len(context["breadcrumbs"]) > 0


@pytest.mark.unit
class TestFilemanagerDownloadUnit:
    """Unit tests for filemanager_download route handler."""

    @pytest.mark.asyncio
    async def test_download_path_traversal_raises_400(self, tmp_path):
        """Test that path traversal in download raises 400."""
        from fastapi import HTTPException

        from app.views.filemanager import filemanager_download

        with patch("app.views.filemanager.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            mock_request = MagicMock()
            mock_request.query_params.get = MagicMock(return_value="../../etc/passwd")

            with pytest.raises(HTTPException) as exc_info:
                await filemanager_download(mock_request)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_download_nonexistent_file_raises_404(self, tmp_path):
        """Test that nonexistent file raises 404."""
        from fastapi import HTTPException

        from app.views.filemanager import filemanager_download

        with patch("app.views.filemanager.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            mock_request = MagicMock()
            mock_request.query_params.get = MagicMock(return_value="nonexistent.pdf")

            with pytest.raises(HTTPException) as exc_info:
                await filemanager_download(mock_request)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_download_directory_raises_404(self, tmp_path):
        """Test that trying to download a directory raises 404."""
        from fastapi import HTTPException

        from app.views.filemanager import filemanager_download

        subdir = tmp_path / "subdir"
        subdir.mkdir()

        with patch("app.views.filemanager.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            mock_request = MagicMock()
            mock_request.query_params.get = MagicMock(return_value="subdir")

            with pytest.raises(HTTPException) as exc_info:
                await filemanager_download(mock_request)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_download_valid_file_returns_file_response(self, tmp_path):
        """Test that valid file returns FileResponse."""
        from fastapi.responses import FileResponse

        from app.views.filemanager import filemanager_download

        test_file = tmp_path / "download_me.pdf"
        test_file.write_bytes(b"%PDF-1.4 content")

        with patch("app.views.filemanager.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            mock_request = MagicMock()
            mock_request.query_params.get = MagicMock(return_value="download_me.pdf")

            result = await filemanager_download(mock_request)
            assert isinstance(result, FileResponse)
            assert result.filename == "download_me.pdf"
