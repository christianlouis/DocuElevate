#!/usr/bin/env python3
"""Unified OCR processing task for DocuElevate.

This task replaces the single-provider ``process_with_azure_document_intelligence``
task with a multi-engine OCR pipeline that:

1. Runs every OCR provider listed in ``OCR_PROVIDERS`` (default: ``azure``).
2. Merges/cross-checks the results using the configured AI model when more
   than one provider is active (see ``OCR_MERGE_STRATEGY``).
3. Writes the best searchable PDF back to the working directory.
4. Hands off to the page-rotation and metadata-extraction pipeline exactly as
   the legacy Azure task did.
"""

import logging
import os
from typing import Optional

from app.celery_app import celery
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.rotate_pdf_pages import rotate_pdf_pages
from app.utils import log_task_progress
from app.utils.ocr_provider import OCRResult, embed_text_layer, get_ocr_providers, merge_ocr_results

logger = logging.getLogger(__name__)


@celery.task(base=BaseTaskWithRetry, bind=True)
def process_with_ocr(self, filename: str, file_id: Optional[int] = None):
    """Run the configured OCR providers on *filename* and continue the pipeline.

    When multiple OCR providers are configured the results are merged using the
    AI model (or a simpler strategy controlled by ``OCR_MERGE_STRATEGY``).

    Args:
        filename: Base name of the file inside ``<workdir>/tmp/``.
        file_id: Optional database record ID passed through to downstream tasks.
    """
    task_id = self.request.id
    log_task_progress(
        task_id,
        "process_with_ocr",
        "in_progress",
        f"Starting OCR for {filename}",
        file_id=file_id,
    )

    try:
        tmp_file_path = os.path.join(settings.workdir, "tmp", filename)
        if not os.path.exists(tmp_file_path):
            raise FileNotFoundError(f"Local file not found: {tmp_file_path}")

        providers = get_ocr_providers()
        provider_names = [p.name for p in providers]
        logger.info(f"[{task_id}] Running {len(providers)} OCR provider(s): {provider_names}")

        log_task_progress(
            task_id,
            "run_ocr_providers",
            "in_progress",
            f"Running OCR providers: {', '.join(provider_names)}",
            file_id=file_id,
        )

        results = []
        errors = []
        for provider in providers:
            pname = provider.__class__.__name__
            try:
                logger.info(f"[{task_id}] Running {pname} on {filename}")
                result: OCRResult = provider.process(tmp_file_path)
                results.append(result)
                logger.info(f"[{task_id}] {pname} extracted {len(result.text)} chars")
            except Exception as exc:
                logger.error(f"[{task_id}] {pname} failed for {filename}: {exc}")
                errors.append(f"{pname}: {exc}")

        if not results:
            error_summary = "; ".join(errors)
            log_task_progress(
                task_id,
                "run_ocr_providers",
                "failure",
                "All OCR providers failed",
                file_id=file_id,
                detail=error_summary,
            )
            raise RuntimeError(f"All OCR providers failed for {filename}: {error_summary}")

        if errors:
            logger.warning(f"[{task_id}] Some OCR providers failed: {'; '.join(errors)}")

        log_task_progress(
            task_id,
            "run_ocr_providers",
            "success",
            f"{len(results)} of {len(providers)} OCR provider(s) succeeded",
            file_id=file_id,
        )

        # Merge results (no-op when only one provider succeeded)
        extracted_text, searchable_pdf_path, rotation_data = merge_ocr_results(results, filename)
        logger.info(
            f"[{task_id}] Merged OCR text: {len(extracted_text)} chars, "
            f"pdf={'yes' if searchable_pdf_path else 'no'}, "
            f"rotations={len(rotation_data)}"
        )

        # If no provider produced a searchable PDF, post-process the original
        # PDF with ocrmypdf to embed an invisible text layer so the output is
        # selectable/searchable in PDF viewers.
        if searchable_pdf_path is None:
            lang = getattr(settings, "tesseract_language", None) or "eng"
            log_task_progress(
                task_id,
                "embed_text_layer",
                "in_progress",
                "Embedding searchable text layer into PDF",
                file_id=file_id,
            )
            embedded = embed_text_layer(tmp_file_path, tmp_file_path, language=lang)
            if embedded:
                searchable_pdf_path = tmp_file_path
                log_task_progress(
                    task_id,
                    "embed_text_layer",
                    "success",
                    "Searchable text layer embedded via ocrmypdf",
                    file_id=file_id,
                )
            else:
                log_task_progress(
                    task_id,
                    "embed_text_layer",
                    "skipped",
                    "ocrmypdf unavailable – PDF will not have a searchable text layer",
                    file_id=file_id,
                )

        log_task_progress(
            task_id,
            "process_with_ocr",
            "success",
            f"OCR complete for {filename}",
            file_id=file_id,
            detail=f"Extracted {len(extracted_text)} chars using {len(results)} provider(s)",
        )

        # Continue pipeline: rotate pages (if needed), then extract metadata
        rotate_pdf_pages.delay(filename, extracted_text, rotation_data, file_id)

        return {
            "file": filename,
            "searchable_pdf": searchable_pdf_path or tmp_file_path,
            "cleaned_text": extracted_text,
            "providers_used": [r.provider for r in results],
        }

    except Exception as exc:
        logger.error(f"[{task_id}] OCR failed for {filename}: {exc}")
        log_task_progress(
            task_id,
            "process_with_ocr",
            "failure",
            f"OCR failed for {filename}",
            file_id=file_id,
            detail=str(exc),
        )
        raise
