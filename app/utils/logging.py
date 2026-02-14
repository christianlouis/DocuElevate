import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import FileProcessingStep, ProcessingLog


class TaskLogCollector(logging.Handler):
    """
    A logging handler that buffers log messages per Celery task ID.

    When log_task_progress() is called, it drains the buffered messages
    for that task and stores them in the ProcessingLog.detail field.
    This captures all logger.info/error/warning output automatically.
    """

    def __init__(self) -> None:
        super().__init__()
        self._buffers: defaultdict[str, list[str]] = defaultdict(list)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        """Buffer a log record if it contains a task ID marker like [task-id]."""
        try:
            msg = self.format(record)
            # Extract task_id from messages formatted as "[task_id] ..."
            if msg and "[" in msg and "]" in msg:
                start = msg.index("[")
                end = msg.index("]", start)
                task_id = msg[start + 1 : end].strip()
                if task_id and len(task_id) >= 8:
                    with self._lock:
                        self._buffers[task_id].append(msg)
        except (ValueError, IndexError):
            pass

    def drain(self, task_id: str) -> str:
        """Return and clear all buffered messages for a task ID."""
        with self._lock:
            messages = self._buffers.pop(task_id, [])
        return "\n".join(messages) if messages else ""


# Singleton collector instance
_collector = TaskLogCollector()
_collector.setLevel(logging.DEBUG)
_collector_installed = False


def _ensure_collector_installed() -> None:
    """Install the TaskLogCollector on the root logger (once)."""
    global _collector_installed
    if not _collector_installed:
        root = logging.getLogger()
        # Avoid duplicate handlers
        if _collector not in root.handlers:
            root.addHandler(_collector)
        _collector_installed = True


def log_task_progress(
    task_id: str,
    step_name: str,
    status: str,
    message: str | None = None,
    file_id: int | None = None,
    detail: str | None = None,
) -> None:
    """
    Logs the progress of a Celery task to the database.

    If no explicit detail is provided, automatically drains any buffered
    worker log output for this task ID and stores it as the detail.

    Also updates the FileProcessingStep table for definitive status tracking.

    Args:
        task_id: The Celery task ID
        step_name: Name of the processing step
        status: Current status (pending, in_progress, success, failure)
        message: Short summary message
        file_id: Optional associated file record ID
        detail: Optional verbose log output for diagnostics.
                If not provided, buffered logger output is used automatically.
    """
    # Auto-capture buffered log output when no explicit detail is given
    if not detail and task_id:
        _ensure_collector_installed()
        collected = _collector.drain(task_id)
        if collected:
            detail = collected

    with SessionLocal() as db:
        # Log to ProcessingLog (for historical viewing)
        log_entry = ProcessingLog(
            task_id=task_id,
            step_name=step_name,
            status=status,
            message=message,
            file_id=file_id,
            detail=detail,
        )
        db.add(log_entry)

        # Update FileProcessingStep table (for status tracking) if file_id is provided
        if file_id and step_name:
            # Find or create the step record
            step_record = (
                db.query(FileProcessingStep)
                .filter(FileProcessingStep.file_id == file_id, FileProcessingStep.step_name == step_name)
                .first()
            )

            now = datetime.now(timezone.utc)

            if not step_record:
                # Create new step record
                step_record = FileProcessingStep(
                    file_id=file_id,
                    step_name=step_name,
                    status=status,
                    started_at=now if status == "in_progress" else None,
                    completed_at=now if status in ("success", "failure", "skipped") else None,
                    error_message=message if status == "failure" else None,
                )
                db.add(step_record)
            else:
                # Update existing step record
                step_record.status = status
                if status == "in_progress" and not step_record.started_at:
                    step_record.started_at = now
                if status in ("success", "failure", "skipped"):
                    step_record.completed_at = now
                if status == "failure":
                    step_record.error_message = message or detail

        db.commit()
