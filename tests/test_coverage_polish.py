"""
Coverage polish tests targeting specific uncovered lines/branches
in files listed in the 90%+ coverage push issue.

Each test class maps to a single source module.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from dropbox.exceptions import ApiError


# ---------------------------------------------------------------------------
# app/tasks/upload_to_dropbox.py  (88 % → 95 %+)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestDropboxClientGenericException:
    """Cover the generic except block in get_dropbox_client (lines 100-102)."""

    @patch("app.tasks.upload_to_dropbox.dropbox.Dropbox")
    @patch("app.tasks.upload_to_dropbox.settings")
    def test_generic_exception_during_client_creation(self, mock_settings, mock_dropbox):
        """Non-AuthError exception propagates from get_dropbox_client."""
        from app.tasks.upload_to_dropbox import get_dropbox_client

        mock_settings.dropbox_app_key = "key"
        mock_settings.dropbox_app_secret = "secret"
        mock_settings.dropbox_refresh_token = "token"

        mock_dropbox.side_effect = RuntimeError("network failure")

        with pytest.raises(RuntimeError, match="network failure"):
            get_dropbox_client()


@pytest.mark.unit
class TestDropboxCheckExistsInDropbox:
    """Cover check_exists_in_dropbox inner function (lines 155-161)."""

    @patch("app.tasks.upload_to_dropbox.get_unique_filename")
    @patch("app.tasks.upload_to_dropbox.extract_remote_path")
    @patch("app.tasks.upload_to_dropbox.get_dropbox_client")
    @patch("app.tasks.upload_to_dropbox.log_task_progress")
    @patch("app.tasks.upload_to_dropbox.settings")
    def test_check_exists_returns_true(
        self, mock_settings, mock_log, mock_client_fn, mock_extract, mock_unique, tmp_path
    ):
        """When files_get_metadata succeeds, check_exists returns True."""
        from app.tasks.upload_to_dropbox import upload_to_dropbox

        mock_settings.dropbox_app_key = "key"
        mock_settings.dropbox_app_secret = "secret"
        mock_settings.dropbox_refresh_token = "token"
        mock_settings.dropbox_folder = "/uploads"
        mock_settings.workdir = str(tmp_path)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"small file")

        mock_dbx = Mock()
        mock_client_fn.return_value = mock_dbx
        mock_extract.return_value = "uploads/test.pdf"

        # Capture the check_exists callback passed to get_unique_filename
        def capture_callback(path, check_fn):
            # Exercise check_exists path where file exists (returns True)
            assert check_fn(path) is True
            # Exercise check_exists path where file doesn't exist (returns False)
            not_found_error = Mock()
            not_found_error.is_path.return_value = True
            not_found_error.get_path.return_value.is_not_found.return_value = True
            mock_dbx.files_get_metadata.side_effect = ApiError("req-id", not_found_error, "not found", "header")
            assert check_fn(path) is False
            # Exercise check_exists path where ApiError is NOT not_found (re-raises)
            other_error = Mock()
            other_error.is_path.return_value = False
            mock_dbx.files_get_metadata.side_effect = ApiError("req-id", other_error, "other", "header")
            with pytest.raises(ApiError):
                check_fn(path)
            # Reset side effect for the actual upload
            mock_dbx.files_get_metadata.side_effect = None
            return path

        mock_unique.side_effect = capture_callback

        result = upload_to_dropbox.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()
        assert result["status"] == "Completed"


@pytest.mark.unit
class TestDropboxUnexpectedExceptionHandler:
    """Cover generic except block in upload_to_dropbox (lines 219-223)."""

    @patch("app.tasks.upload_to_dropbox.get_dropbox_client")
    @patch("app.tasks.upload_to_dropbox.log_task_progress")
    @patch("app.tasks.upload_to_dropbox.settings")
    def test_unexpected_exception_during_upload(self, mock_settings, mock_log, mock_client, tmp_path):
        """Non-Auth/Non-Api exception is caught by the generic handler."""
        from app.tasks.upload_to_dropbox import upload_to_dropbox

        mock_settings.dropbox_app_key = "key"
        mock_settings.dropbox_app_secret = "secret"
        mock_settings.dropbox_refresh_token = "token"
        mock_settings.dropbox_folder = "/uploads"
        mock_settings.workdir = str(tmp_path)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        # Raise a generic exception (not AuthError, not ApiError)
        mock_client.side_effect = RuntimeError("Something unexpected")

        with pytest.raises(Exception, match="Unexpected error"):
            upload_to_dropbox.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()


# ---------------------------------------------------------------------------
# app/tasks/rotate_pdf_pages.py  (91 % → 95 %+)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestDetermineRotationAngle:
    """Cover edge cases in determine_rotation_angle (line 29 & small angles)."""

    def test_very_small_angle_returns_zero(self):
        """Angles < 1° should return 0 (no rotation)."""
        from app.tasks.rotate_pdf_pages import determine_rotation_angle

        assert determine_rotation_angle(0.5) == 0

    def test_angle_close_to_360_returns_zero(self):
        """Angles close to 360° should return 0."""
        from app.tasks.rotate_pdf_pages import determine_rotation_angle

        assert determine_rotation_angle(359.5) == 0

    def test_negative_angle(self):
        """Negative angles should be normalised correctly."""
        from app.tasks.rotate_pdf_pages import determine_rotation_angle

        # -90 should normalise to 270 → rotation = (360-270)%360 = 90
        result = determine_rotation_angle(-90)
        assert result == 90

    def test_angle_45_rounds_to_nearest_90(self):
        """Non-standard angle rounds to nearest 90° multiple."""
        from app.tasks.rotate_pdf_pages import determine_rotation_angle

        # 45° rounds to 0° → rotation_value = (360-0)%360 = 0
        result = determine_rotation_angle(45)
        assert result == 0

    def test_angle_near_90(self):
        """Angle close to 90° should snap to 90°."""
        from app.tasks.rotate_pdf_pages import determine_rotation_angle

        # 88° is within ±5° of 90 → rotation = (360-90)%360 = 270
        result = determine_rotation_angle(88)
        assert result == 270

    def test_angle_near_180(self):
        """Angle close to 180° should snap to 180°."""
        from app.tasks.rotate_pdf_pages import determine_rotation_angle

        result = determine_rotation_angle(182)
        assert result == 180


@pytest.mark.unit
class TestRotatePdfPagesEdgeCases:
    """Cover rotate_pdf_pages edge cases: invalid data, small angles, no rotations."""

    @patch("app.tasks.rotate_pdf_pages.extract_metadata_with_gpt")
    @patch("app.tasks.rotate_pdf_pages.log_task_progress")
    @patch("app.tasks.rotate_pdf_pages.settings")
    def test_invalid_rotation_data_keys(self, mock_settings, mock_log, mock_extract, tmp_path):
        """Invalid rotation data keys/values trigger warning and are skipped (lines 94-95)."""
        from app.tasks.rotate_pdf_pages import rotate_pdf_pages

        workdir = tmp_path / "tmp"
        workdir.mkdir()
        mock_settings.workdir = str(tmp_path)

        pdf_path = workdir / "test.pdf"
        pdf_path.write_bytes(_minimal_pdf())

        mock_extract.delay = Mock()

        result = rotate_pdf_pages.apply(
            args=["test.pdf", "some text"],
            kwargs={"rotation_data": {"not_a_number": "invalid", 0: 0}, "file_id": 1},
        ).get()
        # With only invalid keys and a zero-angle, no rotation needed
        assert result["status"] == "no_rotation_needed"

    @patch("app.tasks.rotate_pdf_pages.extract_metadata_with_gpt")
    @patch("app.tasks.rotate_pdf_pages.log_task_progress")
    @patch("app.tasks.rotate_pdf_pages.settings")
    def test_rotation_angle_determined_as_zero(self, mock_settings, mock_log, mock_extract, tmp_path):
        """Page has rotation data but determine_rotation_angle returns 0 (line 144)."""
        from app.tasks.rotate_pdf_pages import rotate_pdf_pages

        workdir = tmp_path / "tmp"
        workdir.mkdir()
        mock_settings.workdir = str(tmp_path)

        pdf_path = workdir / "test.pdf"
        pdf_path.write_bytes(_minimal_pdf())

        mock_extract.delay = Mock()

        # Angle of 0.5° normalises to < 1° → rotation_angle = 0
        result = rotate_pdf_pages.apply(
            args=["test.pdf", "some text"],
            kwargs={"rotation_data": {0: 0.5}, "file_id": 1},
        ).get()
        # Rotation detected but not applied → "no_rotation_needed" with empty applied_rotations
        assert result["status"] == "no_rotation_needed"
        assert result["applied_rotations"] == {}

    @patch("app.tasks.rotate_pdf_pages.extract_metadata_with_gpt")
    @patch("app.tasks.rotate_pdf_pages.log_task_progress")
    @patch("app.tasks.rotate_pdf_pages.settings")
    def test_successful_rotation(self, mock_settings, mock_log, mock_extract, tmp_path):
        """Verify that a real rotation is applied to the PDF."""
        from app.tasks.rotate_pdf_pages import rotate_pdf_pages

        workdir = tmp_path / "tmp"
        workdir.mkdir()
        mock_settings.workdir = str(tmp_path)

        pdf_path = workdir / "test.pdf"
        pdf_path.write_bytes(_minimal_pdf())

        mock_extract.delay = Mock()

        result = rotate_pdf_pages.apply(
            args=["test.pdf", "some text"],
            kwargs={"rotation_data": {0: 90}, "file_id": 1},
        ).get()
        assert result["status"] == "rotated"
        assert "0" in result["applied_rotations"]


# ---------------------------------------------------------------------------
# app/tasks/convert_to_pdf.py  (91 % → 95 %+)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestConvertToPdfDetection:
    """Cover detection helper edge cases."""

    def test_detect_extension_filetype_fallback(self, tmp_path):
        """Cover _detect_extension filetype.guess branch (line 97-99)."""
        from app.tasks.convert_to_pdf import _detect_extension

        # Create a file with no extension and no puremagic match
        unknown_file = tmp_path / "noext"
        unknown_file.write_bytes(b"\x00" * 100)

        with (
            patch("app.tasks.convert_to_pdf.puremagic.from_file", side_effect=__import__("puremagic").PureError),
            patch("app.tasks.convert_to_pdf.filetype.guess") as mock_guess,
        ):
            mock_result = Mock()
            mock_result.extension = "bin"
            mock_guess.return_value = mock_result
            ext = _detect_extension(str(unknown_file), None, None)
            assert ext == ".bin"

    def test_detect_extension_returns_empty(self, tmp_path):
        """Cover _detect_extension returning empty string when nothing matches."""
        from app.tasks.convert_to_pdf import _detect_extension

        unknown_file = tmp_path / "noext"
        unknown_file.write_bytes(b"\x00" * 100)

        with (
            patch("app.tasks.convert_to_pdf.puremagic.from_file", side_effect=__import__("puremagic").PureError),
            patch("app.tasks.convert_to_pdf.filetype.guess", return_value=None),
        ):
            ext = _detect_extension(str(unknown_file), None, None)
            assert ext == ""

    @patch("app.tasks.convert_to_pdf.requests")
    @patch("app.tasks.convert_to_pdf.process_document")
    @patch("app.tasks.convert_to_pdf.log_task_progress")
    def test_fallback_conversion_for_unknown_mime(self, mock_log, mock_process, mock_requests, tmp_path):
        """Cover the else/fallback branch at lines 300-304."""
        test_file = tmp_path / "unknown.xyz"
        test_file.write_bytes(b"random content")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF-1.4 fake"
        mock_requests.post.return_value = mock_response

        mock_process.delay = Mock()

        with patch("app.tasks.convert_to_pdf.settings") as mock_settings:
            mock_settings.gotenberg_url = "http://localhost:3000"
            mock_settings.http_request_timeout = 30

            with (
                patch("app.tasks.convert_to_pdf._detect_mime_type", return_value=("application/octet-stream", None)),
                patch("app.tasks.convert_to_pdf._detect_extension", return_value=".xyz"),
            ):
                from app.tasks.convert_to_pdf import convert_to_pdf

                result = convert_to_pdf.apply(args=[str(test_file)]).get()
                expected_pdf = str(tmp_path / "unknown.pdf")
                assert result == expected_pdf

    @patch("app.tasks.convert_to_pdf.requests")
    @patch("app.tasks.convert_to_pdf.process_document")
    @patch("app.tasks.convert_to_pdf.log_task_progress")
    def test_gotenberg_non_200_response(self, mock_log, mock_process, mock_requests, tmp_path):
        """Cover the non-200 status code branch."""
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"test content")

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_requests.post.return_value = mock_response

        with patch("app.tasks.convert_to_pdf.settings") as mock_settings:
            mock_settings.gotenberg_url = "http://localhost:3000"
            mock_settings.http_request_timeout = 30

            with (
                patch("app.tasks.convert_to_pdf._detect_mime_type", return_value=("application/octet-stream", None)),
                patch("app.tasks.convert_to_pdf._detect_extension", return_value=".xyz"),
            ):
                from app.tasks.convert_to_pdf import convert_to_pdf

                result = convert_to_pdf.apply(args=[str(test_file)]).get()
                assert result is None

    @patch("app.tasks.convert_to_pdf.requests")
    @patch("app.tasks.convert_to_pdf.process_document")
    @patch("app.tasks.convert_to_pdf.log_task_progress")
    def test_no_mime_type_and_no_extension(self, mock_log, mock_process, mock_requests, tmp_path):
        """Cover the branch where both mime_type and file_ext are empty."""
        test_file = tmp_path / "noext"
        test_file.write_bytes(b"test content")

        with patch("app.tasks.convert_to_pdf.settings") as mock_settings:
            mock_settings.gotenberg_url = "http://localhost:3000"
            mock_settings.http_request_timeout = 30

            mock_self = MagicMock()
            mock_self.request.id = "task-notype"

            with (
                patch("app.tasks.convert_to_pdf._detect_mime_type", return_value=(None, None)),
                patch("app.tasks.convert_to_pdf._detect_extension", return_value=""),
            ):
                from app.tasks.convert_to_pdf import convert_to_pdf

                result = convert_to_pdf.__wrapped__(mock_self, str(test_file))
                assert result is None

    def test_detect_mime_type_from_magic_filetype_fallback(self, tmp_path):
        """Cover _detect_mime_type_from_magic filetype.guess fallback (lines 36-39)."""
        from app.tasks.convert_to_pdf import _detect_mime_type_from_magic

        test_file = tmp_path / "testfile"
        test_file.write_bytes(b"\x00" * 100)

        with patch("app.tasks.convert_to_pdf.puremagic.from_file", return_value=[]):
            with patch("app.tasks.convert_to_pdf.filetype.guess") as mock_guess:
                mock_result = Mock()
                mock_result.mime = "application/octet-stream"
                mock_guess.return_value = mock_result
                result = _detect_mime_type_from_magic(str(test_file))
                assert result == "application/octet-stream"

    def test_detect_mime_type_from_magic_returns_none(self, tmp_path):
        """Cover _detect_mime_type_from_magic returning None."""
        from app.tasks.convert_to_pdf import _detect_mime_type_from_magic

        test_file = tmp_path / "testfile"
        test_file.write_bytes(b"\x00" * 100)

        with (
            patch("app.tasks.convert_to_pdf.puremagic.from_file", return_value=[]),
            patch("app.tasks.convert_to_pdf.filetype.guess", return_value=None),
        ):
            result = _detect_mime_type_from_magic(str(test_file))
            assert result is None

    def test_detect_mime_type_original_filename_fallback(self, tmp_path):
        """Cover _detect_mime_type using original_filename fallback (lines 58-62)."""
        from app.tasks.convert_to_pdf import _detect_mime_type

        # File with no extension
        test_file = tmp_path / "noext"
        test_file.write_bytes(b"content")

        # Original filename has extension
        mime, enc = _detect_mime_type(str(test_file), "document.pdf")
        assert mime == "application/pdf"

    def test_build_filename_with_extension(self, tmp_path):
        """Cover _build_filename when original has extension."""
        from app.tasks.convert_to_pdf import _build_filename

        result = _build_filename("/tmp/uuid123", "report.docx", ".docx")
        assert result == "report.docx"

    def test_build_filename_adds_extension(self, tmp_path):
        """Cover _build_filename when base name needs extension."""
        from app.tasks.convert_to_pdf import _build_filename

        result = _build_filename("/tmp/uuid123", None, ".pdf")
        assert result == "uuid123.pdf"


# ---------------------------------------------------------------------------
# app/utils/file_queries.py  (93 % → 95 %+)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestFileQueriesDuplicateFilter:
    """Cover the 'duplicate' status filter (line 122)."""

    def test_apply_status_filter_duplicate(self, db_session):
        """Filtering by 'duplicate' returns only is_duplicate=True files."""
        from app.models import FileRecord
        from app.utils.file_queries import apply_status_filter

        # Create a normal file and a duplicate file
        normal = FileRecord(
            filehash="normal",
            original_filename="normal.pdf",
            local_filename="/tmp/normal.pdf",
            file_size=100,
            mime_type="application/pdf",
        )
        dup = FileRecord(
            filehash="dup",
            original_filename="dup.pdf",
            local_filename="/tmp/dup.pdf",
            file_size=100,
            mime_type="application/pdf",
            is_duplicate=True,
        )
        db_session.add_all([normal, dup])
        db_session.commit()

        query = db_session.query(FileRecord)
        results = apply_status_filter(query, db_session, "duplicate").all()

        assert len(results) == 1
        assert results[0].is_duplicate is True
        assert results[0].filehash == "dup"


@pytest.mark.unit
class TestFileQueriesDeduplicationEnabled:
    """Cover the enable_deduplication branch (line 81)."""

    @patch("app.config.settings")
    def test_deduplication_enabled_adds_check_for_duplicates(self, mock_settings, db_session):
        """When deduplication is enabled, check_for_duplicates is a real step."""
        from app.models import FileProcessingStep, FileRecord
        from app.utils.file_queries import apply_status_filter

        mock_settings.enable_deduplication = True

        file1 = FileRecord(
            filehash="h1",
            original_filename="f1.pdf",
            local_filename="/tmp/f1.pdf",
            file_size=100,
            mime_type="application/pdf",
        )
        db_session.add(file1)
        db_session.flush()

        step = FileProcessingStep(
            file_id=file1.id,
            step_name="check_for_duplicates",
            status="success",
        )
        db_session.add(step)
        db_session.commit()

        query = db_session.query(FileRecord)
        results = apply_status_filter(query, db_session, "completed").all()
        assert len(results) == 1


# ---------------------------------------------------------------------------
# app/api/url_upload.py  (91 % → 95 %+)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestURLUploadAdditionalCoverage:
    """Cover remaining branches in url_upload."""

    def test_validate_url_safety_invalid_scheme(self):
        """Cover scheme rejection in validate_url_safety (line 86)."""
        from fastapi import HTTPException

        from app.api.url_upload import validate_url_safety

        with pytest.raises(HTTPException) as exc_info:
            validate_url_safety("ftp://example.com/file.pdf")
        assert exc_info.value.status_code == 400
        assert "HTTP" in exc_info.value.detail

    def test_validate_url_safety_blocks_gcp_metadata(self):
        """Cover metadata endpoint blocking for GCP (line 106)."""
        from fastapi import HTTPException

        from app.api.url_upload import validate_url_safety

        with pytest.raises(HTTPException) as exc_info:
            validate_url_safety("http://metadata.google.internal/computeMetadata/v1/")
        assert exc_info.value.status_code == 400

    def test_is_private_ip_unresolvable_hostname(self):
        """Cover DNS resolution failure branch (lines 67-72)."""
        import socket as _socket

        from app.api.url_upload import is_private_ip

        with patch("socket.getaddrinfo", side_effect=_socket.gaierror("nope")):
            result = is_private_ip("nonexistent.invalid.hostname.test")
            assert result is False

    def test_is_private_ip_hostname_resolves_to_private(self):
        """Cover branch where hostname resolves to a private IP (line 64-65)."""
        from app.api.url_upload import is_private_ip

        with patch("socket.getaddrinfo") as mock_gai:
            # Simulate resolving to a private IP
            mock_gai.return_value = [
                (2, 1, 6, "", ("192.168.1.1", 0)),
            ]
            result = is_private_ip("evil.internal.corp")
            assert result is True

    def test_validate_file_type_no_content_type_no_extension(self):
        """Cover the path where both content_type and extension are empty."""
        from app.api.url_upload import validate_file_type

        assert validate_file_type("", "noextfile") is False

    @patch("app.api.url_upload.requests.get")
    @patch("app.api.url_upload.process_document")
    def test_process_url_empty_url_path(self, mock_process, mock_get, client):
        """URL with empty path defaults to 'download' filename (line 197-202)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf", "Content-Length": "50"}
        mock_response.iter_content = Mock(return_value=[b"PDF"])
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        mock_task = Mock()
        mock_task.id = "task-empty-path"
        mock_process.delay.return_value = mock_task

        response = client.post("/api/process-url", json={"url": "https://example.com/"})
        assert response.status_code == 200

    def test_validate_url_safety_blocks_aws_link_local(self):
        """Cover metadata endpoint 169.254.169.253 (line 103)."""
        from fastapi import HTTPException

        from app.api.url_upload import validate_url_safety

        with pytest.raises(HTTPException) as exc_info:
            validate_url_safety("http://169.254.169.253/something")
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# app/main.py  (92 % → 95 %+)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestMainAppCoverage:
    """Cover remaining branches in app/main.py."""

    @pytest.mark.asyncio
    async def test_lifespan_no_config_issues(self):
        """Cover the branch where config has no issues (line 92)."""
        with (
            patch("app.database.init_db"),
            patch("app.database.SessionLocal") as mock_session_cls,
            patch("app.utils.config_loader.load_settings_from_db"),
            patch("app.utils.config_validator.dump_all_settings"),
            patch(
                "app.main.check_all_configs",
                return_value={"email": [], "storage": {}},
            ),
            patch("app.main.init_apprise"),
            patch("app.main.notify_startup"),
            patch("app.main.notify_shutdown"),
            patch("app.utils.ocr_language_manager.ensure_ocr_languages_async"),
        ):
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db

            import logging as _logging

            from app.main import app, lifespan

            with patch.object(_logging, "info") as mock_info:
                async with lifespan(app):
                    pass

                # Verify "valid configuration" was logged
                calls = [str(c) for c in mock_info.call_args_list]
                assert any("valid configuration" in c for c in calls)

    @pytest.mark.asyncio
    async def test_lifespan_with_storage_issues(self):
        """Cover the branch where storage config has issues (line 89-90)."""
        with (
            patch("app.database.init_db"),
            patch("app.database.SessionLocal") as mock_session_cls,
            patch("app.utils.config_loader.load_settings_from_db"),
            patch("app.utils.config_validator.dump_all_settings"),
            patch("app.main.check_all_configs") as mock_check,
            patch("app.main.init_apprise"),
            patch("app.main.notify_startup"),
            patch("app.main.notify_shutdown"),
            patch("app.utils.ocr_language_manager.ensure_ocr_languages_async"),
        ):
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            mock_check.return_value = {
                "email": [],
                "storage": {"s3": ["Missing bucket name"]},
            }

            import logging as _logging

            from app.main import app, lifespan

            with patch.object(_logging, "warning") as mock_warning:
                async with lifespan(app):
                    pass

                # Should log warning about config issues
                calls = [str(c) for c in mock_warning.call_args_list]
                assert any("configuration issues" in c for c in calls)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _minimal_pdf() -> bytes:
    """Return bytes for a minimal valid PDF with one page."""
    return b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
>>
endobj
xref
0 4
0000000000 65535 f\x20
0000000009 00000 n\x20
0000000058 00000 n\x20
0000000115 00000 n\x20
trailer
<<
/Size 4
/Root 1 0 R
>>
startxref
197
%%EOF
"""
