import sys

with open("tests/test_process_document.py", "r") as f:
    content = f.read()

# I will add the mock side_effect logic and the patch.
new_patch = '@patch("app.tasks.process_document._apply_pre_processing_routing")\n@patch("app.tasks.process_document.log_task_progress")'

content = content.replace('@patch("app.tasks.process_document.log_task_progress")', new_patch)

# For success test
sig_success = "def test_process_document_webhook_dispatch_success(\n    mock_webhook, mock_extract, mock_ocr, mock_settings, mock_session_local, mock_log_task_progress, db_session, tmp_path\n):"
new_sig_success = "def test_process_document_webhook_dispatch_success(\n    mock_webhook, mock_extract, mock_ocr, mock_settings, mock_session_local, mock_log_task_progress, mock_routing, db_session, tmp_path\n):"
content = content.replace(sig_success, new_sig_success)

# For error test
sig_error = "def test_process_document_webhook_dispatch_error(\n    mock_webhook, mock_extract, mock_ocr, mock_settings, mock_session_local, mock_log_task_progress, db_session, tmp_path\n):"
new_sig_error = "def test_process_document_webhook_dispatch_error(\n    mock_webhook, mock_extract, mock_ocr, mock_settings, mock_session_local, mock_log_task_progress, mock_routing, db_session, tmp_path\n):"
content = content.replace(sig_error, new_sig_error)

# Now add the side effect implementation right after mock_ocr.delay = MagicMock() in both tests
side_effect_code = """
    def mock_routing_func(db, record, owner_id, task_id):
        record.pipeline_assignment_source = "routing_rule"
        record.pipeline_routing_rule_id = 1
        record.pipeline_assignment_reason = "Matched by test"
    mock_routing.side_effect = mock_routing_func
"""

content = content.replace(
    "mock_ocr.delay = MagicMock()\n\n    from app.tasks.process_document",
    "mock_ocr.delay = MagicMock()\n" + side_effect_code + "\n    from app.tasks.process_document",
)
content = content.replace(
    "mock_ocr.delay = MagicMock()\n    \n    mock_webhook",
    "mock_ocr.delay = MagicMock()\n" + side_effect_code + "\n    mock_webhook",
)

with open("tests/test_process_document.py", "w") as f:
    f.write(content)
