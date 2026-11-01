"""Regression coverage for terminal bulk-upload failures in Celery tasks."""

from unittest.mock import patch

from celery import Task

from app.tasks import retry_config
from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt
from app.tasks.process_with_ocr import process_with_ocr
from app.utils.provider_limits import ProviderRateLimited


def _terminal_failure(task, args, kwargs):
    with patch.object(Task, "on_failure", return_value=None):
        task.on_failure(RuntimeError("upstream permanently failed"), "task-id", args, kwargs, None)


def test_terminal_ocr_failure_marks_positional_file_id(monkeypatch):
    marked = []
    monkeypatch.setattr(
        retry_config, "mark_bulk_terminal_failure", lambda file_id, error: marked.append((file_id, error))
    )

    _terminal_failure(process_with_ocr, ("document.pdf", 721), {})

    assert marked and marked[0][0] == 721
    assert "upstream permanently failed" in marked[0][1]


def test_terminal_metadata_failure_marks_positional_file_id(monkeypatch):
    marked = []
    monkeypatch.setattr(
        retry_config, "mark_bulk_terminal_failure", lambda file_id, error: marked.append((file_id, error))
    )

    _terminal_failure(extract_metadata_with_gpt, ("document.pdf", "text", 722), {})

    assert marked and marked[0][0] == 722


def test_terminal_failure_ignores_noninteger_file_id(monkeypatch):
    marked = []
    monkeypatch.setattr(
        retry_config, "mark_bulk_terminal_failure", lambda file_id, error: marked.append((file_id, error))
    )

    _terminal_failure(process_with_ocr, ("document.pdf", "not-an-id"), {})

    assert marked == []


def test_provider_rate_limit_retry_keeps_bulk_item_reserved(monkeypatch):
    marked = []
    monkeypatch.setattr(
        retry_config, "mark_bulk_terminal_failure", lambda file_id, error: marked.append((file_id, error))
    )

    with patch.object(Task, "retry", return_value=None) as celery_retry:
        process_with_ocr.retry(
            args=("document.pdf", 723),
            exc=ProviderRateLimited("try again", retry_after=60),
        )

    assert celery_retry.called
    assert marked == []
