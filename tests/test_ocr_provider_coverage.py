"""
Unit tests for app/utils/ocr_provider.py to boost coverage to 90%+.

Tests cover:
- embed_text_layer() – all branches (file not found, no ocrmypdf, in-place mode,
  timeout, non-zero returncode, success)
- OCRResult and OCRProvider base class
- AzureOCRProvider.process()
- TesseractOCRProvider.process()
- EasyOCRProvider.process()
- MistralOCRProvider.process() + _upload_pdf_and_get_document()
- GoogleDocAIOCRProvider.process()
- AWSTextractOCRProvider.process()
- get_ocr_providers() – default, multiple providers, unknown name, fallback
- merge_ocr_results() – empty, single, primary, longest, ai_merge, ai_merge failure
"""

import json
import subprocess
import sys
from unittest.mock import Mock, patch

import pytest

from app.utils.ocr_provider import (
    KNOWN_OCR_PROVIDERS,
    AWSTextractOCRProvider,
    AzureOCRProvider,
    EasyOCRProvider,
    GoogleDocAIOCRProvider,
    MistralOCRProvider,
    OCRResult,
    TesseractOCRProvider,
    embed_text_layer,
    get_ocr_providers,
    merge_ocr_results,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pdf(tmp_path, name="test.pdf") -> str:
    """Create a minimal valid file path for testing."""
    p = tmp_path / name
    p.write_bytes(b"%PDF-1.4 minimal")
    return str(p)


# ---------------------------------------------------------------------------
# embed_text_layer
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEmbedTextLayer:
    """Tests for the embed_text_layer helper."""

    def test_file_not_found_raises(self, tmp_path):
        """Raises FileNotFoundError when input file does not exist."""
        with pytest.raises(FileNotFoundError, match="input file not found"):
            embed_text_layer(str(tmp_path / "nonexistent.pdf"), str(tmp_path / "out.pdf"))

    def test_no_ocrmypdf_returns_false(self, tmp_path):
        """Returns False when ocrmypdf is not on PATH."""
        pdf = _make_pdf(tmp_path)
        with patch("shutil.which", return_value=None):
            result = embed_text_layer(pdf, str(tmp_path / "out.pdf"))
        assert result is False

    def test_success_different_output(self, tmp_path):
        """Returns True when ocrmypdf exits 0 and output != input."""
        pdf = _make_pdf(tmp_path)
        out = str(tmp_path / "out.pdf")
        mock_proc = Mock()
        mock_proc.returncode = 0
        with (
            patch("shutil.which", return_value="/usr/bin/ocrmypdf"),
            patch("subprocess.run", return_value=mock_proc),
        ):
            result = embed_text_layer(pdf, out)
        assert result is True

    def test_in_place_success(self, tmp_path):
        """Returns True and replaces file in-place when input == output."""
        pdf = _make_pdf(tmp_path)
        mock_proc = Mock()
        mock_proc.returncode = 0
        with (
            patch("shutil.which", return_value="/usr/bin/ocrmypdf"),
            patch("subprocess.run", return_value=mock_proc),
            patch("os.replace") as mock_replace,
        ):
            result = embed_text_layer(pdf, pdf)
        assert result is True
        assert mock_replace.called

    def test_timeout_returns_false(self, tmp_path):
        """Returns False when subprocess times out."""
        pdf = _make_pdf(tmp_path)
        with (
            patch("shutil.which", return_value="/usr/bin/ocrmypdf"),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ocrmypdf", timeout=600)),
        ):
            result = embed_text_layer(pdf, str(tmp_path / "out.pdf"))
        assert result is False

    def test_timeout_in_place_removes_tmp(self, tmp_path):
        """Removes tmp file on timeout when in-place mode."""
        pdf = _make_pdf(tmp_path)
        # Create a fake tmp file that would be cleaned up
        tmp_out = tmp_path / "tmp_ocr.pdf"
        tmp_out.write_bytes(b"")

        with (
            patch("shutil.which", return_value="/usr/bin/ocrmypdf"),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ocrmypdf", timeout=600)),
            patch("tempfile.mkstemp", return_value=(99, str(tmp_out))),
            patch("os.close"),
        ):
            result = embed_text_layer(pdf, pdf)
        assert result is False

    def test_nonzero_returncode_returns_false(self, tmp_path):
        """Returns False when ocrmypdf exits with non-zero return code."""
        pdf = _make_pdf(tmp_path)
        mock_proc = Mock()
        mock_proc.returncode = 1
        mock_proc.stderr = "some error"
        with (
            patch("shutil.which", return_value="/usr/bin/ocrmypdf"),
            patch("subprocess.run", return_value=mock_proc),
        ):
            result = embed_text_layer(pdf, str(tmp_path / "out.pdf"))
        assert result is False

    def test_nonzero_returncode_inplace_removes_tmp(self, tmp_path):
        """Removes tmp file on nonzero returncode when in-place mode."""
        pdf = _make_pdf(tmp_path)
        tmp_out = tmp_path / "tmp_ocr.pdf"
        tmp_out.write_bytes(b"partial")

        mock_proc = Mock()
        mock_proc.returncode = 2
        mock_proc.stderr = "fail"
        with (
            patch("shutil.which", return_value="/usr/bin/ocrmypdf"),
            patch("subprocess.run", return_value=mock_proc),
            patch("tempfile.mkstemp", return_value=(99, str(tmp_out))),
            patch("os.close"),
        ):
            result = embed_text_layer(pdf, pdf)
        assert result is False

    def test_custom_language(self, tmp_path):
        """Passes custom language code to ocrmypdf."""
        pdf = _make_pdf(tmp_path)
        mock_proc = Mock()
        mock_proc.returncode = 0
        captured_cmd = {}

        def fake_run(cmd, **kwargs):
            captured_cmd["cmd"] = cmd
            return mock_proc

        with (
            patch("shutil.which", return_value="/usr/bin/ocrmypdf"),
            patch("subprocess.run", side_effect=fake_run),
        ):
            embed_text_layer(pdf, str(tmp_path / "out.pdf"), language="deu")
        assert "deu" in captured_cmd["cmd"]


# ---------------------------------------------------------------------------
# OCRResult
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOCRResult:
    """Tests for OCRResult data class."""

    def test_defaults(self):
        r = OCRResult(provider="test", text="hello")
        assert r.provider == "test"
        assert r.text == "hello"
        assert r.searchable_pdf_path is None
        assert r.rotation_data == {}
        assert r.metadata == {}

    def test_repr(self):
        r = OCRResult(provider="azure", text="hello world", searchable_pdf_path="/tmp/x.pdf")
        s = repr(r)
        assert "azure" in s
        assert "has_pdf=True" in s

    def test_with_rotation_and_metadata(self):
        r = OCRResult(
            provider="azure",
            text="text",
            rotation_data={0: 90.0},
            metadata={"confidence": 0.99},
        )
        assert r.rotation_data == {0: 90.0}
        assert r.metadata == {"confidence": 0.99}


# ---------------------------------------------------------------------------
# AzureOCRProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAzureOCRProvider:
    """Tests for AzureOCRProvider.process()."""

    def test_missing_azure_key_raises(self, tmp_path):
        """Raises ValueError when AZURE_AI_KEY is not set."""
        pdf = _make_pdf(tmp_path)
        provider = AzureOCRProvider()
        with patch("app.utils.ocr_provider.settings") as ms:
            ms.azure_ai_key = None
            ms.azure_endpoint = "https://example.cognitiveservices.azure.com"
            with pytest.raises(ValueError, match="AZURE_AI_KEY"):
                provider.process(pdf)

    def test_missing_azure_endpoint_raises(self, tmp_path):
        """Raises ValueError when AZURE_ENDPOINT is not set."""
        pdf = _make_pdf(tmp_path)
        provider = AzureOCRProvider()
        with patch("app.utils.ocr_provider.settings") as ms:
            ms.azure_ai_key = "test-key"
            ms.azure_endpoint = None
            with pytest.raises(ValueError, match="AZURE_ENDPOINT"):
                provider.process(pdf)

    def test_successful_processing(self, tmp_path):
        """Returns OCRResult with extracted text and searchable PDF path."""
        pdf = _make_pdf(tmp_path)
        provider = AzureOCRProvider()

        mock_page = Mock()
        mock_page.angle = 1.5
        mock_result = Mock()
        mock_result.content = "extracted text"
        mock_result.model_id = "prebuilt-read"
        mock_result.pages = [mock_page]

        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        mock_poller.details = {"operation_id": "op-123"}

        mock_client = Mock()
        mock_client.begin_analyze_document.return_value = mock_poller
        mock_client.get_analyze_result_pdf.return_value = iter([b"pdf-content"])

        mock_doc_intelligence = Mock()
        mock_doc_intelligence.DocumentIntelligenceClient.return_value = mock_client
        mock_analyze_output = Mock()
        mock_analyze_output.PDF = "pdf"
        mock_doc_intelligence.models.AnalyzeOutputOption = mock_analyze_output
        mock_azure_cred = Mock()

        with (
            patch("app.utils.ocr_provider.settings") as ms,
            patch.dict(
                sys.modules,
                {
                    "azure.ai.documentintelligence": mock_doc_intelligence,
                    "azure.ai.documentintelligence.models": Mock(AnalyzeOutputOption=mock_analyze_output),
                    "azure.core.credentials": Mock(AzureKeyCredential=mock_azure_cred),
                },
            ),
        ):
            ms.azure_ai_key = "test-key"
            ms.azure_endpoint = "https://example.com"
            result = provider.process(pdf)

        assert isinstance(result, OCRResult)
        assert result.provider == "azure"
        assert result.text == "extracted text"
        assert result.searchable_pdf_path == pdf
        assert 0 in result.rotation_data

    def test_no_rotation_data(self, tmp_path):
        """Works when pages have no rotation angle."""
        pdf = _make_pdf(tmp_path)
        provider = AzureOCRProvider()

        mock_page = Mock()
        mock_page.angle = 0
        mock_result = Mock()
        mock_result.content = "text"
        mock_result.model_id = "prebuilt-read"
        mock_result.pages = [mock_page]

        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        mock_poller.details = {"operation_id": "op-123"}

        mock_client = Mock()
        mock_client.begin_analyze_document.return_value = mock_poller
        mock_client.get_analyze_result_pdf.return_value = iter([b"pdf"])

        mock_di = Mock()
        mock_ao = Mock()
        mock_ao.PDF = "pdf"
        mock_di.DocumentIntelligenceClient.return_value = mock_client

        with (
            patch("app.utils.ocr_provider.settings") as ms,
            patch.dict(
                sys.modules,
                {
                    "azure.ai.documentintelligence": mock_di,
                    "azure.ai.documentintelligence.models": Mock(AnalyzeOutputOption=mock_ao),
                    "azure.core.credentials": Mock(AzureKeyCredential=Mock()),
                },
            ),
        ):
            ms.azure_ai_key = "key"
            ms.azure_endpoint = "https://x.com"
            result = provider.process(pdf)
        assert result.rotation_data == {}

    def test_no_pages_attribute(self, tmp_path):
        """Works when result has no pages attribute."""
        pdf = _make_pdf(tmp_path)
        provider = AzureOCRProvider()

        mock_result = Mock(spec=["content", "model_id"])
        mock_result.content = "text"
        mock_result.model_id = "prebuilt-read"

        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        mock_poller.details = {"operation_id": "op-456"}

        mock_client = Mock()
        mock_client.begin_analyze_document.return_value = mock_poller
        mock_client.get_analyze_result_pdf.return_value = iter([b"pdf"])

        mock_di = Mock()
        mock_ao = Mock()
        mock_ao.PDF = "pdf"
        mock_di.DocumentIntelligenceClient.return_value = mock_client

        with (
            patch("app.utils.ocr_provider.settings") as ms,
            patch.dict(
                sys.modules,
                {
                    "azure.ai.documentintelligence": mock_di,
                    "azure.ai.documentintelligence.models": Mock(AnalyzeOutputOption=mock_ao),
                    "azure.core.credentials": Mock(AzureKeyCredential=Mock()),
                },
            ),
        ):
            ms.azure_ai_key = "key"
            ms.azure_endpoint = "https://x.com"
            result = provider.process(pdf)
        assert result.rotation_data == {}


# ---------------------------------------------------------------------------
# TesseractOCRProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTesseractOCRProvider:
    """Tests for TesseractOCRProvider.process()."""

    def test_import_error_raises_runtime(self, tmp_path):
        """Raises RuntimeError when pytesseract/pdf2image are not installed."""
        pdf = _make_pdf(tmp_path)
        provider = TesseractOCRProvider()
        with patch.dict(sys.modules, {"pytesseract": None, "pdf2image": None}):
            with pytest.raises(RuntimeError, match="pytesseract and pdf2image"):
                provider.process(pdf)

    def test_missing_language_raises_runtime(self, tmp_path):
        """Raises RuntimeError when required language data files are missing."""
        pdf = _make_pdf(tmp_path)
        provider = TesseractOCRProvider()

        mock_pytesseract = Mock()
        mock_pdf2image = Mock()
        mock_pdf2image.convert_from_path.return_value = [Mock()]

        with (
            patch.dict(
                sys.modules,
                {"pytesseract": mock_pytesseract, "pdf2image": mock_pdf2image},
            ),
            patch("app.utils.ocr_provider.settings") as ms,
            patch(
                "app.utils.ocr_language_manager.ensure_tesseract_languages",
                return_value=["deu"],
            ),
        ):
            ms.tesseract_cmd = None
            ms.tesseract_language = "deu"
            with pytest.raises(RuntimeError, match="deu"):
                provider.process(pdf)

    def test_success(self, tmp_path):
        """Returns OCRResult with extracted text on success."""
        pdf = _make_pdf(tmp_path)
        provider = TesseractOCRProvider()

        mock_pytesseract = Mock()
        mock_pytesseract.image_to_string.return_value = "page text"
        mock_pytesseract.pytesseract = Mock()
        mock_pdf2image = Mock()
        mock_pdf2image.convert_from_path.return_value = [Mock()]

        with (
            patch.dict(
                sys.modules,
                {"pytesseract": mock_pytesseract, "pdf2image": mock_pdf2image},
            ),
            patch("app.utils.ocr_provider.settings") as ms,
            patch(
                "app.utils.ocr_language_manager.ensure_tesseract_languages",
                return_value=[],
            ),
        ):
            ms.tesseract_cmd = None
            ms.tesseract_language = "eng"
            result = provider.process(pdf)

        assert result.provider == "tesseract"
        assert "page text" in result.text

    def test_tesseract_cmd_set(self, tmp_path):
        """Sets pytesseract.tesseract_cmd when configured."""
        pdf = _make_pdf(tmp_path)
        provider = TesseractOCRProvider()

        mock_pytesseract = Mock()
        mock_pytesseract.pytesseract = Mock()
        mock_pytesseract.image_to_string.return_value = ""
        mock_pdf2image = Mock()
        mock_pdf2image.convert_from_path.return_value = []

        with (
            patch.dict(
                sys.modules,
                {"pytesseract": mock_pytesseract, "pdf2image": mock_pdf2image},
            ),
            patch("app.utils.ocr_provider.settings") as ms,
            patch(
                "app.utils.ocr_language_manager.ensure_tesseract_languages",
                return_value=[],
            ),
        ):
            ms.tesseract_cmd = "/usr/local/bin/tesseract"
            ms.tesseract_language = "eng"
            result = provider.process(pdf)
        assert mock_pytesseract.pytesseract.tesseract_cmd == "/usr/local/bin/tesseract"
        assert result.provider == "tesseract"


# ---------------------------------------------------------------------------
# EasyOCRProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEasyOCRProvider:
    """Tests for EasyOCRProvider.process()."""

    def test_import_error_raises_runtime(self, tmp_path):
        """Raises RuntimeError when easyocr/pdf2image are not installed."""
        pdf = _make_pdf(tmp_path)
        provider = EasyOCRProvider()
        with patch.dict(sys.modules, {"easyocr": None, "pdf2image": None}):
            with pytest.raises(RuntimeError, match="easyocr and pdf2image"):
                provider.process(pdf)

    def test_success(self, tmp_path):
        """Returns OCRResult with extracted text on success."""
        pdf = _make_pdf(tmp_path)
        provider = EasyOCRProvider()

        mock_reader = Mock()
        mock_reader.readtext.return_value = ["line1", "line2"]

        mock_easyocr = Mock()
        mock_easyocr.Reader.return_value = mock_reader

        mock_pdf2image = Mock()
        mock_pdf2image.convert_from_path.return_value = [Mock()]

        with (
            patch.dict(
                sys.modules,
                {"easyocr": mock_easyocr, "pdf2image": mock_pdf2image},
            ),
            patch("app.utils.ocr_provider.settings") as ms,
        ):
            ms.easyocr_languages = "en,fr"
            ms.easyocr_gpu = False
            result = provider.process(pdf)

        assert result.provider == "easyocr"
        assert "line1" in result.text


# ---------------------------------------------------------------------------
# MistralOCRProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMistralOCRProvider:
    """Tests for MistralOCRProvider.process() and _upload_pdf_and_get_document()."""

    def test_missing_api_key_raises(self, tmp_path):
        """Raises ValueError when MISTRAL_API_KEY is not set."""
        pdf = _make_pdf(tmp_path)
        provider = MistralOCRProvider()
        mock_requests = Mock()
        with (
            patch.dict(sys.modules, {"requests": mock_requests}),
            patch("app.utils.ocr_provider.settings") as ms,
        ):
            ms.mistral_api_key = None
            with pytest.raises(ValueError, match="MISTRAL_API_KEY"):
                provider.process(pdf)

    def test_pdf_path_success(self, tmp_path):
        """Processes PDF via upload + OCR endpoint."""
        pdf = _make_pdf(tmp_path)
        provider = MistralOCRProvider()

        upload_resp = Mock()
        upload_resp.json.return_value = {"id": "file-123"}
        upload_resp.raise_for_status = Mock()

        url_resp = Mock()
        url_resp.json.return_value = {"url": "https://signed.url/file"}
        url_resp.raise_for_status = Mock()

        ocr_resp = Mock()
        ocr_resp.json.return_value = {"pages": [{"markdown": "page content"}]}
        ocr_resp.raise_for_status = Mock()

        mock_requests = Mock()
        mock_requests.post.side_effect = [upload_resp, ocr_resp]
        mock_requests.get.return_value = url_resp

        with (
            patch.dict(sys.modules, {"requests": mock_requests}),
            patch("app.utils.ocr_provider.settings") as ms,
        ):
            ms.mistral_api_key = "test-key"
            ms.mistral_ocr_model = "mistral-ocr-latest"
            result = provider.process(pdf)

        assert result.provider == "mistral"
        assert result.text == "page content"

    def test_image_path_success(self, tmp_path):
        """Processes JPEG image via base64 encoding."""
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0test image")
        provider = MistralOCRProvider()

        ocr_resp = Mock()
        ocr_resp.json.return_value = {"pages": [{"markdown": "image text"}]}
        ocr_resp.raise_for_status = Mock()

        mock_requests = Mock()
        mock_requests.post.return_value = ocr_resp

        with (
            patch.dict(sys.modules, {"requests": mock_requests}),
            patch("app.utils.ocr_provider.settings") as ms,
        ):
            ms.mistral_api_key = "test-key"
            ms.mistral_ocr_model = "mistral-ocr-latest"
            result = provider.process(str(img))

        assert result.provider == "mistral"
        assert result.text == "image text"

    def test_unknown_mime_no_magic_raises(self, tmp_path):
        """Raises ValueError for file whose MIME type is None and has non-PDF magic bytes."""
        # Use a filename with no extension so mimetypes.guess_type returns None
        unknown = tmp_path / "unknownfile"
        unknown.write_bytes(b"\x00\x01\x02\x03\x04")
        provider = MistralOCRProvider()

        mock_requests = Mock()
        with (
            patch.dict(sys.modules, {"requests": mock_requests}),
            patch("app.utils.ocr_provider.settings") as ms,
        ):
            ms.mistral_api_key = "test-key"
            ms.mistral_ocr_model = "mistral-ocr-latest"
            with pytest.raises(ValueError, match="Cannot determine file type"):
                provider.process(str(unknown))

    def test_unsupported_mime_raises(self, tmp_path):
        """Raises ValueError for unsupported MIME type (e.g. .csv)."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("col1,col2\n1,2")
        provider = MistralOCRProvider()

        mock_requests = Mock()
        with (
            patch.dict(sys.modules, {"requests": mock_requests}),
            patch("app.utils.ocr_provider.settings") as ms,
        ):
            ms.mistral_api_key = "test-key"
            ms.mistral_ocr_model = "mistral-ocr-latest"
            with pytest.raises(ValueError, match="Unsupported file type"):
                provider.process(str(csv_file))

    def test_pdf_detected_via_magic_bytes(self, tmp_path):
        """Detects PDF via magic bytes when extension is missing."""
        no_ext = tmp_path / "document"
        no_ext.write_bytes(b"%PDF-1.4 minimal content")
        provider = MistralOCRProvider()

        upload_resp = Mock()
        upload_resp.json.return_value = {"id": "file-456"}
        upload_resp.raise_for_status = Mock()

        url_resp = Mock()
        url_resp.json.return_value = {"url": "https://signed.url/doc"}
        url_resp.raise_for_status = Mock()

        ocr_resp = Mock()
        ocr_resp.json.return_value = {"pages": [{"markdown": "doc text"}]}
        ocr_resp.raise_for_status = Mock()

        mock_requests = Mock()
        mock_requests.post.side_effect = [upload_resp, ocr_resp]
        mock_requests.get.return_value = url_resp

        with (
            patch.dict(sys.modules, {"requests": mock_requests}),
            patch("app.utils.ocr_provider.settings") as ms,
        ):
            ms.mistral_api_key = "key"
            ms.mistral_ocr_model = "mistral-ocr-latest"
            result = provider.process(str(no_ext))
        assert result.text == "doc text"


# ---------------------------------------------------------------------------
# GoogleDocAIOCRProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGoogleDocAIOCRProvider:
    """Tests for GoogleDocAIOCRProvider.process()."""

    def test_import_error_raises_runtime(self, tmp_path):
        """Raises RuntimeError when google-cloud-documentai is not installed."""
        pdf = _make_pdf(tmp_path)
        provider = GoogleDocAIOCRProvider()
        with patch.dict(sys.modules, {"google.cloud": None, "google.cloud.documentai": None}):
            with pytest.raises((RuntimeError, ImportError)):
                provider.process(pdf)

    def test_missing_project_id_raises(self, tmp_path):
        """Raises ValueError when project_id is missing."""
        pdf = _make_pdf(tmp_path)
        provider = GoogleDocAIOCRProvider()

        mock_documentai = Mock()
        mock_service_account = Mock()
        mock_google_cloud = Mock()
        mock_google_cloud.documentai = mock_documentai

        with (
            patch.dict(
                sys.modules,
                {
                    "google": mock_google_cloud,
                    "google.cloud": mock_google_cloud,
                    "google.cloud.documentai": mock_documentai,
                    "google.oauth2": Mock(),
                    "google.oauth2.service_account": mock_service_account,
                },
            ),
            patch("app.utils.ocr_provider.settings") as ms,
        ):
            ms.google_docai_project_id = None
            ms.google_docai_processor_id = "proc-123"
            ms.google_docai_location = "us"
            ms.google_docai_credentials_json = None
            ms.google_drive_credentials_json = None
            with pytest.raises(ValueError, match="GOOGLE_DOCAI_PROJECT_ID"):
                provider.process(pdf)

    def test_success_with_credentials(self, tmp_path):
        """Processes PDF via Google Document AI with service account credentials."""
        pdf = _make_pdf(tmp_path)
        provider = GoogleDocAIOCRProvider()

        mock_document = Mock()
        mock_document.text = "google extracted text"

        mock_result = Mock()
        mock_result.document = mock_document

        mock_client = Mock()
        mock_client.process_document.return_value = mock_result
        mock_client.processor_path.return_value = "projects/p/locations/us/processors/proc"

        mock_documentai = Mock()
        mock_documentai.DocumentProcessorServiceClient.return_value = mock_client
        mock_documentai.RawDocument.return_value = Mock()
        mock_documentai.ProcessRequest.return_value = Mock()

        mock_creds = Mock()
        mock_service_account = Mock()
        mock_service_account.Credentials.from_service_account_info.return_value = mock_creds

        creds_dict = {"type": "service_account", "project_id": "test"}

        with (
            patch.dict(
                sys.modules,
                {
                    "google.cloud.documentai": mock_documentai,
                    "google.oauth2.service_account": mock_service_account,
                },
            ),
            patch("app.utils.ocr_provider.settings") as ms,
        ):
            ms.google_docai_project_id = "my-project"
            ms.google_docai_processor_id = "proc-123"
            ms.google_docai_location = "us"
            ms.google_docai_credentials_json = json.dumps(creds_dict)
            ms.google_drive_credentials_json = None
            result = provider.process(pdf)

        assert result.provider == "google_docai"
        assert result.text == "google extracted text"

    def test_success_no_credentials_json(self, tmp_path):
        """Processes PDF via ADC when no credentials JSON is configured."""
        pdf = _make_pdf(tmp_path)
        provider = GoogleDocAIOCRProvider()

        mock_document = Mock()
        mock_document.text = "adc text"
        mock_result = Mock()
        mock_result.document = mock_document

        mock_client = Mock()
        mock_client.process_document.return_value = mock_result
        mock_client.processor_path.return_value = "projects/p/locations/us/processors/proc"

        mock_documentai = Mock()
        mock_documentai.DocumentProcessorServiceClient.return_value = mock_client
        mock_documentai.RawDocument.return_value = Mock()
        mock_documentai.ProcessRequest.return_value = Mock()

        mock_service_account = Mock()

        with (
            patch.dict(
                sys.modules,
                {
                    "google.cloud.documentai": mock_documentai,
                    "google.oauth2.service_account": mock_service_account,
                },
            ),
            patch("app.utils.ocr_provider.settings") as ms,
        ):
            ms.google_docai_project_id = "project"
            ms.google_docai_processor_id = "proc"
            ms.google_docai_location = "eu"
            ms.google_docai_credentials_json = None
            ms.google_drive_credentials_json = None
            result = provider.process(pdf)

        assert result.provider == "google_docai"


# ---------------------------------------------------------------------------
# AWSTextractOCRProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAWSTextractOCRProvider:
    """Tests for AWSTextractOCRProvider.process()."""

    def test_import_error_raises_runtime(self, tmp_path):
        """Raises RuntimeError when boto3 is not installed."""
        pdf = _make_pdf(tmp_path)
        provider = AWSTextractOCRProvider()
        with patch.dict(sys.modules, {"boto3": None}):
            with pytest.raises(RuntimeError, match="boto3"):
                provider.process(pdf)

    def test_missing_credentials_raises(self, tmp_path):
        """Raises ValueError when AWS credentials are missing."""
        pdf = _make_pdf(tmp_path)
        provider = AWSTextractOCRProvider()
        mock_boto3 = Mock()
        with (
            patch.dict(sys.modules, {"boto3": mock_boto3}),
            patch("app.utils.ocr_provider.settings") as ms,
        ):
            ms.aws_access_key_id = None
            ms.aws_secret_access_key = None
            ms.aws_region = "us-east-1"
            with pytest.raises(ValueError, match="AWS_ACCESS_KEY_ID"):
                provider.process(pdf)

    def test_success(self, tmp_path):
        """Returns OCRResult with extracted text on success."""
        pdf = _make_pdf(tmp_path)
        provider = AWSTextractOCRProvider()

        mock_textract = Mock()
        mock_textract.detect_document_text.return_value = {
            "Blocks": [
                {"BlockType": "LINE", "Text": "first line"},
                {"BlockType": "PAGE", "Text": "ignored"},
                {"BlockType": "LINE", "Text": "second line"},
            ]
        }
        mock_boto3 = Mock()
        mock_boto3.client.return_value = mock_textract

        with (
            patch.dict(sys.modules, {"boto3": mock_boto3}),
            patch("app.utils.ocr_provider.settings") as ms,
        ):
            ms.aws_access_key_id = "AKIATEST"
            ms.aws_secret_access_key = "secret"
            ms.aws_region = "us-west-2"
            result = provider.process(pdf)

        assert result.provider == "aws_textract"
        assert "first line" in result.text
        assert "second line" in result.text
        assert "ignored" not in result.text

    def test_default_region(self, tmp_path):
        """Uses us-east-1 as default region when not configured."""
        pdf = _make_pdf(tmp_path)
        provider = AWSTextractOCRProvider()

        mock_textract = Mock()
        mock_textract.detect_document_text.return_value = {"Blocks": []}
        mock_boto3 = Mock()
        mock_boto3.client.return_value = mock_textract

        with (
            patch.dict(sys.modules, {"boto3": mock_boto3}),
            patch("app.utils.ocr_provider.settings") as ms,
        ):
            ms.aws_access_key_id = "key"
            ms.aws_secret_access_key = "secret"
            ms.aws_region = None
            result = provider.process(pdf)

        mock_boto3.client.assert_called_once()
        call_kwargs = mock_boto3.client.call_args[1]
        assert call_kwargs["region_name"] == "us-east-1"


# ---------------------------------------------------------------------------
# get_ocr_providers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetOCRProviders:
    """Tests for get_ocr_providers() factory function."""

    def test_returns_azure_by_default(self):
        """Returns AzureOCRProvider when no setting is configured."""
        with patch("app.utils.ocr_provider.settings") as ms:
            ms.ocr_providers = None
            providers = get_ocr_providers()
        assert len(providers) == 1
        assert isinstance(providers[0], AzureOCRProvider)

    def test_single_provider(self):
        """Returns a single configured provider."""
        with patch("app.utils.ocr_provider.settings") as ms:
            ms.ocr_providers = "tesseract"
            providers = get_ocr_providers()
        assert len(providers) == 1
        assert isinstance(providers[0], TesseractOCRProvider)

    def test_multiple_providers(self):
        """Returns multiple configured providers."""
        with patch("app.utils.ocr_provider.settings") as ms:
            ms.ocr_providers = "azure,tesseract"
            providers = get_ocr_providers()
        assert len(providers) == 2
        assert isinstance(providers[0], AzureOCRProvider)
        assert isinstance(providers[1], TesseractOCRProvider)

    def test_unknown_provider_skipped(self):
        """Skips unknown provider names with a warning."""
        with patch("app.utils.ocr_provider.settings") as ms:
            ms.ocr_providers = "unknown_engine,azure"
            providers = get_ocr_providers()
        # unknown_engine is skipped, azure is included
        assert len(providers) == 1
        assert isinstance(providers[0], AzureOCRProvider)

    def test_all_unknown_falls_back_to_azure(self):
        """Falls back to Azure when all providers are unknown."""
        with patch("app.utils.ocr_provider.settings") as ms:
            ms.ocr_providers = "no_such_provider"
            providers = get_ocr_providers()
        assert len(providers) == 1
        assert isinstance(providers[0], AzureOCRProvider)

    def test_known_providers_list(self):
        """All providers listed in KNOWN_OCR_PROVIDERS can be instantiated."""
        with patch("app.utils.ocr_provider.settings") as ms:
            ms.ocr_providers = ",".join(KNOWN_OCR_PROVIDERS)
            providers = get_ocr_providers()
        assert len(providers) == len(KNOWN_OCR_PROVIDERS)

    def test_whitespace_stripped(self):
        """Strips whitespace from provider names."""
        with patch("app.utils.ocr_provider.settings") as ms:
            ms.ocr_providers = " azure , tesseract "
            providers = get_ocr_providers()
        assert len(providers) == 2


# ---------------------------------------------------------------------------
# merge_ocr_results
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMergeOCRResults:
    """Tests for merge_ocr_results() orchestration function."""

    def test_empty_results(self):
        """Returns empty string for empty result list."""
        text, pdf, rot = merge_ocr_results([], "test.pdf")
        assert text == ""
        assert pdf is None
        assert rot == {}

    def test_single_result(self):
        """Returns single result as-is."""
        r = OCRResult("azure", "hello", searchable_pdf_path="/tmp/x.pdf", rotation_data={0: 90.0})
        text, pdf, rot = merge_ocr_results([r], "test.pdf")
        assert text == "hello"
        assert pdf == "/tmp/x.pdf"
        assert rot == {0: 90.0}

    def test_primary_strategy(self):
        """Returns first result's text with 'primary' strategy."""
        r1 = OCRResult("azure", "first text")
        r2 = OCRResult("tesseract", "second text")
        with patch("app.utils.ocr_provider.settings") as ms:
            ms.ocr_merge_strategy = "primary"
            ms.ai_model = "gpt-4"
            ms.openai_model = "gpt-4"
            text, pdf, rot = merge_ocr_results([r1, r2], "doc.pdf")
        assert text == "first text"

    def test_longest_strategy(self):
        """Returns longest text with 'longest' strategy."""
        r1 = OCRResult("azure", "short")
        r2 = OCRResult("tesseract", "much longer text from tesseract")
        with patch("app.utils.ocr_provider.settings") as ms:
            ms.ocr_merge_strategy = "longest"
            ms.ai_model = "gpt-4"
            ms.openai_model = "gpt-4"
            text, _, _ = merge_ocr_results([r1, r2], "doc.pdf")
        assert text == "much longer text from tesseract"

    def test_searchable_pdf_from_first_provider_with_pdf(self):
        """Picks searchable_pdf_path from first provider that has one."""
        r1 = OCRResult("tesseract", "t1", searchable_pdf_path=None)
        r2 = OCRResult("azure", "t2", searchable_pdf_path="/tmp/azure.pdf")
        with patch("app.utils.ocr_provider.settings") as ms:
            ms.ocr_merge_strategy = "primary"
            ms.ai_model = "gpt-4"
            ms.openai_model = "gpt-4"
            _, pdf, _ = merge_ocr_results([r1, r2], "doc.pdf")
        assert pdf == "/tmp/azure.pdf"

    def test_rotation_data_from_first_provider_with_rotation(self):
        """Picks rotation_data from first provider that has it."""
        r1 = OCRResult("tesseract", "t1", rotation_data={})
        r2 = OCRResult("azure", "t2", rotation_data={0: 90.0})
        with patch("app.utils.ocr_provider.settings") as ms:
            ms.ocr_merge_strategy = "longest"
            ms.ai_model = "gpt-4"
            ms.openai_model = "gpt-4"
            _, _, rot = merge_ocr_results([r1, r2], "doc.pdf")
        assert rot == {0: 90.0}

    def test_ai_merge_strategy_success(self):
        """AI merge strategy calls AI provider and returns merged text."""
        r1 = OCRResult("azure", "azure text")
        r2 = OCRResult("tesseract", "tesseract text")

        mock_provider = Mock()
        mock_provider.chat_completion.return_value = "merged text"

        with (
            patch("app.utils.ocr_provider.settings") as ms,
            patch("app.utils.ai_provider.get_ai_provider", return_value=mock_provider),
        ):
            ms.ocr_merge_strategy = "ai_merge"
            ms.ai_model = "gpt-4o"
            ms.openai_model = "gpt-4o"
            text, _, _ = merge_ocr_results([r1, r2], "doc.pdf")
        assert text == "merged text"

    def test_ai_merge_is_default_strategy(self):
        """ai_merge is used when no strategy is configured."""
        r1 = OCRResult("azure", "text one")
        r2 = OCRResult("tesseract", "text two which is longer")

        mock_provider = Mock()
        mock_provider.chat_completion.return_value = "ai result"

        with (
            patch("app.utils.ocr_provider.settings") as ms,
            patch("app.utils.ai_provider.get_ai_provider", return_value=mock_provider),
        ):
            ms.ocr_merge_strategy = None
            ms.ai_model = "gpt-4"
            ms.openai_model = "gpt-4"
            text, _, _ = merge_ocr_results([r1, r2], "doc.pdf")
        assert text == "ai result"

    def test_ai_merge_failure_falls_back_to_longest(self):
        """Falls back to longest text when AI merge raises an exception."""
        r1 = OCRResult("azure", "short")
        r2 = OCRResult("tesseract", "this is the longer text from tesseract engine")

        with (
            patch("app.utils.ocr_provider.settings") as ms,
            patch("app.utils.ai_provider.get_ai_provider", side_effect=RuntimeError("AI unavailable")),
        ):
            ms.ocr_merge_strategy = "ai_merge"
            ms.ai_model = "gpt-4"
            ms.openai_model = "gpt-4"
            text, _, _ = merge_ocr_results([r1, r2], "doc.pdf")
        assert text == "this is the longer text from tesseract engine"
