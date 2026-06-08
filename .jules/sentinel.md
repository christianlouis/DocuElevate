## 2026-06-01 - [Fix XSS in status_dashboard.html]
**Vulnerability:** A Cross-Site Scripting (XSS) vulnerability existed in `frontend/templates/status_dashboard.html` where untrusted configuration settings (`value`), external service messages (`data.message`), and token expirations (`data.token_info.expires_in_human`) were injected directly into the DOM via `.innerHTML` without sanitization.
**Learning:** Even internal or admin-focused dashboards can be vulnerable if they display external or user-configurable data without escaping. Constructing HTML strings dynamically from unvalidated sources is a common vector for DOM-based XSS.
**Prevention:** Always use a sanitization function like `escapeHtml` to escape dangerous characters (`<`, `>`, `&`, `"`, `'`) before assigning dynamic content to `.innerHTML`, or prefer `.textContent` when only plaintext is intended.

## 2024-05-28 - Inconsistent escaping of err.message in innerHTML
**Vulnerability:** Across various frontend files (e.g. `file_view.html`, `files.html`), error messages from fetch requests (`err.message`) were being directly concatenated into HTML strings and assigned to `innerHTML` of DOM elements.
**Learning:** This exposes the application to DOM-based XSS vulnerabilities if the API response reflects malicious input or if an attacker can manipulate the error response. The codebase had an `escapeHtml` function defined in some files but not consistently applied or available in others.
**Prevention:** Always ensure that `err.message` or any dynamically generated text is wrapped with `escapeHtml` before being injected into the DOM via `innerHTML` or string interpolation. Create a utility module or ensure `escapeHtml` is globally available and consistently used for all error handling UI updates.
