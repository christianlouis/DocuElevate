import sys

# For test_embed_pdf_metadata.py
with open("tests/test_embed_pdf_metadata.py", "r") as f:
    content = f.read()

content = content.replace(
    'embed_metadata_into_pdf.__wrapped__("/tmp/upload.pdf", "Sample text", metadata, file_id=42)',
    """
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"%PDF-1.4 content")
            tmp_name = f.name
        try:
            embed_metadata_into_pdf.__wrapped__(tmp_name, "Sample text", metadata, file_id=42)
        finally:
            os.unlink(tmp_name)
    """,
)

with open("tests/test_embed_pdf_metadata.py", "w") as f:
    f.write(content)

# For test_process_document.py
with open("tests/test_process_document.py", "r") as f:
    content = f.read()

content = content.replace(
    "mock_realpath.side_effect = lambda path: path", "mock_realpath.side_effect = lambda path, *args, **kwargs: path"
)

with open("tests/test_process_document.py", "w") as f:
    f.write(content)
