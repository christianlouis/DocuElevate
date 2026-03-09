"""
Rule-based document classification engine.

Provides pre-built categories and a rule matcher that classifies documents
using filename patterns, content keywords, and metadata fields.  Custom
rules stored in the database are evaluated alongside the built-in defaults.

Usage::

    from app.utils.classification_rules import classify_document

    result = classify_document(
        filename="2024-03-01_Invoice_Acme.pdf",
        text="Invoice total: $1,234.56",
        metadata={"absender": "Acme Corp"},
        custom_rules=custom_rules_from_db,
    )
    # result -> ClassificationResult(category="invoice", confidence=85, matched_rules=[...])
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-built categories
# ---------------------------------------------------------------------------

#: Canonical category names recognised by the system.  Users may also define
#: their own categories via custom rules.
BUILTIN_CATEGORIES: dict[str, str] = {
    "invoice": "Invoice",
    "contract": "Contract",
    "receipt": "Receipt",
    "letter": "Letter",
    "report": "Report",
    "bank_statement": "Bank Statement",
    "tax_document": "Tax Document",
    "insurance": "Insurance Document",
    "payslip": "Payslip",
    "unknown": "Unknown",
}

# ---------------------------------------------------------------------------
# Rule type constants
# ---------------------------------------------------------------------------

RULE_TYPE_FILENAME = "filename_pattern"
RULE_TYPE_CONTENT = "content_keyword"
RULE_TYPE_METADATA = "metadata_match"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ClassificationRule:
    """A single classification rule."""

    name: str
    category: str
    rule_type: str  # filename_pattern | content_keyword | metadata_match
    pattern: str  # regex for filename, keyword(s) for content, "field=value" for metadata
    priority: int = 0  # higher = evaluated first
    case_sensitive: bool = False

    def __post_init__(self) -> None:
        if self.rule_type not in (RULE_TYPE_FILENAME, RULE_TYPE_CONTENT, RULE_TYPE_METADATA):
            raise ValueError(f"Invalid rule_type: {self.rule_type!r}")


@dataclass
class MatchedRule:
    """Records which rule matched and why."""

    rule_name: str
    rule_type: str
    category: str
    confidence: int


@dataclass
class ClassificationResult:
    """The outcome of running the classification engine on a document."""

    category: str
    confidence: int  # 0 – 100
    matched_rules: list[MatchedRule] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Built-in rules
# ---------------------------------------------------------------------------

BUILTIN_RULES: list[ClassificationRule] = [
    # ── Invoice ───────────────────────────────────────────────────────────
    ClassificationRule("builtin_invoice_filename", "invoice", RULE_TYPE_FILENAME, r"(?i)invoice|rechnung|facture"),
    ClassificationRule(
        "builtin_invoice_content",
        "invoice",
        RULE_TYPE_CONTENT,
        "invoice number|invoice total|amount due|rechnung|rechnungsnummer|total amount|bill to",
    ),
    ClassificationRule("builtin_invoice_metadata", "invoice", RULE_TYPE_METADATA, "document_type=Invoice"),
    ClassificationRule(
        "builtin_invoice_kommunikationsart", "invoice", RULE_TYPE_METADATA, "kommunikationsart=Rechnung"
    ),
    # ── Contract ──────────────────────────────────────────────────────────
    ClassificationRule("builtin_contract_filename", "contract", RULE_TYPE_FILENAME, r"(?i)contract|vertrag|agreement"),
    ClassificationRule(
        "builtin_contract_content",
        "contract",
        RULE_TYPE_CONTENT,
        "hereby agrees|terms and conditions|vertrag|agreement between|party agrees|effective date",
    ),
    ClassificationRule("builtin_contract_metadata", "contract", RULE_TYPE_METADATA, "document_type=Contract"),
    ClassificationRule(
        "builtin_contract_kommunikationsart", "contract", RULE_TYPE_METADATA, "kommunikationsart=Vertrag"
    ),
    # ── Receipt ───────────────────────────────────────────────────────────
    ClassificationRule("builtin_receipt_filename", "receipt", RULE_TYPE_FILENAME, r"(?i)receipt|quittung|beleg"),
    ClassificationRule(
        "builtin_receipt_content",
        "receipt",
        RULE_TYPE_CONTENT,
        "receipt|quittung|payment received|thank you for your purchase|transaction id",
    ),
    ClassificationRule("builtin_receipt_metadata", "receipt", RULE_TYPE_METADATA, "document_type=Receipt"),
    ClassificationRule(
        "builtin_receipt_kommunikationsart", "receipt", RULE_TYPE_METADATA, "kommunikationsart=Quittung"
    ),
    # ── Letter ────────────────────────────────────────────────────────────
    ClassificationRule("builtin_letter_filename", "letter", RULE_TYPE_FILENAME, r"(?i)letter|brief|schreiben"),
    ClassificationRule(
        "builtin_letter_content",
        "letter",
        RULE_TYPE_CONTENT,
        "dear sir|dear madam|sehr geehrte|to whom it may concern|sincerely|mit freundlichen",
    ),
    # ── Report ────────────────────────────────────────────────────────────
    ClassificationRule("builtin_report_filename", "report", RULE_TYPE_FILENAME, r"(?i)report|bericht"),
    ClassificationRule(
        "builtin_report_content",
        "report",
        RULE_TYPE_CONTENT,
        "executive summary|table of contents|annual report|quarterly report|findings",
    ),
    # ── Bank statement ────────────────────────────────────────────────────
    ClassificationRule(
        "builtin_bank_filename",
        "bank_statement",
        RULE_TYPE_FILENAME,
        r"(?i)bank.?statement|kontoauszug",
    ),
    ClassificationRule(
        "builtin_bank_content",
        "bank_statement",
        RULE_TYPE_CONTENT,
        "account statement|kontoauszug|opening balance|closing balance|account number",
    ),
    ClassificationRule(
        "builtin_bank_kommunikationsart", "bank_statement", RULE_TYPE_METADATA, "kommunikationsart=Kontoauszug"
    ),
    # ── Tax document ──────────────────────────────────────────────────────
    ClassificationRule("builtin_tax_filename", "tax_document", RULE_TYPE_FILENAME, r"(?i)tax|steuer|steuerbescheid"),
    ClassificationRule(
        "builtin_tax_content",
        "tax_document",
        RULE_TYPE_CONTENT,
        "tax return|steuerbescheid|taxable income|finanzamt|tax assessment",
    ),
    # ── Insurance ─────────────────────────────────────────────────────────
    ClassificationRule(
        "builtin_insurance_filename", "insurance", RULE_TYPE_FILENAME, r"(?i)insurance|versicherung|police"
    ),
    ClassificationRule(
        "builtin_insurance_content",
        "insurance",
        RULE_TYPE_CONTENT,
        "insurance policy|versicherung|policennummer|coverage|premium|deductible",
    ),
    # ── Payslip ───────────────────────────────────────────────────────────
    ClassificationRule(
        "builtin_payslip_filename", "payslip", RULE_TYPE_FILENAME, r"(?i)payslip|gehaltsabrechnung|lohnabrechnung"
    ),
    ClassificationRule(
        "builtin_payslip_content",
        "payslip",
        RULE_TYPE_CONTENT,
        "gross salary|net salary|gehaltsabrechnung|lohnabrechnung|bruttolohn|nettolohn",
    ),
]


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

#: Base confidence for each rule type when it matches.
_CONFIDENCE_MAP: dict[str, int] = {
    RULE_TYPE_FILENAME: 60,
    RULE_TYPE_CONTENT: 70,
    RULE_TYPE_METADATA: 90,
}

#: Extra confidence per additional matching rule of the same category (capped).
_CONFIDENCE_BONUS_PER_EXTRA_RULE = 10


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------


def _match_filename(rule: ClassificationRule, filename: str) -> bool:
    """Return True if *rule.pattern* (regex) matches anywhere in *filename*."""
    if not filename:
        return False
    flags = 0 if rule.case_sensitive else re.IGNORECASE
    return bool(re.search(rule.pattern, filename, flags))


def _match_content(rule: ClassificationRule, text: str) -> bool:
    """Return True if any keyword in *rule.pattern* appears in *text*.

    Keywords are separated by ``|`` (pipe).
    """
    if not text:
        return False
    keywords = [kw.strip() for kw in rule.pattern.split("|") if kw.strip()]
    text_lower = text if rule.case_sensitive else text.lower()
    return any((kw if rule.case_sensitive else kw.lower()) in text_lower for kw in keywords)


def _match_metadata(rule: ClassificationRule, metadata: dict[str, Any] | None) -> bool:
    """Return True if *rule.pattern* (``field=value``) matches *metadata*.

    Pattern format: ``field_name=expected_value``.
    """
    if not metadata:
        return False
    if "=" not in rule.pattern:
        return False
    field_name, expected_value = rule.pattern.split("=", 1)
    actual = metadata.get(field_name.strip())
    if actual is None:
        return False
    if rule.case_sensitive:
        return str(actual) == expected_value.strip()
    return str(actual).lower() == expected_value.strip().lower()


_MATCHERS = {
    RULE_TYPE_FILENAME: _match_filename,
    RULE_TYPE_CONTENT: _match_content,
    RULE_TYPE_METADATA: _match_metadata,
}


def _evaluate_rule(
    rule: ClassificationRule,
    filename: str,
    text: str,
    metadata: dict[str, Any] | None,
) -> MatchedRule | None:
    """Evaluate a single rule against the document.  Return a :class:`MatchedRule` on match."""
    matcher = _MATCHERS.get(rule.rule_type)
    if matcher is None:
        return None

    # Dispatch to the appropriate matcher based on rule type
    if rule.rule_type == RULE_TYPE_FILENAME:
        matched = matcher(rule, filename)
    elif rule.rule_type == RULE_TYPE_CONTENT:
        matched = matcher(rule, text)
    elif rule.rule_type == RULE_TYPE_METADATA:
        matched = matcher(rule, metadata)
    else:
        matched = False

    if matched:
        return MatchedRule(
            rule_name=rule.name,
            rule_type=rule.rule_type,
            category=rule.category,
            confidence=_CONFIDENCE_MAP.get(rule.rule_type, 50),
        )
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_document(
    filename: str = "",
    text: str = "",
    metadata: dict[str, Any] | None = None,
    custom_rules: list[ClassificationRule] | None = None,
) -> ClassificationResult:
    """Classify a document by evaluating built-in and custom rules.

    Rules are evaluated in priority order (highest first, then built-in before
    custom for the same priority).  The category with the most rule matches
    wins; ties are broken by cumulative confidence.

    Args:
        filename: Original filename of the document.
        text: Extracted / OCR text of the document.
        metadata: Previously-extracted AI metadata dict (e.g. from ``ai_metadata``).
        custom_rules: Optional list of user-defined :class:`ClassificationRule` objects.

    Returns:
        A :class:`ClassificationResult` with the best matching category,
        overall confidence score, and the list of rules that fired.
    """
    all_rules = list(BUILTIN_RULES)
    if custom_rules:
        all_rules.extend(custom_rules)

    # Sort by priority descending (higher priority first)
    all_rules.sort(key=lambda r: r.priority, reverse=True)

    matches: list[MatchedRule] = []
    for rule in all_rules:
        result = _evaluate_rule(rule, filename, text, metadata)
        if result is not None:
            matches.append(result)

    if not matches:
        return ClassificationResult(category="unknown", confidence=0, matched_rules=[])

    # Aggregate by category: pick the one with the most matches, then highest
    # cumulative confidence as tiebreaker.
    category_scores: dict[str, list[MatchedRule]] = {}
    for m in matches:
        category_scores.setdefault(m.category, []).append(m)

    best_category = max(
        category_scores,
        key=lambda cat: (len(category_scores[cat]), sum(m.confidence for m in category_scores[cat])),
    )

    best_matches = category_scores[best_category]
    base_confidence = max(m.confidence for m in best_matches)
    bonus = min(
        (len(best_matches) - 1) * _CONFIDENCE_BONUS_PER_EXTRA_RULE,
        100 - base_confidence,
    )
    final_confidence = min(base_confidence + bonus, 100)

    return ClassificationResult(
        category=best_category,
        confidence=final_confidence,
        matched_rules=best_matches,
    )


def db_rule_to_engine_rule(db_rule: Any) -> ClassificationRule:
    """Convert a database ``ClassificationRuleModel`` row to an engine :class:`ClassificationRule`.

    Args:
        db_rule: A SQLAlchemy model instance with ``name``, ``category``,
            ``rule_type``, ``pattern``, ``priority``, and ``case_sensitive`` attributes.

    Returns:
        A :class:`ClassificationRule` dataclass instance.
    """
    return ClassificationRule(
        name=db_rule.name,
        category=db_rule.category,
        rule_type=db_rule.rule_type,
        pattern=db_rule.pattern,
        priority=db_rule.priority,
        case_sensitive=getattr(db_rule, "case_sensitive", False),
    )
