"""
Unit tests for OCR document processing tasks.

These tests verify OCR processing logic with mocked external AI/ML services
(OpenAI, Azure Document Intelligence). Tests cover typical and edge cases.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from azure.ai.documentintelligence.models import AnalyzeResult

from app.tasks.process_with_azure_document_intelligence import (
    AZURE_DOC_INTELLIGENCE_LIMITS,
    check_page_rotation,
    get_pdf_page_count,
    process_with_azure_document_intelligence,
)
from app.tasks.refine_text_with_gpt import refine_text_with_gpt
from app.tasks.rotate_pdf_pages import determine_rotation_angle, rotate_pdf_pages


@pytest.mark.unit
class TestProcessWithAzureDocumentIntelligence:
    """Tests for Azure Document Intelligence OCR processing."""

    @patch("app.tasks.process_with_azure_document_intelligence.log_task_progress")
    def test_successful_ocr_processing(self, mock_log, tmp_path):
        """Test successful OCR processing with Azure Document Intelligence."""
        # Create tmp directory and test PDF file
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        test_pdf = tmp_dir / "test.pdf"
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

        # Mock Azure Document Intelligence client and response
        mock_page = Mock()
        mock_page.angle = 0

        mock_result = Mock(spec=AnalyzeResult)
        mock_result.content = "This is extracted text from OCR"
        mock_result.model_id = "prebuilt-read"
        mock_result.pages = [mock_page]

        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        mock_poller.details = {"operation_id": "test-operation-123"}

        mock_client = Mock()
        mock_client.begin_analyze_document.return_value = mock_poller
        mock_client.get_analyze_result_pdf.return_value = iter([b"searchable pdf content"])

        with (
            patch(
                "app.tasks.process_with_azure_document_intelligence.document_intelligence_client",
                mock_client,
            ),
            patch("app.tasks.process_with_azure_document_intelligence.settings") as mock_settings,
            patch("app.tasks.process_with_azure_document_intelligence.rotate_pdf_pages") as mock_rotate,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_rotate.delay = MagicMock()

            # Run the task
            result = process_with_azure_document_intelligence.run(filename=test_pdf.name, file_id=1)

            # Verify results
            assert result["file"] == test_pdf.name
            assert result["cleaned_text"] == "This is extracted text from OCR"
            assert "searchable_pdf" in result

            # Verify Azure client was called correctly
            mock_client.begin_analyze_document.assert_called_once()
            mock_client.get_analyze_result_pdf.assert_called_once_with(
                model_id="prebuilt-read", result_id="test-operation-123"
            )

            # Verify rotate_pdf_pages was queued
            mock_rotate.delay.assert_called_once()
            call_args = mock_rotate.delay.call_args
            assert call_args[0][0] == test_pdf.name
            assert call_args[0][1] == "This is extracted text from OCR"
            assert call_args[0][3] == 1  # file_id

    @patch("app.tasks.process_with_azure_document_intelligence.log_task_progress")
    def test_file_not_found_error(self, mock_log, tmp_path):
        """Test that FileNotFoundError is raised when file doesn't exist."""
        with patch("app.tasks.process_with_azure_document_intelligence.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)

            with pytest.raises(FileNotFoundError) as exc_info:
                process_with_azure_document_intelligence.run(filename="nonexistent.pdf", file_id=1)

            assert "Local file not found" in str(exc_info.value)

    @patch("app.tasks.process_with_azure_document_intelligence.log_task_progress")
    def test_file_size_limit_exceeded(self, mock_log, tmp_path):
        """Test file size limit validation (500 MB)."""
        # Create tmp directory and test PDF file
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        test_pdf = tmp_dir / "large.pdf"
        test_pdf.write_bytes(b"dummy content")

        with (
            patch("app.tasks.process_with_azure_document_intelligence.settings") as mock_settings,
            patch("app.tasks.process_with_azure_document_intelligence.os.path.getsize") as mock_getsize,
        ):
            mock_settings.workdir = str(tmp_path)
            # Mock file size to be larger than 500 MB
            mock_getsize.return_value = AZURE_DOC_INTELLIGENCE_LIMITS["max_file_size_bytes"] + 1024

            result = process_with_azure_document_intelligence.run(filename=test_pdf.name, file_id=1)

            # Verify error response
            assert "error" in result
            assert "Size limit exceeded" in result["status"]
            assert "500 MB" in result["error"]

    @patch("app.tasks.process_with_azure_document_intelligence.log_task_progress")
    def test_page_count_limit_exceeded(self, mock_log, tmp_path):
        """Test page count limit validation (2000 pages)."""
        # Create tmp directory and test PDF file
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        test_pdf = tmp_dir / "many_pages.pdf"
        test_pdf.write_bytes(b"%PDF-1.4\n%%EOF")  # Minimal valid PDF

        with (
            patch("app.tasks.process_with_azure_document_intelligence.settings") as mock_settings,
            patch("app.tasks.process_with_azure_document_intelligence.get_pdf_page_count") as mock_page_count,
        ):
            mock_settings.workdir = str(tmp_path)
            # Mock page count to exceed limit
            mock_page_count.return_value = AZURE_DOC_INTELLIGENCE_LIMITS["max_pages"] + 1

            result = process_with_azure_document_intelligence.run(filename=test_pdf.name, file_id=1)

            # Verify error response
            assert "error" in result
            assert "Page limit exceeded" in result["status"]
            assert "2000 pages" in result["error"]

    @patch("app.tasks.process_with_azure_document_intelligence.log_task_progress")
    def test_page_count_unknown_proceeds_with_processing(self, mock_log, tmp_path):
        """Test that processing continues when page count cannot be determined."""
        # Create tmp directory and test PDF file
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        test_pdf = tmp_dir / "test.pdf"
        test_pdf.write_bytes(b"%PDF-1.4\n%%EOF")

        mock_page = Mock()
        mock_page.angle = 0

        mock_result = Mock(spec=AnalyzeResult)
        mock_result.content = "Test content"
        mock_result.model_id = "prebuilt-read"
        mock_result.pages = [mock_page]

        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        mock_poller.details = {"operation_id": "test-123"}

        mock_client = Mock()
        mock_client.begin_analyze_document.return_value = mock_poller
        mock_client.get_analyze_result_pdf.return_value = iter([b"content"])

        with (
            patch(
                "app.tasks.process_with_azure_document_intelligence.document_intelligence_client",
                mock_client,
            ),
            patch("app.tasks.process_with_azure_document_intelligence.settings") as mock_settings,
            patch("app.tasks.process_with_azure_document_intelligence.get_pdf_page_count") as mock_page_count,
            patch("app.tasks.process_with_azure_document_intelligence.rotate_pdf_pages"),
        ):
            mock_settings.workdir = str(tmp_path)
            # Return None to simulate page count determination failure
            mock_page_count.return_value = None

            # Should not raise an error
            result = process_with_azure_document_intelligence.run(filename=test_pdf.name, file_id=1)

            # Verify processing continued
            assert "error" not in result
            assert result["file"] == test_pdf.name

    @patch("app.tasks.process_with_azure_document_intelligence.log_task_progress")
    def test_page_rotation_detection(self, mock_log, tmp_path):
        """Test detection and logging of page rotation."""
        # Create tmp directory and test PDF
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        test_pdf = tmp_dir / "rotated.pdf"
        test_pdf.write_bytes(b"%PDF-1.4\n%%EOF")

        # Mock pages with different rotation angles
        mock_page1 = Mock()
        mock_page1.angle = 90

        mock_page2 = Mock()
        mock_page2.angle = 0

        mock_page3 = Mock()
        mock_page3.angle = 180

        mock_result = Mock(spec=AnalyzeResult)
        mock_result.content = "Rotated document text"
        mock_result.model_id = "prebuilt-read"
        mock_result.pages = [mock_page1, mock_page2, mock_page3]

        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        mock_poller.details = {"operation_id": "test-456"}

        mock_client = Mock()
        mock_client.begin_analyze_document.return_value = mock_poller
        mock_client.get_analyze_result_pdf.return_value = iter([b"content"])

        with (
            patch(
                "app.tasks.process_with_azure_document_intelligence.document_intelligence_client",
                mock_client,
            ),
            patch("app.tasks.process_with_azure_document_intelligence.settings") as mock_settings,
            patch("app.tasks.process_with_azure_document_intelligence.rotate_pdf_pages") as mock_rotate,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_rotate.delay = MagicMock()

            result = process_with_azure_document_intelligence.run(filename=test_pdf.name, file_id=2)

            # Verify rotation data was passed correctly
            mock_rotate.delay.assert_called_once()
            call_args = mock_rotate.delay.call_args
            rotation_data = call_args[0][2]

            # Check rotation data structure (page indices as integers)
            assert 0 in rotation_data and rotation_data[0] == 90
            assert 1 not in rotation_data  # Page 2 has no rotation
            assert 2 in rotation_data and rotation_data[2] == 180

    @patch("app.tasks.process_with_azure_document_intelligence.log_task_progress")
    def test_azure_api_error_handling(self, mock_log, tmp_path):
        """Test error handling when Azure API fails."""
        # Create tmp directory and test PDF
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        test_pdf = tmp_dir / "test.pdf"
        test_pdf.write_bytes(b"%PDF-1.4\n%%EOF")

        mock_client = Mock()
        mock_client.begin_analyze_document.side_effect = Exception("Azure API connection failed")

        with (
            patch(
                "app.tasks.process_with_azure_document_intelligence.document_intelligence_client",
                mock_client,
            ),
            patch("app.tasks.process_with_azure_document_intelligence.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)

            # Should raise the exception
            with pytest.raises(Exception) as exc_info:
                process_with_azure_document_intelligence.run(filename=test_pdf.name, file_id=1)

            assert "Azure API connection failed" in str(exc_info.value)

    def test_get_pdf_page_count_success(self, tmp_path):
        """Test successful page count extraction from PDF."""
        # Create a PDF with text content
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
/Kids [3 0 R 4 0 R]
/Count 2
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
>>
endobj
4 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
>>
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000119 00000 n
0000000182 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
245
%%EOF
"""
        test_pdf.write_bytes(pdf_content)

        page_count = get_pdf_page_count(str(test_pdf))
        assert page_count == 2

    def test_get_pdf_page_count_error(self, tmp_path):
        """Test page count returns None on error."""
        # Create an invalid PDF file
        test_pdf = tmp_path / "invalid.pdf"
        test_pdf.write_bytes(b"not a valid pdf")

        page_count = get_pdf_page_count(str(test_pdf))
        assert page_count is None

    def test_check_page_rotation_with_rotated_pages(self):
        """Test check_page_rotation with rotated pages."""
        # Mock pages with rotation
        mock_page1 = Mock()
        mock_page1.angle = 90

        mock_page2 = Mock()
        mock_page2.angle = 0

        mock_result = Mock()
        mock_result.pages = [mock_page1, mock_page2]

        rotation_data = check_page_rotation(mock_result, "test.pdf")

        assert 0 in rotation_data
        assert rotation_data[0] == 90
        assert 1 not in rotation_data  # No rotation for page 2

    def test_check_page_rotation_no_pages(self):
        """Test check_page_rotation with no page information."""
        mock_result = Mock()
        mock_result.pages = None

        rotation_data = check_page_rotation(mock_result, "test.pdf")

        assert rotation_data == {}

    def test_check_page_rotation_missing_angle_attribute(self):
        """Test check_page_rotation when pages don't have angle attribute."""
        mock_page = Mock(spec=[])  # Page without 'angle' attribute

        mock_result = Mock()
        mock_result.pages = [mock_page]

        rotation_data = check_page_rotation(mock_result, "test.pdf")

        assert rotation_data == {}


@pytest.mark.unit
class TestRefineTextWithGPT:
    """Tests for AI provider text refinement task."""

    @patch("app.tasks.refine_text_with_gpt.log_task_progress")
    def test_successful_text_refinement(self, mock_log):
        """Test successful text refinement with AI provider."""
        raw_text = "This is s0me text with OCR err0rs"
        filename = "test.pdf"
        cleaned = "This is some text with OCR errors"

        # Import the module to patch the correct function
        from app.tasks import extract_metadata_with_gpt as metadata_module

        mock_provider = MagicMock()
        mock_provider.chat_completion.return_value = cleaned

        with (
            patch("app.tasks.refine_text_with_gpt.get_ai_provider", return_value=mock_provider),
            patch.object(metadata_module, "extract_metadata_with_gpt") as mock_extract,
            patch("app.tasks.refine_text_with_gpt.settings") as mock_settings,
        ):
            mock_settings.openai_model = "gpt-4"
            mock_settings.ai_model = None
            mock_extract.delay = MagicMock()

            result = refine_text_with_gpt.run(filename, raw_text)

            # Verify results
            assert result["filename"] == filename
            assert result["cleaned_text"] == cleaned

            # Verify AI provider was called correctly
            mock_provider.chat_completion.assert_called_once()
            call_kwargs = mock_provider.chat_completion.call_args[1]
            assert len(call_kwargs["messages"]) == 2
            assert call_kwargs["messages"][1]["content"] == raw_text

            # Verify metadata extraction was queued
            mock_extract.delay.assert_called_once_with(filename, cleaned)

    @patch("app.tasks.refine_text_with_gpt.log_task_progress")
    def test_openai_api_error(self, mock_log):
        """Test error handling when AI provider call fails."""
        raw_text = "Test text"
        filename = "test.pdf"

        mock_provider = MagicMock()
        mock_provider.chat_completion.side_effect = Exception("OpenAI API error")

        with (
            patch("app.tasks.refine_text_with_gpt.get_ai_provider", return_value=mock_provider),
            patch("app.tasks.refine_text_with_gpt.settings") as mock_settings,
        ):
            mock_settings.openai_model = "gpt-4"
            mock_settings.ai_model = None

            # Should raise the exception
            with pytest.raises(Exception) as exc_info:
                refine_text_with_gpt.run(filename, raw_text)

            assert "OpenAI API error" in str(exc_info.value)


@pytest.mark.unit
class TestRotatePdfPages:
    """Tests for PDF page rotation task."""

    def test_determine_rotation_angle_exact_90(self):
        """Test rotation angle determination for exact 90 degrees."""
        angle = determine_rotation_angle(90)
        assert angle == 270  # PyPDF2 uses clockwise, so 360 - 90 = 270

    def test_determine_rotation_angle_exact_180(self):
        """Test rotation angle determination for exact 180 degrees."""
        angle = determine_rotation_angle(180)
        assert angle == 180  # 360 - 180 = 180

    def test_determine_rotation_angle_exact_270(self):
        """Test rotation angle determination for exact 270 degrees."""
        angle = determine_rotation_angle(270)
        assert angle == 90  # 360 - 270 = 90

    def test_determine_rotation_angle_near_90(self):
        """Test rotation angle determination for angle near 90 degrees."""
        angle = determine_rotation_angle(88)  # Within 5° of 90
        assert angle == 270

        angle = determine_rotation_angle(93)  # Within 5° of 90
        assert angle == 270

    def test_determine_rotation_angle_small_angle(self):
        """Test that very small angles are not rotated."""
        angle = determine_rotation_angle(0.5)
        assert angle == 0

        angle = determine_rotation_angle(359.5)
        assert angle == 0

    def test_determine_rotation_angle_arbitrary(self):
        """Test rotation angle determination for arbitrary angles."""
        # 45 degrees should round to nearest 90-degree increment
        angle = determine_rotation_angle(45)
        # Round(45/90) = Round(0.5) = 0, so 0 * 90 = 0
        assert angle == 0

        # 135 degrees should round to 180
        angle = determine_rotation_angle(135)
        # Round(135/90) = Round(1.5) = 2, so 2 * 90 = 180
        assert angle == 180

    @patch("app.tasks.rotate_pdf_pages.log_task_progress")
    def test_rotate_pdf_pages_with_rotation(self, mock_log, tmp_path):
        """Test PDF rotation with rotation data."""
        # Create tmp directory and test PDF
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        test_pdf = tmp_dir / "test.pdf"
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

        rotation_data = {0: 90}  # Rotate first page by 90 degrees
        extracted_text = "Test text"

        with (
            patch("app.tasks.rotate_pdf_pages.settings") as mock_settings,
            patch("app.tasks.rotate_pdf_pages.extract_metadata_with_gpt") as mock_extract,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_extract.delay = MagicMock()

            result = rotate_pdf_pages.run(
                filename=test_pdf.name,
                extracted_text=extracted_text,
                rotation_data=rotation_data,
                file_id=1,
            )

            # Verify results
            assert result["file"] == test_pdf.name
            assert result["status"] == "rotated"
            assert "applied_rotations" in result
            assert "0" in result["applied_rotations"]

            # Verify metadata extraction was queued
            mock_extract.delay.assert_called_once_with(test_pdf.name, extracted_text, 1)

    @patch("app.tasks.rotate_pdf_pages.log_task_progress")
    def test_rotate_pdf_pages_no_rotation_needed(self, mock_log, tmp_path):
        """Test PDF rotation when no rotation is needed."""
        # Create tmp directory and test PDF
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        test_pdf = tmp_dir / "test.pdf"
        test_pdf.write_bytes(b"%PDF-1.4\n%%EOF")

        extracted_text = "Test text"

        with (
            patch("app.tasks.rotate_pdf_pages.settings") as mock_settings,
            patch("app.tasks.rotate_pdf_pages.extract_metadata_with_gpt") as mock_extract,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_extract.delay = MagicMock()

            # Call with no rotation data
            result = rotate_pdf_pages.run(
                filename=test_pdf.name,
                extracted_text=extracted_text,
                rotation_data=None,
                file_id=1,
            )

            # Verify results
            assert result["status"] == "no_rotation_needed"

            # Verify metadata extraction was still queued
            mock_extract.delay.assert_called_once()

    @patch("app.tasks.rotate_pdf_pages.log_task_progress")
    def test_rotate_pdf_pages_zero_rotations(self, mock_log, tmp_path):
        """Test PDF rotation when rotation data contains only zero angles."""
        # Create tmp directory and test PDF
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        test_pdf = tmp_dir / "test.pdf"
        test_pdf.write_bytes(b"%PDF-1.4\n%%EOF")

        rotation_data = {0: 0, 1: 0}  # All pages have 0 rotation
        extracted_text = "Test text"

        with (
            patch("app.tasks.rotate_pdf_pages.settings") as mock_settings,
            patch("app.tasks.rotate_pdf_pages.extract_metadata_with_gpt") as mock_extract,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_extract.delay = MagicMock()

            result = rotate_pdf_pages.run(
                filename=test_pdf.name,
                extracted_text=extracted_text,
                rotation_data=rotation_data,
                file_id=1,
            )

            # Verify no rotation was applied
            assert result["status"] == "no_rotation_needed"

    @patch("app.tasks.rotate_pdf_pages.log_task_progress")
    def test_rotate_pdf_pages_file_not_found(self, mock_log, tmp_path):
        """Test error handling when PDF file is not found."""
        # Create tmp directory but no PDF
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()

        with (
            patch("app.tasks.rotate_pdf_pages.settings") as mock_settings,
            patch("app.tasks.rotate_pdf_pages.extract_metadata_with_gpt") as mock_extract,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_extract.delay = MagicMock()

            # The function catches FileNotFoundError and returns error status
            result = rotate_pdf_pages.run(
                filename="nonexistent.pdf",
                extracted_text="text",
                rotation_data={0: 90},
                file_id=1,
            )

            # Verify error handling
            assert result["status"] == "rotation_failed"
            assert "error" in result
            assert "PDF file not found" in result["error"]

            # Verify metadata extraction was still queued
            mock_extract.delay.assert_called_once()

    @patch("app.tasks.rotate_pdf_pages.log_task_progress")
    def test_rotate_pdf_pages_continues_on_error(self, mock_log, tmp_path):
        """Test that metadata extraction continues even if rotation fails."""
        # Create tmp directory and invalid PDF
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        test_pdf = tmp_dir / "test.pdf"
        test_pdf.write_bytes(b"invalid pdf")

        rotation_data = {0: 90}
        extracted_text = "Test text"

        with (
            patch("app.tasks.rotate_pdf_pages.settings") as mock_settings,
            patch("app.tasks.rotate_pdf_pages.extract_metadata_with_gpt") as mock_extract,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_extract.delay = MagicMock()

            result = rotate_pdf_pages.run(
                filename=test_pdf.name,
                extracted_text=extracted_text,
                rotation_data=rotation_data,
                file_id=1,
            )

            # Verify error was handled
            assert result["status"] == "rotation_failed"
            assert "error" in result

            # Verify metadata extraction was still queued
            mock_extract.delay.assert_called_once()

    @patch("app.tasks.rotate_pdf_pages.log_task_progress")
    def test_rotate_pdf_pages_with_string_keys(self, mock_log, tmp_path):
        """Test that rotation data with string keys is properly handled."""
        # Create tmp directory and test PDF
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        test_pdf = tmp_dir / "test.pdf"
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

        # Use string keys instead of integer keys
        rotation_data = {"0": "90"}
        extracted_text = "Test text"

        with (
            patch("app.tasks.rotate_pdf_pages.settings") as mock_settings,
            patch("app.tasks.rotate_pdf_pages.extract_metadata_with_gpt") as mock_extract,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_extract.delay = MagicMock()

            result = rotate_pdf_pages.run(
                filename=test_pdf.name,
                extracted_text=extracted_text,
                rotation_data=rotation_data,
                file_id=1,
            )

            # Verify rotation was applied despite string keys
            assert result["status"] == "rotated"
            assert "applied_rotations" in result
