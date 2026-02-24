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


@pytest.mark.unit
class TestMistralOCRProvider:
    """Tests for MistralOCRProvider – Mistral native OCR API integration."""

    def _make_provider(self):
        from app.utils.ocr_provider import MistralOCRProvider

        return MistralOCRProvider()

    # ------------------------------------------------------------------
    # Helpers: build mock response objects
    # ------------------------------------------------------------------

    def _mock_response(self, json_data: dict, status_code: int = 200):
        mock_resp = Mock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = json_data
        mock_resp.raise_for_status = Mock()
        return mock_resp

    def _mock_error_response(self, status_code: int = 422):
        from requests import HTTPError

        mock_resp = Mock()
        mock_resp.status_code = status_code
        mock_resp.raise_for_status.side_effect = HTTPError(response=mock_resp)
        return mock_resp

    # ------------------------------------------------------------------
    # Missing API key
    # ------------------------------------------------------------------

    def test_missing_api_key_raises(self, tmp_path):
        """ValueError is raised when MISTRAL_API_KEY is not configured."""
        provider = self._make_provider()
        dummy_pdf = tmp_path / "doc.pdf"
        dummy_pdf.write_bytes(b"%PDF-1.4\n%%EOF")

        with patch("app.utils.ocr_provider.settings") as mock_settings:
            mock_settings.mistral_api_key = None
            mock_settings.mistral_ocr_model = None

            with pytest.raises(ValueError, match="MISTRAL_API_KEY must be set"):
                provider.process(str(dummy_pdf))

    # ------------------------------------------------------------------
    # PDF workflow
    # ------------------------------------------------------------------

    def test_pdf_uses_document_url_workflow(self, tmp_path):
        """PDF files are uploaded then processed via document_url."""
        provider = self._make_provider()
        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\n%%EOF")

        upload_resp = self._mock_response({"id": "file-abc123"})
        signed_url_resp = self._mock_response({"url": "https://signed.example.com/doc"})
        ocr_resp = self._mock_response({"pages": [{"markdown": "Hello PDF World"}]})

        with (
            patch("app.utils.ocr_provider.settings") as mock_settings,
            patch("requests.post", side_effect=[upload_resp, ocr_resp]) as mock_post,
            patch("requests.get", return_value=signed_url_resp) as mock_get,
        ):
            mock_settings.mistral_api_key = "test-key"
            mock_settings.mistral_ocr_model = "mistral-ocr-latest"

            result = provider.process(str(pdf_file))

        assert result.provider == "mistral"
        assert result.text == "Hello PDF World"

        # First POST should be the file upload
        upload_call = mock_post.call_args_list[0]
        assert "/files" in upload_call[0][0]
        assert upload_call[1]["data"] == {"purpose": "ocr"}

        # GET should fetch the signed URL
        get_call = mock_get.call_args_list[0]
        assert "file-abc123" in get_call[0][0]

        # Second POST should be the OCR call
        ocr_call = mock_post.call_args_list[1]
        assert "/ocr" in ocr_call[0][0]
        ocr_json = ocr_call[1]["json"]
        assert ocr_json["document"]["type"] == "document_url"
        assert ocr_json["document"]["document_url"] == "https://signed.example.com/doc"

    def test_pdf_multi_page_text_joined(self, tmp_path):
        """Text from multiple pages is joined with double newlines."""
        provider = self._make_provider()
        pdf_file = tmp_path / "multi.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\n%%EOF")

        upload_resp = self._mock_response({"id": "file-xyz"})
        signed_url_resp = self._mock_response({"url": "https://signed.example.com/multi"})
        ocr_resp = self._mock_response({"pages": [{"markdown": "Page one text"}, {"markdown": "Page two text"}]})

        with (
            patch("app.utils.ocr_provider.settings") as mock_settings,
            patch("requests.post", side_effect=[upload_resp, ocr_resp]),
            patch("requests.get", return_value=signed_url_resp),
        ):
            mock_settings.mistral_api_key = "test-key"
            mock_settings.mistral_ocr_model = "mistral-ocr-latest"

            result = provider.process(str(pdf_file))

        assert "Page one text" in result.text
        assert "Page two text" in result.text

    # ------------------------------------------------------------------
    # Image workflow
    # ------------------------------------------------------------------

    def test_image_uses_image_url_workflow(self, tmp_path):
        """Image files are base64-encoded and passed as image_url (not document_url)."""
        provider = self._make_provider()
        img_file = tmp_path / "photo.jpg"
        img_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 20)  # minimal JPEG bytes

        ocr_resp = self._mock_response({"pages": [{"markdown": "Image text here"}]})

        with (
            patch("app.utils.ocr_provider.settings") as mock_settings,
            patch("requests.post", return_value=ocr_resp) as mock_post,
            patch("requests.get") as mock_get,
        ):
            mock_settings.mistral_api_key = "test-key"
            mock_settings.mistral_ocr_model = "mistral-ocr-latest"

            result = provider.process(str(img_file))

        assert result.provider == "mistral"
        assert result.text == "Image text here"

        # Should only make a single POST (no file upload step)
        assert mock_post.call_count == 1
        assert mock_get.call_count == 0

        ocr_call = mock_post.call_args_list[0]
        assert "/ocr" in ocr_call[0][0]
        ocr_json = ocr_call[1]["json"]
        assert ocr_json["document"]["type"] == "image_url"
        assert ocr_json["document"]["image_url"].startswith("data:image/jpeg;base64,")

    # ------------------------------------------------------------------
    # Unsupported file type
    # ------------------------------------------------------------------

    def test_unsupported_mime_type_raises(self, tmp_path):
        """ValueError is raised for unsupported file types."""
        provider = self._make_provider()
        txt_file = tmp_path / "document.txt"
        txt_file.write_text("hello world")

        with patch("app.utils.ocr_provider.settings") as mock_settings:
            mock_settings.mistral_api_key = "test-key"
            mock_settings.mistral_ocr_model = "mistral-ocr-latest"

            with pytest.raises(ValueError, match="Unsupported file type"):
                provider.process(str(txt_file))

    def test_unknown_extension_pdf_magic_bytes_detected(self, tmp_path):
        """Files without extension are identified as PDF via magic bytes."""
        provider = self._make_provider()
        no_ext_file = tmp_path / "nodotfile"
        no_ext_file.write_bytes(b"%PDF-1.4\n%%EOF")

        upload_resp = self._mock_response({"id": "file-magic"})
        signed_url_resp = self._mock_response({"url": "https://signed.example.com/magic"})
        ocr_resp = self._mock_response({"pages": [{"markdown": "Magic PDF"}]})

        with (
            patch("app.utils.ocr_provider.settings") as mock_settings,
            patch("requests.post", side_effect=[upload_resp, ocr_resp]),
            patch("requests.get", return_value=signed_url_resp),
        ):
            mock_settings.mistral_api_key = "test-key"
            mock_settings.mistral_ocr_model = "mistral-ocr-latest"

            result = provider.process(str(no_ext_file))

        assert result.text == "Magic PDF"

    def test_unknown_extension_non_pdf_magic_bytes_raises(self, tmp_path):
        """Files without extension that aren't PDFs raise ValueError."""
        provider = self._make_provider()
        unknown_file = tmp_path / "unknownfile"
        unknown_file.write_bytes(b"\x00\x01\x02\x03\x04")

        with patch("app.utils.ocr_provider.settings") as mock_settings:
            mock_settings.mistral_api_key = "test-key"
            mock_settings.mistral_ocr_model = "mistral-ocr-latest"

            with pytest.raises(ValueError, match="Cannot determine file type"):
                provider.process(str(unknown_file))

    # ------------------------------------------------------------------
    # Upload / API error propagation
    # ------------------------------------------------------------------

    def test_upload_failure_raises_http_error(self, tmp_path):
        """HTTPError from the Files API upload is propagated to the caller."""
        from requests import HTTPError

        provider = self._make_provider()
        pdf_file = tmp_path / "bad.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\n%%EOF")

        with (
            patch("app.utils.ocr_provider.settings") as mock_settings,
            patch("requests.post", return_value=self._mock_error_response(status_code=401)),
        ):
            mock_settings.mistral_api_key = "bad-key"
            mock_settings.mistral_ocr_model = "mistral-ocr-latest"

            with pytest.raises(HTTPError):
                provider.process(str(pdf_file))

    def test_ocr_api_failure_raises_http_error(self, tmp_path):
        """HTTPError from the /ocr endpoint is propagated to the caller."""
        from requests import HTTPError

        provider = self._make_provider()
        pdf_file = tmp_path / "bad.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\n%%EOF")

        upload_resp = self._mock_response({"id": "file-err"})
        signed_url_resp = self._mock_response({"url": "https://signed.example.com/err"})

        with (
            patch("app.utils.ocr_provider.settings") as mock_settings,
            patch("requests.post", side_effect=[upload_resp, self._mock_error_response(status_code=422)]),
            patch("requests.get", return_value=signed_url_resp),
        ):
            mock_settings.mistral_api_key = "test-key"
            mock_settings.mistral_ocr_model = "mistral-ocr-latest"

            with pytest.raises(HTTPError):
                provider.process(str(pdf_file))


@pytest.mark.unit
class TestEmbedTextLayer:
    """Tests for the embed_text_layer utility function."""

    def _make_pdf(self, tmp_path, name: str = "test.pdf") -> str:
        """Create a minimal but valid-ish PDF file for testing."""
        pdf_path = tmp_path / name
        pdf_path.write_bytes(
            b"%PDF-1.4\n"
            b"1 0 obj\n<</Type /Catalog /Pages 2 0 R>>\nendobj\n"
            b"2 0 obj\n<</Type /Pages /Kids [3 0 R] /Count 1>>\nendobj\n"
            b"3 0 obj\n<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]>>\nendobj\n"
            b"xref\n0 4\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"0000000115 00000 n \n"
            b"trailer\n<</Size 4 /Root 1 0 R>>\n"
            b"startxref\n190\n%%EOF\n"
        )
        return str(pdf_path)

    def test_missing_input_raises_file_not_found(self, tmp_path):
        """FileNotFoundError is raised when the input PDF does not exist."""
        from app.utils.ocr_provider import embed_text_layer

        with pytest.raises(FileNotFoundError, match="embed_text_layer"):
            embed_text_layer("/nonexistent/path.pdf", str(tmp_path / "out.pdf"))

    def test_returns_false_when_ocrmypdf_not_on_path(self, tmp_path):
        """Returns False (and logs a warning) when ocrmypdf is not installed."""
        from app.utils.ocr_provider import embed_text_layer

        pdf = self._make_pdf(tmp_path)

        with patch("shutil.which", return_value=None):
            result = embed_text_layer(pdf, str(tmp_path / "out.pdf"))

        assert result is False

    def test_returns_true_on_success(self, tmp_path):
        """Returns True when ocrmypdf exits with code 0."""
        from app.utils.ocr_provider import embed_text_layer

        pdf = self._make_pdf(tmp_path)
        output = str(tmp_path / "out.pdf")

        mock_proc = Mock()
        mock_proc.returncode = 0
        mock_proc.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/ocrmypdf"),
            patch("subprocess.run", return_value=mock_proc) as mock_run,
        ):
            result = embed_text_layer(pdf, output, language="eng")

        assert result is True
        args = mock_run.call_args[0][0]
        assert "--skip-text" in args
        assert "-l" in args
        assert "eng" in args

    def test_returns_false_on_nonzero_exit(self, tmp_path):
        """Returns False when ocrmypdf exits with a non-zero code."""
        from app.utils.ocr_provider import embed_text_layer

        pdf = self._make_pdf(tmp_path)

        mock_proc = Mock()
        mock_proc.returncode = 1
        mock_proc.stderr = "some error"

        with (
            patch("shutil.which", return_value="/usr/bin/ocrmypdf"),
            patch("subprocess.run", return_value=mock_proc),
        ):
            result = embed_text_layer(pdf, str(tmp_path / "out.pdf"))

        assert result is False

    def test_returns_false_on_timeout(self, tmp_path):
        """Returns False when ocrmypdf times out."""
        import subprocess

        from app.utils.ocr_provider import embed_text_layer

        pdf = self._make_pdf(tmp_path)

        with (
            patch("shutil.which", return_value="/usr/bin/ocrmypdf"),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ocrmypdf", timeout=600)),
        ):
            result = embed_text_layer(pdf, str(tmp_path / "out.pdf"))

        assert result is False

    def test_in_place_overwrite_on_success(self, tmp_path):
        """When input == output the original file is replaced in-place."""
        from app.utils.ocr_provider import embed_text_layer

        pdf = self._make_pdf(tmp_path)
        original_content = b"ORIGINAL"
        new_content = b"OCRMYPDF_OUTPUT"

        mock_proc = Mock()
        mock_proc.returncode = 0
        mock_proc.stderr = ""

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            # Simulate ocrmypdf writing to the temp output path.
            out_path = cmd[-1]
            with open(out_path, "wb") as fh:
                fh.write(new_content)
            return mock_proc

        with (
            patch("shutil.which", return_value="/usr/bin/ocrmypdf"),
            patch("subprocess.run", side_effect=fake_run),
        ):
            result = embed_text_layer(pdf, pdf)

        assert result is True
        with open(pdf, "rb") as fh:
            assert fh.read() == new_content

    def test_in_place_cleans_up_temp_file_on_failure(self, tmp_path):
        """Temp file created during in-place processing is removed on failure."""
        from app.utils.ocr_provider import embed_text_layer

        pdf = self._make_pdf(tmp_path)

        mock_proc = Mock()
        mock_proc.returncode = 1
        mock_proc.stderr = "error"

        created_tmp: list[str] = []

        real_mkstemp = __import__("tempfile").mkstemp

        def fake_mkstemp(**kwargs):  # noqa: ANN001
            fd, path = real_mkstemp(**kwargs)
            created_tmp.append(path)
            # Write something so the cleanup code can find the file.
            with open(path, "wb") as fh:
                fh.write(b"temp")
            return fd, path

        with (
            patch("shutil.which", return_value="/usr/bin/ocrmypdf"),
            patch("subprocess.run", return_value=mock_proc),
            patch("tempfile.mkstemp", side_effect=fake_mkstemp),
        ):
            result = embed_text_layer(pdf, pdf)

        assert result is False
        # The temporary file should have been cleaned up.
        for tmp in created_tmp:
            assert not __import__("os").path.exists(tmp)


@pytest.mark.unit
class TestProcessWithOCRTextLayerEmbedding:
    """Tests for the embed_text_layer step in process_with_ocr."""

    _MINIMAL_PDF = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<</Type /Catalog /Pages 2 0 R>>\nendobj\n"
        b"2 0 obj\n<</Type /Pages /Kids [3 0 R] /Count 1>>\nendobj\n"
        b"3 0 obj\n<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]>>\nendobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer\n<</Size 4 /Root 1 0 R>>\n"
        b"startxref\n190\n%%EOF\n"
    )

    @patch("app.tasks.process_with_ocr.log_task_progress")
    @patch("app.tasks.process_with_ocr.rotate_pdf_pages")
    def test_embed_text_layer_called_when_no_searchable_pdf(self, mock_rotate, mock_log, tmp_path):
        """embed_text_layer is called when no provider returns a searchable PDF."""
        from app.tasks.process_with_ocr import process_with_ocr
        from app.utils.ocr_provider import OCRResult

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        pdf_file = tmp_dir / "scan.pdf"
        pdf_file.write_bytes(self._MINIMAL_PDF)

        mock_result = OCRResult(provider="mistral", text="Hello from Mistral")

        mock_rotate.delay = Mock()

        with (
            patch("app.tasks.process_with_ocr.settings") as mock_settings,
            patch("app.tasks.process_with_ocr.get_ocr_providers") as mock_providers,
            patch("app.tasks.process_with_ocr.merge_ocr_results", return_value=("Hello from Mistral", None, {})),
            patch("app.tasks.process_with_ocr.embed_text_layer", return_value=True) as mock_embed,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_settings.tesseract_language = "eng"
            provider_mock = Mock()
            provider_mock.name = "mistral"
            provider_mock.process.return_value = mock_result
            mock_providers.return_value = [provider_mock]

            process_with_ocr.run("scan.pdf", file_id=None)

        mock_embed.assert_called_once_with(str(pdf_file), str(pdf_file), language="eng")

    @patch("app.tasks.process_with_ocr.log_task_progress")
    @patch("app.tasks.process_with_ocr.rotate_pdf_pages")
    def test_embed_text_layer_skipped_when_searchable_pdf_exists(self, mock_rotate, mock_log, tmp_path):
        """embed_text_layer is NOT called when a provider already returned a searchable PDF."""
        from app.tasks.process_with_ocr import process_with_ocr
        from app.utils.ocr_provider import OCRResult

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        pdf_file = tmp_dir / "scan.pdf"
        pdf_file.write_bytes(self._MINIMAL_PDF)

        # Azure returns searchable_pdf_path set
        mock_result = OCRResult(provider="azure", text="Hello Azure", searchable_pdf_path=str(pdf_file))

        mock_rotate.delay = Mock()

        with (
            patch("app.tasks.process_with_ocr.settings") as mock_settings,
            patch("app.tasks.process_with_ocr.get_ocr_providers") as mock_providers,
            patch(
                "app.tasks.process_with_ocr.merge_ocr_results",
                return_value=("Hello Azure", str(pdf_file), {}),
            ),
            patch("app.tasks.process_with_ocr.embed_text_layer") as mock_embed,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_settings.tesseract_language = "eng"
            provider_mock = Mock()
            provider_mock.name = "azure"
            provider_mock.process.return_value = mock_result
            mock_providers.return_value = [provider_mock]

            process_with_ocr.run("scan.pdf", file_id=None)

        mock_embed.assert_not_called()

    @patch("app.tasks.process_with_ocr.log_task_progress")
    @patch("app.tasks.process_with_ocr.rotate_pdf_pages")
    def test_embed_text_layer_unavailable_is_handled_gracefully(self, mock_rotate, mock_log, tmp_path):
        """When embed_text_layer returns False the task still succeeds."""
        from app.tasks.process_with_ocr import process_with_ocr
        from app.utils.ocr_provider import OCRResult

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        pdf_file = tmp_dir / "scan.pdf"
        pdf_file.write_bytes(self._MINIMAL_PDF)

        mock_result = OCRResult(provider="tesseract", text="Hello Tesseract")
        mock_rotate.delay = Mock()

        with (
            patch("app.tasks.process_with_ocr.settings") as mock_settings,
            patch("app.tasks.process_with_ocr.get_ocr_providers") as mock_providers,
            patch("app.tasks.process_with_ocr.merge_ocr_results", return_value=("Hello Tesseract", None, {})),
            patch("app.tasks.process_with_ocr.embed_text_layer", return_value=False),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_settings.tesseract_language = "eng+deu"
            provider_mock = Mock()
            provider_mock.name = "tesseract"
            provider_mock.process.return_value = mock_result
            mock_providers.return_value = [provider_mock]

            result = process_with_ocr.run("scan.pdf", file_id=None)

        # Task should succeed and return the original file path as searchable_pdf
        assert result["cleaned_text"] == "Hello Tesseract"
        assert result["searchable_pdf"] == str(pdf_file)
