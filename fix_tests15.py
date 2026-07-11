import sys
import re

with open("tests/test_process_document.py", "r") as f:
    content = f.read()

# I will just write a python script that will cut everything after the original test_process_document_success and rewrite my tests.
lines = content.splitlines()

end_idx = -1
for i, line in enumerate(lines):
    if line.startswith("def test_process_document_webhook_dispatch_success("):
        # We need to find the decorators above it.
        start_idx = i - 1
        while start_idx >= 0 and lines[start_idx].startswith("@patch"):
            start_idx -= 1
        end_idx = start_idx + 1
        break

if end_idx != -1:
    new_content = "\n".join(lines[:end_idx]) + "\n"

    # Now append my clean tests!
    new_content += """
@patch("app.tasks.process_document.log_task_progress")
@patch("app.tasks.process_document.SessionLocal")
@patch("app.tasks.process_document.settings")
@patch("app.tasks.process_document.process_with_ocr")
@patch("app.tasks.process_document.extract_metadata_with_gpt")
@patch("app.tasks.process_document.dispatch_webhook_event")
def test_process_document_webhook_dispatch_success(
    mock_webhook, mock_extract, mock_ocr, mock_settings, mock_session_local, mock_log_task_progress, db_session, tmp_path
):
    import os
    test_pdf = tmp_path / "test_success.pdf"
    test_pdf.write_bytes(b'''%PDF-1.4
%\\xe2\\xe3\\xcf\\xd3
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [ 3 0 R ]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [ 0 0 612 792 ]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test content) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000306 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
399
%%EOF
''')

    mock_settings.workdir = os.path.realpath(str(tmp_path))
    from app.config import settings as real_settings
    real_settings.workdir = mock_settings.workdir
    mock_session_local.return_value.__enter__.return_value = db_session
    mock_session_local.return_value.__exit__.return_value = None
    mock_extract.delay = MagicMock()
    mock_ocr.delay = MagicMock()

    from app.tasks.process_document import process_document
    task_run_func = process_document.run
    
    result = task_run_func(str(test_pdf))
    
    mock_webhook.assert_called_once()
    call_args = mock_webhook.call_args[1]
    assert call_args["event_type"] == "document.routed"
    assert "payload" in call_args

@patch("app.tasks.process_document.log_task_progress")
@patch("app.tasks.process_document.SessionLocal")
@patch("app.tasks.process_document.settings")
@patch("app.tasks.process_document.process_with_ocr")
@patch("app.tasks.process_document.extract_metadata_with_gpt")
@patch("app.tasks.process_document.dispatch_webhook_event")
def test_process_document_webhook_dispatch_error(
    mock_webhook, mock_extract, mock_ocr, mock_settings, mock_session_local, mock_log_task_progress, db_session, tmp_path
):
    import os
    test_pdf = tmp_path / "test_error.pdf"
    test_pdf.write_bytes(b'''%PDF-1.4
%\\xe2\\xe3\\xcf\\xd3
%ERROR_TEST
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [ 3 0 R ]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [ 0 0 612 792 ]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test content error) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000306 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
405
%%EOF
''')

    mock_settings.workdir = os.path.realpath(str(tmp_path))
    from app.config import settings as real_settings
    real_settings.workdir = mock_settings.workdir
    mock_session_local.return_value.__enter__.return_value = db_session
    mock_session_local.return_value.__exit__.return_value = None
    mock_extract.delay = MagicMock()
    mock_ocr.delay = MagicMock()
    
    mock_webhook.side_effect = Exception("Webhook boom")
    
    from app.tasks.process_document import process_document
    task_run_func = process_document.run
    
    result = task_run_func(str(test_pdf))
    
    mock_webhook.assert_called_once()
"""
    with open("tests/test_process_document.py", "w") as f:
        f.write(new_content)
