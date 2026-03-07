"""Tests for the pipelines API endpoints.

Covers CRUD operations for pipelines and steps, ownership/admin access control,
step reordering, and the assign-pipeline-to-file endpoint.
"""

import json
from unittest.mock import patch

import pytest

from app.models import FileRecord, Pipeline, PipelineStep

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_test_file_record(db_session, owner_id=None):
    """Insert a minimal FileRecord and return it.

    Default owner_id=None so tests work without an authenticated session.
    """
    fr = FileRecord(
        owner_id=owner_id,
        filehash="abc123",
        original_filename="test.pdf",
        local_filename="/tmp/test.pdf",
        file_size=1024,
        mime_type="application/pdf",
    )
    db_session.add(fr)
    db_session.commit()
    db_session.refresh(fr)
    return fr


# ---------------------------------------------------------------------------
# Unit tests – step-types catalogue
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStepTypesCatalogue:
    """Tests for the step-types read-only catalogue endpoint."""

    def test_step_types_returns_dict(self, client):
        """GET /api/pipelines/step-types returns a dict of known types."""
        r = client.get("/api/pipelines/step-types")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        # Core built-in types must be present
        for key in ("convert_to_pdf", "ocr", "extract_metadata", "embed_metadata", "compute_embedding"):
            assert key in data, f"Expected step type '{key}' in catalogue"

    def test_each_type_has_label_and_description(self, client):
        """Each step-type entry has at least a label and description."""
        r = client.get("/api/pipelines/step-types")
        for key, meta in r.json().items():
            assert "label" in meta, f"Step type '{key}' missing 'label'"
            assert "description" in meta, f"Step type '{key}' missing 'description'"


# ---------------------------------------------------------------------------
# Integration tests – Pipeline CRUD
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPipelineCRUD:
    """Full CRUD test-suite for pipeline management."""

    def test_list_pipelines_empty(self, client):
        """List returns an empty array when no pipelines exist."""
        r = client.get("/api/pipelines")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_pipeline(self, client):
        """POST /api/pipelines creates a new pipeline."""
        r = client.post(
            "/api/pipelines",
            json={"name": "My Pipeline", "description": "Test description"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "My Pipeline"
        assert data["description"] == "Test description"
        assert data["is_default"] is False
        assert data["is_active"] is True
        assert data["id"] is not None

    def test_create_pipeline_duplicate_name_same_owner_rejected(self, client):
        """Creating two pipelines with the same name is rejected with 409."""
        client.post("/api/pipelines", json={"name": "Dupe"})
        r = client.post("/api/pipelines", json={"name": "Dupe"})
        assert r.status_code == 409

    def test_create_pipeline_empty_name_rejected(self, client):
        """An empty pipeline name returns 422."""
        r = client.post("/api/pipelines", json={"name": "   "})
        assert r.status_code == 422

    def test_get_pipeline_includes_steps(self, client):
        """GET /api/pipelines/{id} returns the pipeline with a steps array."""
        created = client.post("/api/pipelines", json={"name": "With Steps"}).json()
        r = client.get(f"/api/pipelines/{created['id']}")
        assert r.status_code == 200
        assert "steps" in r.json()
        assert r.json()["steps"] == []

    def test_get_pipeline_not_found(self, client):
        """GET on a non-existent pipeline returns 404."""
        r = client.get("/api/pipelines/99999")
        assert r.status_code == 404

    def test_update_pipeline(self, client):
        """PUT /api/pipelines/{id} updates name and description."""
        created = client.post("/api/pipelines", json={"name": "Original"}).json()
        r = client.put(
            f"/api/pipelines/{created['id']}",
            json={"name": "Renamed", "description": "New desc"},
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"
        assert r.json()["description"] == "New desc"

    def test_update_pipeline_empty_name_rejected(self, client):
        """Updating a pipeline with an empty name returns 422."""
        created = client.post("/api/pipelines", json={"name": "Good"}).json()
        r = client.put(f"/api/pipelines/{created['id']}", json={"name": ""})
        assert r.status_code == 422

    def test_update_pipeline_name_conflict_rejected(self, client):
        """Updating a pipeline's name to one already taken returns 409."""
        client.post("/api/pipelines", json={"name": "Taken"})
        second = client.post("/api/pipelines", json={"name": "Other"}).json()
        r = client.put(f"/api/pipelines/{second['id']}", json={"name": "Taken"})
        assert r.status_code == 409

    def test_delete_pipeline(self, client):
        """DELETE /api/pipelines/{id} removes the pipeline."""
        created = client.post("/api/pipelines", json={"name": "Deletable"}).json()
        r = client.delete(f"/api/pipelines/{created['id']}")
        assert r.status_code == 204
        assert client.get(f"/api/pipelines/{created['id']}").status_code == 404

    def test_delete_pipeline_not_found(self, client):
        """Deleting a non-existent pipeline returns 404."""
        r = client.delete("/api/pipelines/99999")
        assert r.status_code == 404

    def test_is_default_flag(self, client):
        """Setting is_default=True marks the pipeline as default."""
        r = client.post("/api/pipelines", json={"name": "Default Pipeline", "is_default": True})
        assert r.status_code == 201
        assert r.json()["is_default"] is True

    def test_only_one_default_per_owner(self, client):
        """When a new default is set, the old one is cleared."""
        first = client.post("/api/pipelines", json={"name": "First Default", "is_default": True}).json()
        second = client.post("/api/pipelines", json={"name": "Second Default", "is_default": True}).json()

        assert second["is_default"] is True
        # The first should no longer be default
        first_updated = client.get(f"/api/pipelines/{first['id']}").json()
        assert first_updated["is_default"] is False

    def test_list_returns_created_pipeline(self, client):
        """After creating a pipeline it appears in the list."""
        client.post("/api/pipelines", json={"name": "Visible"})
        r = client.get("/api/pipelines")
        names = [p["name"] for p in r.json()]
        assert "Visible" in names


# ---------------------------------------------------------------------------
# Integration tests – Step management
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPipelineStepManagement:
    """Tests for adding, updating, deleting, and reordering pipeline steps."""

    def _create_pipeline(self, client, name="Test Pipeline"):
        return client.post("/api/pipelines", json={"name": name}).json()

    def test_add_step(self, client):
        """POST /api/pipelines/{id}/steps adds a step."""
        p = self._create_pipeline(client)
        r = client.post(f"/api/pipelines/{p['id']}/steps", json={"step_type": "ocr"})
        assert r.status_code == 201
        step = r.json()
        assert step["step_type"] == "ocr"
        assert step["position"] == 0
        assert step["enabled"] is True

    def test_add_step_with_config(self, client):
        """A step can be added with a custom config dict."""
        p = self._create_pipeline(client)
        r = client.post(
            f"/api/pipelines/{p['id']}/steps",
            json={"step_type": "ocr", "config": {"force_cloud_ocr": True}},
        )
        assert r.status_code == 201
        assert r.json()["config"]["force_cloud_ocr"] is True

    def test_add_step_with_custom_label(self, client):
        """A step can override the default label."""
        p = self._create_pipeline(client)
        r = client.post(
            f"/api/pipelines/{p['id']}/steps",
            json={"step_type": "convert_to_pdf", "label": "My Converter"},
        )
        assert r.status_code == 201
        assert r.json()["label"] == "My Converter"

    def test_add_invalid_step_type_rejected(self, client):
        """An unrecognised step type returns 422."""
        p = self._create_pipeline(client)
        r = client.post(f"/api/pipelines/{p['id']}/steps", json={"step_type": "nonexistent_step"})
        assert r.status_code == 422

    def test_steps_appended_in_order(self, client):
        """Multiple steps are appended in position order."""
        p = self._create_pipeline(client)
        client.post(f"/api/pipelines/{p['id']}/steps", json={"step_type": "convert_to_pdf"})
        client.post(f"/api/pipelines/{p['id']}/steps", json={"step_type": "ocr"})
        client.post(f"/api/pipelines/{p['id']}/steps", json={"step_type": "extract_metadata"})

        details = client.get(f"/api/pipelines/{p['id']}").json()
        types = [s["step_type"] for s in details["steps"]]
        assert types == ["convert_to_pdf", "ocr", "extract_metadata"]

    def test_update_step(self, client):
        """PUT /api/pipelines/{id}/steps/{step_id} updates enabled flag."""
        p = self._create_pipeline(client)
        step = client.post(f"/api/pipelines/{p['id']}/steps", json={"step_type": "ocr"}).json()

        r = client.put(
            f"/api/pipelines/{p['id']}/steps/{step['id']}",
            json={"enabled": False},
        )
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    def test_update_step_not_found(self, client):
        """Updating a step on the wrong pipeline returns 404."""
        p = self._create_pipeline(client)
        r = client.put(f"/api/pipelines/{p['id']}/steps/99999", json={"enabled": False})
        assert r.status_code == 404

    def test_delete_step(self, client):
        """DELETE /api/pipelines/{id}/steps/{step_id} removes the step."""
        p = self._create_pipeline(client)
        step = client.post(f"/api/pipelines/{p['id']}/steps", json={"step_type": "ocr"}).json()

        r = client.delete(f"/api/pipelines/{p['id']}/steps/{step['id']}")
        assert r.status_code == 204

        details = client.get(f"/api/pipelines/{p['id']}").json()
        assert details["steps"] == []

    def test_delete_step_compacts_positions(self, client):
        """After deleting a step, remaining steps have contiguous positions."""
        p = self._create_pipeline(client)
        s1 = client.post(f"/api/pipelines/{p['id']}/steps", json={"step_type": "convert_to_pdf"}).json()
        client.post(f"/api/pipelines/{p['id']}/steps", json={"step_type": "ocr"})
        client.post(f"/api/pipelines/{p['id']}/steps", json={"step_type": "extract_metadata"})

        client.delete(f"/api/pipelines/{p['id']}/steps/{s1['id']}")

        details = client.get(f"/api/pipelines/{p['id']}").json()
        positions = [s["position"] for s in details["steps"]]
        assert positions == sorted(positions)
        assert positions[0] == 0

    def test_reorder_steps(self, client):
        """PUT /api/pipelines/{id}/steps/reorder reorders all steps."""
        p = self._create_pipeline(client)
        s1 = client.post(f"/api/pipelines/{p['id']}/steps", json={"step_type": "convert_to_pdf"}).json()
        s2 = client.post(f"/api/pipelines/{p['id']}/steps", json={"step_type": "ocr"}).json()
        s3 = client.post(f"/api/pipelines/{p['id']}/steps", json={"step_type": "extract_metadata"}).json()

        # Reverse order
        r = client.put(
            f"/api/pipelines/{p['id']}/steps/reorder",
            json=[s3["id"], s2["id"], s1["id"]],
        )
        assert r.status_code == 200
        types = [s["step_type"] for s in r.json()]
        assert types == ["extract_metadata", "ocr", "convert_to_pdf"]

    def test_reorder_steps_invalid_ids_rejected(self, client):
        """Providing wrong step IDs returns 422."""
        p = self._create_pipeline(client)
        client.post(f"/api/pipelines/{p['id']}/steps", json={"step_type": "ocr"})

        r = client.put(f"/api/pipelines/{p['id']}/steps/reorder", json=[99999])
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Integration tests – System pipeline (admin endpoint)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSystemPipeline:
    """Tests for the admin system-pipeline creation endpoint."""

    def test_create_system_pipeline_as_admin(self, client):
        """An admin can create a system pipeline (owner_id=NULL)."""
        with patch("app.api.pipelines._is_admin", return_value=True):
            r = client.post(
                "/api/pipelines/admin/system",
                json={"name": "Global Default", "is_default": True},
            )
        assert r.status_code == 201
        data = r.json()
        assert data["owner_id"] is None
        assert data["is_default"] is True

    def test_create_system_pipeline_as_non_admin_forbidden(self, client):
        """A non-admin user cannot create a system pipeline."""
        r = client.post(
            "/api/pipelines/admin/system",
            json={"name": "Should Fail"},
        )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Integration tests – File pipeline assignment
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAssignPipelineToFile:
    """Tests for POST /api/files/{id}/assign-pipeline."""

    def test_assign_pipeline_to_file(self, client, db_session):
        """Assigning a pipeline to a file stores pipeline_id on the record."""
        # File with no owner so anonymous test session can access it
        fr = _make_test_file_record(db_session, owner_id=None)
        pipeline = client.post("/api/pipelines", json={"name": "Assign Test"}).json()

        r = client.post(f"/api/files/{fr.id}/assign-pipeline?pipeline_id={pipeline['id']}")
        assert r.status_code == 200
        data = r.json()
        assert data["file_id"] == fr.id
        assert data["pipeline_id"] == pipeline["id"]

        db_session.refresh(fr)
        assert fr.pipeline_id == pipeline["id"]

    def test_clear_pipeline_from_file(self, client, db_session):
        """Passing no pipeline_id clears the assignment."""
        fr = _make_test_file_record(db_session, owner_id=None)
        pipeline = client.post("/api/pipelines", json={"name": "Clearable"}).json()
        client.post(f"/api/files/{fr.id}/assign-pipeline?pipeline_id={pipeline['id']}")

        r = client.post(f"/api/files/{fr.id}/assign-pipeline")
        assert r.status_code == 200
        assert r.json()["pipeline_id"] is None

    def test_assign_nonexistent_pipeline_returns_404(self, client, db_session):
        """Assigning a non-existent pipeline returns 404."""
        fr = _make_test_file_record(db_session, owner_id=None)
        r = client.post(f"/api/files/{fr.id}/assign-pipeline?pipeline_id=99999")
        assert r.status_code == 404

    def test_assign_pipeline_to_nonexistent_file_returns_404(self, client):
        """Assigning a pipeline to a non-existent file returns 404."""
        r = client.post("/api/files/99999/assign-pipeline?pipeline_id=1")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Unit tests – API helper logic
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPipelineAPIHelpers:
    """Unit tests for API helper functions (no DB required)."""

    def test_serialize_step_returns_expected_keys(self, db_session):
        """_serialize_step returns all required fields."""
        from app.api.pipelines import _serialize_step

        # Build a minimal in-memory step
        p = Pipeline(owner_id="u1", name="P", is_default=False, is_active=True)
        db_session.add(p)
        db_session.commit()

        s = PipelineStep(
            pipeline_id=p.id,
            position=0,
            step_type="ocr",
            label="OCR",
            config=json.dumps({"force_cloud_ocr": False}),
            enabled=True,
        )
        db_session.add(s)
        db_session.commit()

        result = _serialize_step(s)
        for key in ("id", "pipeline_id", "position", "step_type", "label", "config", "enabled"):
            assert key in result, f"Missing key '{key}' in serialized step"
        assert result["config"] == {"force_cloud_ocr": False}

    def test_serialize_pipeline_returns_expected_keys(self, db_session):
        """_serialize_pipeline returns all required fields."""
        from app.api.pipelines import _serialize_pipeline

        p = Pipeline(owner_id="u1", name="MyPipeline", is_default=True, is_active=True)
        db_session.add(p)
        db_session.commit()

        result = _serialize_pipeline(p)
        for key in ("id", "owner_id", "name", "description", "is_default", "is_active"):
            assert key in result, f"Missing key '{key}' in serialized pipeline"

    def test_can_access_system_pipeline(self):
        """Anyone can read a system pipeline (owner_id=None)."""
        from app.api.pipelines import _can_access_pipeline

        p = Pipeline(owner_id=None, name="System", is_default=False, is_active=True)
        assert _can_access_pipeline(p, "any_user", admin=False) is True

    def test_cannot_write_system_pipeline_as_regular_user(self):
        """Regular users cannot modify system pipelines."""
        from app.api.pipelines import _can_write_pipeline

        p = Pipeline(owner_id=None, name="System", is_default=False, is_active=True)
        assert _can_write_pipeline(p, "regular_user", admin=False) is False

    def test_admin_can_write_system_pipeline(self):
        """Admins can modify system pipelines."""
        from app.api.pipelines import _can_write_pipeline

        p = Pipeline(owner_id=None, name="System", is_default=False, is_active=True)
        assert _can_write_pipeline(p, "admin", admin=True) is True

    def test_user_can_access_own_pipeline(self):
        """A user can access pipelines they own."""
        from app.api.pipelines import _can_access_pipeline

        p = Pipeline(owner_id="user1", name="Mine", is_default=False, is_active=True)
        assert _can_access_pipeline(p, "user1", admin=False) is True

    def test_user_cannot_access_other_users_pipeline(self):
        """A regular user cannot access another user's pipeline."""
        from app.api.pipelines import _can_access_pipeline

        p = Pipeline(owner_id="user1", name="Theirs", is_default=False, is_active=True)
        assert _can_access_pipeline(p, "user2", admin=False) is False

    def test_admin_can_access_any_pipeline(self):
        """Admins can access any pipeline regardless of owner."""
        from app.api.pipelines import _can_access_pipeline

        p = Pipeline(owner_id="user99", name="Private", is_default=False, is_active=True)
        assert _can_access_pipeline(p, "admin", admin=True) is True
