"""Resumable, recursive Dropbox corpus import for preprod."""

import json
import logging
import os
import uuid

import redis
from celery.result import AsyncResult

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import DocumentIntake, DropboxImportJob, DropboxImportObject, UserIntegration
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils.allowed_types import ALLOWED_EXTENSIONS
from app.utils.dropbox_credentials import resolve_dropbox_oauth_credentials
from app.utils.encryption import decrypt_value
from app.utils.filename_utils import sanitize_filename

logger = logging.getLogger(__name__)

_CELERY_QUEUES = ("document_processor", "default", "celery")


def _pending_queue_depth() -> int | None:
    """Return pending interactive pipeline work, failing open if Redis is unavailable."""
    try:
        client = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        return sum(int(client.llen(queue)) for queue in _CELERY_QUEUES)
    except Exception:  # noqa: BLE001
        logger.warning("Could not inspect queue depth before corpus backfill", exc_info=True)
        return None


def schedule_dropbox_corpus_import(job_id: str, *, countdown: int = 0) -> AsyncResult:
    """Schedule low-priority corpus coordination without blocking interactive uploads."""
    return run_dropbox_corpus_import.apply_async(
        args=[job_id],
        countdown=countdown,
        priority=settings.corpus_backfill_task_priority,
    )


def _bounded_config_int(
    config: dict,
    key: str,
    default: int,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    """Return a validated integer integration override or the global default."""
    raw_value = config.get(key)
    try:
        value = int(raw_value) if raw_value not in (None, "") else default
    except (TypeError, ValueError):
        logger.warning("Ignoring invalid %s integration override: %r", key, raw_value)
        value = default
    value = max(minimum, value)
    return min(value, maximum) if maximum is not None else value


def queue_dropbox_watch_sync(integration_id: int, db_session=None) -> dict:
    """Queue the initial true-up or the next cursor-based delta for a watch source."""
    owns_session = db_session is None
    db = db_session or SessionLocal()
    try:
        integration = db.query(UserIntegration).filter(UserIntegration.id == integration_id).first()
        if not integration or not integration.is_active:
            return {"status": "skipped", "detail": "Dropbox watch integration is inactive"}
        try:
            config = json.loads(integration.config or "{}")
        except (json.JSONDecodeError, TypeError):
            return {"status": "skipped", "detail": "Integration configuration is invalid"}
        if config.get("source_type") != "dropbox" or not config.get("true_up_existing"):
            return {"status": "skipped", "detail": "Dropbox true-up is disabled"}

        root_path = str(config.get("folder_path") or "").strip()
        if not root_path:
            return {"status": "skipped", "detail": "Dropbox folder has not been selected"}

        credentials = _decode(integration.credentials)
        try:
            resolve_dropbox_oauth_credentials(credentials)
        except ValueError:
            return {"status": "skipped", "detail": "Dropbox authorization is incomplete"}

        active = (
            db.query(DropboxImportJob)
            .filter(
                DropboxImportJob.integration_id == integration.id,
                DropboxImportJob.state.in_(("queued", "running")),
            )
            .first()
        )
        if active:
            return {"status": "running", "job_id": active.id}

        previous = (
            db.query(DropboxImportJob)
            .filter(
                DropboxImportJob.integration_id == integration.id,
                DropboxImportJob.root_path == root_path,
                DropboxImportJob.state == "completed",
            )
            .order_by(DropboxImportJob.created_at.desc())
            .first()
        )
        job = DropboxImportJob(
            id=str(uuid.uuid4()),
            integration_id=integration.id,
            owner_id=integration.owner_id,
            root_path=root_path,
            # A completed recursive listing cursor becomes an incremental
            # Dropbox change cursor for the next watch cycle.
            cursor=previous.cursor if previous else None,
        )
        db.add(job)
        db.commit()
        job_id = job.id
        mode = "incremental" if job.cursor else "true-up"
    finally:
        if owns_session:
            db.close()

    schedule_dropbox_corpus_import(job_id)
    return {"status": "queued", "job_id": job_id, "mode": mode}


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
    try:
        app_key, app_secret, refresh_token = resolve_dropbox_oauth_credentials(credentials)
    except ValueError as exc:
        raise RuntimeError("Dropbox source credentials are incomplete") from exc
    return dropbox.Dropbox(
        oauth2_refresh_token=refresh_token,
        app_key=app_key,
        app_secret=app_secret,
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
    queued = False
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
        queued = True
        return "queued"
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
        if not queued and os.path.exists(target_path):
            os.remove(target_path)


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

        try:
            config = json.loads(integration.config or "{}")
        except (json.JSONDecodeError, TypeError):
            config = {}
        if not isinstance(config, dict):
            config = {}
        high_watermark = _bounded_config_int(
            config,
            "backfill_queue_high_watermark",
            settings.corpus_backfill_queue_high_watermark,
            minimum=1,
        )
        queue_depth = _pending_queue_depth()
        if queue_depth is not None and queue_depth >= high_watermark:
            job.state = "queued"
            job.error = f"Paused for queue backpressure at depth {queue_depth}"
            db.commit()
            delay = _bounded_config_int(
                config,
                "backfill_resume_delay_seconds",
                settings.corpus_backfill_resume_delay_seconds,
                minimum=1,
            )
            schedule_dropbox_corpus_import(job.id, countdown=delay)
            return {
                "status": "paused",
                "job_id": job.id,
                "queue_depth": queue_depth,
                "resume_in_seconds": delay,
            }

        job.state = "running"
        job.error = None
        db.commit()
        client = _dropbox_client(integration)
        if job.cursor:
            page = client.files_list_folder_continue(job.cursor)
        else:
            root = "" if job.root_path in {"", "/"} else job.root_path
            batch_size = _bounded_config_int(
                config,
                "backfill_batch_size",
                settings.corpus_backfill_batch_size,
                minimum=1,
                maximum=2000,
            )
            page = client.files_list_folder(root, recursive=True, include_deleted=False, limit=batch_size)

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
            # Persist each enqueued document before moving on. If the worker is
            # interrupted, Dropbox returns the same page and idempotency skips
            # the already committed entries instead of creating orphan tasks.
            db.commit()

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
        schedule_dropbox_corpus_import(job_id)
    return result
