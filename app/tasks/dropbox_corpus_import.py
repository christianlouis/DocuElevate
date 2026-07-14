"""Resumable, recursive Dropbox corpus import for preprod."""

import json
import logging
import os
import uuid

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import DocumentIntake, DropboxImportJob, DropboxImportObject, UserIntegration
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils.allowed_types import ALLOWED_EXTENSIONS
from app.utils.encryption import decrypt_value
from app.utils.filename_utils import sanitize_filename

logger = logging.getLogger(__name__)


def _decode(stored: str | None) -> dict:
    if not stored:
        return {}
    value = decrypt_value(stored)
    try:
        parsed = json.loads(value or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _dropbox_client(integration: UserIntegration):
    import dropbox

    credentials = _decode(integration.credentials)
    required = ("refresh_token", "app_key", "app_secret")
    if not all(credentials.get(key) for key in required):
        raise RuntimeError("Dropbox source credentials are incomplete")
    return dropbox.Dropbox(
        oauth2_refresh_token=credentials["refresh_token"],
        app_key=credentials["app_key"],
        app_secret=credentials["app_secret"],
    )


def _import_file(db, job: DropboxImportJob, integration: UserIntegration, client, entry) -> str:
    """Import one Dropbox FileMetadata and return queued/skipped/failed."""
    filename = sanitize_filename(entry.name) or "document"
    extension = os.path.splitext(filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        return "skipped"
    if getattr(entry, "size", 0) > settings.max_upload_size:
        logger.warning("Dropbox import skipped oversized file %s", entry.path_display)
        return "failed"

    imported = (
        db.query(DropboxImportObject)
        .filter(
            DropboxImportObject.integration_id == integration.id,
            DropboxImportObject.dropbox_file_id == entry.id,
        )
        .first()
    )
    if imported and imported.revision == entry.rev:
        return "skipped"

    idempotency_key = f"dropbox:{integration.id}:{entry.id}:{entry.rev}"
    intake = (
        db.query(DocumentIntake)
        .filter(
            DocumentIntake.principal_id == job.owner_id,
            DocumentIntake.idempotency_key == idempotency_key,
        )
        .first()
    )
    if intake and intake.state == "queued":
        if imported is None:
            imported = DropboxImportObject(
                integration_id=integration.id,
                dropbox_file_id=entry.id,
                revision=entry.rev,
                remote_path=entry.path_display or entry.path_lower,
                intake_id=intake.id,
                task_id=intake.task_id,
            )
            db.add(imported)
        return "skipped"

    target_path = os.path.join(settings.workdir, f"dropbox_{integration.id}_{uuid.uuid4().hex}{extension}")
    temporary_path = f"{target_path}.part"
    try:
        _metadata, response = client.files_download(entry.path_lower)
        content = response.content
        if len(content) > settings.max_upload_size:
            return "failed"
        with open(temporary_path, "wb") as output:
            output.write(content)
        os.replace(temporary_path, target_path)

        if intake is None:
            intake = DocumentIntake(
                principal_id=job.owner_id,
                idempotency_key=idempotency_key,
                source="dropbox-corpus",
                original_filename=filename,
                metadata_json=json.dumps(
                    {
                        "integration_id": integration.id,
                        "dropbox_file_id": entry.id,
                        "dropbox_revision": entry.rev,
                        "dropbox_path": entry.path_display or entry.path_lower,
                    }
                ),
            )
            db.add(intake)
            db.flush()

        from app.api.intake import _queue_document

        task = _queue_document(target_path, filename, None, job.owner_id if settings.multi_user_enabled else None)
        intake.local_path = target_path
        intake.task_id = task.id
        intake.state = "queued"
        if imported is None:
            imported = DropboxImportObject(
                integration_id=integration.id,
                dropbox_file_id=entry.id,
                revision=entry.rev,
                remote_path=entry.path_display or entry.path_lower,
            )
            db.add(imported)
        imported.revision = entry.rev
        imported.remote_path = entry.path_display or entry.path_lower
        imported.intake_id = intake.id
        imported.task_id = task.id
        imported.state = "queued"
        db.flush()
        return "queued"
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)


@celery.task(base=BaseTaskWithRetry, bind=True, name="run_dropbox_corpus_import")
def run_dropbox_corpus_import(self, job_id: str) -> dict:
    """Process one Dropbox result page and schedule the next page if needed."""
    import dropbox

    with SessionLocal() as db:
        job = db.query(DropboxImportJob).filter(DropboxImportJob.id == job_id).first()
        if not job:
            return {"status": "skipped", "detail": "Import job not found"}
        if job.state == "completed":
            return {"status": "completed", "job_id": job.id}
        integration = db.query(UserIntegration).filter(UserIntegration.id == job.integration_id).first()
        if not integration or not integration.is_active:
            raise RuntimeError("Dropbox source integration is missing or inactive")

        job.state = "running"
        db.commit()
        client = _dropbox_client(integration)
        if job.cursor:
            page = client.files_list_folder_continue(job.cursor)
        else:
            root = "" if job.root_path in {"", "/"} else job.root_path
            page = client.files_list_folder(root, recursive=True, include_deleted=False, limit=2000)

        for entry in page.entries:
            if not isinstance(entry, dropbox.files.FileMetadata):
                continue
            job.discovered += 1
            try:
                outcome = _import_file(db, job, integration, client, entry)
            except Exception as exc:
                logger.exception("Dropbox import failed for %s: %s", entry.path_display, exc)
                outcome = "failed"
            if outcome == "queued":
                job.downloaded += 1
                job.queued += 1
            elif outcome == "skipped":
                job.skipped += 1
            else:
                job.failed += 1

        job.cursor = page.cursor
        job.state = "running" if page.has_more else "completed"
        db.commit()
        result = {
            "status": job.state,
            "job_id": job.id,
            "discovered": job.discovered,
            "queued": job.queued,
            "skipped": job.skipped,
            "failed": job.failed,
        }

    if page.has_more:
        run_dropbox_corpus_import.delay(job_id)
    return result
