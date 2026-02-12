"""
Tests for document storage reorganization features.

Tests the new functionality for storing immutable originals and processed copies,
collision handling, and forced Cloud OCR reprocessing.
"""

import os
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models import FileRecord


@pytest.mark.unit
@pytest.mark.requires_db
class TestImmutableOriginalStorage:
    """Test that original files are saved immutably to /workdir/original"""

    def test_new_file_saves_original_copy(self, db_session, tmp_path):
        """Test that a new file creates an immutable original copy"""
        from app.tasks.process_document import process_document
        
        # Create test PDF
        test_pdf = tmp_path / "test_input.pdf"
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
        
        # Setup mocks
        with (
            patch("app.tasks.process_document.SessionLocal") as mock_session_local,
            patch("app.tasks.process_document.settings") as mock_settings,
            patch("app.tasks.process_document.log_task_progress"),
            patch("app.tasks.process_document.extract_metadata_with_gpt") as mock_extract,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_session_local.return_value.__enter__.return_value = db_session
            mock_session_local.return_value.__exit__.return_value = None
            mock_extract.delay = MagicMock()
            
            # Call process_document
            result = process_document(str(test_pdf), original_filename="test_input.pdf")
            
            # Verify original directory was created
            original_dir = tmp_path / "original"
            assert original_dir.exists()
            
            # Verify an original file was saved
            original_files = list(original_dir.glob("*.pdf"))
            assert len(original_files) > 0
            
            # Verify database record has original_file_path
            file_record = db_session.query(FileRecord).first()
            assert file_record is not None
            assert file_record.original_file_path is not None
            assert "original" in file_record.original_file_path

    def test_reprocessing_preserves_original(self, db_session, tmp_path):
        """Test that reprocessing doesn't create a duplicate original"""
        from app.tasks.process_document import process_document

        # Create test file and original with valid PDF content
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
        test_pdf = tmp_path / "test.pdf"
        test_pdf.write_bytes(pdf_content)

        original_dir = tmp_path / "original"
        original_dir.mkdir()
        original_file = original_dir / "existing-original.pdf"
        original_file.write_bytes(pdf_content)
        
        # Create existing file record
        file_record = FileRecord(
            filehash="abc123",
            original_filename="test.pdf",
            local_filename=str(test_pdf),
            original_file_path=str(original_file),
            file_size=100,
            mime_type="application/pdf"
        )
        db_session.add(file_record)
        db_session.commit()
        
        # Setup mocks
        with (
            patch("app.tasks.process_document.SessionLocal") as mock_session_local,
            patch("app.tasks.process_document.settings") as mock_settings,
            patch("app.tasks.process_document.log_task_progress"),
            patch("app.tasks.process_document.extract_metadata_with_gpt") as mock_extract,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_session_local.return_value.__enter__.return_value = db_session
            mock_session_local.return_value.__exit__.return_value = None
            mock_extract.delay = MagicMock()
            
            # Reprocess with file_id
            original_count = len(list(original_dir.glob("*.pdf")))
            process_document(str(test_pdf), file_id=file_record.id)
            
            # Should not create new original file
            new_count = len(list(original_dir.glob("*.pdf")))
            assert new_count == original_count


@pytest.mark.unit
class TestCollisionHandling:
    """Test filename collision handling with -0001 suffix format"""

    def test_collision_handling_in_processed_dir(self, tmp_path):
        """Test that collision handling works in processed directory"""
        from app.utils.filename_utils import get_unique_filepath_with_counter
        
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        
        # Create first file
        (processed_dir / "2024-01-01_Invoice.pdf").touch()
        
        # Get unique path for same filename
        result = get_unique_filepath_with_counter(str(processed_dir), "2024-01-01_Invoice")
        
        assert "2024-01-01_Invoice-0001.pdf" in result
        assert os.path.exists(str(processed_dir / "2024-01-01_Invoice.pdf"))


@pytest.mark.unit
class TestMetadataAugmentation:
    """Test that metadata JSON includes file path references"""

    def test_metadata_includes_file_paths(self, tmp_path):
        """Test that persisted metadata includes original and processed paths"""
        from app.tasks.embed_metadata_into_pdf import persist_metadata
        
        metadata = {
            "filename": "2024-01-01_Invoice",
            "document_type": "Invoice",
            "tags": ["finance", "2024"]
        }
        
        processed_file = tmp_path / "processed" / "2024-01-01_Invoice.pdf"
        processed_file.parent.mkdir(parents=True)
        processed_file.touch()
        
        original_path = "/workdir/original/abc123.pdf"
        processed_path = str(processed_file)
        
        json_path = persist_metadata(
            metadata, 
            str(processed_file),
            original_file_path=original_path,
            processed_file_path=processed_path
        )
        
        # Verify JSON was created
        assert os.path.exists(json_path)
        
        # Verify content
        with open(json_path, 'r') as f:
            saved_metadata = json.load(f)
        
        assert "original_file_path" in saved_metadata
        assert saved_metadata["original_file_path"] == original_path
        assert "processed_file_path" in saved_metadata
        assert saved_metadata["processed_file_path"] == processed_path
        assert saved_metadata["filename"] == "2024-01-01_Invoice"


@pytest.mark.unit
@pytest.mark.requires_db
class TestForceCloudOCR:
    """Test forced Cloud OCR reprocessing functionality"""

    def test_force_cloud_ocr_parameter(self, db_session, tmp_path):
        """Test that force_cloud_ocr parameter skips local text extraction"""
        from app.tasks.process_document import process_document
        
        # Create PDF with embedded text
        test_pdf = tmp_path / "with_text.pdf"
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
(Embedded text here) Tj
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
        
        with (
            patch("app.tasks.process_document.SessionLocal") as mock_session_local,
            patch("app.tasks.process_document.settings") as mock_settings,
            patch("app.tasks.process_document.log_task_progress"),
            patch("app.tasks.process_document.process_with_azure_document_intelligence") as mock_azure,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_session_local.return_value.__enter__.return_value = db_session
            mock_session_local.return_value.__exit__.return_value = None
            mock_azure.delay = MagicMock()
            
            # Process with force_cloud_ocr=True
            result = process_document(str(test_pdf), force_cloud_ocr=True)
            
            # Should queue Azure OCR, not local extraction
            mock_azure.delay.assert_called_once()
            assert result["status"] == "Queued for forced OCR"
