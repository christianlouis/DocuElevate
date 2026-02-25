"""
Comprehensive tests for app/utils/text_quality.py.

Covers:
- detect_pdf_text_source: digital, OCR, and unknown PDF metadata
- check_text_quality: digital bypass, good text, poor text, empty text
- Strict threshold (85) and significant-issues override logic
- compare_text_quality: head-to-head comparison between original and OCR text
- AI failure and JSON-parse error handling
- Integration with process_document: quality check disabled, good quality,
  poor quality (triggers re-OCR), digital source bypass
"""

from unittest.mock import MagicMock, patch

import pytest

from app.utils.text_quality import (
    TextComparisonResult,
    TextQualityResult,
    TextSource,
    check_text_quality,
    compare_text_quality,
    detect_pdf_text_source,
)

# ---------------------------------------------------------------------------
# Helpers / sample texts
# ---------------------------------------------------------------------------

# Well-formed English invoice text – should pass quality checks.
GOOD_TEXT = """
INVOICE #2024-0042
Date: 15 January 2024

Bill To:
  Acme Corporation
  123 Main Street
  Springfield, IL 62701

Description            Qty   Unit Price   Total
Widget A               10    $12.50       $125.00
Widget B               5     $22.00       $110.00
                                Subtotal:  $235.00
                                     Tax:   $17.63
                                   Total:  $252.63

Payment due within 30 days.  Thank you for your business.
"""

# Garbled OCR-artefact text with heavy character substitution – poor quality.
POOR_OCR_TEXT = """
lnv0|c3 #2@24-@@42
D@t3: l5 J@nu@ry 2@24

Bi|l T0:
  Acm3 C0rp0r@ti0n
  l23 M@in Str33t
  Springf|3|d, lL 62701

D3scripti0n            Qty   Unit Pric3   T0t@l
Widg3t A               l0    $l2.5@       $l25.@@
Widg3t B               5     $22.@@       $ll@.@@
                                Subr0t@l:  $235.@@
                                     T@x:   $l7.63
                                   T0t@l:  $252.63

P@ym3nt du3 with|n 30 d@ys.  Th@nk y0u f0r y0ur busin3ss.
"""

# Complete garbage – random symbol soup.
GARBAGE_TEXT = "ÿÿÿÿÿÿÿ   @@@ %%% !!! *** ### ^^^ &&&" * 20

# Text so fragmented it carries no meaning.
FRAGMENTED_TEXT = "a b c d e f g h i j k l m n o p q r s t u v w x y z " * 10

# ---------------------------------------------------------------------------
# Minimal valid PDF bytes used when we need to patch pypdf.PdfReader
# ---------------------------------------------------------------------------
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


def _pdf_with_metadata(tmp_path, producer: str = "", creator: str = "") -> str:
    """Write a minimal PDF file and return its path (metadata is mocked later)."""
    p = tmp_path / "test.pdf"
    p.write_bytes(_MINIMAL_PDF)
    return str(p)


# ---------------------------------------------------------------------------
# detect_pdf_text_source
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectPdfTextSource:
    """Tests for detect_pdf_text_source()."""

    def _mock_metadata(self, producer: str, creator: str = "") -> MagicMock:
        """Build a mock PdfReader whose .metadata dict contains /Producer and /Creator."""
        meta = {}
        if producer:
            meta["/Producer"] = producer
        if creator:
            meta["/Creator"] = creator
        reader = MagicMock()
        reader.metadata = meta
        return reader

    @pytest.mark.parametrize(
        "producer,creator,expected",
        [
            # OCR producers
            ("Tesseract OCR 5.3.0", "", TextSource.OCR_PREVIOUS),
            ("ocrmypdf 14.0", "", TextSource.OCR_PREVIOUS),
            ("ABBYY FineReader 15", "", TextSource.OCR_PREVIOUS),
            ("Nuance PDF Converter", "", TextSource.OCR_PREVIOUS),
            ("ReadIris 17", "", TextSource.OCR_PREVIOUS),
            ("OmniPage 19", "", TextSource.OCR_PREVIOUS),
            # Digital producers
            ("Microsoft Word 365", "", TextSource.DIGITAL),
            ("LibreOffice 7.5", "", TextSource.DIGITAL),
            ("pdflatex", "", TextSource.DIGITAL),
            ("xetex", "", TextSource.DIGITAL),
            ("ReportLab PDF Library", "", TextSource.DIGITAL),
            ("wkhtmltopdf 0.12.6", "", TextSource.DIGITAL),
            ("Chromium 120", "", TextSource.DIGITAL),
            ("Google Docs", "", TextSource.DIGITAL),
            # Creator field
            ("", "Microsoft Excel 2021", TextSource.DIGITAL),
            ("", "Tesseract-OCR", TextSource.OCR_PREVIOUS),
            # Unknown
            ("Adobe Acrobat", "", TextSource.UNKNOWN),
            ("", "", TextSource.UNKNOWN),
        ],
    )
    def test_source_detection(self, tmp_path, producer, creator, expected):
        """Producer/Creator metadata maps to the correct TextSource."""
        pdf_path = _pdf_with_metadata(tmp_path)
        reader_mock = self._mock_metadata(producer, creator)

        with patch("pypdf.PdfReader", return_value=reader_mock):
            result = detect_pdf_text_source(pdf_path)

        assert result == expected

    def test_read_error_returns_unknown(self, tmp_path):
        """If pypdf raises an exception, return UNKNOWN (safe fallback)."""
        pdf_path = _pdf_with_metadata(tmp_path)

        with patch("pypdf.PdfReader", side_effect=Exception("corrupt PDF")):
            result = detect_pdf_text_source(pdf_path)

        assert result == TextSource.UNKNOWN

    def test_none_metadata_returns_unknown(self, tmp_path):
        """If reader.metadata is None, return UNKNOWN."""
        pdf_path = _pdf_with_metadata(tmp_path)
        reader_mock = MagicMock()
        reader_mock.metadata = None

        with patch("pypdf.PdfReader", return_value=reader_mock):
            result = detect_pdf_text_source(pdf_path)

        assert result == TextSource.UNKNOWN


# ---------------------------------------------------------------------------
# check_text_quality – digital bypass
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckTextQualityDigitalBypass:
    """Digital-origin PDFs must skip the AI call and return 100/good."""

    def test_digital_source_skips_ai(self):
        """No AI provider call is made for DIGITAL source."""
        with patch("app.utils.text_quality.get_ai_provider") as mock_provider:
            result = check_text_quality(GOOD_TEXT, TextSource.DIGITAL)

        mock_provider.assert_not_called()
        assert result.is_good_quality is True
        assert result.quality_score == 100
        assert result.text_source == TextSource.DIGITAL

    def test_digital_source_poor_looking_text_still_trusted(self):
        """Even if the text looks poor, digital origin is always trusted."""
        with patch("app.utils.text_quality.get_ai_provider") as mock_provider:
            result = check_text_quality(POOR_OCR_TEXT, TextSource.DIGITAL)

        mock_provider.assert_not_called()
        assert result.is_good_quality is True


# ---------------------------------------------------------------------------
# check_text_quality – empty text
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckTextQualityEmpty:
    """Empty / whitespace text must fail immediately without an AI call."""

    @pytest.mark.parametrize("empty_text", ["", "   ", "\n\t\n"])
    def test_empty_text_fails_without_ai(self, empty_text):
        with patch("app.utils.text_quality.get_ai_provider") as mock_provider:
            result = check_text_quality(empty_text, TextSource.OCR_PREVIOUS)

        mock_provider.assert_not_called()
        assert result.is_good_quality is False
        assert result.quality_score == 0
        assert "empty_text" in result.issues

    def test_empty_text_unknown_source(self):
        with patch("app.utils.text_quality.get_ai_provider") as mock_provider:
            result = check_text_quality("", TextSource.UNKNOWN)

        mock_provider.assert_not_called()
        assert result.is_good_quality is False


# ---------------------------------------------------------------------------
# check_text_quality – AI-backed assessments
# ---------------------------------------------------------------------------


def _make_ai_response(quality_score: int, is_good: bool, feedback: str, issues: list) -> str:
    """Build a JSON string mimicking the AI response format."""
    import json as _json

    return _json.dumps(
        {
            "quality_score": quality_score,
            "is_good_quality": is_good,
            "feedback": feedback,
            "issues": issues,
        }
    )


@pytest.mark.unit
class TestCheckTextQualityAI:
    """Tests for the AI-backed quality assessment."""

    def _mock_provider(self, response: str) -> MagicMock:
        """Return a mock AI provider whose chat_completion returns *response*."""
        provider = MagicMock()
        provider.chat_completion.return_value = response
        return provider

    def _mock_settings(self, mock_settings, threshold: int = 85):
        """Configure mock settings with sensible defaults for quality check tests."""
        mock_settings.ai_model = "gpt-4o-mini"
        mock_settings.openai_model = "gpt-4o-mini"
        mock_settings.text_quality_threshold = threshold
        mock_settings.text_quality_significant_issues = [
            "excessive_typos",
            "garbage_characters",
            "incoherent_text",
            "fragmented_sentences",
        ]

    def test_good_text_passes(self):
        """A high-quality AI response marks text as good."""
        ai_resp = _make_ai_response(90, True, "Well-structured invoice text.", [])
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            self._mock_settings(mock_settings)
            result = check_text_quality(GOOD_TEXT, TextSource.OCR_PREVIOUS)

        assert result.is_good_quality is True
        assert result.quality_score == 90
        assert result.issues == []

    def test_poor_ocr_text_fails(self):
        """A low-quality AI response marks text as poor."""
        ai_resp = _make_ai_response(
            25, False, "Severe OCR artefacts with character substitutions.", ["excessive_typos", "garbage_characters"]
        )
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            self._mock_settings(mock_settings)
            result = check_text_quality(POOR_OCR_TEXT, TextSource.OCR_PREVIOUS)

        assert result.is_good_quality is False
        assert result.quality_score == 25
        assert "excessive_typos" in result.issues
        assert "garbage_characters" in result.issues

    def test_garbage_text_fails(self):
        """Complete garbage text is scored very low."""
        ai_resp = _make_ai_response(5, False, "Random symbol soup – no readable content.", ["garbage_characters"])
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            self._mock_settings(mock_settings)
            result = check_text_quality(GARBAGE_TEXT, TextSource.UNKNOWN)

        assert result.is_good_quality is False
        assert result.quality_score <= 20

    def test_fragmented_text_fails(self):
        """Fragmented text is scored low."""
        ai_resp = _make_ai_response(30, False, "Highly fragmented, no coherent sentences.", ["fragmented_sentences"])
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            self._mock_settings(mock_settings)
            result = check_text_quality(FRAGMENTED_TEXT, TextSource.OCR_PREVIOUS)

        assert result.is_good_quality is False

    def test_score_below_threshold_rejected_even_if_ai_says_good(self):
        """Score below threshold forces rejection even when AI returns is_good_quality=True."""
        # This is the key issue from the bug report: score=68 with is_good_quality=True
        # should NOT be accepted.
        ai_resp = _make_ai_response(68, True, "Text is largely legible with some OCR-induced typos.", [])
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            self._mock_settings(mock_settings, threshold=85)
            result = check_text_quality(POOR_OCR_TEXT, TextSource.OCR_PREVIOUS)

        assert result.is_good_quality is False
        assert result.quality_score == 68

    def test_significant_issues_force_rejection_above_threshold(self):
        """Significant issues force rejection even when score is above threshold."""
        # Score is 88 (above default threshold of 85), but has excessive_typos and garbage_characters.
        ai_resp = _make_ai_response(
            88,
            True,
            "Mostly readable text with some OCR artefacts.",
            ["excessive_typos", "garbage_characters"],
        )
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            self._mock_settings(mock_settings, threshold=85)
            result = check_text_quality(POOR_OCR_TEXT, TextSource.OCR_PREVIOUS)

        assert result.is_good_quality is False
        assert result.quality_score == 88

    def test_significant_issues_with_incoherent_text(self):
        """incoherent_text in issues forces rejection even above threshold."""
        ai_resp = _make_ai_response(
            90,
            True,
            "Text has coherent paragraphs but some incoherent passages.",
            ["incoherent_text"],
        )
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            self._mock_settings(mock_settings, threshold=85)
            result = check_text_quality(POOR_OCR_TEXT, TextSource.OCR_PREVIOUS)

        assert result.is_good_quality is False

    def test_non_significant_issues_do_not_block_good_score(self):
        """Issues not in significant_issues list do not override a good score."""
        # 'minor_formatting' is not in the significant issues list.
        ai_resp = _make_ai_response(
            90,
            True,
            "Well-structured text with minor formatting issues.",
            ["minor_formatting"],
        )
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            self._mock_settings(mock_settings, threshold=85)
            result = check_text_quality(GOOD_TEXT, TextSource.OCR_PREVIOUS)

        assert result.is_good_quality is True
        assert result.quality_score == 90

    def test_borderline_score_below_threshold_is_rejected(self):
        """A score just below the threshold is rejected regardless of AI verdict."""
        ai_resp = _make_ai_response(84, True, "Mostly readable despite minor issues.", [])
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            self._mock_settings(mock_settings, threshold=85)
            result = check_text_quality(GOOD_TEXT, TextSource.OCR_PREVIOUS)

        # Score 84 < threshold 85 → rejected
        assert result.is_good_quality is False
        assert result.quality_score == 84

    def test_borderline_score_at_threshold_is_accepted(self):
        """A score exactly at the threshold is accepted when no significant issues."""
        ai_resp = _make_ai_response(85, True, "Meets the quality threshold.", [])
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            self._mock_settings(mock_settings, threshold=85)
            result = check_text_quality(GOOD_TEXT, TextSource.OCR_PREVIOUS)

        assert result.is_good_quality is True
        assert result.quality_score == 85

    def test_markdown_fences_stripped_before_parse(self):
        """The parser handles AI responses wrapped in markdown code fences."""
        import json as _json

        inner = _json.dumps({"quality_score": 90, "is_good_quality": True, "feedback": "Fine.", "issues": []})
        fenced = f"```json\n{inner}\n```"
        provider = self._mock_provider(fenced)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            self._mock_settings(mock_settings)
            result = check_text_quality(GOOD_TEXT, TextSource.UNKNOWN)

        assert result.is_good_quality is True
        assert result.quality_score == 90

    def test_raw_ai_response_stored_in_result(self):
        """The raw AI response is preserved in TextQualityResult.ai_response_raw."""
        ai_resp = _make_ai_response(88, True, "Good text.", [])
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            self._mock_settings(mock_settings)
            result = check_text_quality(GOOD_TEXT, TextSource.OCR_PREVIOUS)

        assert result.ai_response_raw == ai_resp

    def test_text_truncated_to_sample_max(self):
        """Text longer than _TEXT_SAMPLE_MAX_CHARS is truncated before sending to AI."""
        from app.utils.text_quality import _TEXT_SAMPLE_MAX_CHARS

        long_text = "a" * (_TEXT_SAMPLE_MAX_CHARS + 5000)
        ai_resp = _make_ai_response(90, True, "Fine.", [])
        provider = self._mock_provider(ai_resp)
        captured_prompts: list[str] = []

        def _capture(messages, model, temperature=0, **kw):
            captured_prompts.append(messages[-1]["content"])
            return ai_resp

        provider.chat_completion.side_effect = _capture

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            self._mock_settings(mock_settings)
            check_text_quality(long_text, TextSource.UNKNOWN)

        assert len(captured_prompts) == 1
        # The prompt should NOT contain more than _TEXT_SAMPLE_MAX_CHARS "a"s
        assert "a" * (_TEXT_SAMPLE_MAX_CHARS + 1) not in captured_prompts[0]


# ---------------------------------------------------------------------------
# check_text_quality – error / edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckTextQualityErrorHandling:
    """Tests for failure modes that must not crash the pipeline."""

    def test_json_parse_error_returns_good_quality(self):
        """Unparseable AI response defaults to good quality (avoids false negatives)."""
        provider = MagicMock()
        provider.chat_completion.return_value = "This is not JSON at all."

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            mock_settings.ai_model = None
            mock_settings.openai_model = "gpt-4o-mini"
            mock_settings.text_quality_threshold = 85
            mock_settings.text_quality_significant_issues = [
                "excessive_typos",
                "garbage_characters",
                "incoherent_text",
                "fragmented_sentences",
            ]
            result = check_text_quality(GOOD_TEXT, TextSource.UNKNOWN)

        assert result.is_good_quality is True
        assert result.quality_score == 50

    def test_ai_provider_exception_returns_good_quality(self):
        """If the AI provider raises an exception, default to good quality."""
        provider = MagicMock()
        provider.chat_completion.side_effect = RuntimeError("API timeout")

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            mock_settings.ai_model = None
            mock_settings.openai_model = "gpt-4o-mini"
            mock_settings.text_quality_threshold = 85
            mock_settings.text_quality_significant_issues = [
                "excessive_typos",
                "garbage_characters",
                "incoherent_text",
                "fragmented_sentences",
            ]
            result = check_text_quality(GOOD_TEXT, TextSource.OCR_PREVIOUS)

        assert result.is_good_quality is True
        assert result.quality_score == 50

    def test_ai_provider_exception_stores_none_raw_response(self):
        """ai_response_raw should be None when the provider raises before returning."""
        provider = MagicMock()
        provider.chat_completion.side_effect = ConnectionError("no internet")

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            mock_settings.ai_model = None
            mock_settings.openai_model = "gpt-4o-mini"
            mock_settings.text_quality_threshold = 85
            mock_settings.text_quality_significant_issues = [
                "excessive_typos",
                "garbage_characters",
                "incoherent_text",
                "fragmented_sentences",
            ]
            result = check_text_quality(GOOD_TEXT, TextSource.UNKNOWN)

        assert result.ai_response_raw is None


# ---------------------------------------------------------------------------
# TextQualityResult dataclass
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTextQualityResult:
    """Tests for the TextQualityResult dataclass."""

    def test_default_issues_is_empty_list(self):
        result = TextQualityResult(
            is_good_quality=True,
            quality_score=90,
            text_source=TextSource.DIGITAL,
            feedback="Good.",
        )
        assert result.issues == []
        assert result.ai_response_raw is None

    def test_issues_field(self):
        result = TextQualityResult(
            is_good_quality=False,
            quality_score=20,
            text_source=TextSource.OCR_PREVIOUS,
            feedback="Bad.",
            issues=["excessive_typos"],
        )
        assert result.issues == ["excessive_typos"]


# ---------------------------------------------------------------------------
# Integration: process_document task with text quality check
# ---------------------------------------------------------------------------

# Build a minimal but real PDF with embedded text so pypdf.PdfReader works.
_EMBEDDED_TEXT_PDF = b"""%PDF-1.4
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
(Invoice total is $252.63) Tj
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
404
%%EOF
"""


@pytest.mark.unit
@pytest.mark.requires_db
class TestProcessDocumentTextQuality:
    """Integration tests verifying quality check in process_document."""

    def _write_pdf(self, tmp_path, name: str = "doc.pdf") -> str:
        p = tmp_path / name
        p.write_bytes(_EMBEDDED_TEXT_PDF)
        return str(p)

    def test_quality_check_disabled_skips_ai(self, db_session, tmp_path):
        """When enable_text_quality_check=False, the AI is never called."""
        from app.tasks.process_document import process_document

        pdf_path = self._write_pdf(tmp_path)

        with (
            patch("app.tasks.process_document.SessionLocal") as mock_sl,
            patch("app.tasks.process_document.settings") as mock_settings,
            patch("app.tasks.process_document.log_task_progress"),
            patch("app.tasks.process_document.extract_metadata_with_gpt") as mock_gpt,
            patch("app.tasks.process_document.detect_pdf_text_source") as mock_detect,
            patch("app.tasks.process_document.check_text_quality") as mock_check,
        ):
            mock_sl.return_value.__enter__.return_value = db_session
            mock_sl.return_value.__exit__.return_value = None
            mock_settings.workdir = str(tmp_path)
            mock_settings.enable_deduplication = False
            mock_settings.show_deduplication_step = False
            mock_settings.enable_text_quality_check = False

            result = process_document.run(pdf_path)

        mock_detect.assert_not_called()
        mock_check.assert_not_called()
        mock_gpt.delay.assert_called_once()
        assert result["status"] == "Text extracted locally"

    def test_quality_check_good_text_proceeds_to_gpt(self, db_session, tmp_path):
        """When quality check passes, metadata extraction is queued normally."""
        from app.tasks.process_document import process_document

        pdf_path = self._write_pdf(tmp_path)

        good_quality = TextQualityResult(
            is_good_quality=True,
            quality_score=90,
            text_source=TextSource.OCR_PREVIOUS,
            feedback="Good readable text.",
        )

        with (
            patch("app.tasks.process_document.SessionLocal") as mock_sl,
            patch("app.tasks.process_document.settings") as mock_settings,
            patch("app.tasks.process_document.log_task_progress"),
            patch("app.tasks.process_document.extract_metadata_with_gpt") as mock_gpt,
            patch("app.tasks.process_document.process_with_ocr") as mock_ocr,
            patch("app.tasks.process_document.detect_pdf_text_source", return_value=TextSource.OCR_PREVIOUS),
            patch("app.tasks.process_document.check_text_quality", return_value=good_quality),
        ):
            mock_sl.return_value.__enter__.return_value = db_session
            mock_sl.return_value.__exit__.return_value = None
            mock_settings.workdir = str(tmp_path)
            mock_settings.enable_deduplication = False
            mock_settings.show_deduplication_step = False
            mock_settings.enable_text_quality_check = True

            result = process_document.run(pdf_path)

        mock_gpt.delay.assert_called_once()
        mock_ocr.delay.assert_not_called()
        assert result["status"] == "Text extracted locally"

    def test_quality_check_poor_text_triggers_ocr(self, db_session, tmp_path):
        """When quality check fails, OCR is queued instead of GPT extraction."""
        from app.tasks.process_document import process_document

        pdf_path = self._write_pdf(tmp_path)

        poor_quality = TextQualityResult(
            is_good_quality=False,
            quality_score=20,
            text_source=TextSource.OCR_PREVIOUS,
            feedback="Severe OCR artefacts.",
            issues=["excessive_typos", "garbage_characters"],
        )

        with (
            patch("app.tasks.process_document.SessionLocal") as mock_sl,
            patch("app.tasks.process_document.settings") as mock_settings,
            patch("app.tasks.process_document.log_task_progress"),
            patch("app.tasks.process_document.extract_metadata_with_gpt") as mock_gpt,
            patch("app.tasks.process_document.process_with_ocr") as mock_ocr,
            patch("app.tasks.process_document.detect_pdf_text_source", return_value=TextSource.OCR_PREVIOUS),
            patch("app.tasks.process_document.check_text_quality", return_value=poor_quality),
        ):
            mock_sl.return_value.__enter__.return_value = db_session
            mock_sl.return_value.__exit__.return_value = None
            mock_settings.workdir = str(tmp_path)
            mock_settings.enable_deduplication = False
            mock_settings.show_deduplication_step = False
            mock_settings.enable_text_quality_check = True

            result = process_document.run(pdf_path)

        mock_ocr.delay.assert_called_once()
        mock_gpt.delay.assert_not_called()
        assert "OCR" in result["status"]
        # Verify original text is passed to the OCR task for comparison
        call_args = mock_ocr.delay.call_args
        assert call_args is not None
        # Third argument (original_text) should be a non-empty string
        assert len(call_args.args) >= 3
        assert isinstance(call_args.args[2], str)
        assert len(call_args.args[2]) > 0

    def test_quality_check_digital_source_skips_ai_call(self, db_session, tmp_path):
        """Digital-origin PDFs bypass the AI and proceed directly to GPT."""
        from app.tasks.process_document import process_document

        pdf_path = self._write_pdf(tmp_path)

        digital_result = TextQualityResult(
            is_good_quality=True,
            quality_score=100,
            text_source=TextSource.DIGITAL,
            feedback="Digitally-created PDF – text quality assumed correct; no AI check performed.",
        )

        with (
            patch("app.tasks.process_document.SessionLocal") as mock_sl,
            patch("app.tasks.process_document.settings") as mock_settings,
            patch("app.tasks.process_document.log_task_progress"),
            patch("app.tasks.process_document.extract_metadata_with_gpt") as mock_gpt,
            patch("app.tasks.process_document.process_with_ocr") as mock_ocr,
            patch("app.tasks.process_document.detect_pdf_text_source", return_value=TextSource.DIGITAL),
            patch("app.tasks.process_document.check_text_quality", return_value=digital_result),
        ):
            mock_sl.return_value.__enter__.return_value = db_session
            mock_sl.return_value.__exit__.return_value = None
            mock_settings.workdir = str(tmp_path)
            mock_settings.enable_deduplication = False
            mock_settings.show_deduplication_step = False
            mock_settings.enable_text_quality_check = True

            result = process_document.run(pdf_path)

        mock_gpt.delay.assert_called_once()
        mock_ocr.delay.assert_not_called()
        assert result["status"] == "Text extracted locally"


# ---------------------------------------------------------------------------
# TextComparisonResult dataclass
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTextComparisonResult:
    """Tests for the TextComparisonResult dataclass."""

    def test_default_ai_response_raw_is_none(self):
        result = TextComparisonResult(
            preferred="ocr",
            original_score=60,
            ocr_score=85,
            explanation="OCR is cleaner.",
        )
        assert result.preferred == "ocr"
        assert result.original_score == 60
        assert result.ocr_score == 85
        assert result.ai_response_raw is None

    def test_preferred_original(self):
        result = TextComparisonResult(
            preferred="original",
            original_score=90,
            ocr_score=70,
            explanation="Original is higher quality.",
        )
        assert result.preferred == "original"


# ---------------------------------------------------------------------------
# compare_text_quality
# ---------------------------------------------------------------------------


def _make_comparison_response(original_score: int, ocr_score: int, preferred: str, explanation: str) -> str:
    import json as _json

    return _json.dumps(
        {
            "original_score": original_score,
            "ocr_score": ocr_score,
            "preferred": preferred,
            "explanation": explanation,
        }
    )


@pytest.mark.unit
class TestCompareTextQuality:
    """Tests for compare_text_quality() head-to-head comparison."""

    def _mock_provider(self, response: str) -> MagicMock:
        provider = MagicMock()
        provider.chat_completion.return_value = response
        return provider

    def test_ocr_preferred(self):
        """When AI prefers OCR text, preferred='ocr'."""
        ai_resp = _make_comparison_response(60, 88, "ocr", "OCR output is much cleaner.")
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            mock_settings.ai_model = "gpt-4o-mini"
            mock_settings.openai_model = "gpt-4o-mini"
            result = compare_text_quality(POOR_OCR_TEXT, GOOD_TEXT)

        assert result.preferred == "ocr"
        assert result.original_score == 60
        assert result.ocr_score == 88
        assert "OCR" in result.explanation

    def test_original_preferred(self):
        """When AI prefers original text, preferred='original'."""
        ai_resp = _make_comparison_response(92, 70, "original", "Original is higher quality.")
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            mock_settings.ai_model = "gpt-4o-mini"
            mock_settings.openai_model = "gpt-4o-mini"
            result = compare_text_quality(GOOD_TEXT, POOR_OCR_TEXT)

        assert result.preferred == "original"
        assert result.original_score == 92
        assert result.ocr_score == 70

    def test_equal_preferred(self):
        """When AI finds both equal, preferred='equal'."""
        ai_resp = _make_comparison_response(85, 85, "equal", "Both texts are equivalent quality.")
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            mock_settings.ai_model = None
            mock_settings.openai_model = "gpt-4o-mini"
            result = compare_text_quality(GOOD_TEXT, GOOD_TEXT)

        assert result.preferred == "equal"

    def test_invalid_preferred_value_defaults_to_ocr(self):
        """An unexpected preferred value in the AI response defaults to 'ocr'."""
        import json as _json

        ai_resp = _json.dumps(
            {
                "original_score": 80,
                "ocr_score": 75,
                "preferred": "neither",  # invalid
                "explanation": "Both are bad.",
            }
        )
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            mock_settings.ai_model = None
            mock_settings.openai_model = "gpt-4o-mini"
            result = compare_text_quality(GOOD_TEXT, GOOD_TEXT)

        assert result.preferred == "ocr"

    def test_markdown_fences_stripped(self):
        """Markdown code fences in comparison response are stripped before parsing."""
        import json as _json

        inner = _json.dumps(
            {"original_score": 70, "ocr_score": 90, "preferred": "ocr", "explanation": "OCR is better."}
        )
        fenced = f"```json\n{inner}\n```"
        provider = self._mock_provider(fenced)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            mock_settings.ai_model = None
            mock_settings.openai_model = "gpt-4o-mini"
            result = compare_text_quality(POOR_OCR_TEXT, GOOD_TEXT)

        assert result.preferred == "ocr"
        assert result.ocr_score == 90

    def test_ai_error_defaults_to_ocr(self):
        """AI error during comparison safely defaults to OCR text preferred."""
        provider = MagicMock()
        provider.chat_completion.side_effect = RuntimeError("Timeout")

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            mock_settings.ai_model = None
            mock_settings.openai_model = "gpt-4o-mini"
            result = compare_text_quality(POOR_OCR_TEXT, GOOD_TEXT)

        assert result.preferred == "ocr"
        assert "Timeout" in result.explanation

    def test_raw_response_stored(self):
        """The raw AI response is stored in ai_response_raw."""
        ai_resp = _make_comparison_response(75, 88, "ocr", "OCR is better.")
        provider = self._mock_provider(ai_resp)

        with (
            patch("app.utils.text_quality.get_ai_provider", return_value=provider),
            patch("app.utils.text_quality.settings") as mock_settings,
        ):
            mock_settings.ai_model = None
            mock_settings.openai_model = "gpt-4o-mini"
            result = compare_text_quality(POOR_OCR_TEXT, GOOD_TEXT)

        assert result.ai_response_raw == ai_resp
