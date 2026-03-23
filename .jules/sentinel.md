## 2024-05-24 - SSRF in WebDAV connection test
**Vulnerability:** The `_test_webdav_connection` function had a custom SSRF check that failed to resolve DNS names, allowing attackers to bypass the check by providing a domain that resolves to an internal IP (e.g., `127.0.0.1`).
**Learning:** DNS resolution is required for robust SSRF protection when validating URLs provided by users.
**Prevention:** Use a centralized `is_private_ip` function (now in `app/utils/network.py`) that resolves the hostname to its IPs and checks if any are private.
## 2026-03-19 - Prevent SSRF in IMAP Connection Testing
**Vulnerability:** Server-Side Request Forgery (SSRF) allowed users to port-scan or connect to internal services via user-provided `host` and `port` inputs in IMAP endpoints (`/test` and `pull_inbox`).
**Learning:** Endpoints testing outbound connections with user-provided configurations must validate the destination host before attempting the connection to prevent exploitation of the server's network position.
**Prevention:** Use network utilities like `is_private_ip` that resolve hostnames and block private/loopback/reserved IPs before establishing outbound connections.
