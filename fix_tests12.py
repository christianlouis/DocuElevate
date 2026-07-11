import sys

with open("tests/test_process_document.py", "r") as f:
    content = f.read()

# Add mock_ocr
content = content.replace(
    '@patch("app.tasks.process_document.extract_metadata_with_gpt")',
    '@patch("app.tasks.process_document.process_with_ocr")\n@patch("app.tasks.process_document.extract_metadata_with_gpt")',
)

content = content.replace(
    "def test_process_document_webhook_dispatch_success(\n    mock_webhook, mock_extract, mock_settings, mock_session_local, mock_log_task_progress, db_session, tmp_path\n):",
    "def test_process_document_webhook_dispatch_success(\n    mock_webhook, mock_extract, mock_ocr, mock_settings, mock_session_local, mock_log_task_progress, db_session, tmp_path\n):",
)

content = content.replace(
    "def test_process_document_webhook_dispatch_error(\n    mock_webhook, mock_extract, mock_settings, mock_session_local, mock_log_task_progress, db_session, tmp_path\n):",
    "def test_process_document_webhook_dispatch_error(\n    mock_webhook, mock_extract, mock_ocr, mock_settings, mock_session_local, mock_log_task_progress, db_session, tmp_path\n):",
)

# Mock ocr.delay()
content = content.replace(
    "mock_extract.delay = MagicMock()", "mock_extract.delay = MagicMock()\n        mock_ocr.delay = MagicMock()"
)

# Add unique data for the second test to avoid deduplication
content = content.replace("%\xe2\xe3\xcf\xd3\n1 0 obj", "%\xe2\xe3\xcf\xd3\n%UNIQUE_DATA\n1 0 obj")

with open("tests/test_process_document.py", "w") as f:
    f.write(content.replace("%UNIQUE_DATA", "SUCCESS_TEST", 1).replace("%UNIQUE_DATA", "ERROR_TEST", 1))
