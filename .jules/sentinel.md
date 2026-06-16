## 2026-06-01 - [Fix XSS in status_dashboard.html]
**Vulnerability:** A Cross-Site Scripting (XSS) vulnerability existed in `frontend/templates/status_dashboard.html` where untrusted configuration settings (`value`), external service messages (`data.message`), and token expirations (`data.token_info.expires_in_human`) were injected directly into the DOM via `.innerHTML` without sanitization.
**Learning:** Even internal or admin-focused dashboards can be vulnerable if they display external or user-configurable data without escaping. Constructing HTML strings dynamically from unvalidated sources is a common vector for DOM-based XSS.
**Prevention:** Always use a sanitization function like `escapeHtml` to escape dangerous characters (`<`, `>`, `&`, `"`, `'`) before assigning dynamic content to `.innerHTML`, or prefer `.textContent` when only plaintext is intended.
## 2026-06-16 - Prevent DOM-based XSS in error handling
**Vulnerability:** XSS vulnerability in frontend templates when network error messages (`err.message`) were dynamically assigned to the DOM using `.innerHTML` without escaping.
**Learning:** Network error messages can contain unsanitized input if the error reflects user input or server payload, creating an XSS vector when injected raw via innerHTML.
**Prevention:** Always use a helper function like `escapeHtml` to sanitize any dynamic string before appending it to the DOM using `.innerHTML`, even for variables like `err.message` which seem harmless but can be manipulated in Edge cases.
