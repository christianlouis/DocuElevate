#!/usr/bin/env python3

from __future__ import annotations

import json
import logging
import mimetypes
import os
import shutil
import uuid
from typing import TYPE_CHECKING

import pypdf
from pypdf.errors import PdfReadError

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import DocumentIntake, DropboxImportObject, FileRecord, Pipeline, PipelineStep
from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt
from app.tasks.process_with_ocr import process_with_ocr
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import get_unique_filepath_with_counter, hash_file, log_task_progress
from app.utils.routing_engine import evaluate_pre_processing_routing_rules
from app.utils.step_manager import initialize_file_steps
from app.utils.text_quality import check_text_quality, detect_pdf_text_source
from app.utils.workflow_plan import snapshot_workflow_plan, workflow_stage_keys

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _set_index_first_source_state(db: "Session", task_id: str, state: str, error: str | None = None) -> None:
    """Keep the durable Dropbox/intake ledgers aligned with index-first work."""
    intake = db.query(DocumentIntake).filter(DocumentIntake.task_id == task_id).first()
    if intake:
        intake.state = state
        intake.error = error
    imported = db.query(DropboxImportObject).filter(DropboxImportObject.task_id == task_id).first()
    if imported:
        imported.state = state


def _complete_index_first_document(
    *,
    task_id: str,
    file_id: int,
    extracted_text: str,
    original_filename: str,
    original_input_path: str,
    working_path: str,
) -> dict[str, object]:
    """Persist searchable text and hand the historical document to Qdrant."""
    cleaned_text = extracted_text.strip()
    if not cleaned_text:
        return _mark_index_first_pending(
            task_id,
            file_id,
            "No usable embedded text",
            original_input_path=original_input_path,
            working_path=working_path,
        )

    with SessionLocal() as db:
        record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if record is None:
            raise RuntimeError(f"Index-first FileRecord {file_id} disappeared")
        record.ocr_text = cleaned_text
        if not record.document_title:
            record.document_title = os.path.splitext(original_filename)[0]
        immutable_path = record.original_file_path or original_input_path
        record.local_filename = immutable_path
        _set_index_first_source_state(db, task_id, "indexing")
        db.commit()

    for step in ("extract_metadata_with_gpt", "embed_metadata_into_pdf", "finalize_document_storage"):
        log_task_progress(
            task_id,
            step,
            "skipped",
            "Index-first corpus backfill: document text goes directly to Qdrant",
            file_id=file_id,
        )

    from app.tasks.vector_index import index_document_vectors

    index_document_vectors.delay(file_id, source_task_id=task_id)
    log_task_progress(
        task_id,
        "process_document",
        "success",
        "Embedded text persisted; queued for vector indexing",
        file_id=file_id,
    )

    for path in {original_input_path, working_path}:
        if path and path != immutable_path and os.path.exists(path):
            os.remove(path)
    return {"status": "Queued for vector indexing", "file_id": file_id, "text_chars": len(cleaned_text)}


def _mark_index_first_pending(
    task_id: str,
    file_id: int,
    reason: str,
    *,
    original_input_path: str | None = None,
    working_path: str | None = None,
    embedded_text_checked: bool = False,
) -> dict[str, object]:
    """Retain a corpus item for a later OCR/conversion pass without LLM work."""
    with SessionLocal() as db:
        record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        immutable_path = (record.original_file_path if record else None) or original_input_path
        if record and immutable_path:
            record.local_filename = immutable_path
        _set_index_first_source_state(db, task_id, "needs_ocr", reason)
        db.commit()
    if embedded_text_checked:
        log_task_progress(
            task_id,
            "check_text",
            "success",
            "No embedded text found; deferred to the corpus OCR pass",
            file_id=file_id,
        )
        log_task_progress(
            task_id,
            "extract_text",
            "skipped",
            "No embedded text available; deferred to the corpus OCR pass",
            file_id=file_id,
        )
    log_task_progress(
        task_id,
        "process_document",
        "skipped",
        f"Index-first corpus backfill deferred: {reason}",
        file_id=file_id,
    )
    for path in {original_input_path, working_path}:
        if path and path != immutable_path and os.path.exists(path):
            os.remove(path)
    return {"status": "Index-first pending OCR", "file_id": file_id, "detail": reason}


def _get_pipeline_ocr_config(db: "Session", file_record: FileRecord, owner_id: str | None) -> dict[str, object]:
    """Look up runtime OCR overrides from the file's processing profile.

    Resolution order:
    1. Explicit pipeline assigned to the file (``file_record.pipeline_id``).
    2. User's own default pipeline (``owner_id``, ``is_default=True``).
    3. System default pipeline (``owner_id=NULL``, ``is_default=True``).

    Returns normalized OCR config. ``ocr_language`` is ``None`` when no
    override is configured or the profile uses ``auto``.
    """
    result: dict[str, object] = {"ocr_language": None, "force_cloud_ocr": False}
    pipeline = None

    if file_record.pipeline_id:
        pipeline = db.query(Pipeline).filter(Pipeline.id == file_record.pipeline_id).first()

    if pipeline is None and owner_id:
        pipeline = (
            db.query(Pipeline)
            .filter(
                Pipeline.owner_id == owner_id,
                Pipeline.is_default.is_(True),
                Pipeline.is_active.is_(True),
            )
            .first()
        )

    if pipeline is None:
        pipeline = (
            db.query(Pipeline)
            .filter(
                Pipeline.owner_id.is_(None),
                Pipeline.is_default.is_(True),
                Pipeline.is_active.is_(True),
            )
            .first()
        )

    if pipeline is None:
        return result

    ocr_step = (
        db.query(PipelineStep)
        .filter(
            PipelineStep.pipeline_id == pipeline.id,
            PipelineStep.step_type == "ocr",
            PipelineStep.enabled.is_(True),
        )
        .first()
    )

    if ocr_step is None or not ocr_step.config:
        return result

    try:
        step_config = json.loads(ocr_step.config)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning(
            "Invalid OCR processing-profile config JSON for pipeline_id=%s, step_id=%s: %s",
            pipeline.id,
            ocr_step.id,
            exc,
        )
        return result

    if not isinstance(step_config, dict):
        logger.warning(
            "Invalid OCR processing-profile config for pipeline_id=%s, step_id=%s: expected object, got %s",
            pipeline.id,
            ocr_step.id,
            type(step_config).__name__,
        )
        return result

    lang = step_config.get("ocr_language")
    # "auto" is treated as no override
    result["ocr_language"] = lang if lang and lang != "auto" else None
    result["force_cloud_ocr"] = bool(step_config.get("force_cloud_ocr"))
    return result


def _dispatch_routed_webhook(file_record: FileRecord, task_id: str | None) -> None:
    """Dispatch routing metadata without letting webhook failures stop processing."""
    try:
        from app.utils.webhook import dispatch_webhook_event

        dispatch_webhook_event(
            "document.routed",
            {
                "file_id": file_record.id,
                "filename": file_record.original_filename,
                "pipeline_id": file_record.pipeline_id,
                "assignment_source": file_record.pipeline_assignment_source,
                "routing_rule_id": file_record.pipeline_routing_rule_id,
                "reason": file_record.pipeline_assignment_reason,
            },
        )
    except Exception as webhook_exc:
        logger.warning("[%s] Failed to dispatch document.routed webhook: %s", task_id, webhook_exc)


def _get_pipeline_ocr_language(db: "Session", file_record: FileRecord, owner_id: str | None) -> str | None:
    """Return only the OCR language override from the selected processing profile."""
    config = _get_pipeline_ocr_config(db, file_record, owner_id)
    return config["ocr_language"] if isinstance(config["ocr_language"], str) else None


def _apply_pre_processing_routing(
    db: "Session",
    file_record: FileRecord,
    owner_id: str | None,
    task_id: str | None = None,
) -> None:
    """Assign a processing profile from routing rules known before OCR runs."""
    if file_record.pipeline_id is not None:
        if not file_record.pipeline_assignment_source:
            file_record.pipeline_assignment_source = "manual"
            file_record.pipeline_routing_rule_id = None
            file_record.pipeline_assignment_reason = "Processing profile was already assigned before ingestion routing"
        return

    decision = evaluate_pre_processing_routing_rules(db, owner_id, file_record)
    if decision is None:
        file_record.pipeline_assignment_source = "default"
        file_record.pipeline_routing_rule_id = None
        file_record.pipeline_assignment_reason = (
            "No pre-processing routing rule matched; using the owner or system default profile"
        )
        return

    file_record.pipeline_id = decision.pipeline.id
    file_record.pipeline_assignment_source = "routing_rule"
    file_record.pipeline_routing_rule_id = decision.rule.id
    file_record.pipeline_assignment_reason = (
        f"Matched pre-processing routing rule '{decision.rule.name}' on {decision.rule.field}"
    )

    logger.info(
        "[%s] Pre-processing routing matched rule_id=%s, pipeline_id=%s for file_id=%s",
        task_id or "-",
        decision.rule.id,
        decision.pipeline.id,
        file_record.id,
    )


@celery.task(base=BaseTaskWithRetry, bind=True)
def process_document(
    self,
    original_local_file: str,
    original_filename: str = None,
    file_id: int = None,
    force_cloud_ocr: bool = False,
    owner_id: str = None,
    index_only: bool = False,
):
    """
    Process a document file and trigger appropriate text extraction.

    Args:
        original_local_file: Path to the file on disk
        original_filename: Optional original filename (if different from path basename)
        file_id: Optional existing file record ID. When provided, skips duplicate
                 detection and reuses the existing record (used for reprocessing).
        force_cloud_ocr: If True, forces OCR processing regardless of embedded
                         text quality. Used for re-processing and profile configuration.
        owner_id: Optional user identifier for multi-user mode. When provided, the
                  created FileRecord is associated with this user.
        index_only: Persist embedded text and queue Qdrant indexing without LLM
                    metadata or distribution. Intended for explicit corpus true-up.

    Steps:
      1. Check if we have a FileRecord entry (via SHA-256 hash). If found, skip re-processing.
         (Skipped when file_id is provided for reprocessing.)
      2. If not found, insert a new DB row and continue with the pipeline:
         - Save immutable copy to /workdir/original
         - Copy file to /workdir/tmp for processing
         - Check for embedded text. If present, run local GPT extraction
         - Otherwise, queue Azure Document Intelligence processing
      3. If force_cloud_ocr is True, skip local text extraction and queue OCR
    """
    # Fall back to the configured default_owner_id when no explicit owner was provided
    default_owner_id = settings.default_owner_id
    if owner_id is None and isinstance(default_owner_id, str) and default_owner_id.strip():
        owner_id = default_owner_id

    if index_only and not settings.vector_index_enabled:
        logger.warning("Index-first processing requested while vector indexing is disabled; using full pipeline")
        index_only = False

    task_id = self.request.id
    logger.info(f"[{task_id}] Starting document processing: {original_local_file}")
    log_task_progress(
        task_id,
        "process_document",
        "in_progress",
        f"Processing file: {original_local_file}",
    )

    if not os.path.exists(original_local_file):
        logger.error(f"[{task_id}] File {original_local_file} not found.")
        log_task_progress(
            task_id,
            "process_document",
            "failure",
            "File not found",
            detail=f"File not found on disk: {original_local_file}",
        )
        return {"error": "File not found"}

    # 0. Check for duplicate files (if enabled)
    if settings.enable_deduplication:
        logger.info(f"[{task_id}] Computing file hash for deduplication check...")
        log_task_progress(task_id, "check_for_duplicates", "in_progress", "Computing file hash for deduplication")
        filehash = hash_file(original_local_file)
    else:
        logger.info(f"[{task_id}] Computing file hash (deduplication disabled)...")
        filehash = hash_file(original_local_file)

    # Use provided original_filename or fall back to basename of path
    if original_filename is None:
        original_filename = os.path.basename(original_local_file)
    file_size = os.path.getsize(original_local_file)
    mime_type, _ = mimetypes.guess_type(original_local_file)
    if not mime_type:
        mime_type = "application/octet-stream"

    logger.info(f"[{task_id}] File hash: {filehash[:10]}..., Size: {file_size} bytes, MIME: {mime_type}")

    # Log deduplication step result (only if enabled)
    if settings.enable_deduplication:
        log_task_progress(
            task_id,
            "check_for_duplicates",
            "in_progress",
            f"Hash: {filehash[:10]}..., checking for duplicates",
        )

    # Acquire DB session in the task
    # Profile OCR overrides resolved inside DB session.
    ocr_language: str | None = None
    with SessionLocal() as db:
        # When file_id is provided, we are reprocessing an existing file.
        # Skip the duplicate check and reuse the existing record.
        if file_id is not None:
            existing_record = db.query(FileRecord).filter_by(id=file_id).one_or_none()
            if existing_record is None:
                logger.error(f"[{task_id}] File record with ID {file_id} not found for reprocessing.")
                log_task_progress(task_id, "process_document", "failure", "File record not found", file_id=file_id)
                return {"error": "File record not found", "file_id": file_id}
            logger.info(f"[{task_id}] Reprocessing existing file record ID: {file_id}, skipping duplicate check.")
            log_task_progress(
                task_id,
                "process_document",
                "in_progress",
                f"Reprocessing file record ID: {file_id}",
                file_id=file_id,
            )
            new_record = existing_record
        else:
            # Check for duplicate only if this is a new file (not reprocessing)
            # IMPORTANT: Only consider it a duplicate if it matches a DIFFERENT file
            existing_query = db.query(FileRecord).filter(
                FileRecord.filehash == filehash,
                FileRecord.is_duplicate.is_(False),
            )
            if settings.multi_user_enabled:
                existing_query = existing_query.filter(FileRecord.owner_id == owner_id)
            existing = existing_query.order_by(FileRecord.created_at.asc()).first()
            if existing is None:
                fallback_query = db.query(FileRecord).filter(FileRecord.filehash == filehash)
                if settings.multi_user_enabled:
                    fallback_query = fallback_query.filter(FileRecord.owner_id == owner_id)
                existing = fallback_query.order_by(FileRecord.id.asc()).first()

            # A file is only a duplicate if it matches a different file's hash
            # (not its own hash when reprocessing)
            if existing and existing.id != file_id and settings.enable_deduplication:
                logger.info(f"[{task_id}] Duplicate file detected (hash={filehash[:10]}...) Skipping processing.")
                from app.utils.tribe_scope import ensure_document_scope

                tenant_id, tribe_id = ensure_document_scope(db, owner_id)
                duplicate_record = FileRecord(
                    filehash=filehash,
                    original_filename=original_filename,
                    local_filename="",
                    file_size=file_size,
                    mime_type=mime_type,
                    is_duplicate=True,
                    duplicate_of_id=existing.id,
                    owner_id=owner_id,
                    tenant_id=tenant_id,
                    tribe_id=tribe_id,
                )
                db.add(duplicate_record)
                db.commit()
                db.refresh(duplicate_record)
                if index_only:
                    _set_index_first_source_state(db, task_id, "duplicate")
                    db.commit()

                if settings.enable_deduplication and settings.show_deduplication_step:
                    log_task_progress(
                        task_id,
                        "check_for_duplicates",
                        "success",
                        f"Duplicate detected - matching file ID {existing.id}",
                        file_id=duplicate_record.id,
                        detail=(
                            f"Duplicate file detected.\n"
                            f"File hash: {filehash}\n"
                            f"Original file record ID: {existing.id}\n"
                            f"This file record ID: {duplicate_record.id}\n"
                            f"Original filename: {original_filename}"
                        ),
                    )
                log_task_progress(
                    task_id,
                    "process_document",
                    "success",
                    "Duplicate file detected, skipping",
                    file_id=duplicate_record.id,
                    detail=(
                        f"Duplicate file detected.\n"
                        f"File hash: {filehash}\n"
                        f"Original file record ID: {existing.id}\n"
                        f"Original filename: {original_filename}"
                    ),
                )
                if index_only and os.path.exists(original_local_file):
                    os.remove(original_local_file)
                return {
                    "status": "duplicate_file",
                    "file_id": duplicate_record.id,
                    "original_file_id": existing.id,
                    "detail": "File already processed.",
                }

            # Not a duplicate (or deduplication disabled) -> insert a new record
            logger.info(f"[{task_id}] Creating new file record in database")
            log_task_progress(task_id, "create_file_record", "in_progress", "Creating file record")
            from app.utils.tribe_scope import ensure_document_scope

            tenant_id, tribe_id = ensure_document_scope(db, owner_id)
            new_record = FileRecord(
                filehash=filehash,
                original_filename=original_filename,
                local_filename="",  # Will fill in after we move it
                file_size=file_size,
                mime_type=mime_type,
                is_duplicate=False,
                owner_id=owner_id,
                tenant_id=tenant_id,
                tribe_id=tribe_id,
            )
            db.add(new_record)
            db.commit()
            db.refresh(new_record)
            logger.info(f"[{task_id}] File record created with ID: {new_record.id}")
            log_task_progress(
                task_id,
                "create_file_record",
                "success",
                f"File record ID: {new_record.id}",
                file_id=new_record.id,
            )
            # Update the check_for_duplicates step now that file_id is available.
            # This must happen after initialize_file_steps() which creates the
            # step as "pending".  The dedup check already passed at this point.
            if settings.enable_deduplication:
                log_task_progress(
                    task_id,
                    "check_for_duplicates",
                    "success",
                    "New file - no duplicates found",
                    file_id=new_record.id,
                )

        # 1. Generate a UUID-based filename for storage
        file_ext = os.path.splitext(original_local_file)[1]
        file_uuid = str(uuid.uuid4())
        new_filename = f"{file_uuid}{file_ext}"

        # 2. Save immutable copy to /workdir/original (only for new files, not reprocessing)
        # For reprocessing, the original_file_path should already exist in the database
        if file_id is None:  # New file - save original copy
            # This copy serves as the permanent, untouched reference of the ingested file
            original_dir = os.path.join(settings.workdir, "original")
            os.makedirs(original_dir, exist_ok=True)

            # Use collision-resistant naming with -0001, -0002 suffixes
            base_name = os.path.splitext(new_filename)[0]
            original_file_path = get_unique_filepath_with_counter(original_dir, base_name, file_ext)

            logger.info(f"[{task_id}] Saving immutable original to: {original_file_path}")
            log_task_progress(
                task_id,
                "save_original",
                "in_progress",
                f"Saving original to {os.path.basename(original_file_path)}",
                file_id=new_record.id,
            )
            shutil.copy(original_local_file, original_file_path)
            log_task_progress(
                task_id,
                "save_original",
                "success",
                f"Original saved: {os.path.basename(original_file_path)}",
                file_id=new_record.id,
            )

            # Update the DB with original_file_path
            new_record.original_file_path = original_file_path
        else:
            # Reprocessing - original should already exist
            logger.info(f"[{task_id}] Reprocessing: original file already saved at {new_record.original_file_path}")
            log_task_progress(
                task_id,
                "save_original",
                "success",
                "Reprocessing: using existing original",
                file_id=new_record.id,
            )

        # 3. Copy to /workdir/tmp for processing
        tmp_dir = os.path.join(settings.workdir, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        new_local_path = os.path.join(tmp_dir, new_filename)

        logger.info(f"[{task_id}] Copying file to processing area: {new_local_path}")
        log_task_progress(
            task_id,
            "copy_file",
            "in_progress",
            f"Copying file to {new_filename}",
            file_id=new_record.id,
        )
        # Copy the file instead of moving it
        shutil.copy(original_local_file, new_local_path)
        log_task_progress(
            task_id,
            "copy_file",
            "success",
            f"File copied to {new_filename}",
            file_id=new_record.id,
        )

        # Update the DB with local_filename
        new_record.local_filename = new_local_path
        _apply_pre_processing_routing(db, new_record, owner_id, task_id)
        snapshot_workflow_plan(db, new_record)
        initialize_file_steps(db, new_record.id, workflow_stages=workflow_stage_keys(new_record))
        db.commit()

        if new_record.pipeline_assignment_source == "routing_rule":
            log_task_progress(
                task_id,
                "route_pipeline",
                "success",
                "Processing profile selected by routing rule",
                file_id=new_record.id,
                detail=new_record.pipeline_assignment_reason,
            )
            _dispatch_routed_webhook(new_record, task_id)
        elif new_record.pipeline_assignment_source == "default":
            log_task_progress(
                task_id,
                "route_pipeline",
                "skipped",
                "No routing rule matched; using default profile",
                file_id=new_record.id,
                detail=new_record.pipeline_assignment_reason,
            )

        # Look up processing-profile OCR overrides before the session closes.
        # This reads the OCR step config from the file's assigned pipeline (or
        # the user/system default pipeline) so the settings are available when
        # dispatching process_with_ocr below.
        ocr_config = _get_pipeline_ocr_config(db, new_record, owner_id)
        ocr_language = ocr_config["ocr_language"] if isinstance(ocr_config["ocr_language"], str) else None
        force_cloud_ocr = force_cloud_ocr or bool(ocr_config["force_cloud_ocr"])
        if ocr_language:
            logger.info(f"[{task_id}] Processing profile OCR language configured: {ocr_language!r}")
        if force_cloud_ocr:
            logger.info(f"[{task_id}] Processing profile forced OCR processing enabled")

        # Store file_id before session closes to avoid DetachedInstanceError
        file_id = new_record.id

    # 2. Check for embedded text (outside the DB session to avoid long open transactions)
    # Skip local text extraction if force_cloud_ocr is True
    if force_cloud_ocr:
        if index_only:
            return _mark_index_first_pending(
                task_id,
                file_id,
                "Force OCR is required",
                original_input_path=original_local_file,
                working_path=new_local_path,
            )
        logger.info(f"[{task_id}] Force Cloud OCR requested, skipping embedded text check")
        log_task_progress(
            task_id,
            "check_text",
            "success",
            "Force Cloud OCR requested, queuing OCR",
            file_id=file_id,
        )
        # Mark local text extraction as skipped since force_cloud_ocr was requested
        log_task_progress(
            task_id,
            "extract_text",
            "skipped",
            "Force cloud OCR requested, skipping local extraction",
            file_id=file_id,
        )
        log_task_progress(
            task_id,
            "process_document",
            "success",
            "Queued for forced OCR processing",
            file_id=file_id,
        )
        process_with_ocr.delay(new_filename, file_id, language=ocr_language)
        return {"file": new_local_path, "status": "Queued for forced OCR", "file_id": file_id}

    # If the file is not a PDF, skip embedded text check and convert to PDF first
    is_pdf = mime_type == "application/pdf" or os.path.splitext(new_local_path)[1].lower() == ".pdf"
    if not is_pdf:
        if index_only:
            return _mark_index_first_pending(
                task_id,
                file_id,
                "PDF conversion is required",
                original_input_path=original_local_file,
                working_path=new_local_path,
            )
        logger.info(f"[{task_id}] Non-PDF file detected, queuing PDF conversion before OCR")
        log_task_progress(
            task_id,
            "check_text",
            "skipped",
            "Non-PDF file detected, converting to PDF",
            file_id=file_id,
        )
        # Mark local text extraction as skipped since the file needs PDF conversion first
        log_task_progress(
            task_id,
            "extract_text",
            "skipped",
            "Non-PDF file, text extraction deferred to OCR after conversion",
            file_id=file_id,
        )
        log_task_progress(
            task_id,
            "process_document",
            "success",
            "Queued for PDF conversion",
            file_id=file_id,
        )
        celery.send_task(
            "app.tasks.convert_to_pdf.convert_to_pdf",
            args=[new_local_path, original_filename],
        )
        return {"file": new_local_path, "status": "Queued for PDF conversion", "file_id": file_id}

    logger.info(f"[{task_id}] Checking for embedded text in PDF")
    log_task_progress(
        task_id,
        "check_text",
        "in_progress",
        "Checking for embedded text",
        file_id=file_id,
    )
    try:
        with open(new_local_path, "rb") as file:
            pdf_reader = pypdf.PdfReader(file)
            has_text = False
            for page in pdf_reader.pages:
                if page.extract_text().strip():
                    has_text = True
                    break
    except PdfReadError as exc:
        logger.warning(f"[{task_id}] PDF read error during embedded text check: {exc}")
        log_task_progress(
            task_id,
            "check_text",
            "in_progress",
            "PDF read error, retrying embedded text check",
            file_id=file_id,
            detail=str(exc),
        )
        raise self.retry(
            exc=exc,
            countdown=10,
            kwargs={
                "original_local_file": original_local_file,
                "original_filename": original_filename,
                "file_id": file_id,
                "force_cloud_ocr": force_cloud_ocr,
                "index_only": index_only,
            },
        )

    if has_text:
        logger.info(f"[{task_id}] PDF {original_local_file} contains embedded text. Processing locally.")
        log_task_progress(
            task_id,
            "check_text",
            "success",
            "Embedded text found, extracting locally",
            file_id=file_id,
        )

        # Extract text locally
        logger.info(f"[{task_id}] Extracting text from PDF")
        log_task_progress(
            task_id,
            "extract_text",
            "in_progress",
            "Extracting text locally",
            file_id=file_id,
        )
        extracted_text = ""
        with open(new_local_path, "rb") as file:
            pdf_reader = pypdf.PdfReader(file)
            for page in pdf_reader.pages:
                extracted_text += page.extract_text() + "\n"

        logger.info(f"[{task_id}] Extracted {len(extracted_text)} characters")
        log_task_progress(
            task_id,
            "extract_text",
            "success",
            f"Extracted {len(extracted_text)} characters",
            file_id=file_id,
        )

        if index_only:
            return _complete_index_first_document(
                task_id=task_id,
                file_id=file_id,
                extracted_text=extracted_text,
                original_filename=original_filename,
                original_input_path=original_local_file,
                working_path=new_local_path,
            )

        # ----------------------------------------------------------------
        # AI-based text quality check
        # Digitally-created PDFs are always trusted; OCR-sourced or unknown
        # PDFs are validated.  Poor-quality text triggers automatic re-OCR.
        # ----------------------------------------------------------------
        if settings.enable_text_quality_check:
            text_source = detect_pdf_text_source(new_local_path)
            logger.info(f"[{task_id}] Detected PDF text source: {text_source.value}")

            quality_result = check_text_quality(extracted_text, text_source)
            logger.info(
                f"[{task_id}] Text quality check result: "
                f"good={quality_result.is_good_quality}, score={quality_result.quality_score}, "
                f"source={quality_result.text_source.value}, feedback={quality_result.feedback!r}"
            )

            # Persist the quality score immediately so it's available for filtering
            # even if the file is later sent to OCR for re-processing.
            with SessionLocal() as _db:
                _rec = _db.query(FileRecord).filter_by(id=file_id).first()
                if _rec:
                    _rec.ocr_quality_score = quality_result.quality_score
                    _db.commit()

            if not quality_result.is_good_quality:
                # Poor quality: discard embedded text and re-OCR instead.
                # Pass the original embedded text so the OCR task can compare
                # its result against the original and keep the better version.
                issues_str = ", ".join(quality_result.issues) if quality_result.issues else "unspecified"
                detail_msg = (
                    f"Text quality check FAILED – score={quality_result.quality_score}/100, "
                    f"source={quality_result.text_source.value}, issues=[{issues_str}].\n"
                    f"AI feedback: {quality_result.feedback}\n"
                    f"Embedded text will be compared with fresh OCR output; best version will be used."
                )
                logger.warning(f"[{task_id}] {detail_msg}")
                log_task_progress(
                    task_id,
                    "check_text_quality",
                    "success",
                    f"Poor embedded text detected (score={quality_result.quality_score}/100); queued OCR comparison",
                    file_id=file_id,
                    detail=detail_msg,
                )
                log_task_progress(
                    task_id,
                    "process_document",
                    "success",
                    "Queued for OCR (text quality too low)",
                    file_id=file_id,
                )
                process_with_ocr.delay(new_filename, file_id, extracted_text, language=ocr_language)
                return {
                    "file": new_local_path,
                    "status": "Queued for OCR (poor embedded text quality)",
                    "file_id": file_id,
                }

            # Good quality: record the result and proceed with local extraction.
            detail_msg = (
                f"Text quality check PASSED – score={quality_result.quality_score}/100, "
                f"source={quality_result.text_source.value}.\n"
                f"AI feedback: {quality_result.feedback}"
            )
            log_task_progress(
                task_id,
                "check_text_quality",
                "success",
                f"Text quality OK (score={quality_result.quality_score}/100)",
                file_id=file_id,
                detail=detail_msg,
            )

        # Mark OCR as skipped since we extracted text locally
        log_task_progress(
            task_id,
            "process_with_ocr",
            "skipped",
            "Local text extraction succeeded, OCR not needed",
            file_id=file_id,
        )

        # Call metadata extraction directly
        logger.info(f"[{task_id}] Queueing metadata extraction")
        log_task_progress(
            task_id,
            "process_document",
            "success",
            "Queued for metadata extraction",
            file_id=file_id,
        )
        extract_metadata_with_gpt.delay(new_filename, extracted_text, file_id)
        return {
            "file": new_local_path,
            "status": "Text extracted locally",
            "file_id": file_id,
        }

    # 3. If no embedded text, queue OCR processing
    if index_only:
        return _mark_index_first_pending(
            task_id,
            file_id,
            "No usable embedded text",
            original_input_path=original_local_file,
            working_path=new_local_path,
            embedded_text_checked=True,
        )
    logger.info(f"[{task_id}] No embedded text found. Queueing OCR processing")
    log_task_progress(
        task_id,
        "check_text",
        "success",
        "No embedded text, queuing OCR",
        file_id=file_id,
    )

    # Mark local text extraction as skipped since we're using cloud OCR
    log_task_progress(
        task_id,
        "extract_text",
        "skipped",
        "No embedded text, using OCR instead",
        file_id=file_id,
    )

    log_task_progress(
        task_id,
        "process_document",
        "success",
        "Queued for OCR processing",
        file_id=file_id,
    )
    process_with_ocr.delay(new_filename, file_id, language=ocr_language)
    return {"file": new_local_path, "status": "Queued for OCR", "file_id": file_id}
