import re

with open("app/api/imap_accounts.py", "r") as f:
    content = f.read()

if "is_private_ip" in content:
    print("Patch successful!")
else:
    print("Patch failed!")
