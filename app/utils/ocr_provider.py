#!/usr/bin/env python3
"""OCR provider abstraction layer for DocuElevate.

This module provides a pluggable abstraction for various OCR engines, allowing
the platform to work with Azure Document Intelligence, Tesseract, EasyOCR,
Mistral OCR, Google Cloud Document AI, and AWS Textract without being locked to
a single vendor.

Provider selection is controlled by the ``OCR_PROVIDERS`` environment variable
(comma-separated list, e.g. ``azure,tesseract``).  When multiple providers are
specified, all enabled providers run in parallel and the results are
cross-checked by the configured AI model to produce the best final output.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)


class OCRResult:
    """Container for a single OCR provider's output.

    Attributes:
        provider: Name of the OCR provider (e.g. ``"azure"``, ``"tesseract"``).
        text: The extracted plain text.
        searchable_pdf_path: Optional path to a searchable PDF produced by the
            provider.  ``None`` when the provider does not produce PDFs.
        rotation_data: Optional dict mapping page indices to detected rotation
            angles (same format used by the Azure task).
        metadata: Provider-specific metadata dict (e.g. confidence scores).
    """

    def __init__(
        self,
        provider: str,
        text: str,
        searchable_pdf_path: Optional[str] = None,
        rotation_data: Optional[Dict[int, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.provider = provider
        self.text = text
        self.searchable_pdf_path = searchable_pdf_path
        self.rotation_data = rotation_data or {}
        self.metadata = metadata or {}

    def __repr__(self) -> str:
        return (
            f"OCRResult(provider={self.provider!r}, "
            f"chars={len(self.text)}, "
            f"has_pdf={self.searchable_pdf_path is not None})"
        )


class OCRProvider(ABC):
    """Abstract base class for OCR providers.

    Concrete providers must implement :meth:`process`, which accepts a path to a
    PDF file and returns an :class:`OCRResult`.

    Subclasses should also set :attr:`name` to a short, stable identifier
    (e.g. ``"azure"``, ``"tesseract"``).
    """

    #: Short, stable identifier for this provider.  Must match the key used in
    #: :data:`_PROVIDER_MAP` and in the ``OCR_PROVIDERS`` setting.
    name: str = "unknown"

    @abstractmethod
    def process(self, file_path: str) -> OCRResult:
        """Run OCR on *file_path* and return an :class:`OCRResult`.

        Args:
            file_path: Absolute path to the input PDF file.

        Returns:
            An :class:`OCRResult` with the extracted text and optional
            searchable-PDF path.

        Raises:
            Exception: If OCR processing fails.
        """


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


class AzureOCRProvider(OCRProvider):
    """OCR via Azure Document Intelligence (the existing provider).

    Credentials are read from ``settings.azure_ai_key`` and
    ``settings.azure_endpoint``.
    """

    name = "azure"

    def process(self, file_path: str) -> OCRResult:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.ai.documentintelligence.models import AnalyzeOutputOption
        from azure.core.credentials import AzureKeyCredential

        if not settings.azure_ai_key:
            raise ValueError("AZURE_AI_KEY must be set when using the Azure OCR provider.")
        if not settings.azure_endpoint:
            raise ValueError("AZURE_ENDPOINT must be set when using the Azure OCR provider.")

        client = DocumentIntelligenceClient(
            endpoint=settings.azure_endpoint,
            credential=AzureKeyCredential(settings.azure_ai_key),
        )

        with open(file_path, "rb") as f:
            poller = client.begin_analyze_document("prebuilt-read", body=f, output=[AnalyzeOutputOption.PDF])
        result = poller.result()
        operation_id = poller.details["operation_id"]

        # Extract rotation data
        rotation_data: Dict[int, float] = {}
        if hasattr(result, "pages") and result.pages:
            for i, page in enumerate(result.pages):
                if hasattr(page, "angle") and page.angle is not None and page.angle != 0:
                    rotation_data[i] = page.angle

        # Retrieve searchable PDF
        response = client.get_analyze_result_pdf(model_id=result.model_id, result_id=operation_id)
        searchable_pdf_path = file_path  # overwrite in place
        with open(searchable_pdf_path, "wb") as writer:
            writer.writelines(response)

        extracted_text = result.content if result.content else ""
        logger.info(f"[AzureOCR] Extracted {len(extracted_text)} chars from {os.path.basename(file_path)}")

        return OCRResult(
            provider="azure",
            text=extracted_text,
            searchable_pdf_path=searchable_pdf_path,
            rotation_data=rotation_data,
        )


class TesseractOCRProvider(OCRProvider):
    """OCR via Tesseract (self-hosted, open-source).

    Requires ``pytesseract`` and ``Pillow`` to be installed, plus the
    Tesseract binary on the system.

    Config knobs (from :class:`~app.config.Settings`):
    - ``tesseract_cmd`` – path to the ``tesseract`` binary (optional).
    - ``tesseract_language`` – Tesseract language code(s), e.g. ``"eng"`` or
      ``"eng+deu"`` (default: ``"eng"``).
    """

    name = "tesseract"

    def process(self, file_path: str) -> OCRResult:
        try:
            import pytesseract
            from pdf2image import convert_from_path
        except ImportError as exc:
            raise RuntimeError(
                "pytesseract and pdf2image are required for the Tesseract OCR provider. "
                "Install them with: pip install pytesseract pdf2image"
            ) from exc

        tesseract_cmd = getattr(settings, "tesseract_cmd", None)
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        lang = getattr(settings, "tesseract_language", None) or "eng"

        logger.info(f"[TesseractOCR] Processing {os.path.basename(file_path)} (lang={lang})")
        pages = convert_from_path(file_path, dpi=300)
        texts: List[str] = []
        for i, page_img in enumerate(pages):
            page_text = pytesseract.image_to_string(page_img, lang=lang)
            texts.append(page_text)
            logger.debug(f"[TesseractOCR] Page {i + 1}: {len(page_text)} chars")

        extracted_text = "\n".join(texts)
        logger.info(f"[TesseractOCR] Extracted {len(extracted_text)} chars total")

        return OCRResult(
            provider="tesseract",
            text=extracted_text,
        )


class EasyOCRProvider(OCRProvider):
    """OCR via EasyOCR (self-hosted, deep-learning based).

    Requires the ``easyocr`` package to be installed.

    Config knobs (from :class:`~app.config.Settings`):
    - ``easyocr_languages`` – comma-separated list of language codes
      (default: ``"en"``).
    - ``easyocr_gpu`` – whether to use GPU acceleration (default: ``False``).
    """

    name = "easyocr"

    def process(self, file_path: str) -> OCRResult:
        try:
            import easyocr
            from pdf2image import convert_from_path
        except ImportError as exc:
            raise RuntimeError(
                "easyocr and pdf2image are required for the EasyOCR provider. "
                "Install them with: pip install easyocr pdf2image"
            ) from exc

        lang_str = getattr(settings, "easyocr_languages", None) or "en"
        langs = [lang.strip() for lang in lang_str.split(",") if lang.strip()]
        gpu = getattr(settings, "easyocr_gpu", False)

        logger.info(f"[EasyOCR] Processing {os.path.basename(file_path)} (langs={langs}, gpu={gpu})")
        reader = easyocr.Reader(langs, gpu=gpu)
        pages = convert_from_path(file_path, dpi=300)
        texts: List[str] = []
        for i, page_img in enumerate(pages):
            result = reader.readtext(page_img, detail=0, paragraph=True)
            page_text = "\n".join(result)
            texts.append(page_text)
            logger.debug(f"[EasyOCR] Page {i + 1}: {len(page_text)} chars")

        extracted_text = "\n".join(texts)
        logger.info(f"[EasyOCR] Extracted {len(extracted_text)} chars total")

        return OCRResult(
            provider="easyocr",
            text=extracted_text,
        )


class MistralOCRProvider(OCRProvider):
    """OCR via Mistral's document understanding API.

    Uses the ``mistral-ocr-latest`` model (or ``settings.mistral_ocr_model``)
    via the OpenAI-compatible messages API.

    Config knobs (from :class:`~app.config.Settings`):
    - ``mistral_api_key`` – Mistral API key.
    - ``mistral_ocr_model`` – model name (default: ``"mistral-ocr-latest"``).
    """

    name = "mistral"

    def process(self, file_path: str) -> OCRResult:
        import base64

        try:
            import openai
        except ImportError as exc:
            raise RuntimeError("openai package is required for the Mistral OCR provider.") from exc

        api_key = getattr(settings, "mistral_api_key", None)
        if not api_key:
            raise ValueError("MISTRAL_API_KEY must be set when using the Mistral OCR provider.")

        model = getattr(settings, "mistral_ocr_model", None) or "mistral-ocr-latest"
        base_url = "https://api.mistral.ai/v1"

        logger.info(f"[MistralOCR] Processing {os.path.basename(file_path)} with {model}")

        with open(file_path, "rb") as f:
            pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:application/pdf;base64,{pdf_b64}"},
                        },
                        {
                            "type": "text",
                            "text": "Extract all text from this document. Return only the extracted text, preserving structure.",
                        },
                    ],
                }
            ],
        )
        extracted_text = response.choices[0].message.content or ""
        logger.info(f"[MistralOCR] Extracted {len(extracted_text)} chars")

        return OCRResult(provider="mistral", text=extracted_text)


class GoogleDocAIOCRProvider(OCRProvider):
    """OCR via Google Cloud Document AI.

    Config knobs (from :class:`~app.config.Settings`):
    - ``google_docai_credentials_json`` – Service account JSON (optional;
      falls back to ``google_drive_credentials_json`` or ADC).
    - ``google_docai_project_id`` – GCP project ID (required).
    - ``google_docai_processor_id`` – Document AI processor ID (required).
    - ``google_docai_location`` – processor location, e.g. ``"us"`` (default:
      ``"us"``).
    """

    name = "google_docai"

    def process(self, file_path: str) -> OCRResult:
        try:
            from google.cloud import documentai
            from google.oauth2 import service_account
        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-documentai is required for the Google Document AI OCR provider. "
                "Install it with: pip install google-cloud-documentai"
            ) from exc

        import json

        project_id = getattr(settings, "google_docai_project_id", None)
        processor_id = getattr(settings, "google_docai_processor_id", None)
        location = getattr(settings, "google_docai_location", None) or "us"

        if not project_id or not processor_id:
            raise ValueError(
                "GOOGLE_DOCAI_PROJECT_ID and GOOGLE_DOCAI_PROCESSOR_ID must be set "
                "when using the Google Document AI OCR provider."
            )

        # Credentials: prefer dedicated docai key, then fall back to gdrive SA key
        creds_json = getattr(settings, "google_docai_credentials_json", None) or getattr(
            settings, "google_drive_credentials_json", None
        )

        creds = None
        if creds_json:
            try:
                creds_info = json.loads(creds_json)
                creds = service_account.Credentials.from_service_account_info(
                    creds_info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
            except Exception as e:
                logger.warning(f"[GoogleDocAIOCR] Failed to parse credentials JSON: {e}; using ADC")

        client_options = {"api_endpoint": f"{location}-documentai.googleapis.com"}
        client = documentai.DocumentProcessorServiceClient(
            credentials=creds,
            client_options=client_options,
        )

        processor_name = client.processor_path(project_id, location, processor_id)

        with open(file_path, "rb") as f:
            raw_document = documentai.RawDocument(content=f.read(), mime_type="application/pdf")

        request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)
        result = client.process_document(request=request)
        document = result.document
        extracted_text = document.text or ""
        logger.info(f"[GoogleDocAIOCR] Extracted {len(extracted_text)} chars")

        return OCRResult(provider="google_docai", text=extracted_text)


class AWSTextractOCRProvider(OCRProvider):
    """OCR via AWS Textract.

    Reuses existing AWS credentials from settings (``aws_access_key_id``,
    ``aws_secret_access_key``, ``aws_region``).
    """

    name = "aws_textract"

    def process(self, file_path: str) -> OCRResult:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for the AWS Textract OCR provider.") from exc

        aws_access_key_id = getattr(settings, "aws_access_key_id", None)
        aws_secret_access_key = getattr(settings, "aws_secret_access_key", None)
        region = getattr(settings, "aws_region", None) or "us-east-1"

        if not aws_access_key_id or not aws_secret_access_key:
            raise ValueError(
                "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set when using the AWS Textract OCR provider."
            )

        logger.info(f"[AWSTextract] Processing {os.path.basename(file_path)} (region={region})")

        client = boto3.client(
            "textract",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region,
        )

        with open(file_path, "rb") as f:
            document_bytes = f.read()

        response = client.detect_document_text(Document={"Bytes": document_bytes})

        lines: List[str] = []
        for block in response.get("Blocks", []):
            if block.get("BlockType") == "LINE":
                text = block.get("Text", "")
                if text:
                    lines.append(text)

        extracted_text = "\n".join(lines)
        logger.info(f"[AWSTextract] Extracted {len(extracted_text)} chars")

        return OCRResult(provider="aws_textract", text=extracted_text)


# ---------------------------------------------------------------------------
# Factory & multi-provider orchestration
# ---------------------------------------------------------------------------

_PROVIDER_MAP: Dict[str, type] = {
    "azure": AzureOCRProvider,
    "tesseract": TesseractOCRProvider,
    "easyocr": EasyOCRProvider,
    "mistral": MistralOCRProvider,
    "google_docai": GoogleDocAIOCRProvider,
    "aws_textract": AWSTextractOCRProvider,
}

# Sorted list of known provider names (kept in sync with _PROVIDER_MAP)
KNOWN_OCR_PROVIDERS: List[str] = sorted(_PROVIDER_MAP.keys())

# Maximum characters per OCR result sent to the AI for merging.
# Keeping this bounded prevents excessively large prompts that would exhaust
# the model's context window or incur high token costs.
MAX_OCR_TEXT_FOR_AI_MERGE = 4000


def get_ocr_providers() -> List[OCRProvider]:
    """Return a list of configured OCR provider instances.

    Reads ``settings.ocr_providers`` (comma-separated provider names) and
    returns one instantiated provider per entry.  Falls back to ``["azure"]``
    when the setting is absent.
    """
    raw = getattr(settings, "ocr_providers", None) or "azure"
    provider_names = [name.strip().lower() for name in raw.split(",") if name.strip()]

    providers: List[OCRProvider] = []
    for name in provider_names:
        cls = _PROVIDER_MAP.get(name)
        if cls is None:
            logger.warning(f"Unknown OCR provider '{name}' in OCR_PROVIDERS – skipping.")
            continue
        providers.append(cls())
        logger.debug(f"Registered OCR provider: {name}")

    if not providers:
        logger.warning("No valid OCR providers configured, falling back to Azure.")
        providers.append(AzureOCRProvider())

    return providers


def merge_ocr_results(results: List[OCRResult], filename: str) -> Tuple[str, Optional[str], Dict[int, float]]:
    """Select the best text from multiple OCR results.

    When only one result is available the text is returned as-is.  When
    multiple results exist the AI model is consulted to pick or merge the best
    version (controlled by ``settings.ocr_merge_strategy``).

    Args:
        results: Non-empty list of :class:`OCRResult` objects.
        filename: Document filename used for logging.

    Returns:
        A 3-tuple of ``(best_text, searchable_pdf_path, rotation_data)`` where
        *searchable_pdf_path* and *rotation_data* come from the first result
        that provides them.
    """
    if not results:
        return "", None, {}

    if len(results) == 1:
        r = results[0]
        return r.text, r.searchable_pdf_path, r.rotation_data

    strategy = getattr(settings, "ocr_merge_strategy", None) or "ai_merge"
    logger.info(f"Merging {len(results)} OCR results for {filename} (strategy={strategy})")

    # Best searchable PDF comes from the first provider that produced one
    searchable_pdf_path = next((r.searchable_pdf_path for r in results if r.searchable_pdf_path), None)
    # Best rotation data comes from the first provider that detected any
    rotation_data = next((r.rotation_data for r in results if r.rotation_data), {})

    if strategy == "primary":
        # Simply return the first result's text
        return results[0].text, searchable_pdf_path, rotation_data

    if strategy == "longest":
        best = max(results, key=lambda r: len(r.text))
        return best.text, searchable_pdf_path, rotation_data

    # Default: ai_merge – ask AI to pick/merge the best text
    try:
        from app.utils.ai_provider import get_ai_provider

        provider = get_ai_provider()
        model = settings.ai_model or settings.openai_model

        extracts_block = "\n\n".join(
            f"--- OCR Engine: {r.provider} ---\n{r.text[:MAX_OCR_TEXT_FOR_AI_MERGE]}" for r in results
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert document editor. You will receive OCR extracts of the same document "
                    "produced by different OCR engines. Your task is to produce a single, clean, accurate "
                    "version of the text by cross-referencing all inputs. "
                    "Fix obvious OCR errors, preserve document structure, and return ONLY the final text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Document: {filename}\n\n"
                    f"The following are OCR extracts from different engines:\n\n{extracts_block}\n\n"
                    "Please merge these into the most accurate version of the document text."
                ),
            },
        ]
        merged_text = provider.chat_completion(messages, model=model, temperature=0)
        logger.info(f"AI-merged OCR text: {len(merged_text)} chars for {filename}")
        return merged_text, searchable_pdf_path, rotation_data
    except Exception as exc:
        logger.error(f"AI merge failed for {filename}: {exc}; falling back to longest result")
        best = max(results, key=lambda r: len(r.text))
        return best.text, searchable_pdf_path, rotation_data
