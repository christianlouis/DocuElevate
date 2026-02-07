"""
Unit tests for verifying that original filenames are preserved during upload.

These tests verify the fix for the issue where uploaded files do not maintain
their original file names.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session

from app.tasks.process_document import process_document
from app.models import FileRecord


@pytest.mark.unit
@pytest.mark.requires_db
def test_process_document_preserves_original_filename_parameter(db_session, tmp_path):
    """
    Test that process_document correctly uses the original_filename parameter
    when provided, instead of extracting it from the file path.
    """
    # Create a test PDF file with a UUID-based name
    test_pdf = tmp_path / "e64b2825-9ff2-486b-aff1-08af2957140b.pdf"
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
    
    # The original filename that the user uploaded
    original_filename = "Apostille Sverige.pdf"

    # Mock environment and dependencies
    with patch("app.tasks.process_document.SessionLocal") as mock_session_local, \
         patch("app.tasks.process_document.settings") as mock_settings, \
         patch("app.tasks.process_document.log_task_progress"), \
         patch("app.tasks.process_document.extract_metadata_with_gpt") as mock_extract:

        # Setup mocks
        mock_settings.workdir = str(tmp_path)
        mock_session_local.return_value.__enter__.return_value = db_session
        mock_session_local.return_value.__exit__.return_value = None
        mock_extract.delay = MagicMock()

        # Call the task with the original_filename parameter
        result = process_document.run(str(test_pdf), original_filename=original_filename)

        # Verify that the task completed successfully
        assert "file_id" in result
        assert result["status"] == "Text extracted locally"

        # Verify that a FileRecord was created with the correct original filename
        file_record = db_session.query(FileRecord).first()
        assert file_record is not None
        
        # This is the key assertion - the original filename should be preserved
        assert file_record.original_filename == original_filename
        # The filename should NOT be the UUID-based filename
        assert file_record.original_filename != "e64b2825-9ff2-486b-aff1-08af2957140b.pdf"


@pytest.mark.unit
@pytest.mark.requires_db
def test_process_document_fallback_to_basename_when_no_parameter(db_session, tmp_path):
    """
    Test that process_document falls back to extracting filename from path
    when original_filename parameter is not provided (backward compatibility).
    """
    # Create a test PDF file
    test_pdf = tmp_path / "test_document.pdf"
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
    with patch("app.tasks.process_document.SessionLocal") as mock_session_local, \
         patch("app.tasks.process_document.settings") as mock_settings, \
         patch("app.tasks.process_document.log_task_progress"), \
         patch("app.tasks.process_document.extract_metadata_with_gpt") as mock_extract:

        # Setup mocks
        mock_settings.workdir = str(tmp_path)
        mock_session_local.return_value.__enter__.return_value = db_session
        mock_session_local.return_value.__exit__.return_value = None
        mock_extract.delay = MagicMock()

        # Call the task WITHOUT the original_filename parameter (old behavior)
        result = process_document.run(str(test_pdf))

        # Verify that the task completed successfully
        assert "file_id" in result

        # Verify that the filename was extracted from the path
        file_record = db_session.query(FileRecord).first()
        assert file_record is not None
        assert file_record.original_filename == "test_document.pdf"
