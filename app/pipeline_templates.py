"""Versioned starter templates for processing profiles."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

TEMPLATE_FORMAT_VERSION = "1.0"
SUPPORTED_TEMPLATE_FORMATS = {TEMPLATE_FORMAT_VERSION}
TEMPLATE_CATEGORIES = {"contracts", "invoices", "receipts", "research", "standard"}

BUILT_IN_PIPELINE_TEMPLATES: dict[str, dict[str, Any]] = {
    "standard_document_archive": {
        "format_version": TEMPLATE_FORMAT_VERSION,
        "key": "standard_document_archive",
        "name": "Standard document archive",
        "description": "Normalize, OCR when needed, enrich metadata, index, and deliver to configured destinations.",
        "category": "standard",
        "compatibility": {"min_app_version": "0.173.0", "required_providers": []},
        "pipeline": {"is_active": True, "is_default": False},
        "steps": [
            {"step_type": "convert_to_pdf", "label": "Normalize to PDF"},
            {"step_type": "ocr", "label": "OCR when needed", "config": {"ocr_language": "auto"}},
            {"step_type": "extract_metadata", "label": "Extract document metadata"},
            {"step_type": "embed_metadata", "label": "Write metadata to PDF"},
            {"step_type": "compute_embedding", "label": "Enable semantic search"},
            {"step_type": "send_to_destinations", "label": "Deliver to configured destinations"},
        ],
    },
    "invoice_intake_pack": {
        "format_version": TEMPLATE_FORMAT_VERSION,
        "key": "invoice_intake_pack",
        "name": "Invoice intake pack",
        "description": "Classify invoices, extract accounting metadata, index for search, and deliver.",
        "category": "invoices",
        "compatibility": {"min_app_version": "0.173.0", "required_providers": []},
        "pipeline": {"is_active": True, "is_default": False},
        "steps": [
            {"step_type": "ocr", "label": "OCR invoice", "config": {"ocr_language": "auto"}},
            {"step_type": "classify", "label": "Classify invoice", "config": {"use_builtin_rules": True}},
            {"step_type": "extract_metadata", "label": "Extract invoice metadata"},
            {"step_type": "compute_embedding", "label": "Enable invoice search"},
            {"step_type": "send_to_destinations", "label": "Deliver invoice"},
        ],
    },
    "contract_review_pack": {
        "format_version": TEMPLATE_FORMAT_VERSION,
        "key": "contract_review_pack",
        "name": "Contract review pack",
        "description": "Prepare contracts for review with OCR, classification, metadata, and searchable text.",
        "category": "contracts",
        "compatibility": {"min_app_version": "0.173.0", "required_providers": []},
        "pipeline": {"is_active": True, "is_default": False},
        "steps": [
            {"step_type": "ocr", "label": "OCR contract", "config": {"ocr_language": "auto"}},
            {"step_type": "classify", "label": "Classify contract", "config": {"use_builtin_rules": True}},
            {"step_type": "extract_metadata", "label": "Extract parties and dates"},
            {"step_type": "embed_metadata", "label": "Write review metadata to PDF"},
            {"step_type": "compute_embedding", "label": "Enable clause search"},
        ],
    },
    "receipt_capture_pack": {
        "format_version": TEMPLATE_FORMAT_VERSION,
        "key": "receipt_capture_pack",
        "name": "Receipt capture pack",
        "description": "OCR small receipts, classify them, extract totals, and keep them searchable.",
        "category": "receipts",
        "compatibility": {"min_app_version": "0.173.0", "required_providers": []},
        "pipeline": {"is_active": True, "is_default": False},
        "steps": [
            {"step_type": "ocr", "label": "Force receipt OCR", "config": {"force_cloud_ocr": True}},
            {"step_type": "classify", "label": "Classify receipt", "config": {"use_builtin_rules": True}},
            {"step_type": "extract_metadata", "label": "Extract merchant and total"},
            {"step_type": "compute_embedding", "label": "Enable receipt search"},
        ],
    },
    "research_archive_pack": {
        "format_version": TEMPLATE_FORMAT_VERSION,
        "key": "research_archive_pack",
        "name": "Research archive pack",
        "description": "Prepare papers and research notes for metadata extraction and semantic retrieval.",
        "category": "research",
        "compatibility": {"min_app_version": "0.173.0", "required_providers": []},
        "pipeline": {"is_active": True, "is_default": False},
        "steps": [
            {"step_type": "convert_to_pdf", "label": "Normalize source file"},
            {"step_type": "ocr", "label": "OCR scanned pages", "config": {"ocr_language": "auto"}},
            {"step_type": "extract_metadata", "label": "Extract authors and topics"},
            {"step_type": "compute_embedding", "label": "Enable semantic retrieval"},
        ],
    },
}


def list_builtin_templates() -> list[dict[str, Any]]:
    """Return copies of all built-in templates."""
    return [deepcopy(template) for template in BUILT_IN_PIPELINE_TEMPLATES.values()]


def get_builtin_template(template_key: str) -> dict[str, Any] | None:
    """Return a copy of one built-in template."""
    template = BUILT_IN_PIPELINE_TEMPLATES.get(template_key)
    return deepcopy(template) if template else None


def export_pipeline_template(
    *,
    key: str,
    name: str,
    description: str | None,
    category: str,
    is_active: bool,
    is_default: bool,
    steps: list[dict[str, Any]],
    min_app_version: str,
) -> dict[str, Any]:
    """Build a portable template document from an existing pipeline."""
    return {
        "format_version": TEMPLATE_FORMAT_VERSION,
        "key": key,
        "name": name,
        "description": description or "",
        "category": category,
        "compatibility": {"min_app_version": min_app_version, "required_providers": []},
        "pipeline": {"is_active": is_active, "is_default": is_default},
        "steps": [
            {
                "step_type": step["step_type"],
                **({"label": step["label"]} if step.get("label") else {}),
                **({"config": step["config"]} if step.get("config") else {}),
                **({"enabled": False} if step.get("enabled") is False else {}),
            }
            for step in steps
        ],
    }


def validate_pipeline_template(
    template: dict[str, Any],
    *,
    valid_step_types: set[str],
    current_app_version: str,
) -> dict[str, Any]:
    """Validate and normalize a pipeline template document."""
    if not isinstance(template, dict):
        raise ValueError("Template must be a JSON object")

    format_version = template.get("format_version")
    if format_version not in SUPPORTED_TEMPLATE_FORMATS:
        raise ValueError(f"Unsupported template format_version: {format_version!r}")

    category = template.get("category")
    if category not in TEMPLATE_CATEGORIES:
        raise ValueError(f"Template category must be one of: {sorted(TEMPLATE_CATEGORIES)}")

    key = _required_string(template, "key")
    name = _required_string(template, "name")
    description = template.get("description") or ""
    if not isinstance(description, str):
        raise ValueError("Template description must be a string")

    compatibility = template.get("compatibility") or {}
    if not isinstance(compatibility, dict):
        raise ValueError("Template compatibility must be an object")
    min_app_version = compatibility.get("min_app_version", "0.0.0")
    if not isinstance(min_app_version, str) or not min_app_version:
        raise ValueError("Template compatibility.min_app_version must be a string")
    if _version_tuple(min_app_version) > _version_tuple(current_app_version):
        raise ValueError(f"Template requires DocuElevate {min_app_version} or newer")

    required_providers = compatibility.get("required_providers", [])
    if not isinstance(required_providers, list) or not all(isinstance(item, str) for item in required_providers):
        raise ValueError("Template compatibility.required_providers must be a list of strings")

    pipeline = template.get("pipeline") or {}
    if not isinstance(pipeline, dict):
        raise ValueError("Template pipeline must be an object")

    raw_steps = template.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("Template steps must be a non-empty list")

    steps = [_normalize_step(raw_step, valid_step_types, index) for index, raw_step in enumerate(raw_steps)]

    return {
        "format_version": format_version,
        "key": key,
        "name": name,
        "description": description,
        "category": category,
        "compatibility": {
            "min_app_version": min_app_version,
            "required_providers": required_providers,
        },
        "pipeline": {
            "is_active": bool(pipeline.get("is_active", True)),
            "is_default": bool(pipeline.get("is_default", False)),
        },
        "steps": steps,
    }


def _required_string(data: dict[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Template {field} must be a non-empty string")
    return value.strip()


def _normalize_step(raw_step: Any, valid_step_types: set[str], index: int) -> dict[str, Any]:
    if not isinstance(raw_step, dict):
        raise ValueError(f"Template step {index + 1} must be an object")

    step_type = raw_step.get("step_type")
    if step_type not in valid_step_types:
        raise ValueError(f"Template step {index + 1} has unknown step_type: {step_type!r}")

    label = raw_step.get("label")
    if label is not None and not isinstance(label, str):
        raise ValueError(f"Template step {index + 1} label must be a string")

    config = raw_step.get("config", {})
    if not isinstance(config, dict):
        raise ValueError(f"Template step {index + 1} config must be an object")

    enabled = raw_step.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError(f"Template step {index + 1} enabled must be a boolean")

    return {
        "step_type": step_type,
        "label": label.strip() if isinstance(label, str) and label.strip() else None,
        "config": config,
        "enabled": enabled,
    }


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for part in version.split("."):
        number = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(number or 0))
    return tuple(parts)
