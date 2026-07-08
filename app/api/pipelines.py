"""
Pipelines API endpoints.

Provides full CRUD for processing pipelines and their steps.  Pipelines are
user-specific: regular users can only manage their own pipelines, while admins
can also create and manage *system default* pipelines (owner_id = NULL) that
are visible to all users.

Built-in step types are exposed via GET /api/pipelines/step-types so that UIs
can render the correct configuration form without hard-coding the catalogue.
"""

import json
import logging
from typing import Annotated, Any, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_user_id, require_login
from app.config import settings
from app.database import get_db
from app.models import Pipeline, PipelineStep
from app.pipeline_templates import (
    export_pipeline_template,
    get_builtin_template,
    list_builtin_templates,
    validate_pipeline_template,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipelines", tags=["pipelines"])

DbSession = Annotated[Session, Depends(get_db)]

# ---------------------------------------------------------------------------
# Built-in step type catalogue
# ---------------------------------------------------------------------------

PIPELINE_STEP_TYPES: dict[str, dict[str, Any]] = {
    "convert_to_pdf": {
        "label": "Convert to PDF",
        "description": "Convert non-PDF documents to PDF format using Gotenberg. Runtime order is system-managed.",
        "runtime_effect": "metadata_only",
        "runtime_effect_description": "Stored for profile planning; it does not currently change processing order.",
        "config_schema": {},
    },
    "check_duplicates": {
        "label": "Check for Duplicates",
        "description": "Compare file hash against existing documents to detect duplicates. Runtime order is system-managed.",
        "runtime_effect": "metadata_only",
        "runtime_effect_description": "Stored for profile planning; duplicate checks use global settings today.",
        "config_schema": {},
    },
    "ocr": {
        "label": "OCR Profile Settings",
        "description": "Configure OCR behavior that is applied during the system-managed processing flow.",
        "runtime_effect": "applied_config",
        "runtime_effect_description": "OCR language and forced OCR processing are applied at runtime.",
        "config_schema": {
            "force_cloud_ocr": {
                "type": "boolean",
                "default": False,
                "description": "Always run OCR processing even if the PDF already has embedded text.",
            },
            "ocr_language": {
                "type": "select",
                "default": "auto",
                "description": (
                    "Language(s) used for OCR text extraction.  Applies to Tesseract and EasyOCR "
                    "providers; Azure and Mistral perform auto-detection by default.  "
                    "Use Tesseract codes such as 'eng', 'deu', or 'eng+deu' for multi-language "
                    "documents.  'auto' falls back to the global system setting."
                ),
                "options": [
                    {"value": "auto", "label": "Auto (use system default)"},
                    {"value": "ara", "label": "Arabic"},
                    {"value": "chi_sim", "label": "Chinese (Simplified)"},
                    {"value": "chi_tra", "label": "Chinese (Traditional)"},
                    {"value": "ces", "label": "Czech"},
                    {"value": "dan", "label": "Danish"},
                    {"value": "nld", "label": "Dutch"},
                    {"value": "eng", "label": "English"},
                    {"value": "fin", "label": "Finnish"},
                    {"value": "fra", "label": "French"},
                    {"value": "deu", "label": "German"},
                    {"value": "ell", "label": "Greek"},
                    {"value": "heb", "label": "Hebrew"},
                    {"value": "hin", "label": "Hindi"},
                    {"value": "hun", "label": "Hungarian"},
                    {"value": "ita", "label": "Italian"},
                    {"value": "jpn", "label": "Japanese"},
                    {"value": "kor", "label": "Korean"},
                    {"value": "nor", "label": "Norwegian"},
                    {"value": "pol", "label": "Polish"},
                    {"value": "por", "label": "Portuguese"},
                    {"value": "ron", "label": "Romanian"},
                    {"value": "rus", "label": "Russian"},
                    {"value": "spa", "label": "Spanish"},
                    {"value": "swe", "label": "Swedish"},
                    {"value": "tha", "label": "Thai"},
                    {"value": "tur", "label": "Turkish"},
                    {"value": "ukr", "label": "Ukrainian"},
                    {"value": "vie", "label": "Vietnamese"},
                ],
            },
        },
    },
    "extract_metadata": {
        "label": "Metadata Extraction",
        "description": "Extract structured metadata (document type, sender, recipient, tags) using AI. Runtime order is system-managed.",
        "runtime_effect": "metadata_only",
        "runtime_effect_description": "Stored for profile planning; it does not currently change processing order.",
        "config_schema": {},
    },
    "embed_metadata": {
        "label": "Embed Metadata into PDF",
        "description": "Write the extracted metadata into the PDF document properties. Runtime order is system-managed.",
        "runtime_effect": "metadata_only",
        "runtime_effect_description": "Stored for profile planning; it does not currently change processing order.",
        "config_schema": {},
    },
    "compute_embedding": {
        "label": "Compute Text Embedding",
        "description": "Compute semantic text embeddings for full-text and similarity search. Runtime order is system-managed.",
        "runtime_effect": "metadata_only",
        "runtime_effect_description": "Stored for profile planning; it does not currently change processing order.",
        "config_schema": {},
    },
    "send_to_destinations": {
        "label": "Send to Storage Destinations",
        "description": "Upload the processed document to all configured storage destinations. Runtime order is system-managed.",
        "runtime_effect": "metadata_only",
        "runtime_effect_description": "Stored for profile planning; destination uploads use configured integrations today.",
        "config_schema": {},
    },
    "classify": {
        "label": "Document Classification",
        "description": "Classify the document type using built-in and custom rules. Runtime order is system-managed.",
        "runtime_effect": "metadata_only",
        "runtime_effect_description": "Stored for profile planning; classification rules use their own settings today.",
        "config_schema": {
            "use_builtin_rules": {
                "type": "boolean",
                "default": True,
                "description": "Include the pre-built classification rules (invoice, contract, receipt, etc.).",
            },
        },
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MAX_STEPS_PER_PIPELINE = 50
MAX_NAME_LENGTH = 255

PIPELINE_PRESETS: dict[str, dict[str, Any]] = {
    "standard_document": {
        "name": "Standard document processing",
        "description": "OCR when needed, extract metadata, write PDF metadata, search index, and deliver to destinations.",
        "steps": [
            {"step_type": "ocr", "label": "OCR when needed", "config": {"ocr_language": "auto"}},
            {"step_type": "extract_metadata", "label": "Extract document metadata"},
            {"step_type": "embed_metadata", "label": "Write metadata to PDF"},
            {"step_type": "compute_embedding", "label": "Enable semantic search"},
            {"step_type": "send_to_destinations", "label": "Deliver to configured destinations"},
        ],
    },
    "scan_ocr_only": {
        "name": "Scan and OCR only",
        "description": "Run OCR-focused processing without delivery or AI metadata planning steps.",
        "steps": [
            {
                "step_type": "ocr",
                "label": "OCR scanned document",
                "config": {"force_cloud_ocr": True, "ocr_language": "auto"},
            },
        ],
    },
    "invoice_intake": {
        "name": "Invoice intake",
        "description": "OCR, classify, extract structured metadata, index for search, and deliver to destinations.",
        "steps": [
            {"step_type": "ocr", "label": "OCR invoice"},
            {"step_type": "classify", "label": "Classify document type"},
            {"step_type": "extract_metadata", "label": "Extract invoice metadata"},
            {"step_type": "compute_embedding", "label": "Enable invoice search"},
            {"step_type": "send_to_destinations", "label": "Deliver invoice"},
        ],
    },
    "privacy_local_ocr": {
        "name": "Privacy-first OCR",
        "description": "Keep the profile focused on local OCR/search planning and avoid external delivery actions.",
        "steps": [
            {"step_type": "ocr", "label": "Local OCR preference", "config": {"ocr_language": "auto"}},
            {"step_type": "compute_embedding", "label": "Enable local search"},
        ],
    },
    "no_external_delivery": {
        "name": "Process without delivery",
        "description": "Extract and enrich the document without sending it to configured external destinations.",
        "steps": [
            {"step_type": "ocr", "label": "OCR when needed"},
            {"step_type": "extract_metadata", "label": "Extract document metadata"},
            {"step_type": "embed_metadata", "label": "Write metadata to PDF"},
            {"step_type": "compute_embedding", "label": "Enable search"},
        ],
    },
}


def _get_user_id(request: Request) -> str:
    """Return a stable user identifier from the session.

    Delegates to :func:`app.auth.get_current_user_id` so the same fallback
    logic ("anonymous") is used consistently throughout the application.
    """
    return get_current_user_id(request)


def _is_admin(request: Request) -> bool:
    """Return True if the current session user is an admin."""
    user = get_current_user(request)
    return bool(user and user.get("is_admin"))


def _can_access_pipeline(pipeline: Pipeline, user_id: str, admin: bool) -> bool:
    """Return True if the user may read or write this pipeline."""
    # System pipelines (owner_id=NULL) are readable by everyone; only admins can write
    if pipeline.owner_id is None:
        return True
    # Own pipeline
    return pipeline.owner_id == user_id or admin


def _can_write_pipeline(pipeline: Pipeline, user_id: str, admin: bool) -> bool:
    """Return True if the user may create/update/delete this pipeline."""
    if pipeline.owner_id is None:
        return admin
    return pipeline.owner_id == user_id or admin


def _serialize_step(step: PipelineStep) -> dict[str, Any]:
    return {
        "id": step.id,
        "pipeline_id": step.pipeline_id,
        "position": step.position,
        "step_type": step.step_type,
        "label": step.label,
        "config": json.loads(step.config) if step.config else {},
        "enabled": step.enabled,
        "created_at": step.created_at.isoformat() if step.created_at else None,
        "updated_at": step.updated_at.isoformat() if step.updated_at else None,
    }


def _serialize_pipeline(
    pipeline: Pipeline,
    include_steps: bool = False,
    db: Session | None = None,
    steps: list[PipelineStep] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": pipeline.id,
        "owner_id": pipeline.owner_id,
        "name": pipeline.name,
        "description": pipeline.description,
        "is_default": pipeline.is_default,
        "is_active": pipeline.is_active,
        "created_at": pipeline.created_at.isoformat() if pipeline.created_at else None,
        "updated_at": pipeline.updated_at.isoformat() if pipeline.updated_at else None,
    }
    if include_steps:
        if steps is None and db is not None:
            steps = (
                db.query(PipelineStep)
                .filter(PipelineStep.pipeline_id == pipeline.id)
                .order_by(PipelineStep.position)
                .all()
            )
        data["steps"] = [_serialize_step(s) for s in steps or []]
    return data


def _pipeline_steps_by_id(db: Session, pipeline_ids: list[int]) -> dict[int, list[PipelineStep]]:
    if not pipeline_ids:
        return {}
    grouped: dict[int, list[PipelineStep]] = {pipeline_id: [] for pipeline_id in pipeline_ids}
    steps = (
        db.query(PipelineStep)
        .filter(PipelineStep.pipeline_id.in_(pipeline_ids))
        .order_by(PipelineStep.pipeline_id, PipelineStep.position)
        .all()
    )
    for step in steps:
        grouped.setdefault(step.pipeline_id, []).append(step)
    return grouped


def _pipeline_template_response(template: dict[str, Any]) -> dict[str, Any]:
    return validate_pipeline_template(
        template,
        valid_step_types=set(PIPELINE_STEP_TYPES),
        current_app_version=settings.version,
    )


def _pipeline_name_conflict(name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"A pipeline named '{name}' already exists",
    )


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class PipelineCreate(BaseModel):
    """Body for creating a pipeline."""

    name: str = Field(..., max_length=MAX_NAME_LENGTH, description="Human-readable pipeline name")
    description: str | None = Field(default=None, max_length=4096)
    is_default: bool = Field(default=False)
    is_active: bool = Field(default=True)


class PipelinePresetCreate(BaseModel):
    """Body for creating a pipeline from a built-in preset."""

    name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    description: str | None = Field(default=None, max_length=4096)
    is_default: bool = Field(default=False)
    is_active: bool = Field(default=True)


class PipelineTemplateImport(BaseModel):
    """Body for importing a versioned pipeline template."""

    template: dict[str, Any] = Field(..., description="Versioned pipeline template document")
    name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    description: str | None = Field(default=None, max_length=4096)
    is_default: bool | None = Field(default=None)
    is_active: bool | None = Field(default=None)


class PipelineTemplateValidate(BaseModel):
    """Body for validating a versioned pipeline template without importing it."""

    template: dict[str, Any] = Field(..., description="Versioned pipeline template document")


class PipelineUpdate(BaseModel):
    """Body for updating a pipeline (all fields optional)."""

    name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    description: str | None = Field(default=None, max_length=4096)
    is_default: bool | None = None
    is_active: bool | None = None


class PipelineStepCreate(BaseModel):
    """Body for adding a step to a pipeline."""

    step_type: str = Field(..., description="One of the recognised step type keys")
    label: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = Field(default=True)
    position: int | None = Field(default=None, ge=0, description="Insertion position; appended at end if omitted")


class PipelineStepUpdate(BaseModel):
    """Body for updating a pipeline step (all fields optional)."""

    step_type: str | None = None
    label: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    position: int | None = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# Step-types catalogue endpoint (no auth required — it's public metadata)
# ---------------------------------------------------------------------------


@router.get("/step-types")
def list_step_types() -> dict[str, Any]:
    """Return the catalogue of built-in pipeline step types.

    Returns:
        A mapping of step_type key → metadata (label, description, config_schema).
    """
    return PIPELINE_STEP_TYPES


# ---------------------------------------------------------------------------
# Pipeline CRUD
# ---------------------------------------------------------------------------


@router.get("")
@require_login
def list_pipelines(
    request: Request,
    db: DbSession,
    include_steps: bool = Query(
        default=False,
        description="Include ordered profile steps for each returned pipeline.",
    ),
) -> list[dict[str, Any]]:
    """List pipelines visible to the current user.

    Regular users see: their own pipelines + system pipelines (owner_id=NULL).
    Admins see: all pipelines from all users.

    Returns:
        A list of pipeline objects. Pass ``include_steps=true`` to include
        each pipeline's ordered steps in a single request.
    """
    user_id = _get_user_id(request)
    admin = _is_admin(request)

    if admin:
        pipelines = db.query(Pipeline).order_by(Pipeline.owner_id.nullsfirst(), Pipeline.name).all()
    else:
        pipelines = (
            db.query(Pipeline)
            .filter((Pipeline.owner_id == user_id) | (Pipeline.owner_id.is_(None)))
            .order_by(Pipeline.owner_id.nullsfirst(), Pipeline.name)
            .all()
        )

    if not include_steps:
        return [_serialize_pipeline(p) for p in pipelines]

    pipeline_ids = [cast(int, p.id) for p in pipelines]
    steps_by_pipeline = _pipeline_steps_by_id(db, pipeline_ids)
    return [_serialize_pipeline(p, include_steps=True, steps=steps_by_pipeline.get(p.id, [])) for p in pipelines]


@router.post("", status_code=status.HTTP_201_CREATED)
@require_login
def create_pipeline(request: Request, db: DbSession, body: PipelineCreate) -> dict[str, Any]:
    """Create a new pipeline for the current user.

    Admins can create system default pipelines by passing ``owner_id=null``
    via the body — however, that is handled implicitly: to create a system
    pipeline, call ``POST /api/admin/pipelines`` (admin endpoint) instead.
    Regular users always get their own user_id as owner.

    Returns:
        The created pipeline object.

    Raises:
        HTTPException 409: If a pipeline with the same name already exists for this owner.
    """
    user_id = _get_user_id(request)

    name = body.name.strip() if body.name else ""
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="name is required",
        )

    # Enforce unique name per owner
    existing = db.query(Pipeline).filter(Pipeline.owner_id == user_id, Pipeline.name == name).first()
    if existing:
        raise _pipeline_name_conflict(name)

    # If this pipeline is marked as default, unset the existing default for this user
    if body.is_default:
        _unset_default(db, user_id)

    pipeline = Pipeline(
        owner_id=user_id,
        name=name,
        description=body.description,
        is_default=body.is_default,
        is_active=body.is_active,
    )
    try:
        db.add(pipeline)
        db.commit()
        db.refresh(pipeline)
    except IntegrityError:
        db.rollback()
        raise _pipeline_name_conflict(name)
    except Exception:
        db.rollback()
        logger.exception("Failed to create pipeline user=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create pipeline",
        )

    logger.info("Pipeline created: id=%s, owner=%s, name=%r", pipeline.id, user_id, name)
    return _serialize_pipeline(pipeline)


@router.get("/presets")
@require_login
def list_pipeline_presets() -> list[dict[str, Any]]:
    """Return built-in profile presets suitable for guided setup UIs."""
    return [
        {
            "key": key,
            "name": preset["name"],
            "description": preset["description"],
            "steps": preset["steps"],
        }
        for key, preset in PIPELINE_PRESETS.items()
    ]


@router.post("/presets/{preset_key}", status_code=status.HTTP_201_CREATED)
@require_login
def create_pipeline_from_preset(
    preset_key: str,
    request: Request,
    db: DbSession,
    body: PipelinePresetCreate | None = None,
) -> dict[str, Any]:
    """Create a user-owned processing profile from a built-in preset."""
    preset = PIPELINE_PRESETS.get(preset_key)
    if preset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline preset not found")

    user_id = _get_user_id(request)
    payload = body or PipelinePresetCreate()
    name = preset["name"] if payload.name is None else payload.name
    name = name.strip()
    description = payload.description if payload.description is not None else preset["description"]

    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required")

    existing = db.query(Pipeline).filter(Pipeline.owner_id == user_id, Pipeline.name == name).first()
    if existing:
        raise _pipeline_name_conflict(name)

    if payload.is_default:
        _unset_default(db, user_id)

    pipeline = Pipeline(
        owner_id=user_id,
        name=name,
        description=description,
        is_default=payload.is_default,
        is_active=payload.is_active,
    )
    try:
        db.add(pipeline)
        db.flush()
        for position, step in enumerate(preset["steps"]):
            db.add(
                PipelineStep(
                    pipeline_id=pipeline.id,
                    position=position,
                    step_type=step["step_type"],
                    label=step.get("label"),
                    config=json.dumps(step.get("config", {})),
                    enabled=step.get("enabled", True),
                )
            )
        db.commit()
        db.refresh(pipeline)
    except IntegrityError:
        db.rollback()
        raise _pipeline_name_conflict(name)
    except Exception:
        db.rollback()
        logger.exception("Failed to create pipeline from preset=%s", preset_key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create pipeline from preset",
        )

    logger.info("Pipeline created from preset: id=%s, preset=%s", pipeline.id, preset_key)
    return _serialize_pipeline(pipeline, include_steps=True, db=db)


@router.get("/templates")
@require_login
def list_pipeline_templates() -> list[dict[str, Any]]:
    """Return built-in versioned pipeline templates."""
    return [_pipeline_template_response(template) for template in list_builtin_templates()]


@router.get("/templates/{template_key}")
@require_login
def get_pipeline_template(template_key: str) -> dict[str, Any]:
    """Return one built-in versioned pipeline template."""
    template = get_builtin_template(template_key)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline template not found")
    return _pipeline_template_response(template)


@router.post("/templates/validate")
@require_login
def validate_template(body: PipelineTemplateValidate) -> dict[str, Any]:
    """Validate a pipeline template without importing it."""
    try:
        template = _pipeline_template_response(body.template)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return {"valid": True, "template": template}


@router.post("/templates/import", status_code=status.HTTP_201_CREATED)
@require_login
def import_pipeline_template(
    request: Request,
    db: DbSession,
    body: PipelineTemplateImport,
) -> dict[str, Any]:
    """Import a versioned pipeline template as a user-owned processing profile."""
    try:
        template = _pipeline_template_response(body.template)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    user_id = _get_user_id(request)
    name = (body.name or template["name"]).strip()
    description = body.description if body.description is not None else template["description"]
    is_default = body.is_default if body.is_default is not None else template["pipeline"]["is_default"]
    is_active = body.is_active if body.is_active is not None else template["pipeline"]["is_active"]

    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required")

    existing = db.query(Pipeline).filter(Pipeline.owner_id == user_id, Pipeline.name == name).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A pipeline named '{name}' already exists")

    if is_default:
        _unset_default(db, user_id)

    pipeline = Pipeline(
        owner_id=user_id,
        name=name,
        description=description,
        is_default=is_default,
        is_active=is_active,
    )
    try:
        db.add(pipeline)
        db.flush()
        for position, step in enumerate(template["steps"]):
            db.add(
                PipelineStep(
                    pipeline_id=pipeline.id,
                    position=position,
                    step_type=step["step_type"],
                    label=step["label"],
                    config=json.dumps(step["config"]) if step["config"] else None,
                    enabled=step["enabled"],
                )
            )
        db.commit()
        db.refresh(pipeline)
    except Exception:
        db.rollback()
        logger.exception("Failed to import pipeline template=%s", template["key"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to import pipeline template",
        )

    logger.info("Pipeline imported from template: id=%s, template=%s", pipeline.id, template["key"])
    return _serialize_pipeline(pipeline, include_steps=True, db=db)


@router.get("/{pipeline_id}/template")
@require_login
def export_pipeline_as_template(
    pipeline_id: int,
    request: Request,
    db: DbSession,
    category: str = Query(default="standard", description="Template category for the exported document."),
) -> dict[str, Any]:
    """Export an accessible pipeline as a versioned template document."""
    user_id = _get_user_id(request)
    admin = _is_admin(request)

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline or not _can_access_pipeline(pipeline, user_id, admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    steps = db.query(PipelineStep).filter(PipelineStep.pipeline_id == pipeline_id).order_by(PipelineStep.position).all()
    serialized_steps = [_serialize_step(step) for step in steps]
    template = export_pipeline_template(
        key=f"pipeline-{pipeline.id}",
        name=pipeline.name,
        description=pipeline.description,
        category=category,
        is_active=pipeline.is_active,
        is_default=pipeline.is_default,
        steps=serialized_steps,
        min_app_version=settings.version,
    )
    try:
        return _pipeline_template_response(template)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/{pipeline_id}")
@require_login
def get_pipeline(pipeline_id: int, request: Request, db: DbSession) -> dict[str, Any]:
    """Return a single pipeline with its steps.

    Path Parameters:
        pipeline_id: The ID of the pipeline.

    Returns:
        The pipeline object including its ordered steps.

    Raises:
        HTTPException 404: If the pipeline does not exist or is not accessible.
    """
    user_id = _get_user_id(request)
    admin = _is_admin(request)

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline or not _can_access_pipeline(pipeline, user_id, admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    return _serialize_pipeline(pipeline, include_steps=True, db=db)


@router.put("/{pipeline_id}")
@require_login
def update_pipeline(pipeline_id: int, request: Request, db: DbSession, body: PipelineUpdate) -> dict[str, Any]:
    """Update a pipeline's metadata.

    Path Parameters:
        pipeline_id: The ID of the pipeline to update.

    Returns:
        The updated pipeline object.

    Raises:
        HTTPException 403: If the caller does not own this pipeline.
        HTTPException 404: If the pipeline does not exist.
        HTTPException 409: If the new name conflicts with an existing pipeline.
    """
    user_id = _get_user_id(request)
    admin = _is_admin(request)

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline or not _can_access_pipeline(pipeline, user_id, admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    if not _can_write_pipeline(pipeline, user_id, admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify this pipeline")

    if body.name is not None:
        new_name = body.name.strip()
        if not new_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="name must not be empty",
            )
        if new_name != pipeline.name:
            conflict = (
                db.query(Pipeline)
                .filter(Pipeline.owner_id == pipeline.owner_id, Pipeline.name == new_name, Pipeline.id != pipeline_id)
                .first()
            )
            if conflict:
                raise _pipeline_name_conflict(new_name)
        pipeline.name = new_name

    if body.description is not None:
        pipeline.description = body.description

    if body.is_active is not None:
        pipeline.is_active = body.is_active

    if body.is_default is not None:
        if body.is_default and not pipeline.is_default:
            _unset_default(db, pipeline.owner_id)
        pipeline.is_default = body.is_default

    try:
        db.commit()
        db.refresh(pipeline)
    except IntegrityError:
        db.rollback()
        name = body.name.strip() if body.name else pipeline.name
        raise _pipeline_name_conflict(name)
    except Exception:
        db.rollback()
        logger.exception("Failed to update pipeline id=%s", pipeline_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update pipeline",
        )

    logger.info("Pipeline updated: id=%s, user=%s", pipeline_id, user_id)
    return _serialize_pipeline(pipeline, include_steps=True, db=db)


@router.delete("/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_login
def delete_pipeline(pipeline_id: int, request: Request, db: DbSession) -> None:
    """Delete a pipeline and all its steps.

    Path Parameters:
        pipeline_id: The ID of the pipeline to delete.

    Raises:
        HTTPException 403: If the caller does not own this pipeline.
        HTTPException 404: If the pipeline does not exist.
    """
    user_id = _get_user_id(request)
    admin = _is_admin(request)

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline or not _can_access_pipeline(pipeline, user_id, admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    if not _can_write_pipeline(pipeline, user_id, admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete this pipeline")

    try:
        db.query(PipelineStep).filter(PipelineStep.pipeline_id == pipeline_id).delete()
        db.delete(pipeline)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to delete pipeline id=%s", pipeline_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete pipeline",
        )

    logger.info("Pipeline deleted: id=%s, user=%s", pipeline_id, user_id)


# ---------------------------------------------------------------------------
# Admin-only: create system (owner_id=NULL) pipeline
# ---------------------------------------------------------------------------


@router.post("/admin/system", status_code=status.HTTP_201_CREATED, tags=["admin-pipelines"])
@require_login
def create_system_pipeline(request: Request, db: DbSession, body: PipelineCreate) -> dict[str, Any]:
    """Create a system-level (owner_id=NULL) default pipeline.  Admin only.

    System pipelines are visible to all users and can be set as the global
    default.  Only admins may create them.

    Returns:
        The created system pipeline.

    Raises:
        HTTPException 403: If the caller is not an admin.
        HTTPException 409: If a system pipeline with the same name already exists.
    """
    if not _is_admin(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    name = body.name.strip() if body.name else ""
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="name is required",
        )

    existing = db.query(Pipeline).filter(Pipeline.owner_id.is_(None), Pipeline.name == name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A system pipeline named '{name}' already exists",
        )

    if body.is_default:
        _unset_default(db, None)

    pipeline = Pipeline(
        owner_id=None,
        name=name,
        description=body.description,
        is_default=body.is_default,
        is_active=body.is_active,
    )
    try:
        db.add(pipeline)
        db.commit()
        db.refresh(pipeline)
    except Exception as exc:
        db.rollback()
        logger.exception(f"Failed to create system pipeline: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create system pipeline",
        )

    logger.info(f"System pipeline created: id={pipeline.id}, name={name!r}")
    return _serialize_pipeline(pipeline)


# ---------------------------------------------------------------------------
# Step management
# ---------------------------------------------------------------------------


@router.post("/{pipeline_id}/steps", status_code=status.HTTP_201_CREATED)
@require_login
def add_step(pipeline_id: int, request: Request, db: DbSession, body: PipelineStepCreate) -> dict[str, Any]:
    """Add a step to a pipeline.

    Steps are automatically appended at the end unless an explicit ``position``
    is supplied.  All existing steps at or after the insertion position are
    shifted forward by one.

    Path Parameters:
        pipeline_id: The pipeline to add the step to.

    Returns:
        The created step object.

    Raises:
        HTTPException 403: If the caller cannot modify this pipeline.
        HTTPException 404: If the pipeline does not exist.
        HTTPException 422: If the step_type is not recognised.
        HTTPException 409: If the maximum number of steps per pipeline is reached.
    """
    user_id = _get_user_id(request)
    admin = _is_admin(request)

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline or not _can_access_pipeline(pipeline, user_id, admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    if not _can_write_pipeline(pipeline, user_id, admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify this pipeline")

    if body.step_type not in PIPELINE_STEP_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown step type '{body.step_type}'. Valid types: {sorted(PIPELINE_STEP_TYPES)}",
        )

    current_count = db.query(PipelineStep).filter(PipelineStep.pipeline_id == pipeline_id).count()
    if current_count >= MAX_STEPS_PER_PIPELINE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Maximum of {MAX_STEPS_PER_PIPELINE} steps per pipeline reached",
        )

    # Determine insertion position
    if body.position is None:
        max_pos = (
            db.query(PipelineStep.position)
            .filter(PipelineStep.pipeline_id == pipeline_id)
            .order_by(PipelineStep.position.desc())
            .first()
        )
        insert_pos = (max_pos[0] + 1) if max_pos else 0
    else:
        insert_pos = body.position
        # Shift existing steps
        steps_to_shift = (
            db.query(PipelineStep)
            .filter(PipelineStep.pipeline_id == pipeline_id, PipelineStep.position >= insert_pos)
            .all()
        )
        for s in steps_to_shift:
            s.position += 1

    step = PipelineStep(
        pipeline_id=pipeline_id,
        position=insert_pos,
        step_type=body.step_type,
        label=body.label,
        config=json.dumps(body.config) if body.config else None,
        enabled=body.enabled,
    )
    try:
        db.add(step)
        db.commit()
        db.refresh(step)
    except Exception as exc:
        db.rollback()
        logger.exception(f"Failed to add step to pipeline id={pipeline_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add step",
        )

    logger.info(f"Step added: pipeline={pipeline_id}, step_type={body.step_type!r}, pos={insert_pos}")
    return _serialize_step(step)


@router.put("/{pipeline_id}/steps/reorder")
@require_login
def reorder_steps(
    pipeline_id: int,
    request: Request,
    db: DbSession,
    step_ids: list[int] = Body(..., description="Ordered list of step IDs representing the new order"),
) -> list[dict[str, Any]]:
    """Replace the step order for a pipeline.

    Provide a complete ordered list of *all* step IDs.  Their ``position``
    values will be reassigned 0, 1, 2, … in the given order.

    Path Parameters:
        pipeline_id: The pipeline whose steps are being reordered.

    Returns:
        The updated, ordered list of step objects.

    Raises:
        HTTPException 422: If the provided list does not contain exactly the
            current set of step IDs for this pipeline.
    """
    user_id = _get_user_id(request)
    admin = _is_admin(request)

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline or not _can_access_pipeline(pipeline, user_id, admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    if not _can_write_pipeline(pipeline, user_id, admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify this pipeline")

    existing_steps = db.query(PipelineStep).filter(PipelineStep.pipeline_id == pipeline_id).all()
    existing_ids = {s.id for s in existing_steps}

    if set(step_ids) != existing_ids or len(step_ids) != len(existing_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="step_ids must contain exactly the current step IDs for this pipeline",
        )

    step_map = {s.id: s for s in existing_steps}
    for pos, sid in enumerate(step_ids):
        step_map[sid].position = pos

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception(f"Failed to reorder steps for pipeline id={pipeline_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reorder steps",
        )

    updated = (
        db.query(PipelineStep).filter(PipelineStep.pipeline_id == pipeline_id).order_by(PipelineStep.position).all()
    )
    return [_serialize_step(s) for s in updated]


@router.put("/{pipeline_id}/steps/{step_id}")
@require_login
def update_step(
    pipeline_id: int, step_id: int, request: Request, db: DbSession, body: PipelineStepUpdate
) -> dict[str, Any]:
    """Update an existing pipeline step.

    Path Parameters:
        pipeline_id: The owning pipeline.
        step_id: The step to update.

    Returns:
        The updated step object.
    """
    user_id = _get_user_id(request)
    admin = _is_admin(request)

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline or not _can_access_pipeline(pipeline, user_id, admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    if not _can_write_pipeline(pipeline, user_id, admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify this pipeline")

    step = db.query(PipelineStep).filter(PipelineStep.id == step_id, PipelineStep.pipeline_id == pipeline_id).first()
    if not step:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step not found")

    if body.step_type is not None:
        if body.step_type not in PIPELINE_STEP_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown step type '{body.step_type}'",
            )
        step.step_type = body.step_type

    if body.label is not None:
        step.label = body.label

    if body.config is not None:
        step.config = json.dumps(body.config)

    if body.enabled is not None:
        step.enabled = body.enabled

    if body.position is not None and body.position != step.position:
        old_pos = step.position
        new_pos = body.position
        if new_pos > old_pos:
            # Moving down: shift intervening steps up
            db.query(PipelineStep).filter(
                PipelineStep.pipeline_id == pipeline_id,
                PipelineStep.position > old_pos,
                PipelineStep.position <= new_pos,
                PipelineStep.id != step_id,
            ).update({"position": PipelineStep.position - 1})
        else:
            # Moving up: shift intervening steps down
            db.query(PipelineStep).filter(
                PipelineStep.pipeline_id == pipeline_id,
                PipelineStep.position >= new_pos,
                PipelineStep.position < old_pos,
                PipelineStep.id != step_id,
            ).update({"position": PipelineStep.position + 1})
        step.position = new_pos

    try:
        db.commit()
        db.refresh(step)
    except Exception as exc:
        db.rollback()
        logger.exception(f"Failed to update step id={step_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update step",
        )

    return _serialize_step(step)


@router.delete("/{pipeline_id}/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_login
def delete_step(pipeline_id: int, step_id: int, request: Request, db: DbSession) -> None:
    """Delete a step from a pipeline.

    Path Parameters:
        pipeline_id: The owning pipeline.
        step_id: The step to delete.
    """
    user_id = _get_user_id(request)
    admin = _is_admin(request)

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline or not _can_access_pipeline(pipeline, user_id, admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    if not _can_write_pipeline(pipeline, user_id, admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify this pipeline")

    step = db.query(PipelineStep).filter(PipelineStep.id == step_id, PipelineStep.pipeline_id == pipeline_id).first()
    if not step:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step not found")

    deleted_pos = step.position
    try:
        db.delete(step)
        # Compact remaining step positions
        db.query(PipelineStep).filter(
            PipelineStep.pipeline_id == pipeline_id,
            PipelineStep.position > deleted_pos,
        ).update({"position": PipelineStep.position - 1})
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception(f"Failed to delete step id={step_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete step",
        )

    logger.info(f"Step deleted: id={step_id}, pipeline={pipeline_id}")


# ---------------------------------------------------------------------------
# Helper: unset default flag for an owner
# ---------------------------------------------------------------------------


def _unset_default(db: Session, owner_id: str | None) -> None:
    """Clear the is_default flag on all pipelines for the given owner."""
    if owner_id is None:
        db.query(Pipeline).filter(Pipeline.owner_id.is_(None), Pipeline.is_default.is_(True)).update(
            {"is_default": False}
        )
    else:
        db.query(Pipeline).filter(Pipeline.owner_id == owner_id, Pipeline.is_default.is_(True)).update(
            {"is_default": False}
        )


# ---------------------------------------------------------------------------
# Default system pipeline seeding
# ---------------------------------------------------------------------------

# The steps that make up the standard document-processing workflow.  The order
# here mirrors what the existing Celery-based pipeline executes for every
# uploaded file.
_DEFAULT_PIPELINE_STEPS: list[tuple[str, str]] = [
    ("convert_to_pdf", "Convert to PDF"),
    ("check_duplicates", "Check for Duplicates"),
    ("ocr", "OCR Processing"),
    ("extract_metadata", "Extract Metadata"),
    ("embed_metadata", "Embed Metadata into PDF"),
    ("compute_embedding", "Compute Text Embedding"),
    ("send_to_destinations", "Send to Storage Destinations"),
]

#: Human-readable name shown in the management UI for the auto-seeded pipeline.
DEFAULT_PIPELINE_NAME = "Standard Processing Pipeline"


def seed_default_pipeline(db: Session) -> int:
    """Ensure a system-owned default pipeline exists in the database.

    This function is idempotent — it is a no-op when any system pipeline
    (``owner_id IS NULL``) already exists.  It is intended to be called once
    at application startup (in ``app.main.lifespan``) so that the pipeline
    management UI always shows the default workflow that mirrors the existing
    Celery-based processing steps.

    The created pipeline:

    * ``owner_id = None`` — owned by the system, visible to all users
    * ``is_default = True`` — selected automatically for new documents
    * Steps (in order): convert_to_pdf → check_duplicates → ocr →
      extract_metadata → embed_metadata → compute_embedding →
      send_to_destinations

    Args:
        db: An active SQLAlchemy session.

    Returns:
        ``1`` if a new pipeline was created, ``0`` if one already existed.
    """
    try:
        if db.query(Pipeline).filter(Pipeline.owner_id.is_(None)).count() > 0:
            return 0
    except Exception:
        # Table may not exist yet during the very first migration run.
        return 0

    pipeline = Pipeline(
        owner_id=None,
        name=DEFAULT_PIPELINE_NAME,
        description=(
            "The standard document processing workflow: PDF conversion, "
            "duplicate detection, OCR, metadata extraction and embedding, "
            "semantic embeddings, and final distribution to storage destinations."
        ),
        is_default=True,
        is_active=True,
    )
    db.add(pipeline)
    try:
        db.flush()  # Assign pipeline.id without committing yet
    except Exception as exc:  # pragma: no cover
        db.rollback()
        logger.error(f"Failed to create default pipeline: {exc}")
        return 0

    for pos, (step_type, label) in enumerate(_DEFAULT_PIPELINE_STEPS):
        db.add(
            PipelineStep(
                pipeline_id=pipeline.id,
                position=pos,
                step_type=step_type,
                label=label,
                enabled=True,
            )
        )

    try:
        db.commit()
        logger.info("Seeded default system pipeline: '%s' (id=%d)", DEFAULT_PIPELINE_NAME, pipeline.id)
    except Exception as exc:  # pragma: no cover
        db.rollback()
        logger.error(f"Failed to seed default pipeline steps: {exc}")
        return 0

    return 1
