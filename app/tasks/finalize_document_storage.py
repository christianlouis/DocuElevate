#!/usr/bin/env python3

import os
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
# Import the shared Celery instance
from app.celery_app import celery

# 1) Import the aggregator task
from app.tasks.send_to_all import send_to_all_destinations, get_configured_services_from_validator

# Import notification utility
from app.utils.notification import notify_file_processed


@celery.task(base=BaseTaskWithRetry)
def finalize_document_storage(original_file: str, processed_file: str, metadata: dict):
    """
    Final storage step after embedding metadata.
    We will now call 'send_to_all_destinations' to push the final PDF to Dropbox/Nextcloud/Paperless.
    After uploading, send a notification about the processed file.
    """
    print(f"[INFO] Finalizing document storage for {processed_file}")

    # Determine which destinations are configured
    configured_destinations = []
    try:
        configured_services = get_configured_services_from_validator()
        # Get list of service names that are configured
        for service_name, is_configured in configured_services.items():
            if is_configured:
                # Format service names for display
                display_name = service_name.replace('_', ' ').title()
                configured_destinations.append(display_name)
    except Exception as e:
        print(f"[WARNING] Could not determine configured destinations: {e}")
        configured_destinations = ["configured destinations"]

    # 2) Enqueue uploads to all destinations (Dropbox, Nextcloud, Paperless)
    send_to_all_destinations.delay(processed_file)

    # 3) Send notification about successful file processing
    try:
        # Get file information
        file_size = os.path.getsize(processed_file) if os.path.exists(processed_file) else 0
        filename = os.path.basename(processed_file)
        
        notify_file_processed(
            filename=filename,
            file_size=file_size,
            metadata=metadata,
            destinations=configured_destinations
        )
    except Exception as e:
        print(f"[WARNING] Failed to send file processed notification: {e}")

    return {
        "status": "Completed",
        "file": processed_file
    }
