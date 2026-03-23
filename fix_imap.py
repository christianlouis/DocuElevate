import re

with open("app/api/imap_accounts.py", "r") as f:
    content = f.read()

# Remove duplicate imports
content = re.sub(r"from app\.utils\.network import is_private_ip\nfrom app\.utils\.network import is_private_ip\n", "from app.utils.network import is_private_ip\n", content)

with open("app/api/imap_accounts.py", "w") as f:
    f.write(content)
