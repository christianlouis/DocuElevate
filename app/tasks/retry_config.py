#!/usr/bin/env python3
"""Retry configuration for Celery tasks with exponential backoff and jitter.

Provides a :class:`BaseTaskWithRetry` Celery task base class that implements
configurable retry logic with exponential backoff and optional ±20 % random
jitter.  Pre-defined subclasses offer task-type-specific retry policies:

* :class:`BaseTaskWithRetry` – general default (3 retries: 60 s, 300 s, 900 s)
* :class:`OcrTaskWithRetry` – longer waits for OCR / AI API calls
* :class:`UploadTaskWithRetry` – standard waits for cloud-storage uploads

Usage::

    from app.tasks.retry_config import BaseTaskWithRetry, OcrTaskWithRetry

    @celery.task(base=OcrTaskWithRetry, bind=True)
    def my_ocr_task(self, ...):
        ...
"""

import logging
import math
import random
from typing import Any

from celery import Task

logger = logging.getLogger(__name__)


def mark_bulk_terminal_failure(file_id: int | None, error: str) -> None:
    """Persist a terminal bulk failure; the reconciler releases capacity."""
    if file_id is None:
        return
    from app.database import SessionLocal
    from app.models import UploadItem

    with SessionLocal() as db:
        db.query(UploadItem).filter(
            UploadItem.file_id == file_id,
            UploadItem.state.in_(("accepted", "queued", "processing")),
        ).update({"state": "failed", "error": str(error)[:1000]}, synchronize_session=False)
        db.commit()


def _file_id_from_task_call(task: Task, args: tuple[Any, ...], kwargs: dict[str, Any]) -> int | None:
    """Return a named ``file_id`` after binding a task's actual signature.

    Celery preserves positional arguments in ``on_failure``. Several
    document-pipeline tasks use a positional ``file_id``, so consulting only
    ``kwargs`` would leave their accepted bulk uploads reserved forever.
    """
    import inspect

    try:
        signature = inspect.signature(task.run)
        if "file_id" not in signature.parameters:
            return None
        file_id = signature.bind_partial(*args, **kwargs).arguments.get("file_id")
    except (TypeError, ValueError):
        return None
    return file_id if isinstance(file_id, int) and not isinstance(file_id, bool) else None


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

#: Default per-retry countdowns in seconds (1 min, 5 min, 15 min).
DEFAULT_RETRY_DELAYS: list[int] = [60, 300, 900]


def _parse_delay_string(value: str) -> list[int]:
    """Parse a comma-separated string of integers into a list.

    Args:
        value: Comma-separated integer string, e.g. ``"60,300,900"``.

    Returns:
        Parsed list of integers, e.g. ``[60, 300, 900]``.
    """
    return [int(v.strip()) for v in value.split(",") if v.strip()]


def compute_countdown(
    retries: int,
    base_delays: list[int] | None = None,
    jitter: bool = True,
) -> int:
    """Compute the countdown in seconds for the next retry attempt.

    Selects the appropriate base delay for the given retry number.  When all
    defined delays are exhausted the last delay is doubled for each additional
    attempt.  An optional ±20 % jitter is then applied to spread retry storms.

    Args:
        retries: Current retry count (0-based; 0 = first retry attempt).
        base_delays: Ordered list of base countdown values (in seconds) for
            each retry attempt.  ``None`` uses :data:`DEFAULT_RETRY_DELAYS`.
        jitter: When ``True``, apply ±20 % random jitter to the countdown.

    Returns:
        Countdown in seconds (minimum 1 s).

    Examples::

        >>> compute_countdown(0, [60, 300, 900], jitter=False)
        60
        >>> compute_countdown(1, [60, 300, 900], jitter=False)
        300
        >>> compute_countdown(3, [60, 300, 900], jitter=False)  # beyond list
        1800
    """
    delays = base_delays if base_delays is not None else DEFAULT_RETRY_DELAYS

    if not delays:
        base = 60
    elif retries < len(delays):
        base = delays[retries]
    else:
        # Exhausted defined delays – double the last value for each extra attempt.
        extra = retries - len(delays) + 1
        base = delays[-1] * (2**extra)

    if jitter:
        # ±20 % uniform jitter – not cryptographic, S311 is intentional.
        jitter_factor = 1.0 + random.uniform(-0.2, 0.2)  # noqa: S311
        base = int(base * jitter_factor)

    return max(base, 1)


class BaseTaskWithRetry(Task):
    """Celery task base class with exponential backoff and optional jitter.

    Automatically retries on any :class:`Exception` using delays derived from
    :attr:`retry_delays`.  When :attr:`retry_delays` is ``None`` the value is
    read from ``TASK_RETRY_DELAYS`` (env-var / settings); if that is also
    unset :data:`DEFAULT_RETRY_DELAYS` (``[60, 300, 900]`` seconds) is used.

    Override class attributes in subclasses to customise per-task-type policy:

    * ``max_retries`` (``int``) – maximum retry attempts; default ``3``.
    * ``retry_delays`` (``list[int] | None``) – per-retry countdowns in
      seconds; ``None`` falls back to settings / :data:`DEFAULT_RETRY_DELAYS`.
    * ``retry_jitter`` (``bool``) – add ±20 % jitter; default ``True``.
    """

    #: Retry on any exception raised inside the task body.
    autoretry_for = (Exception,)

    #: Maximum number of retry attempts.
    max_retries: int = 3

    #: Pass max_retries through autoretry_for; no countdown override here
    #: (our retry() method injects the countdown instead).
    retry_kwargs: dict = {"max_retries": 3}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Keep Celery task-specific retry options from mutating the base."""
        super().__init_subclass__(**kwargs)
        cls.retry_kwargs = dict(cls.retry_kwargs)

    #: Per-retry countdown values (seconds).  ``None`` → settings / DEFAULT.
    retry_delays: list[int] | None = None

    #: Apply ±20 % random jitter to prevent thundering-herd problems.
    retry_jitter: bool = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Persist a durable terminal signal after Celery exhausts retries.

        ``log_task_progress`` records individual attempts and therefore cannot
        distinguish a retryable failure from an exhausted task.  The Celery
        lifecycle callback is only called for the final failure, so marking
        the accepted upload here lets the capacity reconciler release it
        without prematurely releasing pending retries.
        """
        try:
            file_id = _file_id_from_task_call(self, tuple(args or ()), dict(kwargs or {}))
            if file_id is not None:
                mark_bulk_terminal_failure(file_id, f"{self.name}: {str(exc)[:1000]}")
        except Exception:
            logger.warning("Could not persist terminal bulk-upload failure for %s", task_id, exc_info=True)
        return super().on_failure(exc, task_id, args, kwargs, einfo)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Keep account deletion from racing an active document task."""
        import inspect

        signature = inspect.signature(self.run)
        if "file_id" not in signature.parameters and "owner_id" not in signature.parameters:
            return super().__call__(*args, **kwargs)
        try:
            bound = signature.bind_partial(*args, **kwargs)
        except TypeError:
            return super().__call__(*args, **kwargs)
        file_id = bound.arguments.get("file_id")
        explicit_owner = bound.arguments.get("owner_id")
        from app.config import settings
        from app.database import SessionLocal
        from app.models import FileRecord
        from app.services.account_deletion import deletion_blocked
        from app.services.account_lifecycle_lock import account_lifecycle_lock

        with SessionLocal() as db:
            file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first() if file_id else None
            if file_id and not file_record:
                return {"status": "skipped", "reason": "file_not_found"}
            if file_record and explicit_owner and file_record.owner_id != explicit_owner:
                return {"status": "skipped", "reason": "owner_mismatch"}
            owner = file_record.owner_id if file_record else explicit_owner
            # New process_document invocations may use the configured default owner.
            if not owner and "owner_id" in signature.parameters and not file_id:
                owner = settings.default_owner_id
            if not owner:
                if not settings.multi_user_enabled:
                    return super().__call__(*args, **kwargs)
                return {"status": "skipped", "reason": "owner_unavailable"}
            with account_lifecycle_lock(db, owner):
                # The deletion could have fenced the owner while this task waited.
                db.expire_all()
                if deletion_blocked(db, owner):
                    return {"status": "skipped", "reason": "account_deletion"}
                if (
                    file_id
                    and not db.query(FileRecord.id)
                    .filter(FileRecord.id == file_id, FileRecord.owner_id == owner)
                    .first()
                ):
                    return {"status": "skipped", "reason": "file_not_found"}
                return super().__call__(*args, **kwargs)

    def retry(
        self,
        args: Any = None,
        kwargs: Any = None,
        exc: BaseException | None = None,
        throw: bool = True,
        eta: Any = None,
        countdown: int | None = None,
        max_retries: int | None = None,
        **options: Any,
    ) -> Any:
        """Retry the task, injecting the backoff countdown when not supplied.

        If *countdown* is not explicitly provided (and *eta* is not set) the
        countdown is computed via :func:`compute_countdown` using this task's
        :attr:`retry_delays` and :attr:`retry_jitter` settings.
        """
        quota_retry = False
        if exc is not None:
            try:
                from app.utils.provider_limits import ProviderQuotaError  # noqa: PLC0415

                quota_retry = isinstance(exc, ProviderQuotaError)
            except ImportError:  # pragma: no cover - defensive import guard
                pass
        if quota_retry:
            try:
                from app.config import settings  # noqa: PLC0415

                max_retries = int(getattr(settings, "provider_limits_max_retries", 20))
            except (ImportError, TypeError, ValueError):  # pragma: no cover
                max_retries = 20

        if countdown is None and eta is None:
            hinted = getattr(exc, "retry_after", None) if exc is not None else None
            countdown = (
                max(1, math.ceil(float(hinted)))
                if hinted is not None
                else compute_countdown(
                    retries=self.request.retries,
                    base_delays=self._effective_retry_delays(),
                    jitter=self.retry_jitter,
                )
            )
            logger.debug(
                "Retry %d/%d for task %s in %d s",
                self.request.retries + 1,
                max_retries if max_retries is not None else self.max_retries,
                self.name,
                countdown,
            )

        return super().retry(
            args=args,
            kwargs=kwargs,
            exc=exc,
            throw=throw,
            eta=eta,
            countdown=countdown,
            max_retries=max_retries,
            **options,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _effective_retry_delays(self) -> list[int]:
        """Return the retry delays to use, with settings-level override support.

        Priority (highest first):

        1. Explicit class-level ``retry_delays`` attribute (not ``None``).
        2. ``TASK_RETRY_DELAYS`` environment variable / setting.
        3. :data:`DEFAULT_RETRY_DELAYS` module-level constant.
        """
        if self.retry_delays is not None:
            return self.retry_delays

        # Lazily read from settings to avoid circular imports at module load.
        try:
            from app.config import settings  # noqa: PLC0415

            raw = getattr(settings, "task_retry_delays", None)
            if raw:
                if isinstance(raw, list):
                    return [int(v) for v in raw]
                if isinstance(raw, str):
                    return _parse_delay_string(raw)
        except Exception as exc:  # pragma: no cover
            logger.debug("Could not read task_retry_delays from settings: %s", exc)

        return DEFAULT_RETRY_DELAYS


# ---------------------------------------------------------------------------
# Task-type-specific retry policies
# ---------------------------------------------------------------------------


class OcrTaskWithRetry(BaseTaskWithRetry):
    """Retry policy for OCR and document-intelligence API tasks.

    Uses longer initial delays to allow transient API rate-limit windows to
    clear before the next attempt.

    Default: 3 retries at 120 s, 600 s, 1800 s.
    """

    retry_delays: list[int] = [120, 600, 1800]


class UploadTaskWithRetry(BaseTaskWithRetry):
    """Retry policy for cloud-storage upload tasks.

    Uses the standard default delays (60 s, 300 s, 900 s) which are
    appropriate for most transient upload failures (network blips, rate
    limits, temporary service outages).
    """

    # Inherits DEFAULT_RETRY_DELAYS via retry_delays = None.
