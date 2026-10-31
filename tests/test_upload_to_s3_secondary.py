"""Focused tests for the optional secondary S3 destination."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.send_to_all import _should_upload_to_s3_secondary, send_to_all_destinations
from app.tasks.upload_to_s3_secondary import upload_to_s3_secondary


def _settings(**overrides):
    values = {
        "s3_secondary_enabled": True,
        "s3_secondary_endpoint": "https://s3.example.test",
        "s3_secondary_bucket": "secondary-bucket",
        "s3_secondary_access_key": "access",
        "s3_secondary_secret_key": "secret",
        "s3_secondary_region": "eu-central",
        "s3_secondary_prefix": "archive",
        "s3_secondary_storage_class": "STANDARD",
        "s3_secondary_acl": None,
    }
    values.update(overrides)
    return MagicMock(**values)


def test_secondary_upload_uses_https_endpoint_and_prefix(tmp_path: Path):
    file_path = tmp_path / "document.pdf"
    file_path.write_bytes(b"pdf")
    expected = {
        "s3_bucket": "secondary-bucket",
        "s3_key": "archive/document.pdf",
        "s3_url": "https://s3.example.test/archive/document.pdf",
    }
    with (
        patch("app.tasks.upload_to_s3_secondary.settings", _settings()),
        patch("app.tasks.upload_to_s3_secondary.upload_file_to_s3", return_value=expected) as upload,
    ):
        result = upload_to_s3_secondary.apply(args=[str(file_path)]).get()

    assert result["s3_key"] == "archive/document.pdf"
    assert upload.call_args.kwargs["endpoint_url"] == "https://s3.example.test"
    assert upload.call_args.kwargs["prefix"] == "archive"


@pytest.mark.parametrize(
    "endpoint",
    [None, "http://s3.example.test", "https://", "https://user:pass@s3.example.test", "https://s3.example.test?x=1"],
)
def test_secondary_upload_rejects_missing_or_insecure_endpoint(tmp_path: Path, endpoint):
    file_path = tmp_path / "document.pdf"
    file_path.write_bytes(b"pdf")
    with patch("app.tasks.upload_to_s3_secondary.settings", _settings(s3_secondary_endpoint=endpoint)):
        with pytest.raises(ValueError, match="HTTPS endpoint"):
            upload_to_s3_secondary.apply(args=[str(file_path)]).get()


def test_secondary_upload_returns_skipped_when_disabled(tmp_path: Path):
    with (
        patch("app.tasks.upload_to_s3_secondary.settings", _settings(s3_secondary_enabled=False)),
        patch("app.tasks.upload_to_s3_secondary.log_task_progress") as progress,
    ):
        result = upload_to_s3_secondary.apply(args=[str(tmp_path / "missing.pdf")]).get()

    assert result["status"] == "Skipped"
    assert result["reason"] == "Secondary S3 is disabled"
    assert progress.call_args.args[2] == "skipped"


def test_secondary_upload_records_missing_file_failure(tmp_path: Path):
    with (
        patch("app.tasks.upload_to_s3_secondary.settings", _settings()),
        patch("app.tasks.upload_to_s3_secondary.log_task_progress") as progress,
    ):
        with pytest.raises(FileNotFoundError):
            upload_to_s3_secondary.apply(args=[str(tmp_path / "missing.pdf")]).get()

    assert progress.call_args.args[2] == "failure"
    assert progress.call_args.args[3] == "File not found"


def test_secondary_destination_is_disabled_by_default():
    with patch("app.tasks.send_to_all.settings", _settings(s3_secondary_enabled=False)):
        assert _should_upload_to_s3_secondary() is False


@pytest.mark.parametrize("endpoint", ["https://", "https://user:pass@s3.example.test", "https://s3.example.test#fragment"])
def test_dispatch_rejects_malformed_endpoint(endpoint):
    with patch("app.tasks.send_to_all.settings", _settings(s3_secondary_endpoint=endpoint)):
        assert _should_upload_to_s3_secondary() is False


def test_secondary_destination_queues_independently_of_primary(tmp_path: Path):
    file_path = tmp_path / "document.pdf"
    file_path.write_bytes(b"pdf")
    service_names = (
        "dropbox",
        "nextcloud",
        "paperless",
        "google_drive",
        "webdav",
        "ftp",
        "sftp",
        "email",
        "evernote",
        "notion",
        "onedrive",
        "s3",
        "s3_secondary",
        "sharepoint",
        "icloud",
    )
    configured = {name: False for name in service_names}
    configured.update({"s3": True, "s3_secondary": True})
    with (
        patch("app.tasks.send_to_all.get_configured_services_from_validator", return_value=configured),
        patch("app.tasks.send_to_all.upload_to_s3") as primary,
        patch("app.tasks.send_to_all.upload_to_s3_secondary") as secondary,
    ):
        primary.delay.return_value = SimpleNamespace(id="primary-task")
        secondary.delay.return_value = SimpleNamespace(id="secondary-task")
        result = send_to_all_destinations.apply(args=[str(file_path)], kwargs={"file_id": 1}).get()

    assert result["tasks"] == {
        "s3_task_id": "primary-task",
        "s3_secondary_task_id": "secondary-task",
    }
    primary.delay.assert_called_once()
    secondary.delay.assert_called_once()
