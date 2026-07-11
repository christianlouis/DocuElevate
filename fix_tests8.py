import sys

with open("tests/test_process_document.py", "r") as f:
    content = f.read()

content = content.replace("âãÏÓ", r"\xe2\xe3\xcf\xd3")

with open("tests/test_process_document.py", "w") as f:
    f.write(content)
