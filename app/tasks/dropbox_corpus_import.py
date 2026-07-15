"""Resumable, recursive Dropbox corpus import for preprod."""

import json
import logging
import os
import shutil
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from threading import local

import redis
from celery.result import AsyncResult
from sqlalchemy.exc import IntegrityError

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import (
    CorpusLlmDailyUsage,
    DocumentIntake,
    DropboxImportJob,
    DropboxImportObject,
    FileRecord,
    ProcessingLog,
    UserIntegration,
)
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils.allowed_types import ALLOWED_EXTENSIONS
from app.utils.dropbox_credentials import resolve_dropbox_oauth_credentials
from app.utils.encryption import decrypt_value
from app.utils.filename_utils import sanitize_filename

logger = logging.getLogger(__name__)

_OCR_CAPABLE_EXTENSIONS = frozenset(
    {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic", ".heif"}
)

_CELERY_QUEUES = ("document_processor", "default", "celery")
_REDIS_PRIORITY_SEPARATOR = "\x06\x16"
_REDIS_PRIORITY_STEPS = range(10)
_METADATA_PROMPT_OUTPUT_HEADROOM = 1500
_MAX_BUDGET_RECHECK_SECONDS = 15 * 60
_PREFETCH_THREAD_STATE = local()


class CorpusDailyBudgetReached(RuntimeError):
    """Raised when a corpus import must wait for the next UTC token window."""

    def __init__(self, *, used: int, budget: int, retry_after_seconds: int) -> None:
        super().__init__(f"Daily corpus LLM token budget reached ({used}/{budget})")
        self.used = used
        self.budget = budget
        self.retry_after_seconds = retry_after_seconds


class CorpusDailyBudgetUnavailable(RuntimeError):
    """Raised when an enabled cost guard cannot reserve tokens safely."""


def _next_utc_reset(now: datetime) -> datetime:
    tomorrow = now.date() + timedelta(days=1)
    return datetime.combine(tomorrow, datetime.min.time(), tzinfo=timezone.utc)


def _reserve_corpus_llm_tokens(*, budget: int | None = None) -> tuple[date | None, int]:
    """Atomically reserve durable LLM capacity for one corpus document.

    A zero budget disables the guard. When enabled, Redis is deliberately
    not involved because it is an intentionally ephemeral task broker. The
    database reservation survives Redis restarts and fails closed if durable
    accounting is unavailable. Interactive uploads do not use this path.
    """
    budget = int(settings.corpus_backfill_daily_llm_token_budget if budget is None else budget)
    if budget <= 0:
        return None, 0

    reservation = max(
        int(settings.corpus_backfill_llm_token_reservation_per_document),
        int(settings.metadata_max_input_tokens) + _METADATA_PROMPT_OUTPUT_HEADROOM,
    )
    now = datetime.now(timezone.utc)
    reset_at = _next_utc_reset(now)
    usage_date = now.date()
    try:
        # The guarded UPDATE is atomic in PostgreSQL and SQLite. If two
        # workers see a missing UTC-day row, one insert wins and the other
        # retries the guarded UPDATE.
        for _attempt in range(2):
            with SessionLocal() as budget_db:
                updated = (
                    budget_db.query(CorpusLlmDailyUsage)
                    .filter(
                        CorpusLlmDailyUsage.usage_date == usage_date,
                        CorpusLlmDailyUsage.reserved_tokens <= budget - reservation,
                    )
                    .update(
                        {CorpusLlmDailyUsage.reserved_tokens: CorpusLlmDailyUsage.reserved_tokens + reservation},
                        synchronize_session=False,
                    )
                )
                if updated:
                    budget_db.commit()
                    return usage_date, reservation

                existing = (
                    budget_db.query(CorpusLlmDailyUsage).filter(CorpusLlmDailyUsage.usage_date == usage_date).first()
                )
                if existing is not None or reservation > budget:
                    used = int(existing.reserved_tokens) if existing is not None else 0
                    retry_after = max(1, int((reset_at - now).total_seconds()) + 5)
                    raise CorpusDailyBudgetReached(
                        used=used,
                        budget=budget,
                        retry_after_seconds=retry_after,
                    )

                budget_db.add(CorpusLlmDailyUsage(usage_date=usage_date, reserved_tokens=reservation))
                try:
                    budget_db.commit()
                    return usage_date, reservation
                except IntegrityError:
                    budget_db.rollback()
                    # A concurrent worker may have created the row. Retry the
                    # guarded UPDATE once; other failures become fail-closed.
                    continue
        raise CorpusDailyBudgetUnavailable(
            "Could not establish durable corpus LLM token accounting after a concurrent update"
        )
    except CorpusDailyBudgetReached:
        raise
    except CorpusDailyBudgetUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CorpusDailyBudgetUnavailable("Could not reserve the enabled corpus LLM token budget") from exc


def _release_corpus_llm_tokens(reservation: tuple[date | None, int]) -> None:
    """Release a reservation when no pipeline task was queued."""
    usage_date, amount = reservation
    if usage_date is None or amount <= 0:
        return
    try:
        with SessionLocal() as budget_db:
            budget_db.query(CorpusLlmDailyUsage).filter(
                CorpusLlmDailyUsage.usage_date == usage_date,
                CorpusLlmDailyUsage.reserved_tokens >= amount,
            ).update(
                {CorpusLlmDailyUsage.reserved_tokens: CorpusLlmDailyUsage.reserved_tokens - amount},
                synchronize_session=False,
            )
            budget_db.commit()
    except Exception:  # noqa: BLE001
        # Keeping a conservative reservation only delays background work; it
        # is safer than losing track of usage and allowing an overage.
        logger.warning("Could not release unused corpus LLM token reservation", exc_info=True)


def _pending_queue_depth() -> int | None:
    """Return queued plus worker-reserved pipeline work, failing open on Redis errors."""
    try:
        client = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        queue_keys = (
            queue if priority == 0 else f"{queue}{_REDIS_PRIORITY_SEPARATOR}{priority}"
            for queue in _CELERY_QUEUES
            for priority in _REDIS_PRIORITY_STEPS
        )
        queued = sum(int(client.llen(queue_key)) for queue_key in queue_keys)
        # Kombu moves Redis messages into this hash as soon as a worker
        # reserves them. Counting it closes the prefetch gap where the visible
        # lists are empty while dozens of tasks are active or reserved.
        in_flight = int(client.hlen("unacked"))
        return queued + in_flight
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


def schedule_dropbox_corpus_ocr_backlog(job_id: str, *, countdown: int = 0) -> AsyncResult:
    """Schedule low-priority OCR-only work after an index-first true-up."""
    return run_dropbox_corpus_ocr_backlog.apply_async(
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
        if previous and _deferred_ocr_enabled(
            config, index_only=previous.is_backfill and _index_first_enabled(integration)
        ):
            # The regular watch poll is the durable recovery trigger if the
            # completion-to-coordinator broker publication was interrupted.
            schedule_dropbox_corpus_ocr_backlog(previous.id)
        job = DropboxImportJob(
            id=str(uuid.uuid4()),
            integration_id=integration.id,
            owner_id=integration.owner_id,
            root_path=root_path,
            # A completed recursive listing cursor becomes an incremental
            # Dropbox change cursor for the next watch cycle.
            cursor=previous.cursor if previous else None,
            is_backfill=previous is None,
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


def _dropbox_client_from_stored_credentials(stored_credentials: str | None):
    import dropbox

    credentials = _decode(stored_credentials)
    try:
        app_key, app_secret, refresh_token = resolve_dropbox_oauth_credentials(credentials)
    except ValueError as exc:
        raise RuntimeError("Dropbox source credentials are incomplete") from exc
    return dropbox.Dropbox(
        oauth2_refresh_token=refresh_token,
        app_key=app_key,
        app_secret=app_secret,
    )


def _dropbox_client(integration: UserIntegration):
    return _dropbox_client_from_stored_credentials(integration.credentials)


def _load_page_entry_keys(job: DropboxImportJob) -> set[str]:
    """Load stable identities already committed within the current Dropbox page."""
    try:
        values = json.loads(job.page_entry_keys or "[]")
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("Saved Dropbox page progress is not valid JSON") from exc
    if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
        raise RuntimeError("Saved Dropbox page progress must be a list of entry identities")
    return set(values)


def _dropbox_file_key(entry) -> str:
    """Return an immutable identity for one Dropbox file revision."""
    file_id = str(getattr(entry, "id", "") or "").strip()
    revision = str(getattr(entry, "rev", "") or "").strip()
    if not file_id or not revision:
        raise RuntimeError("Dropbox file metadata is missing its stable id or revision")
    return f"{file_id}:{revision}"


def _fail_import_job(db, job: DropboxImportJob, message: str) -> None:
    """Persist a terminal coordinator error before surfacing it to Celery."""
    job.state = "failed"
    job.error = message
    db.commit()


def _configured_backfill_token_budget(integration: UserIntegration) -> int:
    """Resolve the live per-integration backfill budget with a global fallback."""
    try:
        config = json.loads(integration.config or "{}")
    except (json.JSONDecodeError, TypeError):
        config = {}
    if not isinstance(config, dict):
        config = {}
    enabled = config.get("backfill_token_budget_enabled", True)
    if enabled is False or str(enabled).strip().lower() in {"0", "false", "no", "off"}:
        return 0
    return _bounded_config_int(
        config,
        "backfill_daily_llm_token_budget",
        settings.corpus_backfill_daily_llm_token_budget,
        minimum=0,
    )


def _index_first_enabled(integration: UserIntegration) -> bool:
    """Return whether this source explicitly opts into RAG-only true-up."""
    if not settings.vector_index_enabled:
        return False
    try:
        config = json.loads(integration.config or "{}")
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(config, dict):
        return False
    value = config.get("backfill_index_first_enabled", False)
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


def _index_first_download_concurrency(config: dict, *, index_only: bool) -> int:
    """Return bounded Dropbox prefetch concurrency for an opt-in initial backfill."""
    if not index_only:
        return 1
    return _bounded_config_int(
        config,
        "backfill_download_concurrency",
        settings.corpus_backfill_download_concurrency,
        minimum=1,
        maximum=8,
    )


def _deferred_ocr_enabled(config: dict, *, index_only: bool) -> bool:
    """Return whether an index-first source opts into the OCR-only second pass."""
    if not index_only:
        return False
    value = config.get(
        "backfill_deferred_ocr_enabled",
        settings.corpus_backfill_deferred_ocr_enabled,
    )
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


def _entry_can_be_prefetched(entry) -> bool:
    """Reject entries that the durable importer would skip before downloading."""
    filename = sanitize_filename(entry.name) or "document"
    extension = os.path.splitext(filename)[1].lower()
    return extension in ALLOWED_EXTENSIONS and getattr(entry, "size", 0) <= settings.max_upload_size


def _prefetch_dropbox_entry(integration_id: int, stored_credentials: str | None, entry) -> str:
    """Download one Dropbox object into an isolated temporary file.

    Each thread creates its own Dropbox client because requests sessions are
    not guaranteed to be thread-safe. The caller owns cleanup of the returned
    path, including when the durable import later discovers a duplicate.
    """
    filename = sanitize_filename(entry.name) or "document"
    extension = os.path.splitext(filename)[1].lower()
    target_path = os.path.join(settings.workdir, f"dropbox_prefetch_{integration_id}_{uuid.uuid4().hex}{extension}")
    temporary_path = f"{target_path}.part"
    try:
        if (
            not hasattr(_PREFETCH_THREAD_STATE, "client")
            or getattr(_PREFETCH_THREAD_STATE, "stored_credentials", None) != stored_credentials
        ):
            _PREFETCH_THREAD_STATE.client = _dropbox_client_from_stored_credentials(stored_credentials)
            _PREFETCH_THREAD_STATE.stored_credentials = stored_credentials
        client = _PREFETCH_THREAD_STATE.client
        _metadata, response = client.files_download(entry.path_lower)
        content = response.content
        if len(content) > settings.max_upload_size:
            raise ValueError("Dropbox object exceeds the configured upload limit")
        with open(temporary_path, "wb") as output:
            output.write(content)
        os.replace(temporary_path, target_path)
        return target_path
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)


def _reserve_job_llm_tokens(job: DropboxImportJob, integration: UserIntegration) -> tuple[date | None, int]:
    """Apply the daily cost guard only to an initial corpus backfill."""
    if not job.is_backfill:
        return None, 0
    budget = _configured_backfill_token_budget(integration)
    if budget <= 0:
        return None, 0
    return _reserve_corpus_llm_tokens(budget=budget)


def _import_file(
    db,
    job: DropboxImportJob,
    integration: UserIntegration,
    client,
    entry,
    *,
    prefetched_path: str | None = None,
) -> str:
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
    if imported and imported.revision == entry.rev and imported.state != "failed":
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

    index_only = job.is_backfill and _index_first_enabled(integration)
    reservation = (None, 0) if index_only else _reserve_job_llm_tokens(job, integration)
    target_path = os.path.join(settings.workdir, f"dropbox_{integration.id}_{uuid.uuid4().hex}{extension}")
    temporary_path = f"{target_path}.part"
    queued = False
    try:
        if prefetched_path:
            if os.path.getsize(prefetched_path) > settings.max_upload_size:
                return "failed"
            os.replace(prefetched_path, target_path)
        else:
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

        source_task_id = str(uuid.uuid4()) if index_only else None
        intake.local_path = target_path
        intake.task_id = source_task_id
        intake.state = "queued"
        intake.error = None
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
        imported.task_id = source_task_id
        imported.state = "queued"
        if index_only:
            # A fast worker must be able to see the correlation id before it
            # reports needs_ocr/indexed/failed against the durable ledgers.
            db.commit()
        else:
            db.flush()

        from app.api.intake import _queue_document

        try:
            task = _queue_document(
                target_path,
                filename,
                None,
                job.owner_id if settings.multi_user_enabled else None,
                index_only=index_only,
                task_id=source_task_id,
            )
        except Exception as exc:
            if index_only:
                intake.state = "failed"
                intake.error = type(exc).__name__
                imported.state = "failed"
                db.commit()
            raise
        if not index_only:
            intake.task_id = task.id
            imported.task_id = task.id
            db.flush()
        queued = True
        return "queued"
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
        if not queued and os.path.exists(target_path):
            os.remove(target_path)
        if not queued:
            _release_corpus_llm_tokens(reservation)


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

        try:
            committed_entry_keys = _load_page_entry_keys(job)
        except RuntimeError as exc:
            _fail_import_job(db, job, str(exc))
            raise

        index_only = job.is_backfill and _index_first_enabled(integration)
        deferred_ocr = _deferred_ocr_enabled(config, index_only=index_only)
        download_concurrency = _index_first_download_concurrency(config, index_only=index_only)
        integration_id = integration.id
        stored_credentials = integration.credentials
        prefetch_executor: ThreadPoolExecutor | None = None
        prefetch_futures: dict[str, Future[str]] = {}
        prefetch_entries: list[tuple[str, object]] = []
        prefetch_position = 0

        def fill_prefetch_window() -> None:
            """Keep at most one bounded window of downloads on disk or in flight."""
            nonlocal prefetch_position
            if prefetch_executor is None:
                return
            while len(prefetch_futures) < download_concurrency and prefetch_position < len(prefetch_entries):
                entry_key, entry = prefetch_entries[prefetch_position]
                prefetch_position += 1
                prefetch_futures[entry_key] = prefetch_executor.submit(
                    _prefetch_dropbox_entry,
                    integration_id,
                    stored_credentials,
                    entry,
                )

        try:
            if download_concurrency > 1:
                prefetch_executor = ThreadPoolExecutor(
                    max_workers=download_concurrency,
                    thread_name_prefix="dropbox-corpus",
                )
                for entry in page.entries:
                    if not isinstance(entry, dropbox.files.FileMetadata) or not _entry_can_be_prefetched(entry):
                        continue
                    try:
                        entry_key = _dropbox_file_key(entry)
                    except RuntimeError:
                        continue
                    if entry_key not in committed_entry_keys:
                        prefetch_entries.append((entry_key, entry))
                fill_prefetch_window()

            for entry in page.entries:
                if not isinstance(entry, dropbox.files.FileMetadata):
                    continue
                try:
                    entry_key = _dropbox_file_key(entry)
                except RuntimeError as exc:
                    _fail_import_job(db, job, str(exc))
                    raise
                if entry_key in committed_entry_keys:
                    continue
                job.discovered += 1
                prefetched_path = None
                try:
                    future = prefetch_futures.pop(entry_key, None)
                    if future:
                        try:
                            prefetched_path = future.result()
                        finally:
                            fill_prefetch_window()
                    outcome = _import_file(
                        db,
                        job,
                        integration,
                        client,
                        entry,
                        prefetched_path=prefetched_path,
                    )
                    if prefetched_path and not os.path.exists(prefetched_path):
                        prefetched_path = None  # ownership moved into the durable pipeline
                except CorpusDailyBudgetReached as exc:
                    job.discovered -= 1
                    job.state = "queued"
                    job.error = str(exc)
                    db.commit()
                    # Redis' default Celery visibility timeout is shorter than a
                    # possible wait to the next UTC day. Short rechecks avoid a
                    # long-lived ETA task being restored and delivered twice.
                    recheck_in = min(exc.retry_after_seconds, _MAX_BUDGET_RECHECK_SECONDS)
                    schedule_dropbox_corpus_import(job.id, countdown=recheck_in)
                    return {
                        "status": "paused",
                        "reason": "daily_llm_token_budget",
                        "job_id": job.id,
                        "tokens_reserved": exc.used,
                        "token_budget": exc.budget,
                        "resume_in_seconds": recheck_in,
                        "budget_resets_in_seconds": exc.retry_after_seconds,
                    }
                except CorpusDailyBudgetUnavailable as exc:
                    job.discovered -= 1
                    job.state = "queued"
                    job.error = str(exc)
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
                        "reason": "daily_llm_token_budget_unavailable",
                        "job_id": job.id,
                        "resume_in_seconds": delay,
                    }
                except Exception as exc:
                    logger.exception("Dropbox import failed for %s: %s", entry.path_display, exc)
                    outcome = "failed"
                finally:
                    if prefetched_path and os.path.exists(prefetched_path):
                        os.remove(prefetched_path)
                if outcome == "queued":
                    job.downloaded += 1
                    job.queued += 1
                elif outcome == "skipped":
                    job.skipped += 1
                else:
                    job.failed += 1
                committed_entry_keys.add(entry_key)
                job.page_entry_keys = json.dumps(sorted(committed_entry_keys))
                # Persist each enqueued document before moving on. If the worker is
                # interrupted, stable file-revision identities prevent recounting
                # committed entries. Unlike a numeric offset, this remains safe if
                # the Dropbox page changes between budget rechecks.
                db.commit()
        finally:
            if prefetch_executor is not None:
                prefetch_executor.shutdown(wait=True, cancel_futures=True)
            for future in prefetch_futures.values():
                if not future.done() or future.cancelled() or future.exception() is not None:
                    continue
                prefetched_path = future.result()
                if os.path.exists(prefetched_path):
                    os.remove(prefetched_path)

        job.cursor = page.cursor
        job.page_entry_keys = "[]"
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
    elif deferred_ocr:
        schedule_dropbox_corpus_ocr_backlog(job_id)
    return result


def _set_deferred_ocr_state(
    db,
    imported: DropboxImportObject,
    state: str,
    error: str | None = None,
) -> None:
    """Keep the import object and its intake ledger aligned."""
    imported.state = state
    if imported.intake_id:
        intake = db.query(DocumentIntake).filter(DocumentIntake.id == imported.intake_id).first()
        if intake:
            intake.state = state
            intake.error = error


def _deferred_ocr_file_id(db, imported: DropboxImportObject) -> int | None:
    """Resolve the FileRecord created by the original index-first task."""
    if not imported.task_id:
        return None
    row = (
        db.query(ProcessingLog.file_id)
        .filter(
            ProcessingLog.task_id == imported.task_id,
            ProcessingLog.file_id.isnot(None),
        )
        .order_by(ProcessingLog.timestamp.desc(), ProcessingLog.id.desc())
        .first()
    )
    return int(row[0]) if row and row[0] is not None else None


def _claim_deferred_state(db, imported: DropboxImportObject, expected: str, claimed: str) -> bool:
    """Atomically claim one import row and align its intake ledger."""
    updated = (
        db.query(DropboxImportObject)
        .filter(DropboxImportObject.id == imported.id, DropboxImportObject.state == expected)
        .update({DropboxImportObject.state: claimed}, synchronize_session=False)
    )
    if not updated:
        db.rollback()
        return False
    if imported.intake_id:
        db.query(DocumentIntake).filter(DocumentIntake.id == imported.intake_id).update(
            {DocumentIntake.state: claimed, DocumentIntake.error: None},
            synchronize_session=False,
        )
    db.commit()
    db.refresh(imported)
    return True


def _recover_stale_deferred_claims(db, integration_id: int, *, stale_before: datetime) -> int:
    """Return abandoned coordinator claims to a recoverable durable state."""
    mappings = {"ocr_claimed": "needs_ocr", "indexing": "ocr_complete"}
    recovered = 0
    for claimed, ready in mappings.items():
        rows = (
            db.query(DropboxImportObject)
            .join(DocumentIntake, DocumentIntake.id == DropboxImportObject.intake_id)
            .filter(
                DropboxImportObject.integration_id == integration_id,
                DropboxImportObject.state == claimed,
                DocumentIntake.updated_at < stale_before,
            )
            .all()
        )
        for imported in rows:
            _set_deferred_ocr_state(db, imported, ready, "Recovered stale deferred claim")
            recovered += 1
    if recovered:
        db.commit()
    return recovered


@celery.task(base=BaseTaskWithRetry, bind=True, name="run_dropbox_corpus_ocr_backlog")
def run_dropbox_corpus_ocr_backlog(self, job_id: str) -> dict:
    """Queue bounded OCR-only work for scanned index-first corpus documents."""
    should_recheck = False
    recheck_delay = settings.corpus_backfill_ocr_recheck_seconds
    queued = 0
    failed = 0

    with SessionLocal() as db:
        job = db.query(DropboxImportJob).filter(DropboxImportJob.id == job_id).first()
        if not job:
            return {"status": "skipped", "detail": "Import job not found"}
        integration = db.query(UserIntegration).filter(UserIntegration.id == job.integration_id).first()
        if not integration or not integration.is_active:
            return {"status": "skipped", "detail": "Dropbox source integration is inactive"}
        try:
            config = json.loads(integration.config or "{}")
        except (json.JSONDecodeError, TypeError):
            config = {}
        if not isinstance(config, dict):
            config = {}
        if job.state != "completed":
            return {"status": "waiting", "job_id": job.id, "detail": "Initial corpus import is not complete"}
        if not _deferred_ocr_enabled(config, index_only=job.is_backfill and _index_first_enabled(integration)):
            return {"status": "disabled", "job_id": job.id}

        recheck_delay = _bounded_config_int(
            config,
            "backfill_ocr_recheck_seconds",
            settings.corpus_backfill_ocr_recheck_seconds,
            minimum=1,
        )
        stale_before = datetime.now(timezone.utc) - timedelta(seconds=max(300, recheck_delay * 10))
        _recover_stale_deferred_claims(db, integration.id, stale_before=stale_before)
        high_watermark = _bounded_config_int(
            config,
            "backfill_queue_high_watermark",
            settings.corpus_backfill_queue_high_watermark,
            minimum=1,
        )
        queue_depth = _pending_queue_depth()
        if queue_depth is not None and queue_depth >= high_watermark:
            should_recheck = True
            result = {
                "status": "paused",
                "job_id": job.id,
                "queue_depth": queue_depth,
                "resume_in_seconds": recheck_delay,
            }
        else:
            batch_size = _bounded_config_int(
                config,
                "backfill_ocr_batch_size",
                settings.corpus_backfill_ocr_batch_size,
                minimum=1,
                maximum=100,
            )
            if queue_depth is not None:
                batch_size = min(batch_size, max(0, high_watermark - queue_depth))
            remaining_slots = batch_size

            from app.tasks.vector_index import index_document_vectors

            index_candidates = (
                db.query(DropboxImportObject)
                .filter(
                    DropboxImportObject.integration_id == integration.id,
                    DropboxImportObject.state == "ocr_complete",
                )
                .order_by(DropboxImportObject.imported_at, DropboxImportObject.id)
                .limit(remaining_slots)
                .all()
            )
            for imported in index_candidates:
                if not _claim_deferred_state(db, imported, "ocr_complete", "indexing"):
                    continue
                file_id = _deferred_ocr_file_id(db, imported)
                record = db.query(FileRecord).filter(FileRecord.id == file_id).first() if file_id else None
                if not record or not record.ocr_text or not imported.task_id:
                    _set_deferred_ocr_state(db, imported, "failed", "OCR text is unavailable for indexing")
                    db.commit()
                    failed += 1
                    continue
                try:
                    index_document_vectors.apply_async(
                        args=[record.id],
                        kwargs={"source_task_id": imported.task_id},
                        priority=settings.corpus_backfill_task_priority,
                    )
                except Exception as exc:
                    _set_deferred_ocr_state(db, imported, "ocr_complete", type(exc).__name__)
                    db.commit()
                    continue
                queued += 1
                remaining_slots -= 1

            candidates = (
                db.query(DropboxImportObject)
                .filter(
                    DropboxImportObject.integration_id == integration.id,
                    DropboxImportObject.state == "needs_ocr",
                )
                .order_by(DropboxImportObject.imported_at, DropboxImportObject.id)
                .limit(remaining_slots)
                .all()
            )

            from app.tasks.process_with_ocr import process_with_ocr

            for imported in candidates:
                if not _claim_deferred_state(db, imported, "needs_ocr", "ocr_claimed"):
                    continue
                file_id = _deferred_ocr_file_id(db, imported)
                record = db.query(FileRecord).filter(FileRecord.id == file_id).first() if file_id else None
                source_path = record.original_file_path if record else None
                if not record or not source_path or not os.path.exists(source_path) or not imported.task_id:
                    _set_deferred_ocr_state(db, imported, "failed", "Original corpus file is unavailable")
                    db.commit()
                    failed += 1
                    continue

                extension = os.path.splitext(record.original_filename or imported.remote_path)[1].lower()
                if extension not in _OCR_CAPABLE_EXTENSIONS:
                    _set_deferred_ocr_state(db, imported, "needs_conversion", "PDF conversion is required")
                    db.commit()
                    continue
                staged_name = f"corpus_ocr_{imported.id}_{uuid.uuid4().hex}{extension or '.pdf'}"
                tmp_dir = os.path.join(settings.workdir, "tmp")
                os.makedirs(tmp_dir, exist_ok=True)
                staged_path = os.path.join(tmp_dir, staged_name)
                try:
                    shutil.copy2(source_path, staged_path)
                    process_with_ocr.apply_async(
                        args=[staged_name, record.id],
                        kwargs={"index_only": True, "source_task_id": imported.task_id},
                        priority=settings.corpus_backfill_task_priority,
                    )
                    _set_deferred_ocr_state(db, imported, "ocr_queued")
                    db.commit()
                    queued += 1
                except Exception as exc:
                    if os.path.exists(staged_path):
                        os.remove(staged_path)
                    _set_deferred_ocr_state(db, imported, "needs_ocr", type(exc).__name__)
                    db.commit()

            pending = (
                db.query(DropboxImportObject.id)
                .filter(
                    DropboxImportObject.integration_id == integration.id,
                    DropboxImportObject.state.in_(
                        (
                            "needs_ocr",
                            "ocr_claimed",
                            "ocr_queued",
                            "ocr_retrying",
                            "ocr_complete",
                            "indexing",
                        )
                    ),
                )
                .first()
                is not None
            )
            should_recheck = pending
            result = {
                "status": "running" if pending else "completed",
                "job_id": job.id,
                "queued": queued,
                "failed": failed,
                "resume_in_seconds": recheck_delay if pending else None,
            }

    if should_recheck:
        schedule_dropbox_corpus_ocr_backlog(job_id, countdown=recheck_delay)
    return result
