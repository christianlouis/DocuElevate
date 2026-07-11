import sys

with open("tests/test_process_document.py", "r") as f:
    content = f.read()

content = content.replace("        mock_ocr.delay = MagicMock()", "    mock_ocr.delay = MagicMock()")

with open("tests/test_process_document.py", "w") as f:
    f.write(content)
