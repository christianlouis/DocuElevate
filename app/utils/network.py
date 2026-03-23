import ipaddress
import logging
import socket
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)


def is_private_ip(hostname: str) -> bool:
    """
    Check if a hostname resolves to a private/internal IP address.
    Protects against SSRF attacks by blocking access to internal networks.
    """
    try:
        # Try to parse as IP address directly
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        # Not a direct IP, try to resolve hostname
        try:
            # Get all IP addresses for this hostname
            addr_info = socket.getaddrinfo(hostname, None)
            for info in addr_info:
                ip_str = info[4][0]
                ip = ipaddress.ip_address(ip_str)
                # Block if ANY resolved IP is private/internal
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return True
            return False
        except (socket.gaierror, socket.error):
            # Cannot resolve.
            # Fail securely: block unresolved domains to prevent DNS rebinding
            # and SSRF bypasses via unresolvable addresses.
            logger.warning(f"Could not resolve hostname (blocking securely): {hostname}")
            return True


def join_url(base: str, *parts: str) -> str:
    """
    Safely join a base URL with one or more path parts.

    Uses urllib.parse to correctly handle scheme/netloc/query/fragment so that
    only the path component is modified.  Leading and trailing slashes are
    stripped from each part before joining, preventing double-slash sequences
    at segment boundaries without touching the scheme separator or query string.

    Examples:
        join_url("https://example.com/dav/", "/remote/", "file.pdf")
        -> "https://example.com/dav/remote/file.pdf"
    """
    parsed = urlsplit(base)
    # Strip each part once and filter out empty segments; use walrus operator
    # to avoid calling strip twice per iteration.
    stripped_parts = [s for p in parts if (s := p.strip("/"))]
    base_path = parsed.path.rstrip("/")
    new_path = base_path + "/" + "/".join(stripped_parts) if stripped_parts else base_path
    # Ensure path is non-empty so the reconstructed URL is valid.
    if not new_path:
        new_path = "/"
    return urlunsplit((parsed.scheme, parsed.netloc, new_path, parsed.query, parsed.fragment))
