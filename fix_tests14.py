import sys

with open("tests/test_process_document.py", "r") as f:
    content = f.read()

# Fix line 98
content = content.replace(
    "        mock_extract.delay = MagicMock()\n    mock_ocr.delay = MagicMock()",
    "        mock_extract.delay = MagicMock()\n        mock_ocr.delay = MagicMock()",
)

# Fix line 102
content = content.replace(
    "        mock_extract.delay = MagicMock()\n    mock_ocr.delay = MagicMock()\n        task_run_func = process_document.run",
    "        mock_extract.delay = MagicMock()\n        mock_ocr.delay = MagicMock()\n        task_run_func = process_document.run",
)

# Fix any other places I messed up with task_run_func
content = content.replace(
    "    mock_ocr.delay = MagicMock()\n    task_run_func = process_document.run",
    "    mock_ocr.delay = MagicMock()\n    task_run_func = process_document.run",
)

# Fix line 1355
content = content.replace(
    "mock_extract.delay = MagicMock()\n    mock_ocr.delay = MagicMock()",
    "mock_extract.delay = MagicMock()\n    mock_ocr.delay = MagicMock()",  # already fine if it's top level block of test
)

with open("tests/test_process_document.py", "w") as f:
    f.write(content)
