"""
Tests for the compliance templates feature.

Covers:
- app/models.py – ComplianceTemplate model
- app/utils/compliance_service.py – service functions (seed, evaluate, apply)
- app/api/compliance.py – REST API endpoints
- app/views/compliance.py – admin view route
"""

from unittest.mock import Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import ComplianceTemplate
from app.utils.compliance_service import (
    COMPLIANCE_TEMPLATES,
    apply_template,
    evaluate_template_status,
    get_all_templates,
    get_compliance_summary,
    get_template_by_name,
    seed_compliance_templates,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ct_engine():
    """In-memory SQLite engine for compliance template tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def ct_session(ct_engine):
    """DB session scoped to one test."""
    Session = sessionmaker(bind=ct_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def ct_client(ct_engine):
    """TestClient with in-memory DB and admin override."""
    from app.api.compliance import _require_admin
    from app.main import app

    def override_db():
        Session = sessionmaker(bind=ct_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def override_admin():
        return {"email": "admin@test.com", "is_admin": True}

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[_require_admin] = override_admin

    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture()
def seeded_session(ct_session):
    """Session with compliance templates already seeded."""
    seed_compliance_templates(ct_session)
    return ct_session


@pytest.fixture()
def seeded_client(ct_engine):
    """TestClient with seeded compliance templates."""
    from app.api.compliance import _require_admin
    from app.main import app

    Session = sessionmaker(bind=ct_engine)
    session = Session()
    seed_compliance_templates(session)
    session.close()

    def override_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def override_admin():
        return {"email": "admin@test.com", "is_admin": True}

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[_require_admin] = override_admin

    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComplianceTemplateModel:
    """Tests for the ComplianceTemplate database model."""

    def test_create_template(self, ct_session):
        """Test creating a compliance template."""
        template = ComplianceTemplate(
            name="test_template",
            display_name="Test Template",
            description="A test compliance template",
            settings_json='{"auth_enabled": "True"}',
            enabled=False,
            status="not_applied",
        )
        ct_session.add(template)
        ct_session.commit()

        assert template.id is not None
        assert template.name == "test_template"
        assert template.display_name == "Test Template"
        assert template.enabled is False
        assert template.status == "not_applied"

    def test_unique_name_constraint(self, ct_session):
        """Test that template names must be unique."""
        t1 = ComplianceTemplate(
            name="unique_test",
            display_name="First",
            settings_json="{}",
        )
        ct_session.add(t1)
        ct_session.commit()

        t2 = ComplianceTemplate(
            name="unique_test",
            display_name="Second",
            settings_json="{}",
        )
        ct_session.add(t2)
        with pytest.raises(Exception):
            ct_session.commit()
        ct_session.rollback()

    def test_default_values(self, ct_session):
        """Test default column values."""
        template = ComplianceTemplate(
            name="defaults_test",
            display_name="Defaults",
            settings_json="{}",
        )
        ct_session.add(template)
        ct_session.commit()

        assert template.enabled is False
        assert template.status == "not_applied"
        assert template.applied_at is None
        assert template.applied_by is None


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComplianceService:
    """Tests for compliance_service utility functions."""

    def test_seed_creates_templates(self, ct_session):
        """Test that seeding creates all three compliance templates."""
        seed_compliance_templates(ct_session)
        templates = ct_session.query(ComplianceTemplate).all()
        names = {t.name for t in templates}

        assert "gdpr" in names
        assert "hipaa" in names
        assert "soc2" in names
        assert len(templates) == 3

    def test_seed_is_idempotent(self, ct_session):
        """Test that seeding twice does not create duplicates."""
        seed_compliance_templates(ct_session)
        seed_compliance_templates(ct_session)
        templates = ct_session.query(ComplianceTemplate).all()
        assert len(templates) == 3

    def test_seed_updates_display_name(self, ct_session):
        """Test that re-seeding updates display_name but preserves state."""
        seed_compliance_templates(ct_session)
        gdpr = ct_session.query(ComplianceTemplate).filter_by(name="gdpr").first()
        gdpr.enabled = True
        ct_session.commit()

        seed_compliance_templates(ct_session)
        gdpr = ct_session.query(ComplianceTemplate).filter_by(name="gdpr").first()
        assert gdpr.enabled is True  # User state preserved

    def test_get_all_templates(self, seeded_session):
        """Test getting all templates."""
        result = get_all_templates(seeded_session)
        assert len(result) == 3
        for t in result:
            assert "id" in t
            assert "name" in t
            assert "display_name" in t
            assert "checks" in t
            assert "check_count" in t

    def test_get_template_by_name_exists(self, seeded_session):
        """Test retrieving an existing template by name."""
        result = get_template_by_name(seeded_session, "gdpr")
        assert result is not None
        assert result.name == "gdpr"

    def test_get_template_by_name_missing(self, seeded_session):
        """Test retrieving a non-existent template."""
        result = get_template_by_name(seeded_session, "nonexistent")
        assert result is None

    @patch("app.utils.settings_service.get_all_settings_from_db")
    def test_evaluate_template_compliant(self, mock_settings, seeded_session):
        """Test evaluation when all checks pass."""
        mock_settings.return_value = {
            "auth_enabled": "True",
            "sentry_send_default_pii": "False",
            "security_headers_enabled": "True",
            "security_header_hsts_enabled": "True",
            "security_header_csp_enabled": "True",
            "security_header_x_frame_options_enabled": "True",
            "enable_deduplication": "True",
        }

        result = evaluate_template_status(seeded_session, "gdpr")
        assert result["status"] == "compliant"
        assert result["passed"] == result["total"]
        assert result["failed"] == 0

    @patch("app.utils.settings_service.get_all_settings_from_db")
    def test_evaluate_template_non_compliant(self, mock_settings, seeded_session):
        """Test evaluation when no checks pass."""
        mock_settings.return_value = {}

        with patch("app.config.settings") as mock_app:
            mock_app.auth_enabled = False
            mock_app.sentry_send_default_pii = True
            mock_app.security_headers_enabled = False
            mock_app.security_header_hsts_enabled = False
            mock_app.security_header_csp_enabled = False
            mock_app.security_header_x_frame_options_enabled = False
            mock_app.enable_deduplication = False

            result = evaluate_template_status(seeded_session, "gdpr")
            assert result["status"] in ("non_compliant", "partial")
            assert result["failed"] > 0

    def test_evaluate_unknown_template(self, seeded_session):
        """Test evaluation of a non-existent template name."""
        result = evaluate_template_status(seeded_session, "unknown")
        assert result["status"] == "unknown"
        assert result["total"] == 0

    @patch("app.utils.settings_service.save_setting_to_db")
    @patch("app.utils.settings_service.get_all_settings_from_db")
    def test_apply_template_success(self, mock_get_settings, mock_save, seeded_session):
        """Test successfully applying a template."""
        mock_save.return_value = True
        mock_get_settings.return_value = {
            "auth_enabled": "True",
            "sentry_send_default_pii": "False",
            "security_headers_enabled": "True",
            "security_header_hsts_enabled": "True",
            "security_header_csp_enabled": "True",
            "security_header_x_frame_options_enabled": "True",
            "enable_deduplication": "True",
        }

        result = apply_template(seeded_session, "gdpr", applied_by="test@admin.com")
        assert result["success"] is True
        assert result["template"] == "gdpr"
        assert "applied_settings" in result

        # Verify template record updated
        gdpr = seeded_session.query(ComplianceTemplate).filter_by(name="gdpr").first()
        assert gdpr.enabled is True
        assert gdpr.applied_by == "test@admin.com"
        assert gdpr.applied_at is not None

    def test_apply_unknown_template(self, seeded_session):
        """Test applying a non-existent template."""
        result = apply_template(seeded_session, "nonexistent")
        assert result["success"] is False
        assert "error" in result

    @patch("app.utils.settings_service.get_all_settings_from_db")
    def test_get_compliance_summary(self, mock_settings, seeded_session):
        """Test compliance summary across all templates."""
        mock_settings.return_value = {}

        result = get_compliance_summary(seeded_session)
        assert "overall_status" in result
        assert "total_checks" in result
        assert "total_passed" in result
        assert "total_failed" in result
        assert "templates" in result
        assert len(result["templates"]) == 3

    def test_compliance_templates_have_checks(self):
        """Test that all built-in templates have compliance checks."""
        for name, defn in COMPLIANCE_TEMPLATES.items():
            assert "checks" in defn, f"Template {name} missing checks"
            assert len(defn["checks"]) > 0, f"Template {name} has no checks"
            for check in defn["checks"]:
                assert "key" in check
                assert "expected" in check
                assert "label" in check
                assert "description" in check

    def test_compliance_templates_have_settings(self):
        """Test that all built-in templates have settings to apply."""
        for name, defn in COMPLIANCE_TEMPLATES.items():
            assert "settings" in defn, f"Template {name} missing settings"
            assert len(defn["settings"]) > 0, f"Template {name} has no settings"


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestComplianceAPI:
    """Tests for compliance API endpoints."""

    def test_list_templates(self, seeded_client):
        """Test GET /api/compliance/templates."""
        resp = seeded_client.get("/api/compliance/templates")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 3
        names = {t["name"] for t in data}
        assert names == {"gdpr", "hipaa", "soc2"}

    def test_get_single_template(self, seeded_client):
        """Test GET /api/compliance/templates/gdpr."""
        resp = seeded_client.get("/api/compliance/templates/gdpr")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["name"] == "gdpr"
        assert "display_name" in data
        assert "checks" in data

    def test_get_nonexistent_template(self, seeded_client):
        """Test GET /api/compliance/templates/unknown returns 404."""
        resp = seeded_client.get("/api/compliance/templates/unknown")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_get_template_status(self, seeded_client):
        """Test GET /api/compliance/templates/gdpr/status."""
        resp = seeded_client.get("/api/compliance/templates/gdpr/status")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "status" in data
        assert "total" in data
        assert "passed" in data
        assert "failed" in data
        assert "check_results" in data

    def test_apply_template(self, seeded_client):
        """Test POST /api/compliance/templates/gdpr/apply."""
        resp = seeded_client.post("/api/compliance/templates/gdpr/apply")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["success"] is True
        assert data["template"] == "gdpr"
        assert "applied_settings" in data

    def test_apply_nonexistent_template(self, seeded_client):
        """Test POST /api/compliance/templates/unknown/apply returns 404."""
        resp = seeded_client.post("/api/compliance/templates/unknown/apply")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_compliance_summary(self, seeded_client):
        """Test GET /api/compliance/summary."""
        resp = seeded_client.get("/api/compliance/summary")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "overall_status" in data
        assert "total_checks" in data
        assert "templates" in data
        assert len(data["templates"]) == 3

    def test_templates_require_admin(self, ct_engine):
        """Test that endpoints require admin access."""
        from app.main import app

        def override_db():
            Session = sessionmaker(bind=ct_engine)
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        # Do NOT override _require_admin so it checks session

        with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
            resp = client.get("/api/compliance/templates")
            assert resp.status_code == status.HTTP_403_FORBIDDEN

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# View tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComplianceView:
    """Tests for the compliance view route."""

    @patch("app.views.compliance.templates")
    @patch("app.views.compliance.settings")
    @pytest.mark.asyncio
    async def test_compliance_page_admin(self, mock_settings, mock_templates):
        """Test compliance page renders for admin users."""
        from app.views.compliance import compliance_page

        mock_settings.version = "1.0.0"
        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}

        await compliance_page(mock_request)
        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        assert call_args[0][0] == "compliance.html"

    @pytest.mark.asyncio
    async def test_compliance_page_non_admin_redirects(self):
        """Test compliance page redirects non-admin users."""
        from app.views.compliance import compliance_page

        mock_request = Mock()
        mock_request.session = {"user": {"id": "user1", "is_admin": False}}

        result = await compliance_page(mock_request)
        assert result.status_code == 302


# ---------------------------------------------------------------------------
# Config / settings metadata tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComplianceConfig:
    """Tests for compliance configuration settings."""

    def test_compliance_enabled_default(self):
        """Test that compliance_enabled defaults to True."""
        from app.config import settings

        assert hasattr(settings, "compliance_enabled")
        assert settings.compliance_enabled is True

    def test_compliance_enabled_in_setting_metadata(self):
        """Test that compliance_enabled has SETTING_METADATA entry."""
        from app.utils.settings_service import SETTING_METADATA

        assert "compliance_enabled" in SETTING_METADATA
        meta = SETTING_METADATA["compliance_enabled"]
        assert meta["category"] == "Feature Flags"
        assert meta["type"] == "boolean"
