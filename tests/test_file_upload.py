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
import os
import pytest
from unittest.mock import patch, MagicMock, Mock
from fastapi.testclient import TestClient


# Module-level mock to prevent Celery connection attempts
@pytest.fixture(autouse=True)
def mock_celery_tasks():
    """Mock Celery tasks to prevent connection attempts."""
    with patch("app.tasks.process_document.process_document") as mock_process_task, \
         patch("app.tasks.convert_to_pdf.convert_to_pdf") as mock_convert_task:
        # Setup the mocked tasks with delay methods
        mock_process_task.delay = Mock()
        mock_convert_task.delay = Mock()
        yield {
            "process_document": mock_process_task,
            "convert_to_pdf": mock_convert_task
        }


@pytest.mark.integration
class TestValidFileUploads:
    """Tests for successful file uploads with various valid file types."""
    
    def test_upload_valid_pdf(self, client: TestClient, sample_pdf_path: str):
        """Test uploading a valid PDF file."""
        with patch("app.api.files.process_document.delay") as mock_process:
            mock_task = MagicMock()
            mock_task.id = "test-task-id-123"
            mock_process.return_value = mock_task
            
            with open(sample_pdf_path, "rb") as f:
                response = client.post(
                    "/api/ui-upload",
                    files={"file": ("document.pdf", f, "application/pdf")}
                )
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify response structure
            assert "task_id" in data
            assert "status" in data
            assert "original_filename" in data
            assert "stored_filename" in data
            
            # Verify response values
            assert data["task_id"] == "test-task-id-123"
            assert data["status"] == "queued"
            assert data["original_filename"] == "document.pdf"
            assert data["stored_filename"].endswith(".pdf")
            
            # Verify the processing task was called
            mock_process.assert_called_once()
            call_args = mock_process.call_args
            assert call_args.kwargs["original_filename"] == "document.pdf"
    
    def test_upload_valid_text_file(self, client: TestClient):
        """Test uploading a valid text file."""
        # Patch where the function is used (in app.api.files module)
        with patch("app.api.files.convert_to_pdf.delay") as mock_convert:
            mock_task = MagicMock()
            mock_task.id = "test-task-txt-456"
            mock_convert.return_value = mock_task
            
            text_content = b"This is a test text file.\nWith multiple lines."
            response = client.post(
                "/api/ui-upload",
                files={"file": ("document.txt", io.BytesIO(text_content), "text/plain")}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "test-task-txt-456"
            assert data["original_filename"] == "document.txt"
            assert data["stored_filename"].endswith(".txt")
            
            # Text files should be converted to PDF
            mock_convert.assert_called_once()
    
    def test_upload_valid_image_jpeg(self, client: TestClient):
        """Test uploading a valid JPEG image."""
        with patch("app.api.files.convert_to_pdf.delay") as mock_convert:
            mock_task = MagicMock()
            mock_task.id = "test-task-img-789"
            mock_convert.return_value = mock_task
            
            # Create a minimal valid JPEG
            jpeg_content = (
                b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
                b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n"
                b"\xff\xd9"
            )
            
            response = client.post(
                "/api/ui-upload",
                files={"file": ("image.jpg", io.BytesIO(jpeg_content), "image/jpeg")}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "test-task-img-789"
            assert data["original_filename"] == "image.jpg"
            
            # Images should be converted to PDF
            mock_convert.assert_called_once()
    
    def test_upload_valid_png_image(self, client: TestClient):
        """Test uploading a valid PNG image."""
        with patch("app.api.files.convert_to_pdf.delay") as mock_convert:
            mock_task = MagicMock()
            mock_task.id = "test-task-png-001"
            mock_convert.return_value = mock_task
            
            # Create a minimal valid PNG (1x1 transparent pixel)
            png_content = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
                b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            
            response = client.post(
                "/api/ui-upload",
                files={"file": ("screenshot.png", io.BytesIO(png_content), "image/png")}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["original_filename"] == "screenshot.png"
            assert data["stored_filename"].endswith(".png")
            mock_convert.assert_called_once()
    
    def test_upload_office_document_docx(self, client: TestClient):
        """Test uploading a Word document."""
        with patch("app.api.files.convert_to_pdf.delay") as mock_convert:
            mock_task = MagicMock()
            mock_task.id = "test-task-docx-002"
            mock_convert.return_value = mock_task
            
            # Create minimal DOCX content (ZIP file with proper structure)
            docx_content = (
                b"PK\x03\x04\x14\x00\x00\x00\x08\x00" + b"\x00" * 50
            )
            
            response = client.post(
                "/api/ui-upload",
                files={"file": (
                    "report.docx",
                    io.BytesIO(docx_content),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["original_filename"] == "report.docx"
            assert data["stored_filename"].endswith(".docx")
            
            # Office documents should be converted to PDF
            mock_convert.assert_called_once()
    
    def test_upload_csv_file(self, client: TestClient):
        """Test uploading a CSV file."""
        with patch("app.api.files.convert_to_pdf.delay") as mock_convert:
            mock_task = MagicMock()
            mock_task.id = "test-task-csv-003"
            mock_convert.return_value = mock_task
            
            csv_content = b"name,age,city\nJohn,30,NYC\nJane,25,LA\n"
            
            response = client.post(
                "/api/ui-upload",
                files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["original_filename"] == "data.csv"
            mock_convert.assert_called_once()


@pytest.mark.integration
class TestInvalidFileUploads:
    """Tests for handling invalid or problematic file uploads."""
    
    def test_upload_file_too_large(self, client: TestClient):
        """Test that files over 500MB are rejected."""
        with patch("app.api.files.convert_to_pdf.delay"):
            # Create a large file content (mock it to avoid memory issues)
            # We'll create the file on disk and then check size
            large_content = b"x" * 1024  # 1KB for testing
            
            with patch("os.path.getsize") as mock_getsize:
                # Mock the file size to be over 500MB
                mock_getsize.return_value = 501 * 1024 * 1024  # 501MB
                
                response = client.post(
                    "/api/ui-upload",
                    files={"file": ("huge.pdf", io.BytesIO(large_content), "application/pdf")}
                )
                
                assert response.status_code == 413  # Request Entity Too Large
                assert "too large" in response.json()["detail"].lower()
    
    def test_upload_executable_file(self, client: TestClient):
        """Test that executable files are handled (attempted conversion)."""
        with patch("app.api.files.convert_to_pdf.delay") as mock_convert:
            mock_task = MagicMock()
            mock_task.id = "test-task-exe-004"
            mock_convert.return_value = mock_task
            
            exe_content = b"MZ\x90\x00"  # PE header
            
            response = client.post(
                "/api/ui-upload",
                files={"file": ("program.exe", io.BytesIO(exe_content), "application/x-msdownload")}
            )
            
            # Per the code, unsupported types get a warning but are still processed
            assert response.status_code == 200
            # The system attempts conversion even for unsupported types
            mock_convert.assert_called_once()
    
    def test_upload_empty_file(self, client: TestClient):
        """Test uploading an empty file."""
        with patch("app.api.files.convert_to_pdf.delay") as mock_convert:
            mock_task = MagicMock()
            mock_task.id = "test-task-empty-005"
            mock_convert.return_value = mock_task
            
            response = client.post(
                "/api/ui-upload",
                files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
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
    
    def test_path_traversal_prevention_dotdot(self, client: TestClient):
        """Test that path traversal attempts are prevented."""
        with patch("app.api.files.process_document.delay") as mock_process:
            mock_task = MagicMock()
            mock_task.id = "test-task-security-001"
            mock_process.return_value = mock_task
            
            # Try to upload a file with path traversal in filename
            malicious_filename = "../../etc/passwd.pdf"
            pdf_content = b"%PDF-1.4\n%EOF"
            
            response = client.post(
                "/api/ui-upload",
                files={"file": (malicious_filename, io.BytesIO(pdf_content), "application/pdf")}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # The original filename should be sanitized (only basename)
            assert data["original_filename"] == "passwd.pdf"
            assert ".." not in data["stored_filename"]
            assert "/" not in data["stored_filename"]
    
    def test_path_traversal_prevention_absolute(self, client: TestClient):
        """Test that absolute path attempts are prevented."""
        with patch("app.api.files.process_document.delay") as mock_process:
            mock_task = MagicMock()
            mock_task.id = "test-task-security-002"
            mock_process.return_value = mock_task
            
            malicious_filename = "/etc/shadow.pdf"
            pdf_content = b"%PDF-1.4\n%EOF"
            
            response = client.post(
                "/api/ui-upload",
                files={"file": (malicious_filename, io.BytesIO(pdf_content), "application/pdf")}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Only the basename should be kept
            assert data["original_filename"] == "shadow.pdf"
            assert not data["stored_filename"].startswith("/")
    
    def test_filename_with_special_characters(self, client: TestClient):
        """Test handling of filenames with special characters."""
        with patch("app.api.files.process_document.delay") as mock_process:
            mock_task = MagicMock()
            mock_task.id = "test-task-special-003"
            mock_process.return_value = mock_task
            
            special_filename = "file name with spaces & special!@#chars.pdf"
            pdf_content = b"%PDF-1.4\n%EOF"
            
            response = client.post(
                "/api/ui-upload",
                files={"file": (special_filename, io.BytesIO(pdf_content), "application/pdf")}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Original filename should be preserved (sanitized by basename)
            assert data["original_filename"] == special_filename
            # Stored filename should have UUID and extension
            assert data["stored_filename"].endswith(".pdf")


@pytest.mark.integration
class TestUploadErrorHandling:
    """Tests for error handling during file uploads."""
    
    def test_upload_disk_write_failure(self, client: TestClient):
        """Test handling of disk write failures."""
        with patch("builtins.open", side_effect=IOError("Disk full")):
            pdf_content = b"%PDF-1.4\n%EOF"
            
            response = client.post(
                "/api/ui-upload",
                files={"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")}
            )
            
            assert response.status_code == 500
            assert "Failed to save file" in response.json()["detail"]
    
    def test_upload_celery_task_failure(self, client: TestClient):
        """Test handling when Celery task queueing fails."""
        with patch("app.api.files.process_document.delay", side_effect=Exception("Celery connection failed")):
            pdf_content = b"%PDF-1.4\n%EOF"
            
            # The endpoint should still handle the error gracefully
            # In this case, the exception will propagate
            with pytest.raises(Exception):
                client.post(
                    "/api/ui-upload",
                    files={"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")}
                )


@pytest.mark.integration
class TestUploadFilenameHandling:
    """Tests for filename handling and UUID generation."""
    
    def test_unique_filename_generation(self, client: TestClient):
        """Test that uploaded files get unique UUIDs."""
        with patch("app.api.files.process_document.delay") as mock_process:
            mock_task = MagicMock()
            mock_task.id = "test-task-uuid-001"
            mock_process.return_value = mock_task
            
            pdf_content = b"%PDF-1.4\n%EOF"
            
            # Upload same file twice
            response1 = client.post(
                "/api/ui-upload",
                files={"file": ("same.pdf", io.BytesIO(pdf_content), "application/pdf")}
            )
            
            response2 = client.post(
                "/api/ui-upload",
                files={"file": ("same.pdf", io.BytesIO(pdf_content), "application/pdf")}
            )
            
            assert response1.status_code == 200
            assert response2.status_code == 200
            
            data1 = response1.json()
            data2 = response2.json()
            
            # Original filenames should be the same
            assert data1["original_filename"] == data2["original_filename"] == "same.pdf"
            
            # But stored filenames should be different (unique UUIDs)
            assert data1["stored_filename"] != data2["stored_filename"]
    
    def test_filename_without_extension(self, client: TestClient):
        """Test handling of files without extensions."""
        with patch("app.api.files.convert_to_pdf.delay") as mock_convert:
            mock_task = MagicMock()
            mock_task.id = "test-task-noext-002"
            mock_convert.return_value = mock_task
            
            content = b"Some content"
            
            response = client.post(
                "/api/ui-upload",
                files={"file": ("NOEXTENSION", io.BytesIO(content), "application/octet-stream")}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["original_filename"] == "NOEXTENSION"
            # Stored filename should be just the UUID without extension
            assert "." not in data["stored_filename"] or data["stored_filename"].count(".") == 0


@pytest.mark.integration
class TestUploadMimeTypeDetection:
    """Tests for MIME type detection and routing."""
    
    def test_pdf_by_extension_only(self, client: TestClient):
        """Test PDF detection by file extension when MIME type is generic."""
        with patch("app.api.files.process_document.delay") as mock_process:
            mock_task = MagicMock()
            mock_task.id = "test-task-mime-001"
            mock_process.return_value = mock_task
            
            pdf_content = b"%PDF-1.4\n%EOF"
            
            response = client.post(
                "/api/ui-upload",
                files={"file": ("doc.pdf", io.BytesIO(pdf_content), "application/octet-stream")}
            )
            
            assert response.status_code == 200
            # Should route to process_document (not convert_to_pdf) based on extension
            mock_process.assert_called_once()
    
    def test_image_by_extension(self, client: TestClient):
        """Test image detection by file extension."""
        with patch("app.api.files.convert_to_pdf.delay") as mock_convert:
            mock_task = MagicMock()
            mock_task.id = "test-task-mime-002"
            mock_convert.return_value = mock_task
            
            # Generic binary content with image extension
            image_content = b"\x00\x01\x02\x03"
            
            response = client.post(
                "/api/ui-upload",
                files={"file": ("photo.jpg", io.BytesIO(image_content), "application/octet-stream")}
            )
            
            assert response.status_code == 200
            # Should route to convert_to_pdf based on .jpg extension
            mock_convert.assert_called_once()
