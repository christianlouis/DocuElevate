"""Routing engine for conditional document-to-pipeline assignment.

Evaluates a set of :class:`PipelineRoutingRule` rows against document
properties and returns the first matching target pipeline (if any).

Supported document fields
-------------------------
* ``file_type`` – MIME type of the file (e.g. ``application/pdf``)
* ``filename``  – original filename
* ``size``      – file size in bytes (numeric comparison)
* ``document_type`` – AI-classified document type (e.g. ``Invoice``)
* ``category``  – alias for ``document_type``
* ``metadata.<key>`` – arbitrary key inside the AI-extracted JSON metadata

Supported comparison operators
------------------------------
* ``equals`` / ``not_equals``
* ``contains`` / ``not_contains`` (substring match, case-insensitive)
* ``regex`` (Python ``re`` full-match, case-insensitive)
* ``gt`` / ``lt`` / ``gte`` / ``lte`` (numeric comparison)
"""

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import Pipeline, PipelineRoutingRule

logger = logging.getLogger(__name__)

# Operators recognised by the engine.
VALID_OPERATORS: frozenset[str] = frozenset(
    {
        "equals",
        "not_equals",
        "contains",
        "not_contains",
        "regex",
        "gt",
        "lt",
        "gte",
        "lte",
    }
)

# Fields that are resolved directly from the FileRecord.
BUILTIN_FIELDS: frozenset[str] = frozenset(
    {
        "file_type",
        "filename",
        "size",
        "document_type",
        "category",
    }
)

TEXT_OPERATORS = {
    "equals": lambda actual, expected: actual == expected,
    "not_equals": lambda actual, expected: actual != expected,
    "contains": lambda actual, expected: expected in actual,
    "not_contains": lambda actual, expected: expected not in actual,
}

NUMERIC_OPERATORS = {
    "gt": lambda actual, expected: actual > expected,
    "lt": lambda actual, expected: actual < expected,
    "gte": lambda actual, expected: actual >= expected,
    "lte": lambda actual, expected: actual <= expected,
}


def _resolve_field(field: str, doc_props: dict[str, Any]) -> Any:
    """Resolve a *field* name to its actual value from *doc_props*.

    ``doc_props`` is expected to contain top-level keys that mirror the
    built-in field names **plus** a ``metadata`` dict with the parsed
    AI metadata JSON.
    """
    if field == "category":
        # ``category`` is an alias for ``document_type``.
        field = "document_type"

    if field.startswith("metadata."):
        meta_key = field[len("metadata.") :]
        metadata = doc_props.get("metadata") or {}
        return metadata.get(meta_key)

    return doc_props.get(field)


def _to_float(value: Any) -> float | None:
    """Try to convert *value* to a float for numeric comparison."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _evaluate_text_condition(actual: Any, operator: str, expected: str) -> bool | None:
    evaluator = TEXT_OPERATORS.get(operator)
    if evaluator is None:
        return None

    actual_str = str(actual).lower()
    expected_lower = expected.lower()
    return evaluator(actual_str, expected_lower)


def _evaluate_regex_condition(actual: Any, expected: str) -> bool:
    try:
        return bool(re.fullmatch(expected, str(actual), flags=re.IGNORECASE))
    except re.error:
        logger.warning("Invalid regex in routing rule: %s", expected)
        return False


def _evaluate_numeric_condition(actual: Any, operator: str, expected: str) -> bool | None:
    evaluator = NUMERIC_OPERATORS.get(operator)
    if evaluator is None:
        return None

    actual_num = _to_float(actual)
    expected_num = _to_float(expected)
    if actual_num is None or expected_num is None:
        return False

    return evaluator(actual_num, expected_num)


def _evaluate_condition(actual: Any, operator: str, expected: str) -> bool:
    """Return ``True`` when *actual* satisfies *operator* against *expected*.

    All string comparisons are case-insensitive.  Numeric operators (``gt``,
    ``lt``, ``gte``, ``lte``) attempt to cast both sides to ``float``.
    """
    if actual is None:
        # If the document property is missing, the rule cannot match
        # (except for ``not_equals`` / ``not_contains`` which should match).
        return operator in {"not_equals", "not_contains"}

    text_result = _evaluate_text_condition(actual, operator, expected)
    if text_result is not None:
        return text_result

    if operator == "regex":
        return _evaluate_regex_condition(actual, expected)

    numeric_result = _evaluate_numeric_condition(actual, operator, expected)
    return bool(numeric_result) if numeric_result is not None else False


def build_document_properties(file_record: Any) -> dict[str, Any]:
    """Build the property dict that the engine evaluates against.

    Args:
        file_record: A :class:`FileRecord` instance (or any object with the
            same attributes).

    Returns:
        A dict with ``file_type``, ``filename``, ``size``, ``document_type``,
        and ``metadata`` keys.
    """
    metadata: dict[str, Any] = {}
    raw_meta = getattr(file_record, "ai_metadata", None)
    if raw_meta:
        try:
            metadata = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
        except (json.JSONDecodeError, TypeError):
            metadata = {}

    return {
        "file_type": getattr(file_record, "mime_type", None),
        "filename": getattr(file_record, "original_filename", None),
        "size": getattr(file_record, "file_size", None),
        "document_type": metadata.get("document_type"),
        "metadata": metadata,
    }


def evaluate_routing_rules(
    db: Session,
    owner_id: str | None,
    doc_props: dict[str, Any],
) -> Pipeline | None:
    """Evaluate routing rules and return the first matching pipeline.

    Rules are fetched for the given *owner_id* **plus** any system-wide rules
    (``owner_id IS NULL``).  Owner rules are evaluated first (by position),
    then system rules.

    Args:
        db: Active database session.
        owner_id: The document owner's identifier (may be ``None``).
        doc_props: Document property dict as produced by
            :func:`build_document_properties`.

    Returns:
        The first matching :class:`Pipeline`, or ``None`` when no rule
        matches (caller should fall back to the default pipeline).
    """
    # Fetch active rules for the owner + system rules, ordered by position.
    rules = (
        db.query(PipelineRoutingRule)
        .filter(
            PipelineRoutingRule.is_active.is_(True),
            (PipelineRoutingRule.owner_id == owner_id) | (PipelineRoutingRule.owner_id.is_(None)),
        )
        .order_by(
            # Owner-specific rules take priority over system rules.
            PipelineRoutingRule.owner_id.is_(None).asc(),
            PipelineRoutingRule.position.asc(),
        )
        .all()
    )

    for rule in rules:
        actual = _resolve_field(rule.field, doc_props)
        if _evaluate_condition(actual, rule.operator, rule.value):
            pipeline = db.query(Pipeline).filter(Pipeline.id == rule.target_pipeline_id).first()
            if pipeline and pipeline.is_active:
                logger.info(
                    "Routing rule matched: rule_id=%s, name=%s, target_pipeline=%s",
                    rule.id,
                    rule.name,
                    rule.target_pipeline_id,
                )
                return pipeline
            logger.warning(
                "Routing rule %s matched but target pipeline %s is inactive or missing",
                rule.id,
                rule.target_pipeline_id,
            )

    return None
