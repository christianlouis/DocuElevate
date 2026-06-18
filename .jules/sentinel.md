## 2026-06-01 - [Fix XSS in status_dashboard.html]
**Vulnerability:** A Cross-Site Scripting (XSS) vulnerability existed in `frontend/templates/status_dashboard.html` where untrusted configuration settings (`value`), external service messages (`data.message`), and token expirations (`data.token_info.expires_in_human`) were injected directly into the DOM via `.innerHTML` without sanitization.
**Learning:** Even internal or admin-focused dashboards can be vulnerable if they display external or user-configurable data without escaping. Constructing HTML strings dynamically from unvalidated sources is a common vector for DOM-based XSS.
**Prevention:** Always use a sanitization function like `escapeHtml` to escape dangerous characters (`<`, `>`, `&`, `"`, `'`) before assigning dynamic content to `.innerHTML`, or prefer `.textContent` when only plaintext is intended.
## 2026-06-18 - [Fix XSS in file_view.html]
**Vulnerability:** A Cross-Site Scripting (XSS) vulnerability existed in `frontend/templates/file_view.html` where an error message (`err.message`) caught from a failed API request was injected directly into the DOM via `.innerHTML` without sanitization.
**Learning:** API responses (especially error messages that might reflect user input or be manipulated) can be vectors for DOM-based XSS when used to build HTML strings dynamically.
**Prevention:** Use an `escapeHtml` function to sanitize dynamic content before appending to `.innerHTML`, or use `.textContent` instead.
