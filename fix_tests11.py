import sys

with open("tests/test_process_document.py", "r") as f:
    content = f.read()

content = content.replace(
    '@patch("app.tasks.process_document.SessionLocal")',
    '@patch("app.tasks.process_document.log_task_progress")\n@patch("app.tasks.process_document.SessionLocal")',
)

content = content.replace(
    "def test_process_document_webhook_dispatch_success(\n    mock_webhook, mock_extract, mock_settings, mock_session_local, db_session, tmp_path\n):",
    "def test_process_document_webhook_dispatch_success(\n    mock_webhook, mock_extract, mock_settings, mock_session_local, mock_log_task_progress, db_session, tmp_path\n):",
)

content = content.replace(
    "def test_process_document_webhook_dispatch_error(\n    mock_webhook, mock_extract, mock_settings, mock_session_local, db_session, tmp_path\n):",
    "def test_process_document_webhook_dispatch_error(\n    mock_webhook, mock_extract, mock_settings, mock_session_local, mock_log_task_progress, db_session, tmp_path\n):",
)

with open("tests/test_process_document.py", "w") as f:
    f.write(content)
