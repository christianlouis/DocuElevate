#!/usr/bin/env python3

import logging
import os

# Import the shared Celery instance
from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import FileRecord
from app.tasks.retry_config import BaseTaskWithRetry

# Import the aggregator tasks and validator
from app.tasks.send_to_all import (
    get_configured_services_from_validator,
    get_user_destination_count,
    send_to_all_destinations,
    send_to_user_destinations,
)

# Import database and logging utils from main
from app.utils import log_task_progress

# Import notification utility
from app.utils.notification import notify_file_processed

logger = logging.getLogger(__name__)


@celery.task(base=BaseTaskWithRetry, bind=True)
def finalize_document_storage(self, original_file: str, processed_file: str, metadata: dict, file_id: int = None):
    """
    Final storage step after embedding metadata.
    Routes the processed document to the appropriate destination(s):

    1. If the document has an identified owner and that owner has active
       DESTINATION UserIntegrations, the file is uploaded to each of those
       integrations (user-specific routing).
    2. Otherwise the file is forwarded to the globally-configured destinations
       via :func:`send_to_all_destinations` (system-wide fallback).

    After queuing uploads, optional PDF/A archival conversion and embedding
    computation are triggered, and a completion notification is sent.
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Finalizing document storage for {processed_file}")

    # 1. Update Database Status
    log_task_progress(
        task_id,
        "finalize_document_storage",
        "in_progress",
        f"Finalizing: {os.path.basename(processed_file)}",
        file_id=file_id,
    )

    # 2. Resolve file_id and owner_id from the database
    owner_id = None
    if file_id is None:
        with SessionLocal() as db:
            # Only as a last resort, try to find by exact match on local_filename
            tmp_path = os.path.join(settings.workdir, "tmp", os.path.basename(original_file))
            file_record = db.query(FileRecord).filter(FileRecord.local_filename == tmp_path).first()
            if file_record:
                file_id = file_record.id
                owner_id = file_record.owner_id
    else:
        with SessionLocal() as db:
            file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
            if file_record:
                owner_id = file_record.owner_id

    # 3. Determine configured destinations for notification
    configured_destinations = []
    try:
        configured_services = get_configured_services_from_validator()
        for service_name, is_configured in configured_services.items():
            if is_configured:
                display_name = service_name.replace("_", " ").title()
                configured_destinations.append(display_name)
    except Exception as e:
        logger.warning(f"[WARNING] Could not determine configured destinations: {e}")
        configured_destinations = ["configured destinations"]

    # 4. Queue Uploads — prefer user-specific destinations when available
    log_task_progress(
        task_id, "finalize_document_storage", "success", "Queuing uploads to destinations", file_id=file_id
    )

    user_dest_count = 0
    if owner_id:
        try:
            user_dest_count = get_user_destination_count(owner_id)
        except Exception as e:
            logger.warning("[%s] Could not query user destination count for owner=%s: %s", task_id, owner_id, e)

    if owner_id and user_dest_count > 0:
        # User has configured their own destinations → use those exclusively
        logger.info(
            "[%s] Routing to %d user-specific destination(s) for owner=%s",
            task_id,
            user_dest_count,
            owner_id,
        )
        send_to_user_destinations.delay(processed_file, owner_id, file_id)
    else:
        # No user-specific destinations → fall back to global configuration
        logger.info("[%s] No user-specific destinations found; using global destinations", task_id)
        send_to_all_destinations.delay(processed_file, True, file_id)

    # 4a. Trigger PDF/A archival conversion if enabled
    if settings.enable_pdfa_conversion:
        try:
            from app.tasks.convert_to_pdfa import convert_to_pdfa

            logger.info(f"[{task_id}] PDF/A conversion enabled, queueing archival conversion")
            convert_to_pdfa.delay(file_id)
        except Exception as e:
            logger.warning(f"[{task_id}] Could not queue PDF/A conversion: {e}")

    # 4b. Queue embedding computation
    if file_id is not None:
        try:
            from app.tasks.compute_embedding import compute_document_embedding

            compute_document_embedding.delay(file_id)
            logger.info(f"[{task_id}] Queued embedding computation for file {file_id}")
        except Exception as e:
            logger.warning(f"[{task_id}] Could not queue embedding task: {e}")

    # 5. Send Notification
    try:
        file_size = os.path.getsize(processed_file) if os.path.exists(processed_file) else 0
        filename = os.path.basename(processed_file)

        notify_file_processed(
            filename=filename, file_size=file_size, metadata=metadata, destinations=configured_destinations
        )
    except Exception as e:
        logger.warning(f"[WARNING] Failed to send file processed notification: {e}")

    return {"status": "Completed", "file": processed_file}
