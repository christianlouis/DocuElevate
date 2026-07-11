import sys

with open("tests/test_process_document.py", "r") as f:
    content = f.read()

content = content.replace(
    "mock_settings.workdir = os.path.realpath(str(tmp_path))",
    "mock_settings.workdir = os.path.realpath(str(tmp_path))\n    from app.config import settings as real_settings\n    real_settings.workdir = mock_settings.workdir",
)

with open("tests/test_process_document.py", "w") as f:
    f.write(content)
