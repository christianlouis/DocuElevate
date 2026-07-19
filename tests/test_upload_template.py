import json
import re
from pathlib import Path

import pytest


@pytest.mark.unit
def test_file_picker_click_is_not_registered_twice():
    """The browse button must rely on the guarded drop-zone handler only."""
    template = Path("frontend/templates/upload.html").read_text(encoding="utf-8")

    assert "onclick=\"document.getElementById('fileInput').click()\"" not in template
    assert "if (event.target !== fileInput)" in template
    assert template.count('dropZone.addEventListener("click"') == 1


@pytest.mark.unit
def test_drop_zone_supports_keyboard_activation():
    """The button-like drop zone must open the picker with Enter or Space."""
    template = Path("frontend/templates/upload.html").read_text(encoding="utf-8")

    assert template.count('dropZone.addEventListener("keydown"') == 1
    assert 'event.key === "Enter" || event.key === " "' in template
    assert "event.preventDefault()" in template


@pytest.mark.unit
def test_upload_journey_copy_has_english_source_translations():
    """New UI copy is sourced from English for the translation automation."""
    template = Path("frontend/templates/upload.html").read_text(encoding="utf-8")
    keys = set(re.findall(r'["\'](upload\.[a-z0-9_]+)["\']', template))

    assert "upload.first_document_heading" in keys
    assert "window.uploadI18n" in template
    translations = json.loads(Path("frontend/translations/en.json").read_text(encoding="utf-8"))
    missing = sorted(keys - translations.keys())
    assert not missing, f"Missing English upload translations: {missing}"


@pytest.mark.unit
def test_upload_script_uses_localized_visible_status_messages():
    """The queue runner must not bypass the server-provided translation map."""
    script = Path("frontend/static/js/upload.js").read_text(encoding="utf-8")

    assert "function uploadMessage" in script
    assert "statusMessage.textContent = uploadMessage('queuedBatch'" in script
    assert "statusEl.textContent = uploadMessage('successTask'" in script


@pytest.mark.unit
def test_first_document_upload_follows_the_created_record_instead_of_losing_context():
    """The onboarding upload must land on its live, owner-filtered pipeline page."""
    template = Path("frontend/templates/upload.html").read_text(encoding="utf-8")
    script = Path("frontend/static/js/upload.js").read_text(encoding="utf-8")

    assert 'get("onboarding") === "first-document"' in template
    assert "/api/bulk-operations/${encodeURIComponent(operationId)}" in template
    assert "/api/logs/task/${encodeURIComponent(taskId)}" in template
    assert "/process?onboarding=first-document" in template
    assert "window.onDocuElevateUploadQueued = followFirstDocument" in template
    assert 'id="firstDocumentDelayedLink"' in template
    assert 'firstDocumentDelayedLink?.classList.remove("hidden")' in template
    assert script.count("window.onDocuElevateUploadQueued({") == 2
    assert "duplicateFileId: result.duplicate_of.original_file_id" in script
    assert "operationId: result.operation_id" in script
    assert "taskIds: result.task_ids" in script
    assert 'payload.state === "completed" && payload.failed_items > 0' in template


@pytest.mark.unit
def test_first_document_pipeline_has_live_elapsed_terminal_journey_copy():
    """Processing stays understandable until it reaches success or an actionable failure."""
    template = Path("frontend/templates/file_detail.html").read_text(encoding="utf-8")
    keys = set(re.findall(r'_[\(]["\'](onboarding\.[a-z0-9_]+)["\']', template))

    assert 'request.query_params.get("onboarding") == "first-document"' in template
    assert 'id="first-document-processing-elapsed"' in template
    assert "docuelevate.firstDocumentStartedAt" in template
    onboarding_status = template[
        template.index('id="first-document-status"') : template.index("<!-- Overall Processing Status Banner -->")
    ]
    assert "window.location.reload()" not in onboarding_status
    assert 'page.getElementById("first-document-status")' in template
    assert 'id="processing-history"' in template
    assert "{% set onboarding_failed = step_summary.main.failure > 0 %}" in template
    assert "onboarding_failed = step_summary.main.failure > 0 or step_summary.uploads.failure" not in template
    translations = json.loads(Path("frontend/translations/en.json").read_text(encoding="utf-8"))
    missing = sorted(keys - translations.keys())
    assert not missing, f"Missing English first-document translations: {missing}"


@pytest.mark.unit
def test_original_non_pdf_preview_does_not_invoke_pdfjs():
    """Images render natively and only actual PDFs are passed to PDF.js."""
    template = Path("frontend/templates/file_detail.html").read_text(encoding="utf-8")

    assert "original_file_exists and (file.mime_type == 'application/pdf'" in template
    assert 'id="original-image-container"' in template
    assert 'src="/files/{{ file.id }}/preview/original"' in template
    assert "'image/png'" in template
    assert "file.mime_type.startswith('image/')" not in template
