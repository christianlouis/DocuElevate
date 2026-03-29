## 2024-05-24 - SSRF in WebDAV connection test
**Vulnerability:** The `_test_webdav_connection` function had a custom SSRF check that failed to resolve DNS names, allowing attackers to bypass the check by providing a domain that resolves to an internal IP (e.g., `127.0.0.1`).
**Learning:** DNS resolution is required for robust SSRF protection when validating URLs provided by users.
**Prevention:** Use a centralized `is_private_ip` function (now in `app/utils/network.py`) that resolves the hostname to its IPs and checks if any are private.
## 2026-03-22 - B310: urllib.request.urlopen replaced with httpx
**Vulnerability:** The `_test_webdav_connection` function used `urllib.request.urlopen`, which natively supports dangerous schemes like `file://` or `ftp://` and follows redirects by default, potentially allowing SSRF bypasses or Local File Inclusion.
**Learning:** `urllib.request` should be avoided for user-supplied URLs. Even when URL schemes are manually validated, `urllib`'s default redirect following behavior can bypass SSRF protections (e.g. redirecting to `127.0.0.1`).
**Prevention:** Use a modern, safer HTTP client like `httpx` with `follow_redirects=False` when testing user-provided URLs.

## 2026-03-20 - Safe Path Traversal Prevention in Low-Level Utilities
**Vulnerability:** The generic file utility `hash_file` in `app/utils/file_operations.py` accepted any file path and was vulnerable to reading arbitrary files via path traversal (e.g., `../../../etc/passwd`) or absolute paths if an attacker could control the `filepath` argument.
**Learning:** Naively checking for `".." in path` breaks legitimate relative paths used internally by the application. Blocking absolute paths entirely also breaks functionality. Input validation should occur at the API boundary, but for defense-in-depth, low-level utilities must enforce expected boundaries (e.g., the application's `workdir`).
**Prevention:** Use `pathlib.Path.resolve()` on both the target path and the allowed base directory (`settings.workdir`). Ensure the resolved target path is strictly within the allowed boundary using `filepath_obj.relative_to(workdir_obj)`, catching the `ValueError` that is raised when the path is out of bounds. This safely blocks both relative traversal attacks and arbitrary absolute paths.
## 2025-05-18 - [SSRF Bypass via DNS Resolution Failure]
**Vulnerability:** The `is_private_ip` function in `app/utils/network.py` failed open (returned `False`) when a hostname could not be resolved (`socket.gaierror`).
**Learning:** This fail-open pattern was originally added to allow external domains in tests, but in production, it created a severe SSRF risk. An attacker could bypass SSRF protections by providing a URL that fails to resolve during the security check but resolves later (DNS rebinding), or by exploiting internal routing behaviors via unresolvable addresses.
**Prevention:** Always fail securely in network authorization functions. If a domain cannot be resolved to verify its safety, the request must be blocked (`return True` / default-deny). Tests should mock DNS resolution correctly instead of compromising production security logic.
## 2026-03-26 - SSRF in Integration Connection Tests
**Vulnerability:** The `_test_imap_connection` and `_test_s3_connection` functions in `app/api/integrations.py` did not validate user-provided `host` and `endpoint_url` variables against `is_private_ip()`. This allowed an attacker to test the presence of internal IMAP servers or direct S3 SDK API calls to internal infrastructure via SSRF.
**Learning:** Any time a new generic connection or integration test is added, SSRF validation may be forgotten if the core network utility (`is_private_ip`) is not systematically applied to all outbound network operations, regardless of the protocol (e.g., IMAP, S3).
**Prevention:** Establish a pattern where any user-configurable host or endpoint URL is immediately passed through the centralized `is_private_ip` validation function before any network call or third-party client initialization.

## 2026-03-29 - SSRF Bypass via HTTP Redirects
**Vulnerability:** The `process_url` endpoint in `app/api/url_upload.py` validated the initial URL using `is_private_ip()` but used `httpx.AsyncClient(follow_redirects=True)` to download the file. This allowed an attacker to bypass SSRF protections by providing a safe external URL that redirects to an internal cloud metadata endpoint (e.g., `169.254.169.254`).
**Learning:** Checking the initial URL is insufficient if the HTTP client automatically follows redirects to new, unvalidated locations.
**Prevention:** When following redirects is required for functionality, use the HTTP client's event hooks (e.g., `event_hooks={"response": [check_redirect]}` in `httpx`) to intercept redirects and validate the new `Location` URL before the client follows it.
