with open("tests/test_upload_email.py", "r") as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if line.startswith("<<<<<<< HEAD"):
        skip = True
        continue
    elif line.startswith("======="):
        skip = True
        continue
    elif line.startswith(">>>>>>> origin/main"):
        skip = False
        continue
    if not skip:
        new_lines.append(line)

with open("tests/test_upload_email.py", "w") as f:
    f.writelines(new_lines)
