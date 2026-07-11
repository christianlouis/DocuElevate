import sys

with open("tests/test_process_document.py", "r") as f:
    content = f.read()

# Insert the fixture safely at the top by splitting on exactly the first occurrence of `from app.tasks.process_document import process_document\n`
parts = content.split("from app.tasks.process_document import process_document\n", 1)

fixture_code = """from app.tasks.process_document import process_document

@pytest.fixture(autouse=True)
def mock_settings_workdir(tmp_path, monkeypatch):
    from app.config import settings as real_settings
    monkeypatch.setattr(real_settings, "workdir", str(tmp_path))
"""

content = parts[0] + fixture_code + parts[1]

with open("tests/test_process_document.py", "w") as f:
    f.write(content)
