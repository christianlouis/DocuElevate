import imaplib
import logging
from typing import Any

from app.utils.network import is_private_ip

logger = logging.getLogger(__name__)


def test_imap_connection(host: str, port: int, username: str, password: str, use_ssl: bool) -> dict[str, Any]:
    """Attempt to connect and log in to the IMAP server.

    Returns a dict with ``{"success": bool, "message": str}``.
    """

    # Security: Prevent SSRF by blocking connections to internal IPs
    if is_private_ip(host):
        logger.warning("SSRF blocked: Attempt to connect to private IP %s", host)
        return {"success": False, "message": "Connection error: Invalid hostname or IP address"}
    try:
        if use_ssl:
            mail = imaplib.IMAP4_SSL(host, port)
        else:
            mail = imaplib.IMAP4(host, port)

        mail.login(username, password)
        mail.logout()
        return {"success": True, "message": "Connection successful"}
    except OSError as exc:
        logger.warning("IMAP network error for %s@%s: %s", username, host, exc)
        return {"success": False, "message": "Connection failed. Check the server address, port, and network access."}
    except Exception as exc:  # noqa: BLE001
        logger.warning("IMAP error for %s@%s: %s", username, host, exc)
        return {"success": False, "message": "Authentication failed. Check the username, password, and TLS settings."}
