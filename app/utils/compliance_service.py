"""Compliance service for managing GDPR, HIPAA, and SOC2 compliance templates.

Provides pre-built compliance configurations that can be applied with one click
to ensure the DocuElevate instance meets regulatory requirements.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import ComplianceTemplate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-built compliance template definitions
# ---------------------------------------------------------------------------

COMPLIANCE_TEMPLATES: dict[str, dict[str, Any]] = {
    "gdpr": {
        "display_name": "GDPR (General Data Protection Regulation)",
        "description": (
            "European Union regulation for data protection and privacy. "
            "Enforces data minimisation, encryption at rest, audit logging, "
            "and limits PII exposure in telemetry."
        ),
        "settings": {
            "auth_enabled": "True",
            "sentry_send_default_pii": "False",
            "security_headers_enabled": "True",
            "security_header_hsts_enabled": "True",
            "security_header_csp_enabled": "True",
            "security_header_x_frame_options_enabled": "True",
            "enable_deduplication": "True",
        },
        "checks": [
            {
                "key": "auth_enabled",
                "expected": "True",
                "label": "Authentication enabled",
                "description": "User authentication must be enabled to control access to personal data.",
            },
            {
                "key": "sentry_send_default_pii",
                "expected": "False",
                "label": "PII excluded from telemetry",
                "description": "Personally identifiable information must not be sent to external monitoring services.",
            },
            {
                "key": "security_headers_enabled",
                "expected": "True",
                "label": "Security headers enabled",
                "description": "HTTP security headers protect against common web vulnerabilities.",
            },
            {
                "key": "security_header_hsts_enabled",
                "expected": "True",
                "label": "HSTS enabled",
                "description": "HTTP Strict Transport Security ensures encrypted connections.",
            },
            {
                "key": "security_header_csp_enabled",
                "expected": "True",
                "label": "Content Security Policy enabled",
                "description": "CSP headers prevent cross-site scripting and data injection attacks.",
            },
            {
                "key": "security_header_x_frame_options_enabled",
                "expected": "True",
                "label": "Clickjacking protection enabled",
                "description": "X-Frame-Options header prevents clickjacking attacks.",
            },
            {
                "key": "enable_deduplication",
                "expected": "True",
                "label": "Deduplication enabled",
                "description": "Data minimisation: avoid storing duplicate documents.",
            },
        ],
    },
    "hipaa": {
        "display_name": "HIPAA (Health Insurance Portability and Accountability Act)",
        "description": (
            "United States regulation for protecting health information. "
            "Requires strong access controls, audit trails, encryption, "
            "and strict session management."
        ),
        "settings": {
            "auth_enabled": "True",
            "multi_user_enabled": "True",
            "sentry_send_default_pii": "False",
            "security_headers_enabled": "True",
            "security_header_hsts_enabled": "True",
            "security_header_csp_enabled": "True",
            "security_header_x_frame_options_enabled": "True",
            "enable_deduplication": "True",
        },
        "checks": [
            {
                "key": "auth_enabled",
                "expected": "True",
                "label": "Authentication enabled",
                "description": "Access controls are required to protect electronic Protected Health Information (ePHI).",
            },
            {
                "key": "multi_user_enabled",
                "expected": "True",
                "label": "Multi-user mode enabled",
                "description": "Individual user accounts required for access accountability.",
            },
            {
                "key": "sentry_send_default_pii",
                "expected": "False",
                "label": "PII excluded from telemetry",
                "description": "Protected Health Information must not be sent to external services.",
            },
            {
                "key": "security_headers_enabled",
                "expected": "True",
                "label": "Security headers enabled",
                "description": "Security headers protect ePHI during transmission.",
            },
            {
                "key": "security_header_hsts_enabled",
                "expected": "True",
                "label": "HSTS enabled",
                "description": "Encrypted transport required for all ePHI transmissions.",
            },
            {
                "key": "security_header_csp_enabled",
                "expected": "True",
                "label": "Content Security Policy enabled",
                "description": "CSP prevents injection attacks that could expose ePHI.",
            },
            {
                "key": "security_header_x_frame_options_enabled",
                "expected": "True",
                "label": "Clickjacking protection enabled",
                "description": "Prevents embedding the application in unauthorized frames.",
            },
            {
                "key": "enable_deduplication",
                "expected": "True",
                "label": "Deduplication enabled",
                "description": "Minimise data footprint for ePHI.",
            },
        ],
    },
    "soc2": {
        "display_name": "SOC 2 (Service Organization Control 2)",
        "description": (
            "Trust Service Criteria framework for service organisations. "
            "Focuses on security, availability, processing integrity, "
            "confidentiality, and privacy."
        ),
        "settings": {
            "auth_enabled": "True",
            "multi_user_enabled": "True",
            "sentry_send_default_pii": "False",
            "security_headers_enabled": "True",
            "security_header_hsts_enabled": "True",
            "security_header_csp_enabled": "True",
            "security_header_x_frame_options_enabled": "True",
            "enable_deduplication": "True",
        },
        "checks": [
            {
                "key": "auth_enabled",
                "expected": "True",
                "label": "Authentication enabled",
                "description": "Logical access controls required (CC6.1).",
            },
            {
                "key": "multi_user_enabled",
                "expected": "True",
                "label": "Multi-user mode enabled",
                "description": "Individual user accounts for access management (CC6.2).",
            },
            {
                "key": "sentry_send_default_pii",
                "expected": "False",
                "label": "PII excluded from telemetry",
                "description": "Confidential information must not leak to external services (CC6.7).",
            },
            {
                "key": "security_headers_enabled",
                "expected": "True",
                "label": "Security headers enabled",
                "description": "Protection against common web threats (CC6.6).",
            },
            {
                "key": "security_header_hsts_enabled",
                "expected": "True",
                "label": "HSTS enabled",
                "description": "Encrypted transport in transit (CC6.7).",
            },
            {
                "key": "security_header_csp_enabled",
                "expected": "True",
                "label": "Content Security Policy enabled",
                "description": "Application-level security controls (CC6.6).",
            },
            {
                "key": "security_header_x_frame_options_enabled",
                "expected": "True",
                "label": "Clickjacking protection enabled",
                "description": "UI redress attack prevention (CC6.6).",
            },
            {
                "key": "enable_deduplication",
                "expected": "True",
                "label": "Deduplication enabled",
                "description": "Data integrity through deduplication (PI1.1).",
            },
        ],
    },
}


def seed_compliance_templates(db: Session) -> None:
    """Create or update the built-in compliance template rows.

    Called once at application startup to ensure the ``compliance_templates``
    table always contains the latest definitions.
    """
    for name, defn in COMPLIANCE_TEMPLATES.items():
        existing = db.query(ComplianceTemplate).filter(ComplianceTemplate.name == name).first()
        if existing is None:
            template = ComplianceTemplate(
                name=name,
                display_name=defn["display_name"],
                description=defn["description"],
                settings_json=json.dumps(defn["settings"]),
                enabled=False,
                status="not_applied",
            )
            db.add(template)
            logger.info(f"Seeded compliance template: {name}")
        else:
            # Update display_name and description if changed, but preserve user state
            existing.display_name = defn["display_name"]
            existing.description = defn["description"]
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to seed compliance templates")


def get_all_templates(db: Session) -> list[dict[str, Any]]:
    """Return all compliance templates with their current status."""
    templates = db.query(ComplianceTemplate).order_by(ComplianceTemplate.name).all()
    result = []
    for t in templates:
        defn = COMPLIANCE_TEMPLATES.get(t.name, {})
        checks = defn.get("checks", [])
        result.append(
            {
                "id": t.id,
                "name": t.name,
                "display_name": t.display_name,
                "description": t.description,
                "enabled": t.enabled,
                "status": t.status,
                "applied_at": t.applied_at.isoformat() if t.applied_at else None,
                "applied_by": t.applied_by,
                "settings": json.loads(t.settings_json) if t.settings_json else {},
                "checks": checks,
                "check_count": len(checks),
            }
        )
    return result


def get_template_by_name(db: Session, name: str) -> ComplianceTemplate | None:
    """Retrieve a single compliance template by name."""
    return db.query(ComplianceTemplate).filter(ComplianceTemplate.name == name).first()


def evaluate_template_status(db: Session, name: str) -> dict[str, Any]:
    """Evaluate the compliance status of a template against live settings.

    Returns a dict with ``status``, ``total``, ``passed``, ``failed``, and
    a list of individual ``check_results``.
    """
    from app.config import settings as app_settings
    from app.utils.settings_service import get_all_settings_from_db

    defn = COMPLIANCE_TEMPLATES.get(name)
    if defn is None:
        return {"status": "unknown", "total": 0, "passed": 0, "failed": 0, "check_results": []}

    db_settings = get_all_settings_from_db(db)
    checks = defn.get("checks", [])
    results: list[dict[str, Any]] = []
    passed = 0

    for check in checks:
        key = check["key"]
        expected = check["expected"]

        # Resolve effective value: DB > config object
        if key in db_settings and db_settings[key] is not None:
            actual = str(db_settings[key])
        else:
            actual = str(getattr(app_settings, key, ""))

        is_passing = actual.lower() == expected.lower()
        if is_passing:
            passed += 1

        results.append(
            {
                "key": key,
                "label": check["label"],
                "description": check["description"],
                "expected": expected,
                "actual": actual,
                "passing": is_passing,
            }
        )

    total = len(checks)
    if passed == total:
        status = "compliant"
    elif passed > 0:
        status = "partial"
    else:
        status = "non_compliant"

    return {
        "status": status,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "check_results": results,
    }


def apply_template(db: Session, name: str, applied_by: str = "admin") -> dict[str, Any]:
    """Apply a compliance template by writing its settings to the database.

    Returns a summary of what was applied.
    """
    from app.utils.settings_service import save_setting_to_db

    defn = COMPLIANCE_TEMPLATES.get(name)
    if defn is None:
        return {"success": False, "error": f"Unknown template: {name}"}

    template = get_template_by_name(db, name)
    if template is None:
        return {"success": False, "error": f"Template not found in database: {name}"}

    applied_settings: dict[str, str] = {}
    errors: list[str] = []

    for key, value in defn["settings"].items():
        try:
            save_setting_to_db(db, key, value, changed_by=f"compliance:{name}")
            applied_settings[key] = value
        except Exception as e:
            errors.append(f"{key}: {e}")
            logger.error(f"Failed to apply compliance setting {key}={value}: {e}")

    # Update the template record
    now = datetime.now(timezone.utc)
    template.enabled = True
    template.settings_json = json.dumps(applied_settings)
    template.applied_at = now
    template.applied_by = applied_by

    # Evaluate and store status
    eval_result = evaluate_template_status(db, name)
    template.status = eval_result["status"]

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(f"Failed to update compliance template record: {name}")
        return {"success": False, "error": "Database commit failed"}

    logger.info(f"Applied compliance template '{name}' by {applied_by}: {len(applied_settings)} settings written")

    return {
        "success": len(errors) == 0,
        "template": name,
        "applied_settings": applied_settings,
        "errors": errors,
        "status": eval_result,
    }


def get_compliance_summary(db: Session) -> dict[str, Any]:
    """Return a high-level compliance dashboard summary across all templates."""
    templates = db.query(ComplianceTemplate).order_by(ComplianceTemplate.name).all()
    summary: list[dict[str, Any]] = []
    total_checks = 0
    total_passed = 0

    for t in templates:
        eval_result = evaluate_template_status(db, t.name)
        total_checks += eval_result["total"]
        total_passed += eval_result["passed"]
        summary.append(
            {
                "name": t.name,
                "display_name": t.display_name,
                "enabled": t.enabled,
                "status": eval_result["status"],
                "total": eval_result["total"],
                "passed": eval_result["passed"],
                "failed": eval_result["failed"],
                "applied_at": t.applied_at.isoformat() if t.applied_at else None,
                "applied_by": t.applied_by,
            }
        )

    overall = "compliant" if total_checks > 0 and total_passed == total_checks else "non_compliant"
    if 0 < total_passed < total_checks:
        overall = "partial"

    return {
        "overall_status": overall,
        "total_checks": total_checks,
        "total_passed": total_passed,
        "total_failed": total_checks - total_passed,
        "templates": summary,
    }
