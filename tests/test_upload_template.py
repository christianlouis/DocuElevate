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
def test_upload_journey_copy_is_localized_in_english_and_german():
    """First-upload guidance and asynchronous status text use the normal locale."""
    template = Path("frontend/templates/upload.html").read_text(encoding="utf-8")
    keys = set(re.findall(r'["\'](upload\.[a-z0-9_]+)["\']', template))

    assert "upload.first_document_heading" in keys
    assert "window.uploadI18n" in template
    for locale in ("en", "de"):
        translations = json.loads(Path(f"frontend/translations/{locale}.json").read_text(encoding="utf-8"))
        missing = sorted(keys - translations.keys())
        assert not missing, f"Missing {locale} upload translations: {missing}"


@pytest.mark.unit
def test_upload_script_uses_localized_visible_status_messages():
    """The queue runner must not bypass the server-provided translation map."""
    script = Path("frontend/static/js/upload.js").read_text(encoding="utf-8")

    assert "function uploadMessage" in script
    assert "statusMessage.textContent = uploadMessage('queuedBatch'" in script
    assert "statusEl.textContent = uploadMessage('successTask'" in script
