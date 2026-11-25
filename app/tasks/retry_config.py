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
from celery.exceptions import Reject, Retry
from sqlalchemy import exc as sqlalchemy_exc

logger = logging.getLogger(__name__)


# PostgreSQL errors that mean the transaction/connection must be retried after
# the database has recovered.  These are deliberately narrower than every
# OperationalError so malformed SQL and other deterministic task failures keep
# the normal finite retry/terminal-failure policy.
_TRANSIENT_POSTGRES_CODES = {
    "08000",  # connection_exception
    "08003",  # connection_does_not_exist
    "08006",  # connection_failure
    "57P01",  # admin_shutdown
    "57P02",  # crash_shutdown
    "57P03",  # cannot_connect_now
    "25P03",  # idle_in_transaction_session_timeout
    "40001",  # serialization_failure
    "40P01",  # deadlock_detected
    "55P03",  # lock_not_available / lock timeout
    "53300",  # too_many_connections
}


def is_transient_database_error(error: BaseException) -> bool:
    """Return whether a database error is safe to retry without abandoning work."""
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None:
        if id(current) in visited:
            break
        visited.add(id(current))
        message = str(current).lower()
        if any(
            marker in message
            for marker in (
                "remaining connection slots are reserved",
                "too many clients already",
                "deadlock detected",
                "could not serialize access",
                "lock timeout",
            )
        ):
            return True
        if isinstance(current, sqlalchemy_exc.TimeoutError):
            return True
        if isinstance(current, sqlalchemy_exc.DisconnectionError):
            return True
        if isinstance(current, sqlalchemy_exc.DBAPIError):
            if current.connection_invalidated:
                return True
            orig = getattr(current, "orig", None)
            code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
            if code in _TRANSIENT_POSTGRES_CODES or (isinstance(code, str) and code.startswith("08")):
                return True
        current = current.__cause__ or current.__context__
    return False


def mark_bulk_processing(file_id: int | None) -> None:
    """Mark an accepted bulk item as processing when its pipeline starts."""
    if file_id is None:
        return
    from app.database import SessionLocal
    from app.models import UploadItem

    with SessionLocal() as db:
        db.query(UploadItem).filter(
            UploadItem.file_id == file_id,
            UploadItem.state.in_(("accepted", "queued")),
        ).update({"state": "processing"}, synchronize_session=False)
        db.commit()


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

        try:
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
                        db.rollback()
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
                    # The lifecycle lock uses its own dedicated connection.
                    # End this read transaction before running the document
                    # work so a worker cannot hold an idle transaction for the
                    # duration of OCR/upload processing.
                    db.rollback()
                    return super().__call__(*args, **kwargs)
        except (Retry, Reject):
            # Celery's autoretry wrapper may already have republished a body
            # failure. Never classify its chained DB exception a second time.
            raise
        except Exception as exc:
            # This guard runs before Celery's autoretry wrapper.  A pool or
            # account-lock failure here must follow the same durable retry path
            # as a DB failure raised by the task body.
            if is_transient_database_error(exc):
                raise self.retry(args=args, kwargs=kwargs, exc=exc)
            raise

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
        # A database outage must not consume the finite document retry budget.
        # Republish the original delivery with the same retry count so the
        # source file remains queued until the transaction can complete.
        if exc is not None and is_transient_database_error(exc) and not self.request.called_directly:
            request = self.request
            countdown = max(
                1,
                math.ceil(
                    float(getattr(exc, "retry_after", 60))
                    if getattr(exc, "retry_after", None) is not None
                    else compute_countdown(
                        retries=0,
                        base_delays=self._effective_retry_delays(),
                        jitter=self.retry_jitter,
                    )
                ),
            )
            sig = self.signature_from_request(
                request,
                args,
                kwargs,
                countdown=countdown,
                eta=None,
                retries=request.retries,
                **options,
            )
            retry = Retry(exc=exc, when=countdown, is_eager=request.is_eager, sig=sig)
            if request.is_eager:
                if throw:
                    raise retry
                return retry
            try:
                sig.apply_async()
            except Exception as publish_exc:
                # Late acknowledgement must requeue the original file if the
                # delayed retry could not be published.
                raise Reject(publish_exc, requeue=True)
            if throw:
                raise retry
            return retry

        # Local provider capacity is a durable wait, not a failed provider
        # attempt. Keep the retry counter unchanged so repeated waits cannot
        # exhaust the finite genuine-error retry allowance.
        from app.utils.provider_limits import ProviderQuotaExceeded

        if isinstance(exc, ProviderQuotaExceeded) and not self.request.called_directly:
            request = self.request
            countdown = max(1, math.ceil(float(exc.retry_after)))
            sig = self.signature_from_request(
                request,
                args,
                kwargs,
                countdown=countdown,
                eta=None,
                retries=request.retries,
                **options,
            )
            retry = Retry(exc=exc, when=countdown, is_eager=request.is_eager, sig=sig)
            if request.is_eager:
                if throw:
                    raise retry
                return retry
            try:
                sig.apply_async()
            except Exception as publish_exc:
                # Preserve the source for broker redelivery if publication of
                # the delayed copy fails.
                raise Reject(publish_exc, requeue=True)
            if throw:
                raise retry
            return retry

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

        # Celery's autoretry wrapper stores its mutable retry kwargs on the
        # task and ``Task.retry`` stores an ``override_max_retries`` attribute.
        # Both mutations normally get cleaned up by code after ``retry``
        # returns, but retry raises ``Retry`` in the normal worker path so that
        # cleanup is unreachable.  Restore them here so a provider retry does
        # not leak its larger finite budget into the next task invocation.
        sentinel = object()
        previous_override = getattr(self, "override_max_retries", sentinel)
        previous_retry_max = self.retry_kwargs.get("max_retries", sentinel)
        try:
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
        finally:
            if previous_override is sentinel:
                self.__dict__.pop("override_max_retries", None)
            else:
                self.override_max_retries = previous_override
            if previous_retry_max is sentinel:
                self.retry_kwargs.pop("max_retries", None)
            else:
                self.retry_kwargs["max_retries"] = previous_retry_max

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
    acks_late = True


class ProviderTaskWithRetry(BaseTaskWithRetry):
    """Retry policy for tasks that reserve shared AI-provider capacity."""

    acks_late = True


class UploadTaskWithRetry(BaseTaskWithRetry):
    """Retry policy for cloud-storage upload tasks.

    Uses the standard default delays (60 s, 300 s, 900 s) which are
    appropriate for most transient upload failures (network blips, rate
    limits, temporary service outages).
    """

    # The lease TTL is deliberately longer than these bounds.  A worker loss
    # therefore releases capacity by expiry without allowing an active upload
    # to be admitted twice.
    soft_time_limit = 900
    time_limit = 960
    acks_late = True

    def _upload_destination_key(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        import inspect

        try:
            bound = inspect.signature(self.run).bind_partial(*args, **kwargs)
            integration_id = bound.arguments.get("integration_id")
        except (TypeError, ValueError):
            integration_id = None
        if integration_id is not None:
            return f"user-integration:{integration_id}"
        return f"task:{self.name}"

    def retry(self, *args: Any, **kwargs: Any) -> Any:
        """Delay capacity waits without consuming provider-failure retries."""
        exc = kwargs.get("exc")
        from app.utils.upload_concurrency import UploadDestinationCapacityError

        if isinstance(exc, UploadDestinationCapacityError):
            request = self.request
            if request.called_directly:
                raise exc
            retry_args = kwargs.pop("args", None)
            retry_kwargs = kwargs.pop("kwargs", None)
            throw = kwargs.pop("throw", True)
            kwargs.pop("exc", None)
            kwargs.pop("countdown", None)
            kwargs.pop("eta", None)
            kwargs.pop("max_retries", None)
            countdown = max(30, int(exc.retry_after))
            sig = self.signature_from_request(
                request,
                retry_args,
                retry_kwargs,
                countdown=countdown,
                eta=None,
                retries=request.retries,
                **kwargs,
            )
            retry = Retry(exc=exc, when=countdown, is_eager=request.is_eager, sig=sig)
            if request.is_eager:
                if throw:
                    raise retry
                return retry
            try:
                sig.apply_async()
            except Exception as publish_exc:
                # Late acknowledgement preserves the source for redelivery
                # when publication of the delayed retry fails.
                raise Reject(publish_exc, requeue=True)
            if throw:
                raise retry
            return retry
        return super().retry(*args, **kwargs)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        from app.utils.upload_concurrency import UploadDestinationCapacityError, acquire, release

        try:
            lease = acquire(self._upload_destination_key(args, kwargs))
        except UploadDestinationCapacityError as exc:
            # __call__ runs outside Celery's autoretry wrapper. Route capacity
            # waits through the same request so they are delayed and do not
            # consume provider-failure retries.
            raise self.retry(args=args, kwargs=kwargs, exc=exc)
        try:
            return super().__call__(*args, **kwargs)
        finally:
            release(lease)

    # Inherits DEFAULT_RETRY_DELAYS via retry_delays = None.
