## 2026-06-01 - [Fix XSS in status_dashboard.html]
**Vulnerability:** A Cross-Site Scripting (XSS) vulnerability existed in `frontend/templates/status_dashboard.html` where untrusted configuration settings (`value`), external service messages (`data.message`), and token expirations (`data.token_info.expires_in_human`) were injected directly into the DOM via `.innerHTML` without sanitization.
**Learning:** Even internal or admin-focused dashboards can be vulnerable if they display external or user-configurable data without escaping. Constructing HTML strings dynamically from unvalidated sources is a common vector for DOM-based XSS.
**Prevention:** Always use a sanitization function like `escapeHtml` to escape dangerous characters (`<`, `>`, `&`, `"`, `'`) before assigning dynamic content to `.innerHTML`, or prefer `.textContent` when only plaintext is intended.

## 2025-02-26 - [DOM-Based XSS in Frontend Templates]
**Vulnerability:** Fetch error handlers assigned `err.message` directly to `innerHTML` without sanitization, allowing DOM-based Cross-Site Scripting (XSS) if the API returned an error message reflecting malicious input.
**Learning:** Error messages returned by APIs should always be treated as untrusted input when rendered in the DOM, especially when using `innerHTML`. This codebase frequently uses vanilla JavaScript with direct DOM manipulation.
**Prevention:** Always define and use an `escapeHtml` function to sanitize user-controlled or API-returned strings before inserting them into the DOM via `innerHTML`, or use `textContent` where applicable.
