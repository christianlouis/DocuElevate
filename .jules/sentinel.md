## 2026-06-01 - [Fix XSS in status_dashboard.html]
**Vulnerability:** A Cross-Site Scripting (XSS) vulnerability existed in `frontend/templates/status_dashboard.html` where untrusted configuration settings (`value`), external service messages (`data.message`), and token expirations (`data.token_info.expires_in_human`) were injected directly into the DOM via `.innerHTML` without sanitization.
**Learning:** Even internal or admin-focused dashboards can be vulnerable if they display external or user-configurable data without escaping. Constructing HTML strings dynamically from unvalidated sources is a common vector for DOM-based XSS.
**Prevention:** Always use a sanitization function like `escapeHtml` to escape dangerous characters (`<`, `>`, `&`, `"`, `'`) before assigning dynamic content to `.innerHTML`, or prefer `.textContent` when only plaintext is intended.

## 2026-06-23 - [Fix XSS in file_view.html error handling]
**Vulnerability:** A Cross-Site Scripting (XSS) vulnerability existed in `frontend/templates/file_view.html` where unescaped error messages (`err.message`) from failed fetch requests were directly appended to `.innerHTML`.
**Learning:** Error messages from external or API sources should not be trusted, as they can reflect user-controlled input (like filename or target language). Concatenating `err.message` into raw HTML is a common vector for DOM-based XSS when requests fail.
**Prevention:** Always use a global sanitization function like `escapeHtml` to sanitize error messages before assigning them to `.innerHTML`, or use `.textContent` instead if no HTML formatting is needed.
