"""API endpoints for managing compliance templates (GDPR, HIPAA, SOC2).

All endpoints require admin privileges.

Available routes:
    GET   /api/compliance/templates               – list all compliance templates
    GET   /api/compliance/templates/{name}         – get a single template with checks
    POST  /api/compliance/templates/{name}/apply   – one-click apply a template
    GET   /api/compliance/templates/{name}/status  – evaluate compliance status
    GET   /api/compliance/summary                  – overall compliance dashboard data
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.utils.compliance_service import (
    COMPLIANCE_TEMPLATES,
    apply_template,
    evaluate_template_status,
    get_all_templates,
    get_compliance_summary,
    get_template_by_name,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/compliance", tags=["compliance"])

DbSession = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Authorisation helper
# ---------------------------------------------------------------------------


def _require_admin(request: Request) -> dict:
    """Ensure the caller is an admin; raises HTTP 403 otherwise."""
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


AdminUser = Annotated[dict, Depends(_require_admin)]


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class CheckResult(BaseModel):
    """Individual compliance check result."""

    key: str
    label: str
    description: str
    expected: str
    actual: str
    passing: bool


class TemplateStatusResponse(BaseModel):
    """Status evaluation for a compliance template."""

    status: str
    total: int
    passed: int
    failed: int
    check_results: list[CheckResult]


class TemplateResponse(BaseModel):
    """Full compliance template representation."""

    id: int
    name: str
    display_name: str
    description: str | None
    enabled: bool
    status: str
    applied_at: str | None
    applied_by: str | None
    settings: dict[str, str]
    checks: list[dict[str, Any]]
    check_count: int


class ApplyResponse(BaseModel):
    """Result of applying a compliance template."""

    success: bool
    template: str | None = None
    applied_settings: dict[str, str] | None = None
    errors: list[str] | None = None
    error: str | None = None
    status: TemplateStatusResponse | None = None


class SummaryTemplateResponse(BaseModel):
    """Per-template summary for the compliance dashboard."""

    name: str
    display_name: str
    enabled: bool
    status: str
    total: int
    passed: int
    failed: int
    applied_at: str | None
    applied_by: str | None


class ComplianceSummaryResponse(BaseModel):
    """Overall compliance dashboard summary."""

    overall_status: str
    total_checks: int
    total_passed: int
    total_failed: int
    templates: list[SummaryTemplateResponse]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates(db: DbSession, admin: AdminUser) -> list[dict[str, Any]]:
    """List all compliance templates with their current status."""
    return get_all_templates(db)


@router.get("/templates/{name}", response_model=TemplateResponse)
async def get_template(name: str, db: DbSession, admin: AdminUser) -> dict[str, Any]:
    """Get a single compliance template by name."""
    templates = get_all_templates(db)
    for t in templates:
        if t["name"] == name:
            return t
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template '{name}' not found")


@router.post("/templates/{name}/apply", response_model=ApplyResponse)
async def apply_compliance_template(name: str, db: DbSession, admin: AdminUser) -> dict[str, Any]:
    """Apply a compliance template (one-click).

    Writes all template settings to the database and evaluates the resulting
    compliance status.
    """
    if name not in COMPLIANCE_TEMPLATES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template '{name}' not found")

    template = get_template_by_name(db, name)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template '{name}' not found")

    admin_email = admin.get("email", "admin")
    result = apply_template(db, name, applied_by=admin_email)
    if not result.get("success") and result.get("error"):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result["error"])
    return result


@router.get("/templates/{name}/status", response_model=TemplateStatusResponse)
async def get_template_status(name: str, db: DbSession, admin: AdminUser) -> dict[str, Any]:
    """Evaluate the live compliance status of a template."""
    template = get_template_by_name(db, name)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template '{name}' not found")
    return evaluate_template_status(db, name)


@router.get("/summary", response_model=ComplianceSummaryResponse)
async def compliance_summary(db: DbSession, admin: AdminUser) -> dict[str, Any]:
    """Overall compliance dashboard summary across all templates."""
    return get_compliance_summary(db)
