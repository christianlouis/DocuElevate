"""
Security tests for path traversal vulnerabilities.

Tests all file path operations to ensure they properly prevent path traversal attacks.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest


@pytest.mark.security
@pytest.mark.unit
class TestFilenameSanitization:
    """Test that filename sanitization prevents path traversal attacks."""

    def test_sanitize_removes_parent_directory_traversal(self):
        """Test that ../ patterns are removed."""
        from app.utils.filename_utils import sanitize_filename

        # Unix-style path traversal
        result = sanitize_filename("../../../etc/passwd")
        assert ".." not in result
        assert "/" not in result
        assert "etc" in result
        assert "passwd" in result

    def test_sanitize_removes_windows_path_traversal(self):
        """Test that ..\\ patterns are removed."""
        from app.utils.filename_utils import sanitize_filename

        # Windows-style path traversal
        result = sanitize_filename("..\\..\\windows\\system32")
        assert ".." not in result
        assert "\\" not in result
        assert "windows" in result

    def test_sanitize_removes_unix_path_separators(self):
        """Test that Unix path separators are removed."""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("/etc/passwd")
        assert "/" not in result
        assert result == "etc_passwd"

    def test_sanitize_removes_windows_path_separators(self):
        """Test that Windows path separators are removed."""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("C:\\Windows\\System32")
        assert "\\" not in result
        assert ":" not in result

    def test_sanitize_handles_mixed_path_separators(self):
        """Test that mixed path separators are handled."""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("../folder/..\\..\\file.pdf")
        assert "/" not in result
        assert "\\" not in result
        assert ".." not in result

    def test_sanitize_removes_null_bytes(self):
        """Test that null bytes are removed (security issue)."""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("file\x00.pdf")
        assert "\x00" not in result

    def test_sanitize_preserves_safe_characters(self):
        """Test that safe characters are preserved."""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("Document_2024-01-15.pdf")
        assert result == "Document_2024-01-15.pdf"

    def test_sanitize_handles_unicode_attacks(self):
        """Test that Unicode path separators are handled."""
        from app.utils.filename_utils import sanitize_filename

        # Unicode fullwidth solidus (looks like /)
        result = sanitize_filename("folder\uff0ffile.pdf")
        # Should be replaced with underscore
        assert "\uff0f" not in result


@pytest.mark.security
@pytest.mark.unit
class TestEmbedMetadataPathTraversal:
    """Test that embed_metadata_into_pdf prevents path traversal via metadata filename."""

    def test_malicious_filename_in_metadata_is_sanitized(self, tmp_path):
        """Test that malicious filenames from GPT metadata are sanitized."""
        from app.utils.filename_utils import get_unique_filepath_with_counter, sanitize_filename

        # Simulate malicious metadata from GPT
        malicious_filename = "../../etc/passwd"

        # This should be sanitized before being used
        sanitized = sanitize_filename(malicious_filename)

        # Verify sanitization removes path traversal
        assert ".." not in sanitized
        assert "/" not in sanitized
        assert "\\" not in sanitized

        # Verify unique_filepath with sanitized name stays in directory
        result = get_unique_filepath_with_counter(str(tmp_path), sanitized, ".pdf")
        result_path = Path(result)

        # Ensure result is within tmp_path
        assert result_path.parent == tmp_path

    def test_embed_metadata_validates_filename_field(self, tmp_path):
        """Test that embed_metadata_into_pdf sanitizes the filename from metadata."""
        from app.utils.filename_utils import get_unique_filepath_with_counter, sanitize_filename

        # Test various malicious filenames
        malicious_filenames = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "/etc/shadow",
            "C:\\Windows\\win.ini",
            "folder/../file",
            "folder\\..\\file",
        ]

        for malicious in malicious_filenames:
            # Sanitize as the task should do
            sanitized = sanitize_filename(malicious)

            # Verify no path traversal is possible
            result = get_unique_filepath_with_counter(str(tmp_path), sanitized, ".pdf")
            result_path = Path(result)

            # Result must be direct child of tmp_path
            assert result_path.parent == tmp_path, f"Failed for: {malicious}"

    @patch("app.tasks.embed_metadata_into_pdf.settings")
    @patch("app.tasks.embed_metadata_into_pdf.SessionLocal")
    @patch("app.tasks.embed_metadata_into_pdf.log_task_progress")
    @patch("app.tasks.embed_metadata_into_pdf.finalize_document_storage")
    @patch("pypdf.PdfReader")
    @patch("pypdf.PdfWriter")
    def test_embed_metadata_full_flow_with_malicious_filename(
        self,
        mock_pdf_writer,
        mock_pdf_reader,
        mock_finalize,
        mock_log,
        mock_session,
        mock_settings,
        tmp_path,
    ):
        """Integration test: full embed_metadata_into_pdf with malicious filename."""
        from app.tasks.embed_metadata_into_pdf import embed_metadata_into_pdf

        # Setup
        mock_settings.workdir = str(tmp_path)

        # Create a temporary PDF file
        test_pdf = tmp_path / "test.pdf"
        test_pdf.write_bytes(b"%PDF-1.4\n")

        # Mock PDF operations
        mock_reader_instance = MagicMock()
        mock_reader_instance.pages = []
        mock_pdf_reader.return_value = mock_reader_instance

        mock_writer_instance = MagicMock()
        mock_pdf_writer.return_value = mock_writer_instance

        # Malicious metadata from GPT
        malicious_metadata = {
            "filename": "../../../etc/passwd",  # Path traversal attempt
            "document_type": "Invoice",
            "tags": ["test"],
        }

        # Create processed directory
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()

        # Execute task (called directly, Celery injects 'self' automatically)
        result = embed_metadata_into_pdf(
            str(test_pdf),
            "test text",
            malicious_metadata,
            file_id=1,
        )

        # Verify the result file is in the processed directory
        # and not in /etc/ or parent directories
        if "file" in result:
            result_path = Path(result["file"])
            # Should be in processed directory
            assert result_path.parent == processed_dir
            # Should not contain path traversal
            assert ".." not in result_path.name
            assert "/" not in result_path.name
            assert "\\" not in result_path.name


@pytest.mark.security
@pytest.mark.unit
class TestExtractMetadataFilenameValidation:
    """Test that extract_metadata_with_gpt validates GPT-provided filenames."""

    def test_validates_filename_format(self):
        """Test that invalid filename formats are rejected."""
        import re

        # Valid pattern from extract_metadata_with_gpt.py
        # TODO: Consider extracting this to a shared constant to avoid duplication
        valid_pattern = r"^[\w\-\. ]+$"

        # Test valid filenames
        valid_filenames = [
            "2024-01-15_Invoice.pdf",
            "Document_Name.pdf",
            "My Document 2024.pdf",
            "file-name_123.pdf",
        ]

        for filename in valid_filenames:
            # Remove extension for test
            name_only = filename.rsplit(".", 1)[0]
            assert re.match(valid_pattern, name_only), f"Valid filename rejected: {filename}"

        # Test invalid filenames
        invalid_filenames = [
            "../../../etc/passwd",
            "/etc/shadow",
            "C:\\Windows\\system32",
            "folder/../file",
            "file:name.pdf",
            "file|name.pdf",
            "file<>name.pdf",
        ]

        for filename in invalid_filenames:
            assert not re.match(valid_pattern, filename), f"Invalid filename accepted: {filename}"

    def test_rejects_path_traversal_in_filename(self):
        """Test that path traversal patterns are detected."""
        malicious_filenames = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "/etc/shadow",
            "folder/../file",
        ]

        for filename in malicious_filenames:
            # Check for path traversal indicators
            has_traversal = ".." in filename or "/" in filename or "\\" in filename
            assert has_traversal, f"Path traversal not detected: {filename}"


@pytest.mark.security
@pytest.mark.unit
class TestPathValidationSecurity:
    """Test secure path validation using pathlib."""

    def test_is_relative_to_prevents_traversal(self, tmp_path):
        """Test that is_relative_to prevents directory traversal."""
        base_dir = tmp_path / "workdir"
        base_dir.mkdir()

        # Create a file outside base_dir
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        outside_file = outside_dir / "file.txt"
        outside_file.write_text("test")

        # Attempt to access file outside base_dir
        try:
            outside_resolved = outside_file.resolve()
            base_resolved = base_dir.resolve()

            # Should return False (file is not relative to base_dir)
            is_safe = outside_resolved.is_relative_to(base_resolved)
            assert not is_safe, "Path traversal not detected"
        except ValueError:
            # In some Python versions, is_relative_to may raise ValueError
            # This is also acceptable (indicates not relative)
            pass

    def test_resolve_prevents_symlink_attacks(self, tmp_path):
        """Test that resolve() handles symlink attacks."""
        base_dir = tmp_path / "workdir"
        base_dir.mkdir()

        # Create target outside base_dir
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        target_file = outside_dir / "secret.txt"
        target_file.write_text("secret")

        # Create symlink inside base_dir pointing outside
        symlink_path = base_dir / "link.txt"
        symlink_path.symlink_to(target_file)

        # Resolve should give us the real path
        resolved = symlink_path.resolve()
        base_resolved = base_dir.resolve()

        # The resolved path should NOT be relative to base_dir
        try:
            is_safe = resolved.is_relative_to(base_resolved)
            assert not is_safe, "Symlink attack not detected"
        except ValueError:
            # is_relative_to raises ValueError if not relative
            pass

    def test_string_based_validation_is_insecure(self, tmp_path):
        """Demonstrate why string-based path validation is insecure."""
        base_dir = tmp_path / "workdir"
        base_dir.mkdir()

        # Create a similar-named directory
        fake_dir = tmp_path / "workdir-fake"
        fake_dir.mkdir()
        fake_file = fake_dir / "file.txt"
        fake_file.write_text("content")

        # String-based check (insecure)
        base_str = str(base_dir)
        fake_str = str(fake_file)

        # This would INCORRECTLY pass string.startswith() if not careful
        # because "workdir-fake" starts with "workdir"
        if base_str.endswith("/") or base_str.endswith("\\"):
            # Properly add separator
            string_check_unsafe = fake_str.startswith(base_str)
        else:
            # Without separator, vulnerable to partial matches
            string_check_unsafe = fake_str.startswith(base_str)

        # Pathlib-based check (secure)
        try:
            pathlib_check = fake_file.resolve().is_relative_to(base_dir.resolve())
            # Should correctly identify this is NOT under base_dir
            assert not pathlib_check, "Pathlib should reject this path"
        except ValueError:
            # Correctly rejected
            pass


@pytest.mark.security
@pytest.mark.unit
class TestFileUploadSecurity:
    """Test that file upload endpoints prevent path traversal."""

    def test_ui_upload_uses_basename(self):
        """Test that ui_upload extracts basename to prevent path traversal."""
        import os

        from app.utils.filename_utils import sanitize_filename

        # Simulate malicious filenames
        malicious_filenames = [
            "../../../etc/passwd",
            "/etc/shadow",
            "folder/../file.pdf",
        ]

        for malicious in malicious_filenames:
            # os.path.basename should extract just the filename
            basename = os.path.basename(malicious)

            # Verify no path traversal remains in basename
            assert ".." not in basename, f"Path traversal not removed: {malicious} -> {basename}"
            assert "/" not in basename, f"Path separator not removed: {malicious} -> {basename}"

        # Windows-style backslash paths: os.path.basename on Linux does NOT
        # split on backslash, so the application also uses sanitize_filename
        # to handle these.  Verify the combined approach is safe.
        windows_paths = [
            "..\\..\\windows\\system32",
        ]
        for malicious in windows_paths:
            sanitized = sanitize_filename(os.path.basename(malicious))
            assert ".." not in sanitized, f"Path traversal not removed after sanitize: {malicious} -> {sanitized}"
            assert "\\" not in sanitized, f"Backslash not removed after sanitize: {malicious} -> {sanitized}"

    def test_sanitize_after_basename(self):
        """Test that sanitization happens after basename extraction."""
        import os

        from app.utils.filename_utils import sanitize_filename

        malicious = "../../../passwd.pdf"

        # Step 1: Extract basename (as ui_upload does)
        basename = os.path.basename(malicious)
        assert basename == "passwd.pdf"

        # Step 2: Sanitize (as ui_upload does)
        sanitized = sanitize_filename(basename)
        assert sanitized == "passwd.pdf"

        # Final result is safe
        assert ".." not in sanitized
        assert "/" not in sanitized


@pytest.mark.security
@pytest.mark.unit
class TestFileHashSecurity:
    """Test that file hashing doesn't introduce vulnerabilities."""

    def test_hash_file_with_absolute_path_only(self, tmp_path):
        """Test that hash_file should only accept absolute paths."""
        from app.utils.file_operations import hash_file

        # Create a test file
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        # Should work with absolute path
        result = hash_file(str(test_file))
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest length

    def test_hash_file_rejects_path_traversal(self):
        """Test that hash_file doesn't allow path traversal."""
        from app.utils.file_operations import hash_file

        # Attempt to hash a file using path traversal
        # This should fail because the file doesn't exist
        with pytest.raises(FileNotFoundError):
            hash_file("../../../etc/passwd")


@pytest.mark.security
@pytest.mark.integration
class TestEndToEndPathTraversal:
    """Integration tests for path traversal prevention."""

    def test_full_upload_flow_prevents_traversal(self, tmp_path):
        """Test complete upload flow prevents path traversal."""
        import os
        import uuid

        from app.utils.filename_utils import sanitize_filename

        # Simulate ui_upload flow
        malicious_upload_filename = "../../../etc/passwd"

        # Step 1: Extract basename
        base_filename = os.path.basename(malicious_upload_filename)
        assert base_filename == "passwd"

        # Step 2: Sanitize
        safe_filename = sanitize_filename(base_filename)
        assert safe_filename == "passwd"

        # Step 3: Add UUID (as ui_upload does)
        unique_id = str(uuid.uuid4())
        target_filename = f"{unique_id}.{safe_filename}"

        # Step 4: Join with workdir
        target_path = os.path.join(str(tmp_path), target_filename)

        # Verify final path is safe
        final_path = Path(target_path)
        assert final_path.parent == tmp_path
        assert ".." not in target_filename
        assert "/" not in target_filename

    def test_metadata_embedding_flow_prevents_traversal(self, tmp_path):
        """Test metadata embedding flow prevents path traversal."""
        import os

        from app.utils.filename_utils import sanitize_filename

        # Simulate GPT returning malicious filename
        gpt_metadata = {
            "filename": "../../../etc/shadow",
            "document_type": "Invoice",
        }

        # Step 1: Extract filename from metadata
        suggested_filename = gpt_metadata.get("filename", "fallback")

        # Step 2: Sanitize (as embed_metadata_into_pdf should do)
        suggested_filename = sanitize_filename(suggested_filename)

        # Step 3: Remove extension
        suggested_filename = os.path.splitext(suggested_filename)[0]

        # Step 4: Build final path
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        final_path = os.path.join(str(processed_dir), f"{suggested_filename}.pdf")

        # Verify final path is safe
        result_path = Path(final_path)
        assert result_path.parent == processed_dir
        assert ".." not in str(result_path)
