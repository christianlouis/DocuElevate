"""Tests for the classification rules API endpoints.

Covers CRUD operations, validation, and access control for
``/api/classification-rules``.
"""

import pytest

from app.models import ClassificationRuleModel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule(db_session, owner_id="anonymous", **overrides):
    """Insert a ClassificationRuleModel and return it."""
    defaults = {
        "owner_id": owner_id,
        "name": "test_rule",
        "category": "invoice",
        "rule_type": "filename_pattern",
        "pattern": r"(?i)invoice",
        "priority": 0,
        "case_sensitive": False,
        "enabled": True,
    }
    defaults.update(overrides)
    rule = ClassificationRuleModel(**defaults)
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)
    return rule


# ---------------------------------------------------------------------------
# Categories & Rule Types endpoints
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCategoriesEndpoint:
    """Tests for GET /api/classification-rules/categories."""

    def test_list_categories(self, client):
        """Should return a dict of built-in categories."""
        r = client.get("/api/classification-rules/categories")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert "invoice" in data
        assert "contract" in data
        assert "receipt" in data
        assert "unknown" in data


@pytest.mark.unit
class TestRuleTypesEndpoint:
    """Tests for GET /api/classification-rules/rule-types."""

    def test_list_rule_types(self, client):
        """Should return a list of valid rule types."""
        r = client.get("/api/classification-rules/rule-types")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 3
        type_values = {item["type"] for item in data}
        assert "filename_pattern" in type_values
        assert "content_keyword" in type_values
        assert "metadata_match" in type_values


# ---------------------------------------------------------------------------
# CRUD Operations
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestClassificationRuleCRUD:
    """Full CRUD test-suite for classification rules."""

    def test_list_rules_empty(self, client):
        """List returns an empty array when no rules exist."""
        r = client.get("/api/classification-rules/")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_rule(self, client):
        """POST should create a new classification rule."""
        r = client.post(
            "/api/classification-rules/",
            json={
                "name": "My Invoice Rule",
                "category": "invoice",
                "rule_type": "filename_pattern",
                "pattern": r"(?i)rechnung",
                "priority": 10,
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "My Invoice Rule"
        assert data["category"] == "invoice"
        assert data["rule_type"] == "filename_pattern"
        assert data["priority"] == 10
        assert data["enabled"] is True
        assert data["id"] is not None

    def test_create_rule_invalid_type_rejected(self, client):
        """Creating a rule with an invalid rule_type should be rejected."""
        r = client.post(
            "/api/classification-rules/",
            json={
                "name": "Bad Rule",
                "category": "test",
                "rule_type": "invalid_type",
                "pattern": "test",
            },
        )
        assert r.status_code == 400

    def test_create_duplicate_name_rejected(self, client):
        """Creating two rules with the same name should be rejected."""
        payload = {
            "name": "Dupe Rule",
            "category": "invoice",
            "rule_type": "filename_pattern",
            "pattern": "test",
        }
        r1 = client.post("/api/classification-rules/", json=payload)
        assert r1.status_code == 201
        r2 = client.post("/api/classification-rules/", json=payload)
        assert r2.status_code == 409

    def test_get_rule(self, client):
        """GET should return a specific rule by ID."""
        create_resp = client.post(
            "/api/classification-rules/",
            json={
                "name": "Get Test Rule",
                "category": "contract",
                "rule_type": "content_keyword",
                "pattern": "agreement|terms",
            },
        )
        rule_id = create_resp.json()["id"]

        r = client.get(f"/api/classification-rules/{rule_id}")
        assert r.status_code == 200
        assert r.json()["name"] == "Get Test Rule"
        assert r.json()["category"] == "contract"

    def test_get_nonexistent_rule(self, client):
        """GET for a nonexistent rule should return 404."""
        r = client.get("/api/classification-rules/99999")
        assert r.status_code == 404

    def test_update_rule(self, client):
        """PUT should update an existing rule."""
        create_resp = client.post(
            "/api/classification-rules/",
            json={
                "name": "Update Test",
                "category": "receipt",
                "rule_type": "filename_pattern",
                "pattern": "receipt",
            },
        )
        rule_id = create_resp.json()["id"]

        r = client.put(
            f"/api/classification-rules/{rule_id}",
            json={"category": "invoice", "priority": 50},
        )
        assert r.status_code == 200
        assert r.json()["category"] == "invoice"
        assert r.json()["priority"] == 50
        # Name should be unchanged
        assert r.json()["name"] == "Update Test"

    def test_update_nonexistent_rule(self, client):
        """PUT for a nonexistent rule should return 404."""
        r = client.put("/api/classification-rules/99999", json={"category": "test"})
        assert r.status_code == 404

    def test_update_invalid_rule_type_rejected(self, client):
        """PUT with an invalid rule_type should be rejected."""
        create_resp = client.post(
            "/api/classification-rules/",
            json={
                "name": "Invalid Update",
                "category": "test",
                "rule_type": "filename_pattern",
                "pattern": "test",
            },
        )
        rule_id = create_resp.json()["id"]

        r = client.put(
            f"/api/classification-rules/{rule_id}",
            json={"rule_type": "bad_type"},
        )
        assert r.status_code == 400

    def test_delete_rule(self, client):
        """DELETE should remove the rule."""
        create_resp = client.post(
            "/api/classification-rules/",
            json={
                "name": "Delete Test",
                "category": "test",
                "rule_type": "content_keyword",
                "pattern": "test",
            },
        )
        rule_id = create_resp.json()["id"]

        r = client.delete(f"/api/classification-rules/{rule_id}")
        assert r.status_code == 204

        # Verify it's gone
        r2 = client.get(f"/api/classification-rules/{rule_id}")
        assert r2.status_code == 404

    def test_delete_nonexistent_rule(self, client):
        """DELETE for a nonexistent rule should return 404."""
        r = client.delete("/api/classification-rules/99999")
        assert r.status_code == 404

    def test_list_rules_after_create(self, client):
        """List should return created rules."""
        client.post(
            "/api/classification-rules/",
            json={
                "name": "List Rule 1",
                "category": "invoice",
                "rule_type": "filename_pattern",
                "pattern": "test1",
            },
        )
        client.post(
            "/api/classification-rules/",
            json={
                "name": "List Rule 2",
                "category": "contract",
                "rule_type": "content_keyword",
                "pattern": "test2",
            },
        )
        r = client.get("/api/classification-rules/")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_create_rule_with_all_fields(self, client):
        """Create a rule providing all optional fields."""
        r = client.post(
            "/api/classification-rules/",
            json={
                "name": "Full Rule",
                "category": "tax_document",
                "rule_type": "metadata_match",
                "pattern": "department=finance",
                "priority": 100,
                "case_sensitive": True,
                "enabled": False,
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["case_sensitive"] is True
        assert data["enabled"] is False
        assert data["priority"] == 100

    def test_create_rule_defaults(self, client):
        """Create a rule with minimal fields to test defaults."""
        r = client.post(
            "/api/classification-rules/",
            json={
                "name": "Minimal Rule",
                "category": "invoice",
                "rule_type": "filename_pattern",
                "pattern": "test",
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["priority"] == 0
        assert data["case_sensitive"] is False
        assert data["enabled"] is True
