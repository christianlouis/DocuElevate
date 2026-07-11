import sys

with open("tests/test_process_document.py", "r") as f:
    content = f.read()

content = content.replace(
    "        mock_extract.delay = MagicMock()\n    task_run_func = process_document.run",
    "        mock_extract.delay = MagicMock()\n        task_run_func = process_document.run",
)

with open("tests/test_process_document.py", "w") as f:
    f.write(content)
