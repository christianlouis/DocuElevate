#!/usr/bin/env python3
"""Unified OCR processing task for DocuElevate.

This task replaces the single-provider ``process_with_azure_document_intelligence``
task with a multi-engine OCR pipeline that:

1. Runs every OCR provider listed in ``OCR_PROVIDERS`` (default: ``tesseract``).
2. Merges/cross-checks the results using the configured AI model when more
   than one provider is active (see ``OCR_MERGE_STRATEGY``).
3. Writes the best searchable PDF back to the working directory.
4. Optionally compares the OCR output against the original embedded text
   (passed as *original_text*) using a head-to-head AI review and keeps the
   higher-quality text for downstream processing.
5. Hands off to the page-rotation and metadata-extraction pipeline exactly as
   the legacy Azure task did.
"""

import logging
import os

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import FileRecord
from app.tasks.retry_config import OcrTaskWithRetry
from app.tasks.rotate_pdf_pages import rotate_pdf_pages
from app.utils import log_task_progress
from app.utils.ocr_provider import OCRResult, embed_text_layer, get_ocr_providers, merge_ocr_results
from app.utils.text_quality import TextSource, check_text_quality, compare_text_quality

logger = logging.getLogger(__name__)


def _remove_index_only_ocr_artifacts(*paths: str | None) -> None:
    """Remove only OCR artifacts created inside DocuElevate's tmp directory."""
    tmp_root = os.path.realpath(os.path.join(settings.workdir, "tmp"))
    for path in paths:
        if not path:
            continue
        real_path = os.path.realpath(path)
        try:
            is_tmp_artifact = os.path.commonpath((tmp_root, real_path)) == tmp_root
        except ValueError:
            is_tmp_artifact = False
        if is_tmp_artifact and os.path.isfile(real_path):
            os.remove(real_path)


def _complete_index_only_ocr(
    *,
    file_id: int,
    source_task_id: str,
    filename: str,
    extracted_text: str,
    providers_used: list[str],
    tmp_file_path: str,
    searchable_pdf_path: str | None,
) -> dict:
    """Persist OCR text and recoverably hand it to the low-priority indexer."""
    cleaned_text = extracted_text.strip()
    from app.tasks.vector_index import _set_source_state, index_document_vectors

    with SessionLocal() as db:
        record = db.query(FileRecord).filter_by(id=file_id).first()
        if record is None:
            _set_source_state(db, source_task_id, "failed", "File not found")
            db.commit()
            raise RuntimeError(f"Index-only OCR FileRecord {file_id} disappeared")
        if not cleaned_text:
            _set_source_state(db, source_task_id, "failed", "OCR returned no usable text")
            db.commit()
            _remove_index_only_ocr_artifacts(tmp_file_path, searchable_pdf_path)
            return {
                "status": "failed",
                "file_id": file_id,
                "detail": "OCR returned no usable text",
            }
        record.ocr_text = cleaned_text
        if not record.document_title:
            record.document_title = os.path.splitext(record.original_filename or filename)[0]
        # This durable state lets the periodic coordinator recover a broker
        # publication failure without rerunning OCR.
        _set_source_state(db, source_task_id, "ocr_complete")
        db.commit()

    for step in ("extract_metadata_with_gpt", "embed_metadata_into_pdf", "finalize_document_storage"):
        log_task_progress(
            source_task_id,
            step,
            "skipped",
            "Deferred corpus OCR: text goes directly to Qdrant",
            file_id=file_id,
        )

    with SessionLocal() as db:
        _set_source_state(db, source_task_id, "indexing")
        db.commit()

    queued = False
    try:
        index_document_vectors.apply_async(
            args=[file_id],
            kwargs={"source_task_id": source_task_id},
            priority=settings.corpus_backfill_task_priority,
        )
        queued = True
    except Exception:
        logger.warning(
            "Could not publish deferred vector indexing for file %s; coordinator will retry",
            file_id,
            exc_info=True,
        )
        with SessionLocal() as db:
            _set_source_state(db, source_task_id, "ocr_complete", "Vector queue publication failed")
            db.commit()

    _remove_index_only_ocr_artifacts(tmp_file_path, searchable_pdf_path)
    return {
        "status": "queued_for_vector_index" if queued else "pending_vector_index",
        "file_id": file_id,
        "text_chars": len(cleaned_text),
        "providers_used": providers_used,
    }


@celery.task(base=OcrTaskWithRetry, bind=True)
def process_with_ocr(
    self,
    filename: str,
    file_id: int | None = None,
    original_text: str | None = None,
    language: str | None = None,
    index_only: bool = False,
    source_task_id: str | None = None,
):
    """Run the configured OCR providers on *filename* and continue the pipeline.

    When multiple OCR providers are configured the results are merged using the
    AI model (or a simpler strategy controlled by ``OCR_MERGE_STRATEGY``).

    If *original_text* is provided (the original embedded text that failed the
    quality check), the OCR result is compared against it using a head-to-head
    AI review.  The higher-quality text is passed to downstream tasks.

    Args:
        filename: Base name of the file inside ``<workdir>/tmp/``.
        file_id: Optional database record ID passed through to downstream tasks.
        original_text: Optional original embedded text for head-to-head comparison.
        language: Optional Tesseract-style language code(s) (e.g. ``"eng+deu"``)
            to override the global OCR language settings for this specific run.
            Pass ``None`` or ``"auto"`` to use the global settings.  This
            enables per-pipeline language configuration.
        index_only: Persist OCR text and queue Qdrant indexing without metadata
            extraction, rotation, or destination distribution.
        source_task_id: Durable intake/import correlation ID for index-only work.
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

        providers = get_ocr_providers(language=language)
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

        if index_only:
            if file_id is None or not source_task_id:
                raise ValueError("Index-only OCR requires file_id and source_task_id")
            return _complete_index_only_ocr(
                file_id=file_id,
                source_task_id=source_task_id,
                filename=filename,
                extracted_text=extracted_text,
                providers_used=[r.provider for r in results],
                tmp_file_path=tmp_file_path,
                searchable_pdf_path=searchable_pdf_path,
            )

        # If explicitly enabled and no provider produced a searchable PDF,
        # post-process the original with ocrmypdf. This is intentionally opt-in:
        # it runs OCR a second time and can be memory-intensive. The extracted
        # text remains searchable inside DocuElevate without this PDF layer.
        embed_text_layer_enabled = getattr(settings, "ocr_embed_text_layer", False) is True
        if searchable_pdf_path is None and embed_text_layer_enabled:
            # Use the per-call language override; fall back to global setting
            embed_lang = (
                language
                if language and language != "auto"
                else (getattr(settings, "tesseract_language", None) or "eng")
            )
            log_task_progress(
                task_id,
                "embed_text_layer",
                "in_progress",
                "Embedding searchable text layer into PDF",
                file_id=file_id,
            )
            embedded = embed_text_layer(tmp_file_path, tmp_file_path, language=embed_lang)
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
        elif searchable_pdf_path is None:
            log_task_progress(
                task_id,
                "embed_text_layer",
                "skipped",
                "PDF text-layer embedding is disabled; extracted OCR text remains searchable in DocuElevate",
                file_id=file_id,
            )

        # ----------------------------------------------------------------
        # Head-to-head comparison with original embedded text (if provided)
        # ----------------------------------------------------------------
        final_text = extracted_text
        if original_text and original_text.strip() and extracted_text.strip():
            logger.info(f"[{task_id}] Original embedded text provided; running head-to-head quality comparison")
            log_task_progress(
                task_id,
                "compare_ocr_quality",
                "in_progress",
                "Comparing OCR result against original embedded text",
                file_id=file_id,
            )
            try:
                comparison = compare_text_quality(original_text, extracted_text)
                comparison_detail = (
                    f"Original score: {comparison.original_score}/100, "
                    f"OCR score: {comparison.ocr_score}/100, "
                    f"Preferred: {comparison.preferred}\n"
                    f"AI explanation: {comparison.explanation}"
                )
                logger.info(f"[{task_id}] OCR comparison – {comparison_detail}")

                if comparison.preferred == "original":
                    # Original text is actually better – use it instead of OCR.
                    final_text = original_text
                    logger.info(
                        f"[{task_id}] Original embedded text selected "
                        f"(original={comparison.original_score} > ocr={comparison.ocr_score})"
                    )
                    log_task_progress(
                        task_id,
                        "compare_ocr_quality",
                        "success",
                        f"Original text preferred (original={comparison.original_score}/100 vs "
                        f"ocr={comparison.ocr_score}/100)",
                        file_id=file_id,
                        detail=comparison_detail,
                    )
                else:
                    logger.info(
                        f"[{task_id}] OCR text selected "
                        f"(preferred={comparison.preferred!r}, "
                        f"ocr={comparison.ocr_score}, original={comparison.original_score})"
                    )
                    log_task_progress(
                        task_id,
                        "compare_ocr_quality",
                        "success",
                        f"OCR text preferred (ocr={comparison.ocr_score}/100 vs "
                        f"original={comparison.original_score}/100)",
                        file_id=file_id,
                        detail=comparison_detail,
                    )
            except Exception as cmp_exc:
                logger.warning(f"[{task_id}] Head-to-head comparison failed ({cmp_exc}); keeping OCR text")
                log_task_progress(
                    task_id,
                    "compare_ocr_quality",
                    "skipped",
                    f"Comparison failed ({cmp_exc}); keeping OCR output",
                    file_id=file_id,
                )
        elif original_text is not None:
            # original_text was provided but one side is empty – pick whichever has content.
            if not extracted_text.strip() and original_text.strip():
                final_text = original_text
                logger.info(f"[{task_id}] OCR returned empty text; falling back to original embedded text")
                log_task_progress(
                    task_id,
                    "compare_ocr_quality",
                    "success",
                    "OCR empty – using original embedded text",
                    file_id=file_id,
                )
            else:
                log_task_progress(
                    task_id,
                    "compare_ocr_quality",
                    "skipped",
                    "No original text to compare; using OCR output",
                    file_id=file_id,
                )

        log_task_progress(
            task_id,
            "process_with_ocr",
            "success",
            f"OCR complete for {filename}",
            file_id=file_id,
            detail=f"Extracted {len(extracted_text)} chars using {len(results)} provider(s); "
            f"final text length: {len(final_text)} chars",
        )

        # Score the final embedded text — the text that will land in ocr_text.
        # We always call check_text_quality() on final_text because:
        #   - merge_ocr_results() may have AI-merged output from several engines
        #   - compare_text_quality() scores are relative (not the same scale)
        #   - The original may have been preferred, reversing the OCR output
        # OCR-produced (or AI-merged) text is treated as TextSource.OCR_PREVIOUS
        # so the quality AI call is always made.
        if file_id is not None:
            try:
                quality_result = check_text_quality(final_text, TextSource.OCR_PREVIOUS)
                logger.info(
                    f"[{task_id}] Final text quality: score={quality_result.quality_score}/100, "
                    f"good={quality_result.is_good_quality}, feedback={quality_result.feedback!r}"
                )
                with SessionLocal() as _db:
                    _rec = _db.query(FileRecord).filter_by(id=file_id).first()
                    if _rec:
                        _rec.ocr_quality_score = quality_result.quality_score
                        _db.commit()
                logger.info(f"[{task_id}] Saved ocr_quality_score={quality_result.quality_score} for file_id={file_id}")
            except Exception as _score_exc:
                logger.warning(f"[{task_id}] Could not persist ocr_quality_score: {_score_exc}")

        # Continue pipeline: rotate pages (if needed), then extract metadata
        rotate_pdf_pages.delay(filename, final_text, rotation_data, file_id)

        return {
            "file": filename,
            "searchable_pdf": searchable_pdf_path or tmp_file_path,
            "cleaned_text": final_text,
            "providers_used": [r.provider for r in results],
        }

    except Exception as exc:
        if index_only and source_task_id:
            from app.tasks.vector_index import _set_source_state

            with SessionLocal() as db:
                final_attempt = self.request.retries >= self.max_retries
                _set_source_state(
                    db,
                    source_task_id,
                    "failed" if final_attempt else "ocr_retrying",
                    type(exc).__name__,
                )
                db.commit()
            if final_attempt:
                _remove_index_only_ocr_artifacts(locals().get("tmp_file_path"), locals().get("searchable_pdf_path"))
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
