"""Celery task for rule-based document classification.

This task is executed as a pipeline step (``step_type="classify"``).  It
applies built-in and user-defined classification rules against the document's
filename, OCR text, and existing AI metadata to assign a ``document_type``
category.

The result is stored in the ``ai_metadata`` JSON blob on the
:class:`~app.models.FileRecord` (field ``classification``).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.celery_app import celery
from app.database import SessionLocal
from app.models import ClassificationRuleModel, FileRecord
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import log_task_progress
from app.utils.classification_rules import (
    ClassificationResult,
    classify_document,
    db_rule_to_engine_rule,
)

logger = logging.getLogger(__name__)

STEP_NAME = "classify_document"


def _load_custom_rules(owner_id: str | None) -> list[Any]:
    """Load enabled custom classification rules from the database.

    Returns engine-level :class:`ClassificationRule` dataclass instances.
    Rules are loaded in priority-descending order.  System rules
    (``owner_id IS NULL``) and the user's own rules are both included.
    """
    with SessionLocal() as db:
        query = db.query(ClassificationRuleModel).filter(ClassificationRuleModel.enabled.is_(True))
        if owner_id:
            query = query.filter(
                (ClassificationRuleModel.owner_id.is_(None)) | (ClassificationRuleModel.owner_id == owner_id)
            )
        else:
            query = query.filter(ClassificationRuleModel.owner_id.is_(None))
        rules = query.order_by(ClassificationRuleModel.priority.desc()).all()
        return [db_rule_to_engine_rule(r) for r in rules]


@celery.task(base=BaseTaskWithRetry, bind=True)
def classify_document_task(
    self: Any,
    file_id: int,
    owner_id: str | None = None,
) -> dict[str, Any]:
    """Classify a document using rule-based matching.

    This task:
    1. Loads the :class:`FileRecord` from the database.
    2. Gathers filename, OCR text, and existing AI metadata.
    3. Loads built-in + user-defined classification rules.
    4. Runs the classification engine.
    5. Persists the result into ``ai_metadata.classification``.

    Args:
        file_id: Primary key of the :class:`FileRecord` to classify.
        owner_id: Owner identifier for loading user-specific rules.

    Returns:
        Dict with ``category``, ``confidence``, and ``matched_rules``.
    """
    task_id = self.request.id

    log_task_progress(
        task_id,
        STEP_NAME,
        "in_progress",
        f"Starting classification for file {file_id}",
        file_id=file_id,
    )

    try:
        with SessionLocal() as db:
            file_record: FileRecord | None = db.query(FileRecord).filter(FileRecord.id == file_id).first()
            if file_record is None:
                log_task_progress(
                    task_id,
                    STEP_NAME,
                    "failure",
                    f"FileRecord {file_id} not found",
                    file_id=file_id,
                )
                return {"status": "error", "detail": "File not found"}

            # Gather inputs
            filename = file_record.original_filename or ""
            text = file_record.ocr_text or ""
            existing_metadata: dict[str, Any] = {}
            if file_record.ai_metadata:
                try:
                    existing_metadata = json.loads(file_record.ai_metadata)
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Failed to parse ai_metadata for file %s, starting fresh", file_id)
                    existing_metadata = {}

            # Load custom rules
            effective_owner = owner_id or file_record.owner_id
            custom_rules = _load_custom_rules(effective_owner)

            # Run classification engine
            result: ClassificationResult = classify_document(
                filename=filename,
                text=text,
                metadata=existing_metadata,
                custom_rules=custom_rules,
            )

            # Persist result into ai_metadata
            classification_data = {
                "category": result.category,
                "confidence": result.confidence,
                "matched_rules": [
                    {
                        "rule_name": m.rule_name,
                        "rule_type": m.rule_type,
                        "category": m.category,
                        "confidence": m.confidence,
                    }
                    for m in result.matched_rules
                ],
            }

            existing_metadata["classification"] = classification_data

            # If no document_type was set yet, populate it from the classification
            if not existing_metadata.get("document_type"):
                from app.utils.classification_rules import BUILTIN_CATEGORIES

                existing_metadata["document_type"] = BUILTIN_CATEGORIES.get(
                    result.category, result.category.replace("_", " ").title()
                )

            file_record.ai_metadata = json.dumps(existing_metadata, ensure_ascii=False)
            db.commit()

        log_task_progress(
            task_id,
            STEP_NAME,
            "success",
            f"Classified as '{result.category}' with confidence {result.confidence}",
            file_id=file_id,
            detail=f"Matched {len(result.matched_rules)} rule(s)",
        )

        return {
            "status": "success",
            "category": result.category,
            "confidence": result.confidence,
            "matched_rules": len(result.matched_rules),
        }

    except Exception as e:
        logger.exception("Classification failed for file %s: %s", file_id, e)
        log_task_progress(
            task_id,
            STEP_NAME,
            "failure",
            f"Classification failed: {e}",
            file_id=file_id,
        )
        raise
