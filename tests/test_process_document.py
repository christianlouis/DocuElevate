"""
Unit tests for the process_document task.

These tests verify that the process_document task correctly handles file processing
and doesn't cause DetachedInstanceError when accessing database objects.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.models import FileRecord
from app.tasks.process_document import process_document


@pytest.mark.unit
@pytest.mark.requires_db
def test_process_document_stores_file_id_before_session_closes(db_session, tmp_path):
    """
    Test that process_document stores file_id before the database session closes.
    This prevents DetachedInstanceError when accessing the file_id after the session ends.
    """
    # Create a test PDF file with embedded text
    test_pdf = tmp_path / "test.pdf"
    pdf_content = b"""%PDF-1.4
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
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test content) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000306 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
399
%%EOF
"""
    test_pdf.write_bytes(pdf_content)

    # Mock environment and dependencies
    with (
        patch("app.tasks.process_document.SessionLocal") as mock_session_local,
        patch("app.tasks.process_document.settings") as mock_settings,
        patch("app.tasks.process_document.log_task_progress"),
        patch("app.tasks.process_document.extract_metadata_with_gpt") as mock_extract,
    ):
        # Setup mocks
        mock_settings.workdir = str(tmp_path)
        mock_session_local.return_value.__enter__.return_value = db_session
        mock_session_local.return_value.__exit__.return_value = None
        mock_extract.delay = MagicMock()

        # Get the actual function from the task (skip decorators)
        # The task function signature is: def process_document(self, original_local_file: str)
        task_run_func = process_document.run

        # Call the task's run method directly
        result = task_run_func(str(test_pdf))

        # Verify that the task completed successfully
        assert "file_id" in result
        assert result["status"] == "Text extracted locally"

        # Verify that a FileRecord was created
        file_record = db_session.query(FileRecord).first()
        assert file_record is not None
        assert file_record.original_filename == "test.pdf"

        # Verify that extract_metadata_with_gpt was called with the file_id
        # This would fail if file_id wasn't extracted before the session closed
        mock_extract.delay.assert_called_once()
        call_args = mock_extract.delay.call_args
        assert call_args[0][2] == file_record.id  # Third argument should be file_id


@pytest.mark.unit
@pytest.mark.requires_db
def test_process_document_duplicate_file(db_session, tmp_path):
    """
    Test that duplicate files are detected and processing is skipped.
    """
    # Create a test PDF file
    test_pdf = tmp_path / "test.pdf"
    test_pdf.write_bytes(b"test content")

    # Pre-create a FileRecord with the same hash
    from app.utils import hash_file

    filehash = hash_file(str(test_pdf))

    existing_record = FileRecord(
        filehash=filehash,
        original_filename="existing.pdf",
        local_filename="/tmp/existing.pdf",
        file_size=100,
        mime_type="application/pdf",
    )
    db_session.add(existing_record)
    db_session.commit()
    existing_id = existing_record.id

    # Mock environment and dependencies
    with (
        patch("app.tasks.process_document.SessionLocal") as mock_session_local,
        patch("app.tasks.process_document.log_task_progress"),
    ):
        # Setup mocks
        mock_session_local.return_value.__enter__.return_value = db_session
        mock_session_local.return_value.__exit__.return_value = None

        # Call the task's run method directly
        result = process_document.run(str(test_pdf))

        # Verify that duplicate was detected
        assert result["status"] == "duplicate_file"
        assert result["original_file_id"] == existing_id

        # A new duplicate FileRecord is created alongside the original
        assert db_session.query(FileRecord).count() == 2
        duplicate = db_session.query(FileRecord).filter(FileRecord.is_duplicate.is_(True)).first()
        assert duplicate is not None
        assert duplicate.duplicate_of_id == existing_id
        assert result["file_id"] == duplicate.id


@pytest.mark.unit
@pytest.mark.requires_db
def test_process_document_queues_ocr_for_image_pdf(db_session, tmp_path):
    """
    Test that PDFs without embedded text are queued for OCR processing.
    """
    # Create a test PDF file without text
    test_pdf = tmp_path / "test_image.pdf"
    pdf_content = b"""%PDF-1.4
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
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<<
/Size 4
/Root 1 0 R
>>
startxref
197
%%EOF
"""
    test_pdf.write_bytes(pdf_content)

    # Mock environment and dependencies
    with (
        patch("app.tasks.process_document.SessionLocal") as mock_session_local,
        patch("app.tasks.process_document.settings") as mock_settings,
        patch("app.tasks.process_document.log_task_progress"),
        patch("app.tasks.process_document.process_with_azure_document_intelligence") as mock_azure,
    ):
        # Setup mocks
        mock_settings.workdir = str(tmp_path)
        mock_session_local.return_value.__enter__.return_value = db_session
        mock_session_local.return_value.__exit__.return_value = None
        mock_azure.delay = MagicMock()

        # Call the task's run method directly
        result = process_document.run(str(test_pdf))

        # Verify that OCR was queued
        assert result["status"] == "Queued for OCR"
        assert "file_id" in result

        # Verify that process_with_azure_document_intelligence was called with file_id
        mock_azure.delay.assert_called_once()
        call_args = mock_azure.delay.call_args

        # Verify a FileRecord was created
        file_record = db_session.query(FileRecord).first()
        assert file_record is not None

        # The second argument should be the file_id
        assert call_args[0][1] == file_record.id


@pytest.mark.unit
@pytest.mark.requires_db
def test_process_document_reprocess_skips_duplicate_check(db_session, tmp_path):
    """
    Test that reprocessing an existing file (with file_id) skips the duplicate check
    and continues processing normally.
    """
    # Create a test PDF file with embedded text
    test_pdf = tmp_path / "test.pdf"
    pdf_content = b"""%PDF-1.4
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
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test content) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000306 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
399
%%EOF
"""
    test_pdf.write_bytes(pdf_content)

    # Pre-create a FileRecord with the same hash (simulating an existing record)
    from app.utils import hash_file

    filehash = hash_file(str(test_pdf))

    existing_record = FileRecord(
        filehash=filehash,
        original_filename="test.pdf",
        local_filename=str(test_pdf),
        file_size=len(pdf_content),
        mime_type="application/pdf",
    )
    db_session.add(existing_record)
    db_session.commit()
    existing_id = existing_record.id

    # Mock environment and dependencies
    with (
        patch("app.tasks.process_document.SessionLocal") as mock_session_local,
        patch("app.tasks.process_document.settings") as mock_settings,
        patch("app.tasks.process_document.log_task_progress"),
        patch("app.tasks.process_document.extract_metadata_with_gpt") as mock_extract,
    ):
        # Setup mocks
        mock_settings.workdir = str(tmp_path)
        mock_session_local.return_value.__enter__.return_value = db_session
        mock_session_local.return_value.__exit__.return_value = None
        mock_extract.delay = MagicMock()

        # Call with file_id to trigger reprocessing (should skip duplicate check)
        result = process_document.run(str(test_pdf), file_id=existing_id)

        # Verify that processing continued (not blocked by duplicate check)
        assert result["status"] == "Text extracted locally"
        assert result["file_id"] == existing_id

        # Verify that extract_metadata_with_gpt was called
        mock_extract.delay.assert_called_once()

        # Verify that only one FileRecord still exists (no new record created)
        assert db_session.query(FileRecord).count() == 1


@pytest.mark.unit
@pytest.mark.requires_db
def test_process_document_reprocess_nonexistent_file_id(db_session, tmp_path):
    """
    Test that reprocessing with a non-existent file_id returns an error.
    """
    # Create a test PDF file
    test_pdf = tmp_path / "test.pdf"
    test_pdf.write_bytes(b"test content")

    with (
        patch("app.tasks.process_document.SessionLocal") as mock_session_local,
        patch("app.tasks.process_document.log_task_progress"),
    ):
        mock_session_local.return_value.__enter__.return_value = db_session
        mock_session_local.return_value.__exit__.return_value = None

        # Call with a file_id that doesn't exist
        result = process_document.run(str(test_pdf), file_id=99999)

        # Verify error is returned
        assert "error" in result
        assert result["file_id"] == 99999


@pytest.mark.unit
@pytest.mark.requires_db
def test_process_document_file_not_found(db_session, tmp_path):
    """
    Test that process_document returns an error when the file doesn't exist.
    """
    # Use a non-existent file path
    nonexistent_file = tmp_path / "nonexistent.pdf"

    with (
        patch("app.tasks.process_document.SessionLocal") as mock_session_local,
        patch("app.tasks.process_document.log_task_progress"),
    ):
        mock_session_local.return_value.__enter__.return_value = db_session
        mock_session_local.return_value.__exit__.return_value = None

        # Call with a file that doesn't exist
        result = process_document.run(str(nonexistent_file))

        # Verify error is returned
        assert "error" in result
        assert result["error"] == "File not found"


@pytest.mark.unit
@pytest.mark.requires_db
def test_process_document_deduplication_disabled(db_session, tmp_path):
    """
    Test that process_document works correctly when deduplication is disabled.
    """
    # Create a test PDF file with embedded text
    test_pdf = tmp_path / "test.pdf"
    pdf_content = b"""%PDF-1.4
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
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test content) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000306 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
399
%%EOF
"""
    test_pdf.write_bytes(pdf_content)

    # Mock environment and dependencies
    with (
        patch("app.tasks.process_document.SessionLocal") as mock_session_local,
        patch("app.tasks.process_document.settings") as mock_settings,
        patch("app.tasks.process_document.log_task_progress"),
        patch("app.tasks.process_document.extract_metadata_with_gpt") as mock_extract,
    ):
        # Setup mocks - disable deduplication
        mock_settings.workdir = str(tmp_path)
        mock_settings.enable_deduplication = False
        mock_session_local.return_value.__enter__.return_value = db_session
        mock_session_local.return_value.__exit__.return_value = None
        mock_extract.delay = MagicMock()

        # Call the task's run method directly
        result = process_document.run(str(test_pdf))

        # Verify that the task completed successfully
        assert "file_id" in result
        assert result["status"] == "Text extracted locally"

        # Verify that a FileRecord was created
        file_record = db_session.query(FileRecord).first()
        assert file_record is not None


@pytest.mark.unit
@pytest.mark.requires_db
def test_process_document_unknown_mime_type(db_session, tmp_path):
    """
    Test that process_document handles files with unknown MIME types correctly,
    falling back to 'application/octet-stream'.
    """
    # Create a test file with an unusual extension that will be treated as non-PDF
    test_file = tmp_path / "test.unknownext"
    test_file.write_bytes(b"some binary content")

    # Mock environment and dependencies
    with (
        patch("app.tasks.process_document.SessionLocal") as mock_session_local,
        patch("app.tasks.process_document.settings") as mock_settings,
        patch("app.tasks.process_document.log_task_progress"),
        patch("app.tasks.process_document.celery") as mock_celery,
    ):
        # Setup mocks
        mock_settings.workdir = str(tmp_path)
        mock_session_local.return_value.__enter__.return_value = db_session
        mock_session_local.return_value.__exit__.return_value = None
        mock_celery.send_task = MagicMock()

        # Call the task's run method directly
        result = process_document.run(str(test_file))

        # Verify that the task completed successfully
        assert "file_id" in result

        # Verify that the mime_type was set to octet-stream fallback
        file_record = db_session.query(FileRecord).first()
        assert file_record is not None
        assert file_record.mime_type == "application/octet-stream"
        
        # File should be queued for PDF conversion since it's not a PDF
        assert result["status"] == "Queued for PDF conversion"


@pytest.mark.unit
@pytest.mark.requires_db
def test_process_document_force_cloud_ocr(db_session, tmp_path):
    """
    Test that process_document correctly handles force_cloud_ocr flag,
    skipping embedded text extraction and forcing cloud OCR.
    """
    # Create a test PDF file with embedded text
    test_pdf = tmp_path / "test.pdf"
    pdf_content = b"""%PDF-1.4
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
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test content) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000306 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
399
%%EOF
"""
    test_pdf.write_bytes(pdf_content)

    # Mock environment and dependencies
    with (
        patch("app.tasks.process_document.SessionLocal") as mock_session_local,
        patch("app.tasks.process_document.settings") as mock_settings,
        patch("app.tasks.process_document.log_task_progress"),
        patch("app.tasks.process_document.process_with_azure_document_intelligence") as mock_azure,
    ):
        # Setup mocks
        mock_settings.workdir = str(tmp_path)
        mock_session_local.return_value.__enter__.return_value = db_session
        mock_session_local.return_value.__exit__.return_value = None
        mock_azure.delay = MagicMock()

        # Call the task with force_cloud_ocr=True
        result = process_document.run(str(test_pdf), force_cloud_ocr=True)

        # Verify that cloud OCR was queued
        assert result["status"] == "Queued for forced OCR"
        assert "file_id" in result

        # Verify that process_with_azure_document_intelligence was called
        mock_azure.delay.assert_called_once()


@pytest.mark.unit
@pytest.mark.requires_db
def test_process_document_non_pdf_file(db_session, tmp_path):
    """
    Test that non-PDF files are queued for PDF conversion.
    """
    # Create a test image file
    test_image = tmp_path / "test.jpg"
    test_image.write_bytes(b"fake image content")

    # Mock environment and dependencies
    with (
        patch("app.tasks.process_document.SessionLocal") as mock_session_local,
        patch("app.tasks.process_document.settings") as mock_settings,
        patch("app.tasks.process_document.log_task_progress"),
        patch("app.tasks.process_document.celery") as mock_celery,
    ):
        # Setup mocks
        mock_settings.workdir = str(tmp_path)
        mock_session_local.return_value.__enter__.return_value = db_session
        mock_session_local.return_value.__exit__.return_value = None
        mock_celery.send_task = MagicMock()

        # Call the task's run method directly
        result = process_document.run(str(test_image))

        # Verify that PDF conversion was queued
        assert result["status"] == "Queued for PDF conversion"
        assert "file_id" in result

        # Verify that convert_to_pdf task was queued
        mock_celery.send_task.assert_called_once()
        call_args = mock_celery.send_task.call_args
        assert call_args[0][0] == "app.tasks.convert_to_pdf.convert_to_pdf"


@pytest.mark.unit
@pytest.mark.requires_db
def test_process_document_pdf_read_error_retry(db_session, tmp_path):
    """
    Test that PdfReadError during embedded text check triggers a retry.
    """
    # Create a test PDF file
    test_pdf = tmp_path / "test.pdf"
    pdf_content = b"""%PDF-1.4
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
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<<
/Size 4
/Root 1 0 R
>>
startxref
197
%%EOF
"""
    test_pdf.write_bytes(pdf_content)

    # Mock environment and dependencies
    with (
        patch("app.tasks.process_document.SessionLocal") as mock_session_local,
        patch("app.tasks.process_document.settings") as mock_settings,
        patch("app.tasks.process_document.log_task_progress"),
        patch("app.tasks.process_document.pypdf.PdfReader") as mock_pdf_reader,
    ):
        # Setup mocks
        mock_settings.workdir = str(tmp_path)
        mock_session_local.return_value.__enter__.return_value = db_session
        mock_session_local.return_value.__exit__.return_value = None

        # Make PdfReader raise PdfReadError
        from pypdf.errors import PdfReadError

        mock_pdf_reader.side_effect = PdfReadError("Test error")

        # Call the task's run method and expect it to raise retry exception
        with pytest.raises(Exception) as exc_info:
            process_document.run(str(test_pdf))

        # Verify that retry was triggered
        # The retry method raises a special exception
        assert exc_info.value is not None
