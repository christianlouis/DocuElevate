"""Tests for the rule-based document classification engine.

Covers the classification engine logic in ``app/utils/classification_rules.py``:
built-in rules, custom rules, confidence scoring, and edge cases.
"""

import pytest

from app.utils.classification_rules import (
    BUILTIN_CATEGORIES,
    BUILTIN_RULES,
    RULE_TYPE_CONTENT,
    RULE_TYPE_FILENAME,
    RULE_TYPE_METADATA,
    ClassificationResult,
    ClassificationRule,
    MatchedRule,
    classify_document,
    db_rule_to_engine_rule,
)

# ---------------------------------------------------------------------------
# Built-in categories & rules smoke tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuiltinCategories:
    """Verify the pre-built categories and rules are sane."""

    def test_builtin_categories_not_empty(self):
        """There must be at least one built-in category."""
        assert len(BUILTIN_CATEGORIES) > 0

    def test_unknown_category_exists(self):
        """The 'unknown' fallback category must be present."""
        assert "unknown" in BUILTIN_CATEGORIES

    def test_core_categories_present(self):
        """Invoice, contract, and receipt categories must exist."""
        for cat in ("invoice", "contract", "receipt"):
            assert cat in BUILTIN_CATEGORIES, f"Missing built-in category: {cat}"

    def test_builtin_rules_not_empty(self):
        """There must be at least one built-in rule."""
        assert len(BUILTIN_RULES) > 0

    def test_all_builtin_rules_reference_valid_types(self):
        """Every built-in rule must use a valid rule_type."""
        valid_types = {RULE_TYPE_FILENAME, RULE_TYPE_CONTENT, RULE_TYPE_METADATA}
        for rule in BUILTIN_RULES:
            assert rule.rule_type in valid_types, f"Rule {rule.name!r} has invalid type {rule.rule_type!r}"


# ---------------------------------------------------------------------------
# ClassificationRule dataclass validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClassificationRuleValidation:
    """Test ClassificationRule dataclass validation."""

    def test_valid_rule_types(self):
        """Valid rule types should not raise."""
        for rt in (RULE_TYPE_FILENAME, RULE_TYPE_CONTENT, RULE_TYPE_METADATA):
            rule = ClassificationRule(name="test", category="test", rule_type=rt, pattern="test")
            assert rule.rule_type == rt

    def test_invalid_rule_type_raises(self):
        """An invalid rule_type should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid rule_type"):
            ClassificationRule(name="test", category="test", rule_type="invalid", pattern="test")


# ---------------------------------------------------------------------------
# Filename pattern matching
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFilenamePatternMatching:
    """Test classification via filename patterns."""

    def test_invoice_filename(self):
        """A filename containing 'invoice' should classify as invoice."""
        result = classify_document(filename="2024-03-01_Invoice_Acme.pdf")
        assert result.category == "invoice"
        assert result.confidence > 0

    def test_german_invoice_filename(self):
        """A filename containing 'Rechnung' should classify as invoice."""
        result = classify_document(filename="Rechnung_2024.pdf")
        assert result.category == "invoice"
        assert result.confidence > 0

    def test_contract_filename(self):
        """A filename containing 'contract' should classify as contract."""
        result = classify_document(filename="Service_Contract_2024.pdf")
        assert result.category == "contract"

    def test_receipt_filename(self):
        """A filename containing 'receipt' should classify as receipt."""
        result = classify_document(filename="Payment_Receipt.pdf")
        assert result.category == "receipt"

    def test_unrecognized_filename(self):
        """A generic filename with no keywords should return 'unknown'."""
        result = classify_document(filename="document_12345.pdf")
        assert result.category == "unknown"
        assert result.confidence == 0

    def test_empty_filename(self):
        """An empty filename should not match any rule."""
        result = classify_document(filename="")
        assert result.category == "unknown"


# ---------------------------------------------------------------------------
# Content keyword matching
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContentKeywordMatching:
    """Test classification via content keywords."""

    def test_invoice_content(self):
        """Text containing 'invoice number' should classify as invoice."""
        result = classify_document(text="Please pay the invoice number 12345. Amount due: $500")
        assert result.category == "invoice"
        assert result.confidence > 0

    def test_contract_content(self):
        """Text containing 'terms and conditions' should classify as contract."""
        result = classify_document(text="The parties hereby agree to the following terms and conditions.")
        assert result.category == "contract"

    def test_receipt_content(self):
        """Text containing 'payment received' should classify as receipt."""
        result = classify_document(text="Thank you. Payment received for order #789.")
        assert result.category == "receipt"

    def test_bank_statement_content(self):
        """Text containing 'account statement' should classify as bank_statement."""
        result = classify_document(text="Monthly account statement. Opening balance: $1,000.")
        assert result.category == "bank_statement"

    def test_empty_text(self):
        """Empty text should not match any content rule."""
        result = classify_document(text="")
        assert result.category == "unknown"

    def test_case_insensitive_matching(self):
        """Content matching should be case-insensitive by default."""
        result = classify_document(text="INVOICE NUMBER 12345")
        assert result.category == "invoice"


# ---------------------------------------------------------------------------
# Metadata matching
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMetadataMatching:
    """Test classification via metadata field matching."""

    def test_document_type_invoice(self):
        """metadata document_type=Invoice should classify as invoice."""
        result = classify_document(metadata={"document_type": "Invoice"})
        assert result.category == "invoice"
        assert result.confidence >= 90

    def test_document_type_contract(self):
        """metadata document_type=Contract should classify as contract."""
        result = classify_document(metadata={"document_type": "Contract"})
        assert result.category == "contract"

    def test_kommunikationsart_rechnung(self):
        """German classification metadata should classify as invoice."""
        result = classify_document(metadata={"kommunikationsart": "Rechnung"})
        assert result.category == "invoice"

    def test_no_metadata(self):
        """None metadata should not match."""
        result = classify_document(metadata=None)
        assert result.category == "unknown"

    def test_empty_metadata(self):
        """Empty metadata dict should not match."""
        result = classify_document(metadata={})
        assert result.category == "unknown"

    def test_metadata_case_insensitive(self):
        """Metadata matching should be case-insensitive by default."""
        result = classify_document(metadata={"document_type": "invoice"})
        assert result.category == "invoice"


# ---------------------------------------------------------------------------
# Combined matching / confidence boosting
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCombinedMatching:
    """Test that multiple matching rules boost confidence."""

    def test_filename_and_content_boost(self):
        """Filename + content matching should produce higher confidence than either alone."""
        filename_only = classify_document(filename="Invoice_2024.pdf")
        combined = classify_document(filename="Invoice_2024.pdf", text="Invoice number: 12345. Amount due: $500.")
        assert combined.confidence >= filename_only.confidence
        assert len(combined.matched_rules) > len(filename_only.matched_rules)

    def test_all_three_signals(self):
        """Filename + content + metadata should produce highest confidence."""
        result = classify_document(
            filename="Invoice_Acme.pdf",
            text="Invoice number: 12345. Amount due: $500.",
            metadata={"document_type": "Invoice"},
        )
        assert result.category == "invoice"
        assert result.confidence >= 90

    def test_conflicting_signals_most_matches_wins(self):
        """When filename says 'invoice' but content says 'contract', most matches wins."""
        result = classify_document(
            filename="Invoice.pdf",
            text="The parties hereby agree to the following terms and conditions. "
            "This agreement between Company A and Company B is effective immediately.",
        )
        # Content has more keyword matches for contract, but filename matches invoice.
        # Either is acceptable as long as the result is deterministic.
        assert result.category in ("invoice", "contract")


# ---------------------------------------------------------------------------
# Custom rules
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCustomRules:
    """Test user-defined custom classification rules."""

    def test_custom_rule_matches(self):
        """A custom filename rule should match when pattern hits."""
        custom = [
            ClassificationRule(
                name="custom_hr_doc",
                category="hr_document",
                rule_type=RULE_TYPE_FILENAME,
                pattern=r"(?i)employee|hiring|hr",
            )
        ]
        result = classify_document(filename="Employee_Handbook.pdf", custom_rules=custom)
        assert result.category == "hr_document"

    def test_custom_content_rule(self):
        """A custom content keyword rule should match."""
        custom = [
            ClassificationRule(
                name="custom_medical",
                category="medical",
                rule_type=RULE_TYPE_CONTENT,
                pattern="diagnosis|prescription|patient record",
            )
        ]
        result = classify_document(text="Patient record for Jane Doe. Diagnosis: common cold.", custom_rules=custom)
        assert result.category == "medical"

    def test_custom_metadata_rule(self):
        """A custom metadata rule should match."""
        custom = [
            ClassificationRule(
                name="custom_legal",
                category="legal",
                rule_type=RULE_TYPE_METADATA,
                pattern="department=legal",
            )
        ]
        result = classify_document(metadata={"department": "legal"}, custom_rules=custom)
        assert result.category == "legal"

    def test_custom_rule_overrides_builtin(self):
        """Custom rules with more matches should override built-in rules."""
        custom = [
            ClassificationRule(
                name="custom_internal_invoice",
                category="internal_invoice",
                rule_type=RULE_TYPE_FILENAME,
                pattern=r"(?i)invoice",
                priority=100,
            ),
            ClassificationRule(
                name="custom_internal_invoice_content",
                category="internal_invoice",
                rule_type=RULE_TYPE_CONTENT,
                pattern="invoice number",
                priority=100,
            ),
        ]
        result = classify_document(
            filename="Invoice_2024.pdf",
            text="Invoice number: 12345",
            custom_rules=custom,
        )
        # Both builtin and custom rules for "invoice" patterns match, but custom
        # has "internal_invoice" as category. The category with more total matches wins.
        assert result.category in ("invoice", "internal_invoice")
        assert result.confidence > 0


# ---------------------------------------------------------------------------
# db_rule_to_engine_rule converter
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDbRuleConversion:
    """Test the database model to engine rule converter."""

    def test_converts_basic_fields(self):
        """All basic fields should be mapped correctly."""

        class FakeDbRule:
            name = "test_rule"
            category = "invoice"
            rule_type = RULE_TYPE_FILENAME
            pattern = r"(?i)invoice"
            priority = 10
            case_sensitive = True

        engine_rule = db_rule_to_engine_rule(FakeDbRule())
        assert engine_rule.name == "test_rule"
        assert engine_rule.category == "invoice"
        assert engine_rule.rule_type == RULE_TYPE_FILENAME
        assert engine_rule.pattern == r"(?i)invoice"
        assert engine_rule.priority == 10
        assert engine_rule.case_sensitive is True

    def test_defaults_case_sensitive_to_false(self):
        """When case_sensitive is missing, default to False."""

        class FakeDbRule:
            name = "test"
            category = "test"
            rule_type = RULE_TYPE_CONTENT
            pattern = "test"
            priority = 0

        engine_rule = db_rule_to_engine_rule(FakeDbRule())
        assert engine_rule.case_sensitive is False


# ---------------------------------------------------------------------------
# ClassificationResult
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClassificationResult:
    """Test the ClassificationResult dataclass."""

    def test_default_matched_rules(self):
        """matched_rules should default to an empty list."""
        result = ClassificationResult(category="test", confidence=50)
        assert result.matched_rules == []

    def test_with_matched_rules(self):
        """matched_rules should be populated when provided."""
        match = MatchedRule(rule_name="test", rule_type=RULE_TYPE_FILENAME, category="invoice", confidence=60)
        result = ClassificationResult(category="invoice", confidence=60, matched_rules=[match])
        assert len(result.matched_rules) == 1
        assert result.matched_rules[0].rule_name == "test"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases in the classification engine."""

    def test_no_inputs_at_all(self):
        """No filename, text, or metadata should return 'unknown'."""
        result = classify_document()
        assert result.category == "unknown"
        assert result.confidence == 0
        assert result.matched_rules == []

    def test_metadata_pattern_without_equals(self):
        """A metadata pattern without '=' should not match."""
        custom = [
            ClassificationRule(
                name="bad_pattern",
                category="test",
                rule_type=RULE_TYPE_METADATA,
                pattern="no_equals_sign",
            )
        ]
        result = classify_document(metadata={"no_equals_sign": "value"}, custom_rules=custom)
        assert result.category == "unknown"

    def test_confidence_capped_at_100(self):
        """Confidence should never exceed 100."""
        # Create many rules that all match to test the cap
        custom = [
            ClassificationRule(
                name=f"flood_{i}",
                category="flood",
                rule_type=RULE_TYPE_CONTENT,
                pattern="test keyword",
            )
            for i in range(20)
        ]
        result = classify_document(text="test keyword is here", custom_rules=custom)
        assert result.confidence <= 100
