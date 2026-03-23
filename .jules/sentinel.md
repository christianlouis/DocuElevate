## 2024-05-24 - SSRF in WebDAV connection test
**Vulnerability:** The `_test_webdav_connection` function had a custom SSRF check that failed to resolve DNS names, allowing attackers to bypass the check by providing a domain that resolves to an internal IP (e.g., `127.0.0.1`).
**Learning:** DNS resolution is required for robust SSRF protection when validating URLs provided by users.
**Prevention:** Use a centralized `is_private_ip` function (now in `app/utils/network.py`) that resolves the hostname to its IPs and checks if any are private.
## 2026-03-22 - B310: urllib.request.urlopen replaced with httpx
**Vulnerability:** The `_test_webdav_connection` function used `urllib.request.urlopen`, which natively supports dangerous schemes like `file://` or `ftp://` and follows redirects by default, potentially allowing SSRF bypasses or Local File Inclusion.
**Learning:** `urllib.request` should be avoided for user-supplied URLs. Even when URL schemes are manually validated, `urllib`'s default redirect following behavior can bypass SSRF protections (e.g. redirecting to `127.0.0.1`).
**Prevention:** Use a modern, safer HTTP client like `httpx` with `follow_redirects=False` when testing user-provided URLs.

## 2025-05-18 - [SSRF Bypass via DNS Resolution Failure]
**Vulnerability:** The `is_private_ip` function in `app/utils/network.py` failed open (returned `False`) when a hostname could not be resolved (`socket.gaierror`).
**Learning:** This fail-open pattern was originally added to allow external domains in tests, but in production, it created a severe SSRF risk. An attacker could bypass SSRF protections by providing a URL that fails to resolve during the security check but resolves later (DNS rebinding), or by exploiting internal routing behaviors via unresolvable addresses.
**Prevention:** Always fail securely in network authorization functions. If a domain cannot be resolved to verify its safety, the request must be blocked (`return True` / default-deny). Tests should mock DNS resolution correctly instead of compromising production security logic.
