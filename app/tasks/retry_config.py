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
import random
from typing import Any

from celery import Task

logger = logging.getLogger(__name__)

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

    #: Per-retry countdown values (seconds).  ``None`` → settings / DEFAULT.
    retry_delays: list[int] | None = None

    #: Apply ±20 % random jitter to prevent thundering-herd problems.
    retry_jitter: bool = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        if countdown is None and eta is None:
            countdown = compute_countdown(
                retries=self.request.retries,
                base_delays=self._effective_retry_delays(),
                jitter=self.retry_jitter,
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
