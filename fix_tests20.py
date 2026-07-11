import sys
import re

with open("tests/test_process_document.py", "r") as f:
    content = f.read()

# First, undo the previous bad insertion
bad_insertion = """
@pytest.fixture(autouse=True)
def mock_settings_workdir(tmp_path, monkeypatch):
    from app.config import settings as real_settings
    monkeypatch.setattr(real_settings, "workdir", str(tmp_path))


@pytest.mark.unit
@pytest.mark.requires_db
def test_process_document_stores_file_id_before_session_closes"""

content = content.replace(bad_insertion, "def test_process_document_stores_file_id_before_session_closes")

# Now insert it right after the imports
imports_end = "from app.tasks.process_document import process_document"
fixture_code = """

@pytest.fixture(autouse=True)
def mock_settings_workdir(tmp_path, monkeypatch):
    from app.config import settings as real_settings
    monkeypatch.setattr(real_settings, "workdir", str(tmp_path))
"""
content = content.replace(imports_end, imports_end + fixture_code)

with open("tests/test_process_document.py", "w") as f:
    f.write(content)
