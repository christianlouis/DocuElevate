import sys

with open("tests/test_process_document.py", "r") as f:
    content = f.read()

# Add monkeypatch to the function signatures
content = content.replace(
    "mock_log_task_progress,\n    mock_routing,\n    db_session,\n    tmp_path,\n):",
    "mock_log_task_progress,\n    mock_routing,\n    db_session,\n    tmp_path,\n    monkeypatch,\n):",
)

# Replace the mutating code with monkeypatch
bad_code = """    mock_settings.workdir = os.path.realpath(str(tmp_path))
    from app.config import settings as real_settings

    real_settings.workdir = mock_settings.workdir"""

good_code = """    mock_settings.workdir = os.path.realpath(str(tmp_path))
    from app.config import settings as real_settings
    monkeypatch.setattr(real_settings, "workdir", mock_settings.workdir)"""

content = content.replace(bad_code, good_code)

with open("tests/test_process_document.py", "w") as f:
    f.write(content)
