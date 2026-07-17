"""Regression coverage for password-protected PDF handling."""

from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pypdf
import pytest

from app.config import settings
from app.models import FileRecord
from app.tasks.process_document import process_document
from app.utils.pdf_security import (
    ENCRYPTED_PDF_ERROR_CODE,
    ENCRYPTED_PDF_MESSAGE,
    EncryptedPdfPasswordRequiredError,
    open_pdf_reader,
)
from app.views.files import _compute_processing_flow

pytestmark = pytest.mark.unit


def _write_encrypted_pdf(path: Path, user_password: str, owner_credential: str = "owner-password") -> None:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt(user_password=user_password, owner_password=owner_credential)
    with path.open("wb") as output:
        writer.write(output)


def test_pdf_with_real_user_password_is_rejected_before_page_access(tmp_path):
    protected_pdf = tmp_path / "protected.pdf"
    _write_encrypted_pdf(protected_pdf, user_password="required-password")

    with protected_pdf.open("rb") as source, pytest.raises(EncryptedPdfPasswordRequiredError):
        open_pdf_reader(source)


def test_owner_password_only_pdf_remains_processable(tmp_path):
    owner_only_pdf = tmp_path / "owner-only.pdf"
    _write_encrypted_pdf(owner_only_pdf, user_password="")

    with owner_only_pdf.open("rb") as source:
        reader = open_pdf_reader(source)
        assert len(reader.pages) == 1


@pytest.mark.requires_db
@pytest.mark.parametrize("force_cloud_ocr", [False, True])
def test_process_document_stops_cleanly_for_password_protected_pdf(db_session, tmp_path, force_cloud_ocr):
    protected_pdf = tmp_path / "protected.pdf"
    _write_encrypted_pdf(protected_pdf, user_password="required-password")

    with (
        patch.object(settings, "workdir", str(tmp_path)),
        patch("app.tasks.process_document.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.process_document.log_task_progress") as progress,
        patch("app.tasks.process_document.process_with_ocr.delay") as queue_ocr,
        patch("app.tasks.process_document.extract_metadata_with_gpt.delay") as queue_metadata,
    ):
        result = process_document.run(str(protected_pdf), force_cloud_ocr=force_cloud_ocr)

    assert result["status"] == "Password required"
    assert result["error_code"] == ENCRYPTED_PDF_ERROR_CODE
    assert result["error"] == ENCRYPTED_PDF_MESSAGE
    queue_ocr.assert_not_called()
    queue_metadata.assert_not_called()

    record = db_session.query(FileRecord).filter(FileRecord.id == result["file_id"]).one()
    assert record.original_file_path
    assert Path(record.original_file_path).exists()
    assert any(
        call.args[1:4] == ("check_text", "failure", ENCRYPTED_PDF_MESSAGE)
        and call.kwargs["detail"] == ENCRYPTED_PDF_ERROR_CODE
        for call in progress.call_args_list
    )
    assert any(
        call.args[1:4] == ("process_with_ocr", "skipped", "Skipped because the PDF requires a password")
        for call in progress.call_args_list
    )


def test_password_required_flow_suppresses_retry_and_requests_replacement():
    log = SimpleNamespace(
        step_name="check_text",
        status="failure",
        message=ENCRYPTED_PDF_MESSAGE,
        detail=ENCRYPTED_PDF_ERROR_CODE,
        timestamp=datetime.now(timezone.utc),
        task_id="encrypted-pdf-task",
    )

    check_text = next(stage for stage in _compute_processing_flow([log]) if stage["key"] == "check_text")

    assert check_text["status"] == "failure"
    assert check_text["can_retry"] is False
    assert check_text["requires_source_replacement"] is True


def test_file_detail_contains_prominent_encrypted_pdf_remediation():
    template = Path("frontend/templates/file_detail.html").read_text(encoding="utf-8")

    assert "{% if encrypted_pdf_password_required %}" in template
    assert 'role="alert"' in template
    assert "did not send it to OCR or AI services" in template
