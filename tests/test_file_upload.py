"""
Tests for file upload functionality via the ui-upload endpoint.

Tests cover:
- Valid file uploads (PDF, images, office documents, text files)
- Invalid file types
- File size validation
- Malformed files
- Security issues (path traversal)
- Error handling
"""

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# Fixture to mock all celery tasks at module level
@pytest.fixture(autouse=True)
def mock_celery_tasks():
    """Mock all Celery tasks to prevent execution."""
    # Patch the entire task object where it's used (in app.api.files)
    with (
        patch("app.api.files.process_document") as mock_process_task,
        patch("app.api.files.convert_to_pdf") as mock_convert_task,
    ):
        # Setup default return values for .delay()
        mock_task = MagicMock()
        mock_task.id = "test-task-id-123"
        mock_process_task.delay.return_value = mock_task
        mock_convert_task.delay.return_value = mock_task

        yield {
            "process_document": mock_process_task.delay,
            "convert_to_pdf": mock_convert_task.delay,
        }


@pytest.mark.integration
class TestValidFileUploads:
    """Tests for successful file uploads with various valid file types."""

    def test_upload_valid_pdf(self, client: TestClient, sample_pdf_path: str, mock_celery_tasks):
        """Test uploading a valid PDF file."""
        with open(sample_pdf_path, "rb") as f:
            response = client.post("/api/ui-upload", files={"file": ("document.pdf", f, "application/pdf")})

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "task_id" in data
        assert "status" in data
        assert "original_filename" in data
        assert "stored_filename" in data

        # Verify response values
        assert data["status"] == "queued"
        assert data["original_filename"] == "document.pdf"
        assert data["stored_filename"].endswith(".pdf")

        # Verify the processing task was called
        mock_celery_tasks["process_document"].assert_called_once()
        call_args = mock_celery_tasks["process_document"].call_args
        assert call_args.kwargs["original_filename"] == "document.pdf"

    def test_upload_valid_text_file(self, client: TestClient, mock_celery_tasks):
        """Test uploading a valid text file."""
        text_content = b"This is a test text file.\nWith multiple lines."
        response = client.post(
            "/api/ui-upload",
            files={"file": ("document.txt", io.BytesIO(text_content), "text/plain")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["original_filename"] == "document.txt"
        assert data["stored_filename"].endswith(".txt")

        # Text files should be converted to PDF
        mock_celery_tasks["convert_to_pdf"].assert_called_once()

    def test_upload_valid_image_jpeg(self, client: TestClient, mock_celery_tasks):
        """Test uploading a valid JPEG image."""
        # Create a minimal valid JPEG
        jpeg_content = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n"
            b"\xff\xd9"
        )

        response = client.post(
            "/api/ui-upload",
            files={"file": ("image.jpg", io.BytesIO(jpeg_content), "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["original_filename"] == "image.jpg"

        # Images should be converted to PDF
        mock_celery_tasks["convert_to_pdf"].assert_called_once()

    def test_upload_valid_png_image(self, client: TestClient, mock_celery_tasks):
        """Test uploading a valid PNG image."""
        # Create a minimal valid PNG (1x1 transparent pixel)
        png_content = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        response = client.post(
            "/api/ui-upload",
            files={"file": ("screenshot.png", io.BytesIO(png_content), "image/png")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["original_filename"] == "screenshot.png"
        assert data["stored_filename"].endswith(".png")
        mock_celery_tasks["convert_to_pdf"].assert_called_once()

    def test_upload_office_document_docx(self, client: TestClient, mock_celery_tasks):
        """Test uploading a Word document."""
        # Create minimal DOCX content (ZIP file with proper structure)
        docx_content = b"PK\x03\x04\x14\x00\x00\x00\x08\x00" + b"\x00" * 50

        response = client.post(
            "/api/ui-upload",
            files={
                "file": (
                    "report.docx",
                    io.BytesIO(docx_content),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["original_filename"] == "report.docx"
        assert data["stored_filename"].endswith(".docx")

        # Office documents should be converted to PDF
        mock_celery_tasks["convert_to_pdf"].assert_called_once()

    def test_upload_csv_file(self, client: TestClient, mock_celery_tasks):
        """Test uploading a CSV file."""
        csv_content = b"name,age,city\nJohn,30,NYC\nJane,25,LA\n"

        response = client.post(
            "/api/ui-upload",
            files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["original_filename"] == "data.csv"
        mock_celery_tasks["convert_to_pdf"].assert_called_once()


@pytest.mark.integration
class TestInvalidFileUploads:
    """Tests for handling invalid or problematic file uploads."""

    def test_upload_file_too_large(self, client: TestClient):
        """Test that files exceeding MAX_UPLOAD_SIZE are rejected."""
        from app.config import settings

        # Temporarily lower the upload limit so a tiny file exceeds it,
        # avoiding the need to allocate a real 1 GB payload in memory.
        small_limit = 100  # 100 bytes
        small_content = b"x" * (small_limit + 1)

        with patch.object(settings, "max_upload_size", small_limit):
            response = client.post(
                "/api/ui-upload",
                files={"file": ("huge.pdf", io.BytesIO(small_content), "application/pdf")},
            )

        assert response.status_code == 413  # Request Entity Too Large
        assert "too large" in response.json()["detail"].lower()
        assert "SECURITY_AUDIT.md" in response.json()["detail"]

    def test_upload_executable_file(self, client: TestClient, mock_celery_tasks):
        """Test that executable files are handled (attempted conversion)."""
        exe_content = b"MZ\x90\x00"  # PE header

        response = client.post(
            "/api/ui-upload",
            files={
                "file": (
                    "program.exe",
                    io.BytesIO(exe_content),
                    "application/x-msdownload",
                )
            },
        )

        # Per the code, unsupported types get a warning but are still processed
        assert response.status_code == 200
        # The system attempts conversion even for unsupported types
        mock_celery_tasks["convert_to_pdf"].assert_called_once()

    def test_upload_empty_file(self, client: TestClient, mock_celery_tasks):
        """Test uploading an empty file."""
        response = client.post(
            "/api/ui-upload",
            files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
        )

        # Empty files are accepted and queued for processing
        assert response.status_code == 200
        data = response.json()
        assert data["original_filename"] == "empty.txt"

    def test_upload_without_file(self, client: TestClient):
        """Test POST request without a file."""
        response = client.post("/api/ui-upload")

        # FastAPI should return a validation error
        assert response.status_code == 422  # Unprocessable Entity


@pytest.mark.integration
@pytest.mark.security
class TestUploadSecurity:
    """Tests for security aspects of file uploads."""

    def test_path_traversal_prevention_dotdot(self, client: TestClient, mock_celery_tasks):
        """Test that path traversal attempts are prevented."""
        # Try to upload a file with path traversal in filename
        malicious_filename = "../../etc/passwd.pdf"
        pdf_content = b"%PDF-1.4\n%EOF"

        response = client.post(
            "/api/ui-upload",
            files={"file": (malicious_filename, io.BytesIO(pdf_content), "application/pdf")},
        )

        assert response.status_code == 200
        data = response.json()

        # The original filename should be sanitized (only basename)
        assert data["original_filename"] == "passwd.pdf"
        assert ".." not in data["stored_filename"]
        assert "/" not in data["stored_filename"]

    def test_path_traversal_prevention_absolute(self, client: TestClient, mock_celery_tasks):
        """Test that absolute path attempts are prevented."""
        malicious_filename = "/etc/shadow.pdf"
        pdf_content = b"%PDF-1.4\n%EOF"

        response = client.post(
            "/api/ui-upload",
            files={"file": (malicious_filename, io.BytesIO(pdf_content), "application/pdf")},
        )

        assert response.status_code == 200
        data = response.json()

        # Only the basename should be kept
        assert data["original_filename"] == "shadow.pdf"
        assert not data["stored_filename"].startswith("/")

    def test_filename_with_special_characters(self, client: TestClient, mock_celery_tasks):
        """Test handling of filenames with special characters."""
        special_filename = "file name with spaces & special!@#chars.pdf"
        pdf_content = b"%PDF-1.4\n%EOF"

        response = client.post(
            "/api/ui-upload",
            files={"file": (special_filename, io.BytesIO(pdf_content), "application/pdf")},
        )

        assert response.status_code == 200
        data = response.json()

        # Original filename should be sanitized (special chars replaced with underscores)
        assert "!" not in data["original_filename"]
        assert "@" not in data["original_filename"]
        assert "#" not in data["original_filename"]
        # Spaces and basic characters should be preserved
        assert "file" in data["original_filename"]
        assert ".pdf" in data["original_filename"]
        # Stored filename should have UUID and extension
        assert data["stored_filename"].endswith(".pdf")

    def test_path_traversal_prevention_windows_style(self, client: TestClient, mock_celery_tasks):
        """Test that Windows-style path traversal attempts are prevented."""
        # Try Windows-style path with backslashes
        malicious_filename = "..\\..\\..\\windows\\system32\\config.pdf"
        pdf_content = b"%PDF-1.4\n%EOF"

        response = client.post(
            "/api/ui-upload",
            files={"file": (malicious_filename, io.BytesIO(pdf_content), "application/pdf")},
        )

        assert response.status_code == 200
        data = response.json()

        # On Unix systems, os.path.basename doesn't recognize Windows backslashes,
        # so the full string goes to sanitize_filename which then:
        # 1. Replaces backslashes with underscores
        # 2. Replaces .. with underscores
        # 3. Strips leading/trailing underscores
        # Result: "windows_system32_config.pdf"
        expected_filename = "windows_system32_config.pdf"
        assert data["original_filename"] == expected_filename
        # Verify no dangerous characters remain
        assert "\\" not in data["original_filename"]
        assert ".." not in data["original_filename"]
        assert "/" not in data["original_filename"]

    def test_path_traversal_prevention_mixed_separators(self, client: TestClient, mock_celery_tasks):
        """Test handling of filenames with mixed path separators."""
        malicious_filename = "../path\\to/file.pdf"
        pdf_content = b"%PDF-1.4\n%EOF"

        response = client.post(
            "/api/ui-upload",
            files={"file": (malicious_filename, io.BytesIO(pdf_content), "application/pdf")},
        )

        assert response.status_code == 200
        data = response.json()

        # os.path.basename recognizes Unix / separators and extracts "file.pdf"
        # sanitize_filename then ensures it's safe (already is in this case)
        expected_filename = "file.pdf"
        assert data["original_filename"] == expected_filename
        # Verify no dangerous characters remain
        assert "/" not in data["original_filename"]
        assert "\\" not in data["original_filename"]
        assert ".." not in data["original_filename"]


@pytest.mark.integration
class TestUploadErrorHandling:
    """Tests for error handling during file uploads."""

    def test_upload_disk_write_failure(self, client: TestClient):
        """Test handling of disk write failures."""
        with patch("builtins.open", side_effect=IOError("Disk full")):
            pdf_content = b"%PDF-1.4\n%EOF"

            response = client.post(
                "/api/ui-upload",
                files={"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")},
            )

            assert response.status_code == 500
            assert "Failed to save file" in response.json()["detail"]

    def test_upload_celery_task_failure(self, client: TestClient, mock_celery_tasks):
        """Test handling when Celery task queueing fails."""
        mock_celery_tasks["process_document"].side_effect = Exception("Celery connection failed")

        pdf_content = b"%PDF-1.4\n%EOF"

        # The endpoint should still handle the error gracefully
        # In this case, the exception will propagate
        with pytest.raises(Exception):
            client.post(
                "/api/ui-upload",
                files={"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")},
            )


@pytest.mark.integration
class TestUploadFilenameHandling:
    """Tests for filename handling and UUID generation."""

    def test_unique_filename_generation(self, client: TestClient, mock_celery_tasks):
        """Test that uploaded files get unique UUIDs."""
        pdf_content = b"%PDF-1.4\n%EOF"

        # Upload same file twice
        response1 = client.post(
            "/api/ui-upload",
            files={"file": ("same.pdf", io.BytesIO(pdf_content), "application/pdf")},
        )

        response2 = client.post(
            "/api/ui-upload",
            files={"file": ("same.pdf", io.BytesIO(pdf_content), "application/pdf")},
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        # Original filenames should be the same
        assert data1["original_filename"] == data2["original_filename"] == "same.pdf"

        # But stored filenames should be different (unique UUIDs)
        assert data1["stored_filename"] != data2["stored_filename"]

    def test_filename_without_extension(self, client: TestClient, mock_celery_tasks):
        """Test handling of files without extensions."""
        content = b"Some content"

        response = client.post(
            "/api/ui-upload",
            files={"file": ("NOEXTENSION", io.BytesIO(content), "application/octet-stream")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["original_filename"] == "NOEXTENSION"
        # Stored filename should be just the UUID without extension
        assert "." not in data["stored_filename"] or data["stored_filename"].count(".") == 0


@pytest.mark.integration
class TestUploadMimeTypeDetection:
    """Tests for MIME type detection and routing."""

    def test_pdf_by_extension_only(self, client: TestClient, mock_celery_tasks):
        """Test PDF detection by file extension when MIME type is generic."""
        pdf_content = b"%PDF-1.4\n%EOF"

        response = client.post(
            "/api/ui-upload",
            files={"file": ("doc.pdf", io.BytesIO(pdf_content), "application/octet-stream")},
        )

        assert response.status_code == 200
        # Should route to process_document (not convert_to_pdf) based on extension
        mock_celery_tasks["process_document"].assert_called_once()

    def test_image_by_extension(self, client: TestClient, mock_celery_tasks):
        """Test image detection by file extension."""
        # Generic binary content with image extension
        image_content = b"\x00\x01\x02\x03"

        response = client.post(
            "/api/ui-upload",
            files={
                "file": (
                    "photo.jpg",
                    io.BytesIO(image_content),
                    "application/octet-stream",
                )
            },
        )

        assert response.status_code == 200
        # Should route to convert_to_pdf based on .jpg extension
        mock_celery_tasks["convert_to_pdf"].assert_called_once()


@pytest.mark.integration
class TestFileSplitting:
    """Tests for file splitting functionality when MAX_SINGLE_FILE_SIZE is configured."""

    def test_pdf_splitting_when_configured(self, client: TestClient, sample_pdf_path: str, mock_celery_tasks):
        """Test that PDFs are split when they exceed MAX_SINGLE_FILE_SIZE."""
        from app.config import settings

        # Mock settings to enable file splitting with a very small limit
        with patch.object(settings, "max_single_file_size", 100):  # 100 bytes limit
            # Mock the split_pdf_by_size function to return fake split files
            with patch("app.utils.file_splitting.split_pdf_by_size") as mock_split:
                mock_split.return_value = [
                    "/workdir/test_part1.pdf",
                    "/workdir/test_part2.pdf",
                    "/workdir/test_part3.pdf",
                ]

                # Mock should_split_file to return True
                with patch("app.utils.file_splitting.should_split_file", return_value=True):
                    with open(sample_pdf_path, "rb") as f:
                        response = client.post(
                            "/api/ui-upload",
                            files={"file": ("large.pdf", f, "application/pdf")},
                        )

                    assert response.status_code == 200
                    data = response.json()

                    # Verify response indicates splitting occurred
                    assert "split_into_parts" in data
                    assert data["split_into_parts"] == 3
                    assert "task_ids" in data
                    assert len(data["task_ids"]) == 3
                    assert "message" in data
                    assert "split" in data["message"].lower()

                    # Verify each split file was queued for processing
                    assert mock_celery_tasks["process_document"].call_count == 3

    def test_no_splitting_when_not_configured(self, client: TestClient, sample_pdf_path: str, mock_celery_tasks):
        """Test that PDFs are not split when MAX_SINGLE_FILE_SIZE is None."""
        from app.config import settings

        # Ensure max_single_file_size is None (default)
        with patch.object(settings, "max_single_file_size", None):
            with open(sample_pdf_path, "rb") as f:
                response = client.post(
                    "/api/ui-upload",
                    files={"file": ("document.pdf", f, "application/pdf")},
                )

            assert response.status_code == 200
            data = response.json()

            # Verify no splitting occurred
            assert "split_into_parts" not in data
            assert "task_id" in data  # Single task ID, not task_ids array
            assert data["status"] == "queued"

            # Verify file was processed directly without splitting
            mock_celery_tasks["process_document"].assert_called_once()

    def test_no_splitting_for_small_files(self, client: TestClient, sample_pdf_path: str, mock_celery_tasks):
        """Test that small PDFs are not split even when MAX_SINGLE_FILE_SIZE is configured."""
        from app.config import settings

        # Configure a very large limit
        with patch.object(settings, "max_single_file_size", 1000000000):  # 1GB limit
            with open(sample_pdf_path, "rb") as f:
                response = client.post(
                    "/api/ui-upload",
                    files={"file": ("small.pdf", f, "application/pdf")},
                )

            assert response.status_code == 200
            data = response.json()

            # Verify no splitting occurred for small file
            assert "split_into_parts" not in data
            assert "task_id" in data

            # Verify file was processed directly
            mock_celery_tasks["process_document"].assert_called_once()

    def test_splitting_fallback_on_error(self, client: TestClient, sample_pdf_path: str, mock_celery_tasks):
        """Test that if splitting fails, the file is processed as a whole."""
        from app.config import settings

        with patch.object(settings, "max_single_file_size", 100):  # Small limit
            with patch("app.utils.file_splitting.should_split_file", return_value=True):
                # Mock split_pdf_by_size to raise an exception
                with patch(
                    "app.utils.file_splitting.split_pdf_by_size",
                    side_effect=Exception("Split failed"),
                ):
                    with open(sample_pdf_path, "rb") as f:
                        response = client.post(
                            "/api/ui-upload",
                            files={"file": ("document.pdf", f, "application/pdf")},
                        )

                    # Should still succeed, falling back to processing the whole file
                    assert response.status_code == 200
                    data = response.json()

                    # Verify no splitting data in response
                    assert "split_into_parts" not in data
                    assert "task_id" in data

                    # File should be processed as a whole
                    mock_celery_tasks["process_document"].assert_called_once()

    def test_non_pdf_not_split(self, client: TestClient, mock_celery_tasks):
        """Test that non-PDF files are never split, even with MAX_SINGLE_FILE_SIZE configured."""
        from app.config import settings

        with patch.object(settings, "max_single_file_size", 100):  # Small limit
            # Upload an image file
            image_content = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
                b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )

            response = client.post(
                "/api/ui-upload",
                files={"file": ("image.png", io.BytesIO(image_content), "image/png")},
            )

            assert response.status_code == 200
            data = response.json()

            # Images should not be split (they're converted to PDF first)
            assert "split_into_parts" not in data
            assert "task_id" in data

            # Should be queued for conversion
            mock_celery_tasks["convert_to_pdf"].assert_called_once()
