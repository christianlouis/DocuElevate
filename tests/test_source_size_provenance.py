"""Focused tests for trusted source policy provenance."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.integrations import _validate_destination_size_config
from app.models import IntegrationDirection, IntegrationType, UserIntegration
from app.tasks.upload_to_user_integration import _effective_size_config


def test_override_keys_are_numeric_source_ids():
    with pytest.raises(Exception, match="source integration IDs"):
        _validate_destination_size_config(IntegrationType.EMAIL, {"size_policy_overrides": {"imap": "link"}})


def test_override_is_ignored_without_trusted_file_provenance():
    cfg = {"size_policy": "stop", "size_policy_overrides": {"3": "link"}}
    assert _effective_size_config(cfg, None)["size_policy"] == "stop"
    assert _effective_size_config(cfg, SimpleNamespace(source_integration_id=None))["size_policy"] == "stop"


def test_watch_enqueue_forwards_source_id(tmp_path):
    from app.tasks import watch_folder_tasks

    source = tmp_path / "sample.pdf"
    source.write_bytes(b"pdf")
    with patch.object(watch_folder_tasks.process_document, "delay") as queued:
        watch_folder_tasks._enqueue_file(str(source), owner_id="owner", source_integration_id=9)
    queued.assert_called_once_with(str(source), owner_id="owner", source_integration_id=9)


def test_source_provenance_and_overrides_enforce_owner_and_direction(db_session):
    from app.tasks.process_document import _trusted_source_integration_id

    source = UserIntegration(
        owner_id="owner",
        direction=IntegrationDirection.SOURCE,
        integration_type=IntegrationType.IMAP,
        name="Source",
        is_active=True,
    )
    destination = UserIntegration(
        owner_id="owner",
        direction=IntegrationDirection.DESTINATION,
        integration_type=IntegrationType.EMAIL,
        name="Destination",
        is_active=True,
    )
    db_session.add_all((source, destination))
    db_session.commit()
    assert _trusted_source_integration_id(db_session, "task", "owner", source.id) == source.id
    assert _trusted_source_integration_id(db_session, "task", "other", source.id) is None
    assert _trusted_source_integration_id(db_session, "task", "owner", destination.id) is None
    config = {"size_policy_overrides": {str(source.id): "link"}}
    _validate_destination_size_config(IntegrationType.EMAIL, config, db_session, "owner")
    with pytest.raises(HTTPException, match="unknown source"):
        _validate_destination_size_config(IntegrationType.EMAIL, config, db_session, "other")
    source.is_active = False
    db_session.commit()
    assert _trusted_source_integration_id(db_session, "task", "owner", source.id) is None


def test_lossless_pdf_copy_preserves_pages_metadata_and_original(tmp_path):
    from pypdf import PdfReader, PdfWriter

    from app.utils.pdf_delivery import optimize_pdf_bytes

    path = tmp_path / "original.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=200)
    writer.add_blank_page(width=300, height=400)
    writer.add_metadata({"/Title": "Complete document"})
    writer.write(path)
    original = path.read_bytes() + b"\n" * 10000
    path.write_bytes(original)
    optimized = optimize_pdf_bytes(str(path))
    assert optimized is not None and len(optimized) < len(original)
    from io import BytesIO

    reader = PdfReader(BytesIO(optimized))
    assert len(reader.pages) == 2
    assert reader.metadata.title == "Complete document"
    assert reader.pages[1].mediabox.width == 300
    assert path.read_bytes() == original
    path.write_bytes(original + b"\n% /ByteRange")
    assert optimize_pdf_bytes(str(path)) is None
