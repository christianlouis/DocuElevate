"""Per-file workflow plan snapshots derived from processing profiles."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from app.models import FileRecord, Pipeline, PipelineStep
from app.utils.pipeline_stages import PIPELINE_STEP_TO_STAGES

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

WORKFLOW_PLAN_VERSION = 1


def resolve_file_pipeline(db: Session, file_record: FileRecord) -> Pipeline | None:
    """Resolve explicit, owner-default, then system-default processing profile."""
    pipeline = None
    if file_record.pipeline_id:
        pipeline = db.query(Pipeline).filter(Pipeline.id == file_record.pipeline_id).first()
    if pipeline is None and file_record.owner_id:
        pipeline = (
            db.query(Pipeline)
            .filter(
                Pipeline.owner_id == file_record.owner_id,
                Pipeline.is_default.is_(True),
                Pipeline.is_active.is_(True),
            )
            .first()
        )
    if pipeline is None:
        pipeline = (
            db.query(Pipeline)
            .filter(
                Pipeline.owner_id.is_(None),
                Pipeline.is_default.is_(True),
                Pipeline.is_active.is_(True),
            )
            .first()
        )
    return pipeline


def build_workflow_plan(db: Session, file_record: FileRecord) -> dict[str, Any]:
    """Build an ordered execution/status plan from the selected profile."""
    pipeline = resolve_file_pipeline(db, file_record)
    steps: list[dict[str, Any]] = []
    if pipeline is not None:
        pipeline_steps = (
            db.query(PipelineStep)
            .filter(PipelineStep.pipeline_id == pipeline.id)
            .order_by(PipelineStep.position, PipelineStep.id)
            .all()
        )
        for step in pipeline_steps:
            if not step.enabled:
                continue
            try:
                config = json.loads(step.config) if step.config else {}
            except (json.JSONDecodeError, TypeError):
                config = {}
            steps.append(
                {
                    "step_type": step.step_type,
                    "label": step.label or step.step_type,
                    "position": step.position,
                    "config": config if isinstance(config, dict) else {},
                    "stages": PIPELINE_STEP_TO_STAGES.get(step.step_type, []),
                }
            )

    return {
        "version": WORKFLOW_PLAN_VERSION,
        "pipeline_id": pipeline.id if pipeline else None,
        "pipeline_name": pipeline.name if pipeline else None,
        "assignment_source": file_record.pipeline_assignment_source or "default",
        "assignment_reason": file_record.pipeline_assignment_reason,
        "steps": steps,
    }


def snapshot_workflow_plan(db: Session, file_record: FileRecord) -> dict[str, Any]:
    """Persist and return the plan that status/retry must use for this run."""
    plan = build_workflow_plan(db, file_record)
    file_record.workflow_plan = json.dumps(plan, ensure_ascii=False, separators=(",", ":"))
    file_record.workflow_plan_version = WORKFLOW_PLAN_VERSION
    if plan["pipeline_id"] is not None and file_record.pipeline_id is None:
        file_record.pipeline_id = plan["pipeline_id"]
    db.flush()
    return plan


def load_workflow_plan(file_record: FileRecord) -> dict[str, Any] | None:
    """Load a valid persisted workflow plan, if available."""
    if not file_record.workflow_plan:
        return None
    try:
        plan = json.loads(file_record.workflow_plan)
    except (json.JSONDecodeError, TypeError):
        return None
    return plan if isinstance(plan, dict) and isinstance(plan.get("steps"), list) else None


def workflow_stage_keys(file_record: FileRecord) -> list[str] | None:
    """Return ordered unique runtime stages from a file's immutable plan."""
    plan = load_workflow_plan(file_record)
    if plan is None or not plan["steps"]:
        return None
    ordered = ["create_file_record"]
    for step in plan["steps"]:
        for stage in step.get("stages", []):
            if stage not in ordered:
                ordered.append(stage)
    return ordered
