## 2026-06-01 - [Fix XSS in status_dashboard.html]
**Vulnerability:** A Cross-Site Scripting (XSS) vulnerability existed in `frontend/templates/status_dashboard.html` where untrusted configuration settings (`value`), external service messages (`data.message`), and token expirations (`data.token_info.expires_in_human`) were injected directly into the DOM via `.innerHTML` without sanitization.
**Learning:** Even internal or admin-focused dashboards can be vulnerable if they display external or user-configurable data without escaping. Constructing HTML strings dynamically from unvalidated sources is a common vector for DOM-based XSS.
**Prevention:** Always use a sanitization function like `escapeHtml` to escape dangerous characters (`<`, `>`, `&`, `"`, `'`) before assigning dynamic content to `.innerHTML`, or prefer `.textContent` when only plaintext is intended.

## 2026-06-23 - [Fix XSS in file_view.html error handling]
**Vulnerability:** A Cross-Site Scripting (XSS) vulnerability existed in `frontend/templates/file_view.html` where unescaped error messages (`err.message`) from failed fetch requests were directly appended to `.innerHTML`.
**Learning:** Error messages from external or API sources should not be trusted, as they can reflect user-controlled input (like filename or target language). Concatenating `err.message` into raw HTML is a common vector for DOM-based XSS when requests fail.
**Prevention:** Always use a global sanitization function like `escapeHtml` to sanitize error messages before assigning them to `.innerHTML`, or use `.textContent` instead if no HTML formatting is needed.

## 2026-06-25 - [Fix DOM-based XSS in google_drive_callback.html]
**Vulnerability:** A DOM-based Cross-Site Scripting (XSS) vulnerability existed in `frontend/templates/google_drive_callback.html` where `folderName` received from the `google.picker.Document.NAME` API was directly inserted into `innerHTML` without sanitization.
**Learning:** Third-party APIs that return user-controlled data, such as folder or file names from Google Drive Picker, are untrusted and must be sanitized before DOM insertion. Do not trust external data blindly even if it comes from reputable providers.
**Prevention:** Use a sanitization function like `escapeHtml` to escape dangerous characters (`<`, `>`, `&`, `"`, `'`) before assigning dynamic content to `.innerHTML`, or assign text specifically via `.textContent`.
## 2026-06-26 - Fix Path Traversal in Automation Upload Endpoint

**Vulnerability:** The endpoint `/api/automation/actions/upload` relied solely on `os.path.basename()` to sanitize file names. This is insufficient to prevent path traversal since it may not correctly strip OS-specific paths (like Windows paths evaluated on Linux) or certain special characters, allowing malicious users to write files outside the intended upload directory.

**Learning:** Relying solely on `os.path.basename` is an incomplete protection mechanism against path traversal in file uploads.

**Prevention:** Always use a dedicated filename sanitization utility (such as `sanitize_filename` from `app.utils.filename_utils`) to rigorously strip directory components, path separators, and `..` patterns from untrusted input before using it to write files to disk.
## 2026-06-27 - [Fix DOM-based XSS by unifying escapeHtml]
**Vulnerability:** DOM-rendering code in `frontend/static/js/upload.js`, `comments.js`, and `sharing.js` relied on local HTML escaping helpers instead of the shared `window.escapeHtml`, increasing sanitizer drift risk across future DOM insertions.
**Learning:** Duplicating security-critical escaping logic makes it easy for future fixes to land in one helper while other call sites keep stale behavior.
**Prevention:** Use the centralized `window.escapeHtml` helper consistently across vanilla JS files for HTML string construction, especially when interpolating untrusted names into element text or attributes.
