import sys

with open("tests/test_process_document.py", "r") as f:
    content = f.read()

content = content.replace(
    'mock_webhook.side_effect = Exception("Webhook boom")',
    'mock_webhook.side_effect = Exception("Webhook boom")\n    mock_extract.delay = MagicMock()',
)
content = content.replace(
    "mock_webhook.assert_called_once()", "mock_extract.delay = MagicMock()\n    mock_webhook.assert_called_once()"
)
# Make sure we add it BEFORE task_run_func is called.
content = content.replace(
    "task_run_func = process_document.run", "mock_extract.delay = MagicMock()\n    task_run_func = process_document.run"
)

with open("tests/test_process_document.py", "w") as f:
    f.write(content)
