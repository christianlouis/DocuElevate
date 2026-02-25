"""Utility module for assessing the quality of embedded text in PDF documents.

This module provides functionality to:

- Detect whether a PDF's embedded text came from a digital creation process
  (e.g., exported from Word, LibreOffice, LaTeX) or a previous OCR pass.
- Assess the quality of extracted text using an AI model.
- Compare two candidate text extractions and choose the higher-quality one.
- Log detailed feedback for debugging and continuous improvement.

**Rationale**

Some files contain embedded text that is of poor quality — characterised by
excessive typos, nonsensical content, or textual fragments that do not reflect
the meaning of the document.  The most common cause is that the PDF was
previously processed by an OCR engine of varying quality.

If the embedded text is from a digitally created PDF, the quality is assumed to
be good and no AI check is performed.  If the text appears to come from a prior
OCR pass (or the source is unknown), the AI quality check is performed.  Poor
quality text triggers automatic re-OCR so that the downstream pipeline operates
on the best available text.

After re-OCR, the new text is scored and compared head-to-head against the
original embedded text via :func:`compare_text_quality` to ensure the pipeline
always uses the highest-quality extraction available.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.config import settings
from app.utils.ai_provider import get_ai_provider

logger = logging.getLogger(__name__)

# Maximum characters of text forwarded to the AI for quality assessment.
_TEXT_SAMPLE_MAX_CHARS = 3000

# ---------------------------------------------------------------------------
# Text source detection
# ---------------------------------------------------------------------------

# Keywords (lower-cased) in /Producer or /Creator that indicate a prior OCR pass.
_OCR_PRODUCER_KEYWORDS: list[str] = [
    "tesseract",
    "ocrmypdf",
    "abbyy",
    "nuance",
    "readiris",
    "omnipage",
    "recognita",
    "recogniform",
    "acrobat capture",
    "pdf ocr",
    "exactscan",
    "iris ocr",
    "prizmo",
    "pdfsandwich",
    "pdf2searchable",
]

# Keywords (lower-cased) in /Producer or /Creator that indicate digital authoring.
_DIGITAL_PRODUCER_KEYWORDS: list[str] = [
    "microsoft",
    "libreoffice",
    "openoffice",
    "indesign",
    "photoshop",
    "quarkxpress",
    "latex",
    "pdftex",
    "pdflatex",
    "xetex",
    "lualatex",
    "word",
    "excel",
    "powerpoint",
    "pages",
    "keynote",
    "numbers",
    "scribus",
    "affinity",
    "canva",
    "fpdf",
    "reportlab",
    "itext",
    "fpdf2",
    "wkhtmltopdf",
    "google docs",
    "chromium",
    "chrome",
    "webkit",
    "prawn",
    "cairo",
    "pango",
    "ghostscript",
    "inkscape",
]


class TextSource(str, Enum):
    """Indicates the origin of text embedded in a PDF."""

    DIGITAL = "digital"  # Created by a digital authoring tool (Word, LibreOffice, LaTeX…)
    OCR_PREVIOUS = "ocr"  # Previously run through an OCR engine
    UNKNOWN = "unknown"  # Source cannot be determined


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------


@dataclass
class TextQualityResult:
    """Result of an embedded-text quality assessment."""

    is_good_quality: bool
    quality_score: int  # 0-100; 0 = completely garbled, 100 = perfect
    text_source: TextSource
    feedback: str
    issues: list[str] = field(default_factory=list)
    ai_response_raw: Optional[str] = None


@dataclass
class TextComparisonResult:
    """Result of a head-to-head comparison between two candidate texts."""

    preferred: str  # "original" | "ocr" | "equal"
    original_score: int
    ocr_score: int
    explanation: str
    ai_response_raw: Optional[str] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_pdf_text_source(pdf_path: str) -> TextSource:
    """Detect whether a PDF's text layer was created digitally or via OCR.

    Inspects the ``/Producer`` and ``/Creator`` metadata fields for known OCR
    or digital-authoring-tool names.

    Args:
        pdf_path: Absolute path to the PDF file.

    Returns:
        :class:`TextSource` indicating the likely origin of the embedded text.
    """
    try:
        import pypdf

        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            info = reader.metadata or {}

        producer = str(info.get("/Producer", "") or "").lower()
        creator = str(info.get("/Creator", "") or "").lower()
        combined = f"{producer} {creator}"

        logger.debug(f"[text_quality] PDF metadata – Producer: {producer!r}, Creator: {creator!r}")

        for keyword in _OCR_PRODUCER_KEYWORDS:
            if keyword in combined:
                logger.info(
                    f"[text_quality] Detected OCR-origin PDF "
                    f"(keyword={keyword!r}, producer={producer!r}, creator={creator!r})"
                )
                return TextSource.OCR_PREVIOUS

        for keyword in _DIGITAL_PRODUCER_KEYWORDS:
            if keyword in combined:
                logger.info(
                    f"[text_quality] Detected digitally-created PDF "
                    f"(keyword={keyword!r}, producer={producer!r}, creator={creator!r})"
                )
                return TextSource.DIGITAL

        logger.info(
            f"[text_quality] Could not determine PDF text source "
            f"(producer={producer!r}, creator={creator!r}); treating as UNKNOWN"
        )
        return TextSource.UNKNOWN

    except Exception as exc:
        logger.warning(f"[text_quality] Failed to read PDF metadata from {pdf_path}: {exc}")
        return TextSource.UNKNOWN


def check_text_quality(text: str, text_source: TextSource) -> TextQualityResult:
    """Assess the quality of embedded PDF text using an AI model.

    Digitally-originated text is assumed to be correct and is **not** forwarded
    to the AI.  Text from a previous OCR pass, or of unknown origin, is
    assessed for:

    - Excessive typos and OCR character-substitution artefacts.
    - Lack of semantic coherence.
    - Garbage characters or symbol soup.

    The acceptance criteria are controlled by two settings:

    - ``settings.text_quality_threshold`` – minimum score (default 85) for
      auto-acceptance.
    - ``settings.text_quality_significant_issues`` – list of issue labels that
      force re-OCR even when the score meets the threshold (e.g.
      ``excessive_typos``, ``garbage_characters``, ``incoherent_text``,
      ``fragmented_sentences``).

    The text sample and the full AI feedback are logged at DEBUG / INFO level
    to aid debugging and continuous quality improvement.

    Args:
        text: The extracted text content to evaluate.
        text_source: Where the text came from (digital, OCR, or unknown).

    Returns:
        :class:`TextQualityResult` with the quality assessment.
    """
    # 1. Digital PDFs are assumed good – skip the AI call entirely.
    if text_source == TextSource.DIGITAL:
        logger.info(
            "[text_quality] Skipping quality check for digitally-created PDF "
            "(source detected as digital; text quality assumed correct)."
        )
        return TextQualityResult(
            is_good_quality=True,
            quality_score=100,
            text_source=text_source,
            feedback="Digitally-created PDF – text quality assumed correct; no AI check performed.",
        )

    # 2. Trivial case: empty or whitespace-only text.
    stripped = text.strip()
    if not stripped:
        logger.info("[text_quality] Text is empty; marking as poor quality.")
        return TextQualityResult(
            is_good_quality=False,
            quality_score=0,
            text_source=text_source,
            feedback="No text content to evaluate.",
            issues=["empty_text"],
        )

    # 3. Retrieve configurable thresholds.
    threshold = getattr(settings, "text_quality_threshold", 85)
    significant_issues: list[str] = list(
        getattr(
            settings,
            "text_quality_significant_issues",
            ["excessive_typos", "garbage_characters", "incoherent_text", "fragmented_sentences"],
        )
    )

    sample = stripped[:_TEXT_SAMPLE_MAX_CHARS]
    logger.info(
        f"[text_quality] Assessing text quality "
        f"(source={text_source.value}, sample_chars={len(sample)}, total_chars={len(stripped)}, "
        f"threshold={threshold})"
    )
    logger.debug(f"[text_quality] Text sample forwarded to AI:\n{sample}")

    prompt = (
        "You are a document quality assessor. Your task is to evaluate whether the "
        "text extracted from a PDF is high-quality and semantically meaningful, or "
        "whether it looks like garbled OCR output with typos, garbage characters, or "
        "nonsensical fragments.\n\n"
        "Evaluate the following text and return a JSON object with exactly these fields:\n"
        '  "quality_score": integer 0-100 (0=completely garbled, 100=perfect text)\n'
        f'  "is_good_quality": boolean (true if quality_score >= {threshold} AND no significant issues)\n'
        '  "feedback": one-sentence summary of your assessment\n'
        '  "issues": list of issues found (e.g. ["excessive_typos", "garbage_characters", '
        '"incoherent_text", "fragmented_sentences"]); empty list if none\n\n'
        f"Criteria for POOR quality (score < {threshold}):\n"
        "- Excessive typos, misspellings, or letter substitutions typical of OCR errors\n"
        "- Garbage characters (%, @, #, symbols mixed randomly into words)\n"
        "- Incoherent or nonsensical sentences that carry no meaning\n"
        "- Sequences of random characters or numbers without context\n"
        "- Heavy fragmentation (isolated letters or words without sentence structure)\n\n"
        f"Criteria for GOOD quality (score >= {threshold}):\n"
        "- Mostly readable text with at most very minor imperfections\n"
        "- Coherent sentences and/or paragraphs\n"
        "- Recognisable language (any language accepted)\n"
        "- No significant OCR artefacts\n\n"
        f"Text to evaluate:\n---\n{sample}\n---\n\n"
        "Return only the JSON object, no markdown fences."
    )

    response_text: Optional[str] = None
    try:
        provider = get_ai_provider()
        model = settings.ai_model or settings.openai_model or "gpt-4o-mini"
        response_text = provider.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "You are a document quality assessor. Respond only with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            model=model,
            temperature=0,
        )

        logger.info(f"[text_quality] AI quality check raw response: {response_text[:500]}")

        # Strip optional markdown code fences before parsing.
        clean = re.sub(r"```(?:json)?\s*", "", response_text).strip().rstrip("`").strip()
        parsed: dict = json.loads(clean)

        quality_score = int(parsed.get("quality_score", 0))
        is_good_ai = bool(parsed.get("is_good_quality", quality_score >= threshold))
        feedback = str(parsed.get("feedback", ""))
        issues = list(parsed.get("issues", []))

        # Apply strict rules: reject when score is below threshold OR when any
        # significant issue is present (even if the AI says is_good_quality=true).
        score_ok = quality_score >= threshold
        has_significant_issue = bool(significant_issues and any(i in issues for i in significant_issues))

        if has_significant_issue and is_good_ai:
            logger.warning(
                f"[text_quality] Overriding AI is_good_quality=True – significant issues present: "
                f"{[i for i in issues if i in significant_issues]}  (score={quality_score})"
            )

        is_good = score_ok and is_good_ai and not has_significant_issue

        logger.info(
            f"[text_quality] Quality assessment complete – "
            f"score={quality_score}, threshold={threshold}, score_ok={score_ok}, "
            f"ai_good={is_good_ai}, significant_issues_found={has_significant_issue}, "
            f"final_good={is_good}, issues={issues}, feedback={feedback!r}"
        )

        return TextQualityResult(
            is_good_quality=is_good,
            quality_score=quality_score,
            text_source=text_source,
            feedback=feedback,
            issues=issues,
            ai_response_raw=response_text,
        )

    except json.JSONDecodeError as exc:
        logger.warning(
            f"[text_quality] Could not parse AI quality response as JSON: {exc}. "
            "Treating text as acceptable quality to avoid false negatives."
        )
        return TextQualityResult(
            is_good_quality=True,
            quality_score=50,
            text_source=text_source,
            feedback=f"AI response could not be parsed as JSON ({exc}); assuming acceptable quality.",
            ai_response_raw=response_text,
        )

    except Exception as exc:
        logger.error(
            f"[text_quality] AI quality check failed: {exc}. "
            "Treating text as acceptable quality to avoid false negatives."
        )
        return TextQualityResult(
            is_good_quality=True,
            quality_score=50,
            text_source=text_source,
            feedback=f"Quality check could not be performed ({exc}); assuming acceptable quality.",
            ai_response_raw=response_text,
        )


def compare_text_quality(original_text: str, ocr_text: str) -> TextComparisonResult:
    """Compare the quality of two candidate text extractions side-by-side using AI.

    Used after a re-OCR pass to decide whether the new OCR output is actually
    better than the original embedded text.  The AI evaluates both texts
    independently and then picks the preferred one.

    Args:
        original_text: Text extracted from the PDF's original embedded layer.
        ocr_text: Text produced by the re-OCR pipeline.

    Returns:
        :class:`TextComparisonResult` indicating which text is preferred and why.
    """
    orig_sample = original_text.strip()[:_TEXT_SAMPLE_MAX_CHARS]
    ocr_sample = ocr_text.strip()[:_TEXT_SAMPLE_MAX_CHARS]

    logger.info(f"[text_quality] Comparing original ({len(orig_sample)} chars) vs OCR ({len(ocr_sample)} chars) texts")

    prompt = (
        "You are a document quality assessor comparing two text extractions from the same PDF.\n\n"
        "TEXT A (original embedded text):\n"
        f"---\n{orig_sample}\n---\n\n"
        "TEXT B (re-OCR text):\n"
        f"---\n{ocr_sample}\n---\n\n"
        "Score each text independently (0–100) and decide which is better for downstream "
        "document processing (metadata extraction, search, AI analysis).\n\n"
        "Return a JSON object with exactly these fields:\n"
        '  "original_score": integer 0-100 for TEXT A\n'
        '  "ocr_score": integer 0-100 for TEXT B\n'
        '  "preferred": one of "original", "ocr", or "equal"\n'
        '  "explanation": one-sentence rationale\n\n'
        "Return only the JSON object, no markdown fences."
    )

    response_text: Optional[str] = None
    try:
        provider = get_ai_provider()
        model = settings.ai_model or settings.openai_model or "gpt-4o-mini"
        response_text = provider.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "You are a document quality assessor. Respond only with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            model=model,
            temperature=0,
        )

        logger.info(f"[text_quality] AI comparison raw response: {response_text[:500]}")

        clean = re.sub(r"```(?:json)?\s*", "", response_text).strip().rstrip("`").strip()
        parsed: dict = json.loads(clean)

        original_score = int(parsed.get("original_score", 0))
        ocr_score = int(parsed.get("ocr_score", 0))
        preferred = str(parsed.get("preferred", "ocr"))
        explanation = str(parsed.get("explanation", ""))

        if preferred not in ("original", "ocr", "equal"):
            logger.warning(f"[text_quality] Unexpected preferred value {preferred!r}; defaulting to 'ocr'")
            preferred = "ocr"

        logger.info(
            f"[text_quality] Comparison result – original={original_score}, ocr={ocr_score}, "
            f"preferred={preferred!r}, explanation={explanation!r}"
        )

        return TextComparisonResult(
            preferred=preferred,
            original_score=original_score,
            ocr_score=ocr_score,
            explanation=explanation,
            ai_response_raw=response_text,
        )

    except Exception as exc:
        logger.warning(f"[text_quality] Comparison failed ({exc}); defaulting to OCR text.")
        # Safe fallback: if comparison fails, keep the OCR result (which was
        # triggered because the original text was already deemed poor).
        return TextComparisonResult(
            preferred="ocr",
            original_score=0,
            ocr_score=0,
            explanation=f"Comparison could not be performed ({exc}); defaulting to OCR output.",
            ai_response_raw=response_text,
        )
