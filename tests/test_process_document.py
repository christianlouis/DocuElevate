"""
Unit tests for the process_document task.

These tests verify that the process_document task correctly handles file processing
and doesn't cause DetachedInstanceError when accessing database objects.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session

from app.tasks.process_document import process_document
from app.models import FileRecord


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
    with patch("app.tasks.process_document.SessionLocal") as mock_session_local, patch(
        "app.tasks.process_document.settings"
    ) as mock_settings, patch("app.tasks.process_document.log_task_progress"), patch(
        "app.tasks.process_document.extract_metadata_with_gpt"
    ) as mock_extract:

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
    with patch("app.tasks.process_document.SessionLocal") as mock_session_local, patch(
        "app.tasks.process_document.log_task_progress"
    ):

        # Setup mocks
        mock_session_local.return_value.__enter__.return_value = db_session
        mock_session_local.return_value.__exit__.return_value = None

        # Call the task's run method directly
        result = process_document.run(str(test_pdf))

        # Verify that duplicate was detected
        assert result["status"] == "duplicate_file"
        assert result["file_id"] == existing_id

        # Verify only one FileRecord exists
        assert db_session.query(FileRecord).count() == 1


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
    with patch("app.tasks.process_document.SessionLocal") as mock_session_local, patch(
        "app.tasks.process_document.settings"
    ) as mock_settings, patch("app.tasks.process_document.log_task_progress"), patch(
        "app.tasks.process_document.process_with_azure_document_intelligence"
    ) as mock_azure:

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
