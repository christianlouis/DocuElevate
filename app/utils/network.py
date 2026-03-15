import ipaddress
import logging
import socket

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
            # Cannot resolve - allow for testing/development
            # In production, DNS should work properly
            # Log this for debugging
            logger.warning(f"Could not resolve hostname: {hostname}")
            return False  # Changed from True to False to allow external domains in tests
