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
