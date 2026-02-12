"""
Migration utility to backfill FileProcessingStep table from existing ProcessingLog entries.

This script analyzes historical logs and populates the FileProcessingStep table
for files that were processed before the status tracking table was created.
"""

import logging
from typing import Dict, List

from sqlalchemy.orm import Session

from app.models import FileProcessingStep, ProcessingLog

logger = logging.getLogger(__name__)


def migrate_logs_to_steps(db: Session, file_id: int, dry_run: bool = False) -> Dict:
    """
    Migrate ProcessingLog entries to FileProcessingStep for a single file.

    Analyzes all logs for the file and creates/updates FileProcessingStep entries
    based on the latest status per step found in the logs.

    Args:
        db: Database session
        file_id: ID of the file to migrate
        dry_run: If True, don't commit changes, just report what would be done

    Returns:
        Dictionary with migration results:
        {
            "file_id": 123,
            "steps_created": 5,
            "steps_updated": 3,
            "steps_skipped": 2,
            "errors": []
        }
    """
    results = {"file_id": file_id, "steps_created": 0, "steps_updated": 0, "steps_skipped": 0, "errors": []}

    try:
        # Get all logs for this file, ordered by timestamp
        logs = (
            db.query(ProcessingLog)
            .filter(ProcessingLog.file_id == file_id)
            .order_by(ProcessingLog.timestamp.asc())
            .all()
        )

        if not logs:
            logger.info(f"No logs found for file {file_id}")
            return results

        # Parse logs to extract latest status per step
        step_states = _parse_logs_to_step_states(logs)

        # Create or update FileProcessingStep entries
        for step_name, state in step_states.items():
            existing_step = (
                db.query(FileProcessingStep)
                .filter(FileProcessingStep.file_id == file_id, FileProcessingStep.step_name == step_name)
                .first()
            )

            if existing_step:
                # Update existing step only if it differs
                if (
                    existing_step.status != state["status"]
                    or existing_step.started_at != state["started_at"]
                    or existing_step.completed_at != state["completed_at"]
                ):
                    logger.info(
                        f"Updating step {step_name} for file {file_id}: {existing_step.status} -> {state['status']}"
                    )
                    existing_step.status = state["status"]
                    existing_step.started_at = state["started_at"]
                    existing_step.completed_at = state["completed_at"]
                    existing_step.error_message = state["error_message"]
                    results["steps_updated"] += 1
                else:
                    logger.debug(f"Step {step_name} for file {file_id} already up to date")
                    results["steps_skipped"] += 1
            else:
                # Create new step
                logger.info(f"Creating step {step_name} for file {file_id} with status {state['status']}")
                new_step = FileProcessingStep(
                    file_id=file_id,
                    step_name=step_name,
                    status=state["status"],
                    started_at=state["started_at"],
                    completed_at=state["completed_at"],
                    error_message=state["error_message"],
                )
                db.add(new_step)
                results["steps_created"] += 1

        if not dry_run:
            db.commit()
            logger.info(
                f"Migration complete for file {file_id}: "
                f"{results['steps_created']} created, "
                f"{results['steps_updated']} updated, "
                f"{results['steps_skipped']} skipped"
            )
        else:
            db.rollback()
            logger.info(f"Dry run complete for file {file_id} (no changes committed)")

    except Exception as e:
        logger.error(f"Error migrating file {file_id}: {str(e)}")
        results["errors"].append(str(e))
        db.rollback()

    return results


def _parse_logs_to_step_states(logs: List[ProcessingLog]) -> Dict[str, Dict]:
    """
    Parse logs to determine the final state of each step.

    Processes logs in chronological order to build a state machine
    tracking the progression of each step.

    Args:
        logs: List of ProcessingLog entries ordered by timestamp

    Returns:
        Dictionary mapping step_name to state dict:
        {
            "step_name": {
                "status": "success",
                "started_at": datetime,
                "completed_at": datetime,
                "error_message": None
            }
        }
    """
    step_states = {}

    for log in logs:
        step_name = log.step_name
        status = log.status.lower()

        # Initialize step state if first time seeing this step
        if step_name not in step_states:
            step_states[step_name] = {
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "error_message": None,
            }

        # Update state based on log entry
        if status == "in_progress":
            # Step started
            if step_states[step_name]["started_at"] is None:
                step_states[step_name]["started_at"] = log.timestamp
            step_states[step_name]["status"] = "in_progress"

        elif status == "success":
            # Step completed successfully
            if step_states[step_name]["started_at"] is None:
                # If we never saw in_progress, assume it started around this time
                step_states[step_name]["started_at"] = log.timestamp
            step_states[step_name]["status"] = "success"
            step_states[step_name]["completed_at"] = log.timestamp
            step_states[step_name]["error_message"] = None

        elif status == "failure":
            # Step failed
            if step_states[step_name]["started_at"] is None:
                step_states[step_name]["started_at"] = log.timestamp
            step_states[step_name]["status"] = "failure"
            step_states[step_name]["completed_at"] = log.timestamp
            step_states[step_name]["error_message"] = log.message

        elif status in ["pending", "queued"]:
            # Only update if step hasn't started yet
            if step_states[step_name]["status"] == "pending":
                step_states[step_name]["status"] = "pending"

        # Note: If we see success/failure after a previous success/failure,
        # the later one wins (represents retry/reprocessing)

    return step_states


def migrate_all_files(db: Session, batch_size: int = 100, dry_run: bool = False) -> Dict:
    """
    Migrate all files that have logs but no FileProcessingStep entries.

    Args:
        db: Database session
        batch_size: Number of files to process in each batch
        dry_run: If True, don't commit changes

    Returns:
        Dictionary with overall migration statistics:
        {
            "total_files": 150,
            "files_migrated": 145,
            "files_failed": 5,
            "total_steps_created": 1200,
            "total_steps_updated": 350,
            "errors": [...]
        }
    """
    summary = {
        "total_files": 0,
        "files_migrated": 0,
        "files_failed": 0,
        "total_steps_created": 0,
        "total_steps_updated": 0,
        "total_steps_skipped": 0,
        "errors": [],
    }

    # Find all files that have logs but no steps
    files_with_logs = db.query(ProcessingLog.file_id).distinct().all()
    file_ids_with_logs = {file_id for (file_id,) in files_with_logs if file_id is not None}

    files_with_steps = db.query(FileProcessingStep.file_id).distinct().all()
    file_ids_with_steps = {file_id for (file_id,) in files_with_steps}

    files_to_migrate = list(file_ids_with_logs - file_ids_with_steps)

    summary["total_files"] = len(files_to_migrate)
    logger.info(f"Found {len(files_to_migrate)} files to migrate")

    # Process in batches
    for i in range(0, len(files_to_migrate), batch_size):
        batch = files_to_migrate[i : i + batch_size]
        logger.info(
            f"Processing batch {i // batch_size + 1}: files {i + 1} to {min(i + batch_size, len(files_to_migrate))}"
        )

        for file_id in batch:
            result = migrate_logs_to_steps(db, file_id, dry_run=dry_run)

            if result["errors"]:
                summary["files_failed"] += 1
                summary["errors"].extend(result["errors"])
            else:
                summary["files_migrated"] += 1
                summary["total_steps_created"] += result["steps_created"]
                summary["total_steps_updated"] += result["steps_updated"]
                summary["total_steps_skipped"] += result["steps_skipped"]

    logger.info(
        f"Migration summary: {summary['files_migrated']} files migrated, "
        f"{summary['files_failed']} failed, "
        f"{summary['total_steps_created']} steps created, "
        f"{summary['total_steps_updated']} steps updated"
    )

    return summary


def verify_migration(db: Session, file_id: int) -> Dict:
    """
    Verify that migration for a file is correct by comparing logs to steps.

    Args:
        db: Database session
        file_id: ID of the file to verify

    Returns:
        Dictionary with verification results:
        {
            "file_id": 123,
            "is_valid": True,
            "discrepancies": [],
            "log_steps": ["step1", "step2"],
            "table_steps": ["step1", "step2"]
        }
    """
    result = {"file_id": file_id, "is_valid": True, "discrepancies": [], "log_steps": [], "table_steps": []}

    # Get logs and parse them
    logs = (
        db.query(ProcessingLog).filter(ProcessingLog.file_id == file_id).order_by(ProcessingLog.timestamp.asc()).all()
    )

    if not logs:
        result["discrepancies"].append("No logs found for file")
        result["is_valid"] = False
        return result

    expected_states = _parse_logs_to_step_states(logs)
    result["log_steps"] = sorted(expected_states.keys())

    # Get actual steps from table
    actual_steps = db.query(FileProcessingStep).filter(FileProcessingStep.file_id == file_id).all()
    result["table_steps"] = sorted([s.step_name for s in actual_steps])

    # Compare
    actual_states = {s.step_name: s for s in actual_steps}

    # Check for missing steps
    for step_name in expected_states:
        if step_name not in actual_states:
            result["discrepancies"].append(f"Step '{step_name}' missing from table")
            result["is_valid"] = False
            continue

        # Compare status
        expected = expected_states[step_name]
        actual = actual_states[step_name]

        if expected["status"] != actual.status:
            result["discrepancies"].append(
                f"Step '{step_name}' status mismatch: " f"expected '{expected['status']}', got '{actual.status}'"
            )
            result["is_valid"] = False

    # Check for extra steps in table
    for step_name in actual_states:
        if step_name not in expected_states:
            result["discrepancies"].append(f"Extra step '{step_name}' in table not found in logs")
            # Not marking as invalid since this might be intentional

    return result
