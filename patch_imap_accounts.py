import re

with open("app/api/imap_accounts.py", "r") as f:
    content = f.read()

# Add import
import_stmt = "from app.utils.network import is_private_ip\n"
content = re.sub(
    r"(from app\.utils\.user_scope import get_current_owner_id\n)",
    r"\1" + import_stmt,
    content
)

# Add SSRF check
ssrf_check = """
    # Security: Prevent SSRF by blocking connections to internal IPs
    if is_private_ip(host):
        logger.warning("SSRF blocked: Attempt to connect to private IP %s", host)
        return {"success": False, "message": "Connection error: Invalid hostname or IP address"}
"""

content = re.sub(
    r"(def _test_imap_connection\(host: str, port: int, username: str, password: str, use_ssl: bool\) -> dict\[str, Any\]:\n    \"\"\"Attempt to connect and log in to the IMAP server.\n\n    Returns a dict with ``\{\"success\": bool, \"message\": str\}``\.\n    \"\"\"\n)",
    r"\1" + ssrf_check,
    content
)

with open("app/api/imap_accounts.py", "w") as f:
    f.write(content)
