"""Tests for the pipelines API endpoints.

Covers CRUD operations for pipelines and steps, ownership/admin access control,
step reordering, and the assign-pipeline-to-file endpoint.
"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

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

    def test_step_types_declare_runtime_effect(self, client):
        """Step-type metadata identifies what currently affects processing."""
        r = client.get("/api/pipelines/step-types")
        data = r.json()

        assert data["ocr"]["runtime_effect"] == "applied_config"
        assert data["ocr"]["runtime_effect_description"]

        metadata_only = set(data) - {"ocr"}
        for key in metadata_only:
            assert data[key]["runtime_effect"] == "metadata_only"
            assert data[key]["runtime_effect_description"]

    def test_force_ocr_copy_does_not_overpromise_cloud_provider(self, client):
        """force_cloud_ocr copy describes forced OCR behavior, not only cloud providers."""
        r = client.get("/api/pipelines/step-types")
        description = r.json()["ocr"]["config_schema"]["force_cloud_ocr"]["description"]

        assert "run OCR processing" in description
        assert "cloud OCR" not in description

    def test_processing_profile_translation_keys_exist(self):
        """New processing-profile UI copy is routed through translation keys."""
        import json
        from pathlib import Path

        root = Path(__file__).parents[1]
        translations = json.loads((root / "frontend" / "translations" / "en.json").read_text())
        template = (root / "frontend" / "templates" / "pipelines.html").read_text()

        expected_keys = [
            "pipelines.add_profile_setting_btn",
            "pipelines.add_profile_setting_title",
            "pipelines.add_setting",
            "pipelines.applied_at_runtime",
            "pipelines.collapse_settings_aria",
            "pipelines.disabled_profile_metadata",
            "pipelines.disabled_runtime_config",
            "pipelines.edit_profile_setting_title",
            "pipelines.expand_settings_aria",
            "pipelines.force_cloud_ocr_label",
            "pipelines.profile_contract_body",
            "pipelines.profile_contract_inline",
            "pipelines.profile_contract_title",
            "pipelines.profile_metadata",
            "pipelines.create_preset_aria",
            "pipelines.preset_created_message",
            "pipelines.preset_created_title",
            "pipelines.preset_failed_default",
            "pipelines.preset_failed_title",
            "pipelines.preset_steps",
            "pipelines.presets_hint",
            "pipelines.presets_title",
            "pipelines.routing_document_type",
            "pipelines.routing_document_type_placeholder",
            "pipelines.routing_file_type",
            "pipelines.routing_file_type_placeholder",
            "pipelines.routing_filename",
            "pipelines.routing_filename_placeholder",
            "pipelines.routing_matched",
            "pipelines.routing_metadata",
            "pipelines.routing_metadata_error",
            "pipelines.routing_metadata_placeholder",
            "pipelines.routing_missing_target",
            "pipelines.routing_no_match",
            "pipelines.routing_size",
            "pipelines.routing_size_placeholder",
            "pipelines.routing_test_btn",
            "pipelines.routing_test_hint",
            "pipelines.routing_test_title",
            "pipelines.save_changes",
            "pipelines.setting_plural",
            "pipelines.setting_singular",
            "pipelines.step_modal_contract",
            "pipelines.use_preset",
        ]
        for key in expected_keys:
            assert key in translations, f"Missing translation key: {key}"

        assert "Current profile contract" not in template
        assert "metadata disabled" not in template
        assert 'placeholder="invoice_2026.pdf"' not in template
        assert 'role="alert"' in template
        preset_button = template.split(':aria-label="i18n.createPreset', 1)[0].rsplit("<button", 1)[1]
        assert "min-h-[44px]" in preset_button
        assert "style=" not in preset_button
        assert "this.i18n.presetCreatedTitle" in template
        assert "this.i18n.presetFailedTitle" in template

    def test_pipeline_page_batch_loads_profile_details(self):
        """The pipeline UI asks the list endpoint for steps in one request."""
        from pathlib import Path

        root = Path(__file__).parents[1]
        template = (root / "frontend" / "templates" / "pipelines.html").read_text()

        assert "fetch('/api/pipelines?include_steps=true')" in template
        assert "Promise.all(list.map(p => this.fetchPipeline(p.id)))" not in template

    def test_pipeline_page_exposes_routing_dry_run(self):
        """The pipeline UI can dry-run routing rules from the profiles page."""
        from pathlib import Path

        root = Path(__file__).parents[1]
        template = (root / "frontend" / "templates" / "pipelines.html").read_text()

        assert "evaluateRoutingRules()" in template
        assert "fetch('/api/routing-rules/evaluate'" in template
        assert "pipelines.routing_test_title" in template


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

    def test_list_pipelines_can_include_steps(self, client):
        """GET /api/pipelines?include_steps=true batch-loads ordered steps."""
        pipeline = client.post("/api/pipelines", json={"name": "Batch Details"}).json()
        client.post(f"/api/pipelines/{pipeline['id']}/steps", json={"step_type": "convert_to_pdf"})
        client.post(f"/api/pipelines/{pipeline['id']}/steps", json={"step_type": "ocr"})

        r = client.get("/api/pipelines?include_steps=true")

        assert r.status_code == 200
        batch_pipeline = next(p for p in r.json() if p["id"] == pipeline["id"])
        assert [step["step_type"] for step in batch_pipeline["steps"]] == ["convert_to_pdf", "ocr"]

    def test_list_pipelines_omits_steps_by_default(self, client):
        """The default list response stays lightweight for API callers."""
        pipeline = client.post("/api/pipelines", json={"name": "Lightweight"}).json()
        client.post(f"/api/pipelines/{pipeline['id']}/steps", json={"step_type": "ocr"})

        r = client.get("/api/pipelines")

        assert r.status_code == 200
        batch_pipeline = next(p for p in r.json() if p["id"] == pipeline["id"])
        assert "steps" not in batch_pipeline

    def test_list_pipeline_presets_returns_guided_options(self, client):
        """GET /api/pipelines/presets exposes built-in guided profile presets."""
        r = client.get("/api/pipelines/presets")

        assert r.status_code == 200
        presets = r.json()
        preset_keys = {preset["key"] for preset in presets}
        assert {"standard_document", "scan_ocr_only", "invoice_intake"}.issubset(preset_keys)
        for preset in presets:
            assert preset["name"]
            assert preset["description"]
            assert preset["steps"]

    def test_create_pipeline_from_preset(self, client):
        """POST /api/pipelines/presets/{key} creates a profile with preset steps."""
        r = client.post("/api/pipelines/presets/scan_ocr_only", json={})

        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Scan and OCR only"
        assert data["description"] == "Run OCR-focused processing without delivery or AI metadata planning steps."
        assert [step["step_type"] for step in data["steps"]] == ["ocr"]
        assert data["steps"][0]["label"] == "OCR scanned document"
        assert data["steps"][0]["config"]["force_cloud_ocr"] is True
        assert data["steps"][0]["config"]["ocr_language"] == "auto"

    def test_create_pipeline_from_preset_accepts_custom_name_and_default(self, client):
        """Preset creation can customize the name and make the new profile default."""
        existing = client.post("/api/pipelines", json={"name": "Existing Default", "is_default": True}).json()

        r = client.post(
            "/api/pipelines/presets/privacy_local_ocr",
            json={"name": "Local OCR", "description": "Internal only", "is_default": True},
        )

        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Local OCR"
        assert data["description"] == "Internal only"
        assert data["is_default"] is True
        assert client.get(f"/api/pipelines/{existing['id']}").json()["is_default"] is False

    def test_create_pipeline_from_unknown_preset_returns_404(self, client):
        """Unknown preset keys are rejected."""
        r = client.post("/api/pipelines/presets/not-a-preset", json={})

        assert r.status_code == 404

    def test_create_pipeline_from_preset_duplicate_name_rejected(self, client):
        """Preset creation keeps the same per-owner unique-name guard as manual creation."""
        first = client.post("/api/pipelines/presets/invoice_intake", json={})
        second = client.post("/api/pipelines/presets/invoice_intake", json={})

        assert first.status_code == 201
        assert second.status_code == 409

    def test_create_pipeline_from_preset_rejects_blank_custom_name(self, client):
        """Whitespace-only preset name overrides are invalid instead of falling back."""
        r = client.post("/api/pipelines/presets/scan_ocr_only", json={"name": "   "})

        assert r.status_code == 422
        assert r.json()["detail"] == "name is required"

    def test_pipeline_name_unique_per_owner_database_guard(self, db_session):
        """The database also rejects duplicate pipeline names for the same owner."""
        db_session.add_all(
            [
                Pipeline(owner_id="owner-a", name="Invoices"),
                Pipeline(owner_id="owner-a", name="Invoices"),
            ]
        )

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_create_pipeline_from_preset_logs_without_owner_identifier(self, client):
        """Preset creation logs operational context without owner/user identifiers."""
        with patch("app.api.pipelines.logger") as mock_logger:
            r = client.post("/api/pipelines/presets/no_external_delivery", json={})

        assert r.status_code == 201
        mock_logger.info.assert_called_once_with(
            "Pipeline created from preset: id=%s, preset=%s",
            r.json()["id"],
            "no_external_delivery",
        )

    def test_create_pipeline_from_preset_rolls_back_without_logging_owner_identifier(self, client, db_session):
        """Preset creation rollback logs the preset key but not the session owner."""
        with (
            patch.object(db_session, "commit", side_effect=RuntimeError("database unavailable")),
            patch.object(db_session, "rollback", wraps=db_session.rollback) as mock_rollback,
            patch("app.api.pipelines.logger") as mock_logger,
        ):
            r = client.post("/api/pipelines/presets/no_external_delivery", json={})

        assert r.status_code == 500
        assert r.json()["detail"] == "Failed to create pipeline from preset"
        mock_rollback.assert_called_once()
        mock_logger.exception.assert_called_once_with(
            "Failed to create pipeline from preset=%s",
            "no_external_delivery",
        )

    def test_list_pipeline_templates_returns_versioned_starter_kits(self, client):
        """GET /api/pipelines/templates exposes first-class starter templates."""
        r = client.get("/api/pipelines/templates")

        assert r.status_code == 200
        templates = r.json()
        assert len(templates) >= 5
        categories = {template["category"] for template in templates}
        assert {"contracts", "invoices", "receipts", "research", "standard"}.issubset(categories)
        for template in templates:
            assert template["format_version"] == "1.0"
            assert template["compatibility"]["min_app_version"]
            assert isinstance(template["compatibility"]["required_providers"], list)
            assert template["steps"]

    def test_get_pipeline_template_returns_one_template(self, client):
        """GET /api/pipelines/templates/{key} returns one built-in starter kit."""
        r = client.get("/api/pipelines/templates/invoice_intake_pack")

        assert r.status_code == 200
        data = r.json()
        assert data["key"] == "invoice_intake_pack"
        assert data["category"] == "invoices"
        assert [step["step_type"] for step in data["steps"]][:2] == ["ocr", "classify"]

    def test_validate_pipeline_template_accepts_portable_json(self, client):
        """Templates can be validated without creating a pipeline."""
        template = client.get("/api/pipelines/templates/receipt_capture_pack").json()

        r = client.post("/api/pipelines/templates/validate", json={"template": template})

        assert r.status_code == 200
        assert r.json()["valid"] is True
        assert r.json()["template"]["key"] == "receipt_capture_pack"

    def test_validate_pipeline_template_rejects_unknown_steps(self, client):
        """Validation rejects templates that reference unsupported step types."""
        template = client.get("/api/pipelines/templates/receipt_capture_pack").json()
        template["steps"][0]["step_type"] = "unknown_external_step"

        r = client.post("/api/pipelines/templates/validate", json={"template": template})

        assert r.status_code == 422
        assert "unknown step_type" in r.json()["detail"]

    def test_import_pipeline_template_creates_profile_with_steps(self, client):
        """POST /api/pipelines/templates/import creates a user pipeline from a template."""
        template = client.get("/api/pipelines/templates/contract_review_pack").json()

        r = client.post(
            "/api/pipelines/templates/import",
            json={"template": template, "name": "Contract Ops", "is_default": True},
        )

        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Contract Ops"
        assert data["is_default"] is True
        assert data["description"] == template["description"]
        assert [step["step_type"] for step in data["steps"]] == [
            "ocr",
            "classify",
            "extract_metadata",
            "embed_metadata",
            "compute_embedding",
        ]

    def test_import_pipeline_template_duplicate_name_rejected(self, client):
        """Template imports keep the per-owner unique-name guard."""
        template = client.get("/api/pipelines/templates/research_archive_pack").json()

        first = client.post("/api/pipelines/templates/import", json={"template": template})
        second = client.post("/api/pipelines/templates/import", json={"template": template})

        assert first.status_code == 201
        assert second.status_code == 409

    def test_export_pipeline_as_template(self, client):
        """An existing pipeline can be exported as a versioned template document."""
        pipeline = client.post(
            "/api/pipelines",
            json={"name": "Export Me", "description": "Reusable profile"},
        ).json()
        client.post(
            f"/api/pipelines/{pipeline['id']}/steps",
            json={"step_type": "ocr", "label": "OCR export", "config": {"ocr_language": "eng"}},
        )

        r = client.get(f"/api/pipelines/{pipeline['id']}/template?category=research")

        assert r.status_code == 200
        template = r.json()
        assert template["format_version"] == "1.0"
        assert template["key"] == f"pipeline-{pipeline['id']}"
        assert template["category"] == "research"
        assert template["steps"][0]["step_type"] == "ocr"
        assert template["steps"][0]["config"]["ocr_language"] == "eng"

    def test_builtin_templates_have_documented_samples(self):
        """Each shipped workflow template has docs and sample metadata."""
        from pathlib import Path

        from app.pipeline_templates import BUILT_IN_PIPELINE_TEMPLATES

        root = Path(__file__).parents[1]
        docs_dir = root / "docs" / "templates"
        readme = (docs_dir / "README.md").read_text()
        sample_files = {
            "standard_document_archive": "standard-document.sample.json",
            "invoice_intake_pack": "invoice.sample.json",
            "contract_review_pack": "contract.sample.json",
            "receipt_capture_pack": "receipt.sample.json",
            "research_archive_pack": "research.sample.json",
        }

        assert set(sample_files) == set(BUILT_IN_PIPELINE_TEMPLATES)
        for template_key, sample_file in sample_files.items():
            assert template_key in readme
            assert sample_file in readme
            sample = json.loads((docs_dir / sample_file).read_text())
            assert sample["filename"]
            assert sample["file_type"]
            assert sample["document_type"]
            assert isinstance(sample["metadata"], dict)

        for example_file in ("email-forwarding.example.json", "webhook-receiver.example.json"):
            assert example_file in readme
            example = json.loads((docs_dir / example_file).read_text())
            assert example["integration"]


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
        assert fr.pipeline_assignment_source == "manual"
        assert fr.pipeline_routing_rule_id is None
        assert "manually assigned" in fr.pipeline_assignment_reason

    def test_clear_pipeline_from_file(self, client, db_session):
        """Passing no pipeline_id clears the assignment."""
        fr = _make_test_file_record(db_session, owner_id=None)
        pipeline = client.post("/api/pipelines", json={"name": "Clearable"}).json()
        client.post(f"/api/files/{fr.id}/assign-pipeline?pipeline_id={pipeline['id']}")

        r = client.post(f"/api/files/{fr.id}/assign-pipeline")
        assert r.status_code == 200
        assert r.json()["pipeline_id"] is None

        db_session.refresh(fr)
        assert fr.pipeline_assignment_source == "default"
        assert fr.pipeline_routing_rule_id is None
        assert "Manual assignment cleared" in fr.pipeline_assignment_reason

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


# ---------------------------------------------------------------------------
# Unit + integration tests – seed_default_pipeline
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSeedDefaultPipeline:
    """Tests for the seed_default_pipeline startup helper."""

    def test_seed_creates_pipeline(self, db_session):
        """seed_default_pipeline creates exactly one system pipeline."""
        from app.api.pipelines import seed_default_pipeline

        result = seed_default_pipeline(db_session)

        assert result == 1
        pipelines = db_session.query(Pipeline).filter(Pipeline.owner_id.is_(None)).all()
        assert len(pipelines) == 1

    def test_seeded_pipeline_is_default(self, db_session):
        """The seeded pipeline has is_default=True and is_active=True."""
        from app.api.pipelines import seed_default_pipeline

        seed_default_pipeline(db_session)
        p = db_session.query(Pipeline).filter(Pipeline.owner_id.is_(None)).first()

        assert p is not None
        assert p.is_default is True
        assert p.is_active is True

    def test_seeded_pipeline_has_correct_name(self, db_session):
        """The seeded pipeline uses the canonical DEFAULT_PIPELINE_NAME."""
        from app.api.pipelines import DEFAULT_PIPELINE_NAME, seed_default_pipeline

        seed_default_pipeline(db_session)
        p = db_session.query(Pipeline).filter(Pipeline.owner_id.is_(None)).first()

        assert p.name == DEFAULT_PIPELINE_NAME

    def test_seeded_pipeline_steps_count(self, db_session):
        """The seeded pipeline has the correct number of steps."""
        from app.api.pipelines import _DEFAULT_PIPELINE_STEPS, seed_default_pipeline

        seed_default_pipeline(db_session)
        p = db_session.query(Pipeline).filter(Pipeline.owner_id.is_(None)).first()
        steps = db_session.query(PipelineStep).filter(PipelineStep.pipeline_id == p.id).all()

        assert len(steps) == len(_DEFAULT_PIPELINE_STEPS)

    def test_seeded_pipeline_step_types_and_order(self, db_session):
        """Steps are in the correct order and match the expected step types."""
        from app.api.pipelines import _DEFAULT_PIPELINE_STEPS, seed_default_pipeline

        seed_default_pipeline(db_session)
        p = db_session.query(Pipeline).filter(Pipeline.owner_id.is_(None)).first()
        steps = (
            db_session.query(PipelineStep)
            .filter(PipelineStep.pipeline_id == p.id)
            .order_by(PipelineStep.position)
            .all()
        )

        expected_types = [step_type for step_type, _ in _DEFAULT_PIPELINE_STEPS]
        actual_types = [s.step_type for s in steps]
        assert actual_types == expected_types

    def test_seeded_pipeline_all_steps_enabled(self, db_session):
        """All seeded steps are enabled by default."""
        from app.api.pipelines import seed_default_pipeline

        seed_default_pipeline(db_session)
        p = db_session.query(Pipeline).filter(Pipeline.owner_id.is_(None)).first()
        steps = db_session.query(PipelineStep).filter(PipelineStep.pipeline_id == p.id).all()

        assert all(s.enabled for s in steps), "All seeded steps should be enabled"

    def test_seed_is_idempotent(self, db_session):
        """Calling seed_default_pipeline twice does not create a duplicate."""
        from app.api.pipelines import seed_default_pipeline

        first = seed_default_pipeline(db_session)
        second = seed_default_pipeline(db_session)

        assert first == 1
        assert second == 0  # No-op on second call

        count = db_session.query(Pipeline).filter(Pipeline.owner_id.is_(None)).count()
        assert count == 1

    def test_seeded_pipeline_visible_via_api(self, client):
        """The default pipeline is visible in the GET /api/pipelines listing."""
        from app.api.pipelines import DEFAULT_PIPELINE_NAME, seed_default_pipeline
        from app.database import get_db

        # Seed using the same DB session that the test client uses
        db = next(client.app.dependency_overrides[get_db]())
        seed_default_pipeline(db)

        r = client.get("/api/pipelines")
        assert r.status_code == 200
        names = [p["name"] for p in r.json()]
        assert DEFAULT_PIPELINE_NAME in names

    def test_seeded_pipeline_default_flag_visible_via_api(self, client):
        """The seeded pipeline is returned with is_default=True via the API."""
        from app.api.pipelines import DEFAULT_PIPELINE_NAME, seed_default_pipeline
        from app.database import get_db

        db = next(client.app.dependency_overrides[get_db]())
        seed_default_pipeline(db)

        r = client.get("/api/pipelines")
        default_pipelines = [p for p in r.json() if p["name"] == DEFAULT_PIPELINE_NAME]
        assert len(default_pipelines) == 1
        assert default_pipelines[0]["is_default"] is True
