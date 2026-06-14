## 2026-06-01 - [Fix XSS in status_dashboard.html]
**Vulnerability:** A Cross-Site Scripting (XSS) vulnerability existed in `frontend/templates/status_dashboard.html` where untrusted configuration settings (`value`), external service messages (`data.message`), and token expirations (`data.token_info.expires_in_human`) were injected directly into the DOM via `.innerHTML` without sanitization.
**Learning:** Even internal or admin-focused dashboards can be vulnerable if they display external or user-configurable data without escaping. Constructing HTML strings dynamically from unvalidated sources is a common vector for DOM-based XSS.
**Prevention:** Always use a sanitization function like `escapeHtml` to escape dangerous characters (`<`, `>`, `&`, `"`, `'`) before assigning dynamic content to `.innerHTML`, or prefer `.textContent` when only plaintext is intended.
## 2026-06-14 - [Fix XSS in file_view.html]
**Vulnerability:** A DOM-based Cross-Site Scripting (XSS) vulnerability existed in `frontend/templates/file_view.html` where `err.message` from API catch blocks (text extraction, translations) was injected directly into the DOM using `area.innerHTML` without escaping.
**Learning:** Error messages from external APIs or backend services can contain malicious input (e.g. reflected user input), which becomes executable when rendered as HTML.
**Prevention:** All dynamic string data, including error messages, must be sanitized using a localized `escapeHtml` implementation before being concatenated into strings destined for `.innerHTML`.
