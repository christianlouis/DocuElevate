import sys

with open("tests/test_process_document.py", "r") as f:
    content = f.read()

content = content.replace(
    'call_args = mock_webhook.call_args[1]\n    assert call_args["event_type"] == "document.routed"',
    'call_args = mock_webhook.call_args[0]\n    assert call_args[0] == "document.routed"',
)

content = content.replace('assert "payload" in call_args', 'assert "file_id" in call_args[1]')

with open("tests/test_process_document.py", "w") as f:
    f.write(content)
