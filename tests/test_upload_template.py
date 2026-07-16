from pathlib import Path


def test_file_picker_click_is_not_registered_twice():
    """The browse button must rely on the guarded drop-zone handler only."""
    template = Path("frontend/templates/upload.html").read_text(encoding="utf-8")

    assert "onclick=\"document.getElementById('fileInput').click()\"" not in template
    assert "if (event.target !== fileInput)" in template
