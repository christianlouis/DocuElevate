"""Tests for the routing rules API and routing engine.

Covers CRUD operations for routing rules, rule evaluation (dry-run and engine),
operator logic, access control, and edge cases.
"""

import json

import pytest

from app.models import FileRecord, Pipeline, PipelineRoutingRule
from app.utils.routing_engine import (
    BUILTIN_FIELDS,
    VALID_OPERATORS,
    _evaluate_condition,
    _resolve_field,
    _to_float,
    build_document_properties,
    evaluate_routing_rules,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pipeline(db_session, name="Test Pipeline", owner_id="testuser", is_active=True):
    """Insert a minimal Pipeline and return it."""
    p = Pipeline(owner_id=owner_id, name=name, is_default=False, is_active=is_active)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _make_rule(db_session, target_pipeline_id, **kwargs):
    """Insert a PipelineRoutingRule and return it."""
    defaults = {
        "owner_id": "testuser",
        "name": "Test Rule",
        "position": 0,
        "field": "file_type",
        "operator": "equals",
        "value": "application/pdf",
        "is_active": True,
    }
    defaults.update(kwargs)
    defaults["target_pipeline_id"] = target_pipeline_id
    rule = PipelineRoutingRule(**defaults)
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)
    return rule


def _make_file_record(db_session, **kwargs):
    """Insert a minimal FileRecord and return it."""
    defaults = {
        "owner_id": "testuser",
        "filehash": "abc123",
        "original_filename": "test.pdf",
        "local_filename": "/tmp/test.pdf",
        "file_size": 1024,
        "mime_type": "application/pdf",
    }
    defaults.update(kwargs)
    fr = FileRecord(**defaults)
    db_session.add(fr)
    db_session.commit()
    db_session.refresh(fr)
    return fr


# ===========================================================================
# Unit tests – routing engine
# ===========================================================================


@pytest.mark.unit
class TestResolveField:
    """Tests for _resolve_field()."""

    def test_builtin_field(self):
        """Built-in fields are resolved directly from the dict."""
        props = {"file_type": "application/pdf", "size": 1024}
        assert _resolve_field("file_type", props) == "application/pdf"
        assert _resolve_field("size", props) == 1024

    def test_category_alias(self):
        """'category' is an alias for 'document_type'."""
        props = {"document_type": "Invoice"}
        assert _resolve_field("category", props) == "Invoice"

    def test_metadata_field(self):
        """'metadata.<key>' resolves from the nested metadata dict."""
        props = {"metadata": {"sender": "Acme Corp", "amount": 100.50}}
        assert _resolve_field("metadata.sender", props) == "Acme Corp"
        assert _resolve_field("metadata.amount", props) == 100.50

    def test_missing_metadata_key(self):
        """Missing metadata key returns None."""
        props = {"metadata": {"sender": "Acme"}}
        assert _resolve_field("metadata.missing_key", props) is None

    def test_missing_metadata_dict(self):
        """Missing metadata dict returns None."""
        props = {}
        assert _resolve_field("metadata.sender", props) is None

    def test_missing_builtin_field(self):
        """Missing built-in field returns None."""
        props = {}
        assert _resolve_field("file_type", props) is None


@pytest.mark.unit
class TestToFloat:
    """Tests for _to_float()."""

    def test_int_value(self):
        assert _to_float(42) == 42.0

    def test_float_value(self):
        assert _to_float(3.14) == 3.14

    def test_string_number(self):
        assert _to_float("100") == 100.0

    def test_none_returns_none(self):
        assert _to_float(None) is None

    def test_non_numeric_string_returns_none(self):
        assert _to_float("not-a-number") is None


@pytest.mark.unit
class TestEvaluateCondition:
    """Tests for _evaluate_condition()."""

    def test_equals_match(self):
        assert _evaluate_condition("application/pdf", "equals", "application/pdf") is True

    def test_equals_case_insensitive(self):
        assert _evaluate_condition("Application/PDF", "equals", "application/pdf") is True

    def test_equals_no_match(self):
        assert _evaluate_condition("image/png", "equals", "application/pdf") is False

    def test_not_equals_match(self):
        assert _evaluate_condition("image/png", "not_equals", "application/pdf") is True

    def test_not_equals_no_match(self):
        assert _evaluate_condition("application/pdf", "not_equals", "application/pdf") is False

    def test_contains_match(self):
        assert _evaluate_condition("invoice_2024.pdf", "contains", "invoice") is True

    def test_contains_case_insensitive(self):
        assert _evaluate_condition("INVOICE_2024.PDF", "contains", "invoice") is True

    def test_contains_no_match(self):
        assert _evaluate_condition("receipt.pdf", "contains", "invoice") is False

    def test_not_contains_match(self):
        assert _evaluate_condition("receipt.pdf", "not_contains", "invoice") is True

    def test_not_contains_no_match(self):
        assert _evaluate_condition("invoice_2024.pdf", "not_contains", "invoice") is False

    def test_regex_match(self):
        assert _evaluate_condition("invoice_2024.pdf", "regex", r"invoice_\d+\.pdf") is True

    def test_regex_no_match(self):
        assert _evaluate_condition("receipt.pdf", "regex", r"invoice_\d+\.pdf") is False

    def test_regex_case_insensitive(self):
        assert _evaluate_condition("INVOICE_2024.PDF", "regex", r"invoice_\d+\.pdf") is True

    def test_regex_invalid_pattern(self):
        """Invalid regex should return False, not raise."""
        assert _evaluate_condition("test", "regex", r"[invalid") is False

    def test_gt(self):
        assert _evaluate_condition(2048, "gt", "1024") is True
        assert _evaluate_condition(1024, "gt", "1024") is False

    def test_lt(self):
        assert _evaluate_condition(512, "lt", "1024") is True
        assert _evaluate_condition(1024, "lt", "1024") is False

    def test_gte(self):
        assert _evaluate_condition(1024, "gte", "1024") is True
        assert _evaluate_condition(2048, "gte", "1024") is True
        assert _evaluate_condition(512, "gte", "1024") is False

    def test_lte(self):
        assert _evaluate_condition(1024, "lte", "1024") is True
        assert _evaluate_condition(512, "lte", "1024") is True
        assert _evaluate_condition(2048, "lte", "1024") is False

    def test_none_actual_returns_false(self):
        """When the actual value is None, most operators return False."""
        assert _evaluate_condition(None, "equals", "test") is False
        assert _evaluate_condition(None, "contains", "test") is False
        assert _evaluate_condition(None, "regex", "test") is False
        assert _evaluate_condition(None, "gt", "10") is False

    def test_none_actual_not_equals_returns_true(self):
        """not_equals should return True when actual is None."""
        assert _evaluate_condition(None, "not_equals", "test") is True

    def test_none_actual_not_contains_returns_true(self):
        """not_contains should return True when actual is None."""
        assert _evaluate_condition(None, "not_contains", "test") is True

    def test_non_numeric_gt_returns_false(self):
        """Non-numeric values should return False for numeric operators."""
        assert _evaluate_condition("abc", "gt", "100") is False

    def test_unknown_operator_returns_false(self):
        """Unknown operator should return False."""
        assert _evaluate_condition("test", "unknown_op", "test") is False


@pytest.mark.unit
class TestBuildDocumentProperties:
    """Tests for build_document_properties()."""

    def test_basic_properties(self):
        """Properties are extracted from FileRecord attributes."""
        fr = _MockFileRecord(
            mime_type="application/pdf",
            original_filename="test.pdf",
            file_size=2048,
            ai_metadata=json.dumps({"document_type": "Invoice", "sender": "Acme"}),
        )
        props = build_document_properties(fr)
        assert props["file_type"] == "application/pdf"
        assert props["filename"] == "test.pdf"
        assert props["size"] == 2048
        assert props["document_type"] == "Invoice"
        assert props["metadata"]["sender"] == "Acme"

    def test_no_metadata(self):
        """When ai_metadata is None, metadata is an empty dict."""
        fr = _MockFileRecord(mime_type="image/png", original_filename="img.png", file_size=512, ai_metadata=None)
        props = build_document_properties(fr)
        assert props["metadata"] == {}
        assert props["document_type"] is None

    def test_invalid_metadata_json(self):
        """Invalid JSON in ai_metadata should result in empty metadata."""
        fr = _MockFileRecord(
            mime_type="application/pdf",
            original_filename="test.pdf",
            file_size=1024,
            ai_metadata="not-json",
        )
        props = build_document_properties(fr)
        assert props["metadata"] == {}


class _MockFileRecord:
    """Lightweight stand-in for FileRecord in unit tests."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ===========================================================================
# Unit tests – evaluate_routing_rules (DB-backed)
# ===========================================================================


@pytest.mark.unit
class TestEvaluateRoutingRules:
    """Tests for evaluate_routing_rules() with a real DB session."""

    def test_first_match_wins(self, db_session):
        """The first matching rule (by position) is used."""
        p1 = _make_pipeline(db_session, name="Pipeline A")
        p2 = _make_pipeline(db_session, name="Pipeline B")

        _make_rule(db_session, p1.id, position=0, field="file_type", operator="equals", value="application/pdf")
        _make_rule(db_session, p2.id, position=1, field="file_type", operator="equals", value="application/pdf")

        doc = {"file_type": "application/pdf", "metadata": {}}
        result = evaluate_routing_rules(db_session, "testuser", doc)
        assert result is not None
        assert result.id == p1.id

    def test_no_match_returns_none(self, db_session):
        """When no rule matches, None is returned (caller uses default)."""
        p = _make_pipeline(db_session, name="Pipeline A")
        _make_rule(db_session, p.id, field="file_type", operator="equals", value="image/png")

        doc = {"file_type": "application/pdf", "metadata": {}}
        result = evaluate_routing_rules(db_session, "testuser", doc)
        assert result is None

    def test_inactive_rule_skipped(self, db_session):
        """Inactive rules are not evaluated."""
        p = _make_pipeline(db_session, name="Pipeline A")
        _make_rule(db_session, p.id, is_active=False)

        doc = {"file_type": "application/pdf", "metadata": {}}
        result = evaluate_routing_rules(db_session, "testuser", doc)
        assert result is None

    def test_inactive_pipeline_skipped(self, db_session):
        """Matching rule with inactive target pipeline is skipped."""
        p = _make_pipeline(db_session, name="Inactive Pipeline", is_active=False)
        _make_rule(db_session, p.id)

        doc = {"file_type": "application/pdf", "metadata": {}}
        result = evaluate_routing_rules(db_session, "testuser", doc)
        assert result is None

    def test_system_rules_evaluated_after_user_rules(self, db_session):
        """System rules (owner_id=NULL) are evaluated after user-specific rules."""
        p_user = _make_pipeline(db_session, name="User Pipeline")
        p_system = _make_pipeline(db_session, name="System Pipeline", owner_id=None)

        # System rule at position 0, user rule at position 1 — user should still win.
        _make_rule(
            db_session,
            p_system.id,
            owner_id=None,
            position=0,
            field="file_type",
            operator="equals",
            value="application/pdf",
            name="System Rule",
        )
        _make_rule(
            db_session,
            p_user.id,
            owner_id="testuser",
            position=1,
            field="file_type",
            operator="equals",
            value="application/pdf",
            name="User Rule",
        )

        doc = {"file_type": "application/pdf", "metadata": {}}
        result = evaluate_routing_rules(db_session, "testuser", doc)
        assert result is not None
        assert result.id == p_user.id

    def test_metadata_field_routing(self, db_session):
        """Rules can match on metadata.* fields."""
        p = _make_pipeline(db_session, name="Invoice Pipeline")
        _make_rule(
            db_session,
            p.id,
            field="metadata.sender",
            operator="contains",
            value="acme",
        )

        doc = {"file_type": "application/pdf", "metadata": {"sender": "Acme Corporation"}}
        result = evaluate_routing_rules(db_session, "testuser", doc)
        assert result is not None
        assert result.id == p.id

    def test_size_routing(self, db_session):
        """Rules can match on file size with numeric comparison."""
        p = _make_pipeline(db_session, name="Large File Pipeline")
        _make_rule(
            db_session,
            p.id,
            field="size",
            operator="gt",
            value="1048576",
        )

        # 2 MB file
        doc = {"size": 2097152, "metadata": {}}
        result = evaluate_routing_rules(db_session, "testuser", doc)
        assert result is not None
        assert result.id == p.id

    def test_regex_routing(self, db_session):
        """Rules can match using regex on filename."""
        p = _make_pipeline(db_session, name="Invoice Pipeline")
        _make_rule(
            db_session,
            p.id,
            field="filename",
            operator="regex",
            value=r"invoice_\d{4}.*",
        )

        doc = {"filename": "invoice_2024_q1.pdf", "metadata": {}}
        result = evaluate_routing_rules(db_session, "testuser", doc)
        assert result is not None
        assert result.id == p.id


# ===========================================================================
# API tests – operators endpoint (public)
# ===========================================================================


@pytest.mark.unit
class TestOperatorsEndpoint:
    """Tests for the /api/routing-rules/operators catalogue endpoint."""

    def test_operators_returns_lists(self, client):
        """GET /api/routing-rules/operators returns operators and fields."""
        r = client.get("/api/routing-rules/operators")
        assert r.status_code == 200
        data = r.json()
        assert "operators" in data
        assert "builtin_fields" in data
        assert "metadata_prefix" in data
        assert set(data["operators"]) == VALID_OPERATORS
        assert set(data["builtin_fields"]) == BUILTIN_FIELDS


# ===========================================================================
# API tests – CRUD
# ===========================================================================


@pytest.mark.unit
class TestRoutingRuleCRUD:
    """Tests for the routing rules CRUD API endpoints."""

    def test_create_rule(self, client, db_session):
        """POST /api/routing-rules creates a new rule."""
        p = _make_pipeline(db_session, name="Target Pipeline")
        r = client.post(
            "/api/routing-rules",
            json={
                "name": "Route PDFs",
                "field": "file_type",
                "operator": "equals",
                "value": "application/pdf",
                "target_pipeline_id": p.id,
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Route PDFs"
        assert data["field"] == "file_type"
        assert data["operator"] == "equals"
        assert data["target_pipeline_id"] == p.id
        assert data["is_active"] is True

    def test_create_rule_invalid_field(self, client, db_session):
        """POST with an invalid field returns 422."""
        p = _make_pipeline(db_session, name="Target")
        r = client.post(
            "/api/routing-rules",
            json={
                "name": "Bad field",
                "field": "invalid_field",
                "operator": "equals",
                "value": "test",
                "target_pipeline_id": p.id,
            },
        )
        assert r.status_code == 422

    def test_create_rule_invalid_operator(self, client, db_session):
        """POST with an invalid operator returns 422."""
        p = _make_pipeline(db_session, name="Target")
        r = client.post(
            "/api/routing-rules",
            json={
                "name": "Bad op",
                "field": "file_type",
                "operator": "invalid_op",
                "value": "test",
                "target_pipeline_id": p.id,
            },
        )
        assert r.status_code == 422

    def test_create_rule_missing_pipeline(self, client):
        """POST referencing a nonexistent pipeline returns 404."""
        r = client.post(
            "/api/routing-rules",
            json={
                "name": "No pipeline",
                "field": "file_type",
                "operator": "equals",
                "value": "application/pdf",
                "target_pipeline_id": 99999,
            },
        )
        assert r.status_code == 404

    def test_list_rules(self, client, db_session):
        """GET /api/routing-rules returns the user's rules."""
        p = _make_pipeline(db_session, name="Pipeline")
        _make_rule(db_session, p.id, name="Rule 1", position=0, owner_id="anonymous")
        _make_rule(db_session, p.id, name="Rule 2", position=1, owner_id="anonymous")

        r = client.get("/api/routing-rules")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 2
        names = [d["name"] for d in data]
        assert "Rule 1" in names
        assert "Rule 2" in names

    def test_get_rule(self, client, db_session):
        """GET /api/routing-rules/{id} returns a specific rule."""
        p = _make_pipeline(db_session, name="Pipeline")
        rule = _make_rule(db_session, p.id, name="My Rule", owner_id="anonymous")

        r = client.get(f"/api/routing-rules/{rule.id}")
        assert r.status_code == 200
        assert r.json()["name"] == "My Rule"

    def test_get_rule_not_found(self, client):
        """GET /api/routing-rules/{id} returns 404 for nonexistent rule."""
        r = client.get("/api/routing-rules/99999")
        assert r.status_code == 404

    def test_update_rule(self, client, db_session):
        """PUT /api/routing-rules/{id} updates a rule."""
        p = _make_pipeline(db_session, name="Pipeline")
        rule = _make_rule(db_session, p.id, name="Old Name", owner_id="anonymous")

        r = client.put(
            f"/api/routing-rules/{rule.id}",
            json={"name": "New Name", "operator": "contains"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "New Name"
        assert data["operator"] == "contains"

    def test_update_rule_invalid_field(self, client, db_session):
        """PUT with invalid field returns 422."""
        p = _make_pipeline(db_session, name="Pipeline")
        rule = _make_rule(db_session, p.id, owner_id="anonymous")

        r = client.put(f"/api/routing-rules/{rule.id}", json={"field": "bad_field"})
        assert r.status_code == 422

    def test_update_rule_invalid_operator(self, client, db_session):
        """PUT with invalid operator returns 422."""
        p = _make_pipeline(db_session, name="Pipeline")
        rule = _make_rule(db_session, p.id, owner_id="anonymous")

        r = client.put(f"/api/routing-rules/{rule.id}", json={"operator": "bad_op"})
        assert r.status_code == 422

    def test_update_rule_missing_pipeline(self, client, db_session):
        """PUT with nonexistent target pipeline returns 404."""
        p = _make_pipeline(db_session, name="Pipeline")
        rule = _make_rule(db_session, p.id, owner_id="anonymous")

        r = client.put(f"/api/routing-rules/{rule.id}", json={"target_pipeline_id": 99999})
        assert r.status_code == 404

    def test_delete_rule(self, client, db_session):
        """DELETE /api/routing-rules/{id} removes a rule."""
        p = _make_pipeline(db_session, name="Pipeline")
        rule = _make_rule(db_session, p.id, owner_id="anonymous")

        r = client.delete(f"/api/routing-rules/{rule.id}")
        assert r.status_code == 204

        # Verify it's gone
        r = client.get(f"/api/routing-rules/{rule.id}")
        assert r.status_code == 404

    def test_delete_rule_not_found(self, client):
        """DELETE for nonexistent rule returns 404."""
        r = client.delete("/api/routing-rules/99999")
        assert r.status_code == 404


# ===========================================================================
# API tests – reorder
# ===========================================================================


@pytest.mark.unit
class TestReorderRoutingRules:
    """Tests for the PUT /api/routing-rules/reorder endpoint."""

    def test_reorder_rules(self, client, db_session):
        """Reordering updates the position of rules."""
        p = _make_pipeline(db_session, name="Pipeline")
        r1 = _make_rule(db_session, p.id, name="A", position=0, owner_id="anonymous")
        r2 = _make_rule(db_session, p.id, name="B", position=1, owner_id="anonymous")

        r = client.put(
            "/api/routing-rules/reorder",
            json={"rule_ids": [r2.id, r1.id]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data[0]["id"] == r2.id
        assert data[0]["position"] == 0
        assert data[1]["id"] == r1.id
        assert data[1]["position"] == 1

    def test_reorder_invalid_ids(self, client, db_session):
        """Reorder with invalid IDs returns 422."""
        r = client.put(
            "/api/routing-rules/reorder",
            json={"rule_ids": [99999]},
        )
        assert r.status_code == 422


# ===========================================================================
# API tests – evaluate (dry-run)
# ===========================================================================


@pytest.mark.unit
class TestEvaluateEndpoint:
    """Tests for the POST /api/routing-rules/evaluate dry-run endpoint."""

    def test_evaluate_match(self, client, db_session):
        """Evaluate returns the matching rule and target pipeline."""
        p = _make_pipeline(db_session, name="Invoice Pipeline")
        _make_rule(
            db_session,
            p.id,
            name="PDF Route",
            field="file_type",
            operator="equals",
            value="application/pdf",
            owner_id="anonymous",
        )

        r = client.post(
            "/api/routing-rules/evaluate",
            json={"file_type": "application/pdf"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["matched"] is True
        assert data["rule"]["name"] == "PDF Route"
        assert data["target_pipeline"]["id"] == p.id

    def test_evaluate_no_match(self, client, db_session):
        """Evaluate returns matched=False when no rule applies."""
        p = _make_pipeline(db_session, name="Pipeline")
        _make_rule(
            db_session,
            p.id,
            name="PNG Route",
            field="file_type",
            operator="equals",
            value="image/png",
            owner_id="anonymous",
        )

        r = client.post(
            "/api/routing-rules/evaluate",
            json={"file_type": "application/pdf"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["matched"] is False
        assert data["rule"] is None

    def test_evaluate_with_metadata(self, client, db_session):
        """Evaluate with metadata.* fields works."""
        p = _make_pipeline(db_session, name="Invoice Pipeline")
        _make_rule(
            db_session,
            p.id,
            name="Invoice Route",
            field="metadata.sender",
            operator="contains",
            value="acme",
            owner_id="anonymous",
        )

        r = client.post(
            "/api/routing-rules/evaluate",
            json={"metadata": {"sender": "Acme Corporation"}},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["matched"] is True

    def test_evaluate_with_size(self, client, db_session):
        """Evaluate with size comparisons works."""
        p = _make_pipeline(db_session, name="Large Pipeline")
        _make_rule(
            db_session,
            p.id,
            name="Large Files",
            field="size",
            operator="gt",
            value="1000000",
            owner_id="anonymous",
        )

        r = client.post(
            "/api/routing-rules/evaluate",
            json={"size": 2000000},
        )
        assert r.status_code == 200
        assert r.json()["matched"] is True


# ===========================================================================
# API tests – metadata field validation
# ===========================================================================


@pytest.mark.unit
class TestFieldValidation:
    """Tests for field validation in routing rule creation."""

    def test_metadata_prefix_accepted(self, client, db_session):
        """Fields with 'metadata.' prefix are valid."""
        p = _make_pipeline(db_session, name="Pipeline")
        r = client.post(
            "/api/routing-rules",
            json={
                "name": "Metadata Rule",
                "field": "metadata.sender",
                "operator": "equals",
                "value": "test",
                "target_pipeline_id": p.id,
            },
        )
        assert r.status_code == 201

    def test_bare_metadata_rejected(self, client, db_session):
        """Just 'metadata.' without a key suffix is invalid."""
        p = _make_pipeline(db_session, name="Pipeline")
        r = client.post(
            "/api/routing-rules",
            json={
                "name": "Bad Metadata",
                "field": "metadata.",
                "operator": "equals",
                "value": "test",
                "target_pipeline_id": p.id,
            },
        )
        assert r.status_code == 422

    @pytest.mark.parametrize("field", sorted(BUILTIN_FIELDS))
    def test_builtin_fields_accepted(self, client, db_session, field):
        """All built-in fields are accepted."""
        p = _make_pipeline(db_session, name=f"Pipeline for {field}")
        r = client.post(
            "/api/routing-rules",
            json={
                "name": f"Rule for {field}",
                "field": field,
                "operator": "equals",
                "value": "test",
                "target_pipeline_id": p.id,
            },
        )
        assert r.status_code == 201


# ===========================================================================
# API tests – auto-position
# ===========================================================================


@pytest.mark.unit
class TestAutoPosition:
    """Tests for automatic position assignment."""

    def test_auto_position_increments(self, client, db_session):
        """Rules created without position get incrementing positions."""
        p = _make_pipeline(db_session, name="Pipeline")

        r1 = client.post(
            "/api/routing-rules",
            json={
                "name": "First",
                "field": "file_type",
                "operator": "equals",
                "value": "application/pdf",
                "target_pipeline_id": p.id,
            },
        )
        r2 = client.post(
            "/api/routing-rules",
            json={
                "name": "Second",
                "field": "file_type",
                "operator": "equals",
                "value": "image/png",
                "target_pipeline_id": p.id,
            },
        )
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r2.json()["position"] > r1.json()["position"]
