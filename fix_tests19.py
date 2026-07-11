import sys

with open("tests/test_process_document.py", "r") as f:
    content = f.read()

# Add autouse fixture
fixture_code = """
@pytest.fixture(autouse=True)
def mock_settings_workdir(tmp_path, monkeypatch):
    from app.config import settings as real_settings
    monkeypatch.setattr(real_settings, "workdir", str(tmp_path))
"""

content = content.replace(
    "def test_process_document_stores_file_id_before_session_closes",
    fixture_code
    + "\n\n@pytest.mark.unit\n@pytest.mark.requires_db\ndef test_process_document_stores_file_id_before_session_closes",
)

with open("tests/test_process_document.py", "w") as f:
    f.write(content)
