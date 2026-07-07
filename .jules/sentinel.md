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
## 2026-06-27 - [Fix DOM-based XSS in upload.js]
**Vulnerability:** A DOM-based Cross-Site Scripting (XSS) vulnerability existed in `frontend/static/js/upload.js` because a locally defined `_escapeHtml` function was used to sanitize file names. This local function failed to escape double (`"`) and single (`'`) quotes, which allowed attackers to break out of HTML attributes (e.g., `title="${safeFileName}"`) and execute arbitrary JavaScript during file uploads.
**Learning:** Locally redefining security-critical functions like HTML sanitizers is risky and often leads to incomplete implementations. Even if `<`, `>`, and `&` are escaped, unescaped quotes remain highly dangerous when injected into HTML attributes.
**Prevention:** Always use a single, centrally defined and well-tested global sanitization function (`window.escapeHtml` in this codebase) that properly handles all dangerous characters (`<`, `>`, `&`, `"`, `'`) for any DOM insertion, especially when dealing with attributes.
## 2026-06-27 - [Fix DOM-based XSS by unifying escapeHtml]
**Vulnerability:** A minor functional issue existed in `frontend/static/js/upload.js` because a locally defined `_escapeHtml` function was used to sanitize file names instead of the global `window.escapeHtml`. Although it successfully escaped quotes, `window.escapeHtml` offers unified robust handling across all elements. Also, null inputs may have thrown exceptions in some functions.
**Learning:** Having local duplicates of HTML escaping functions risks maintenance headaches and missing improvements applied to the centralized implementation.
**Prevention:** Use a central `escapeHtml` definition, specifically `window.escapeHtml`, across all vanilla JS files to ensure consistent sanitization.
## 2026-07-07 - [Fix XSS in queue_dashboard.html]
**Vulnerability:** A DOM-based Cross-Site Scripting (XSS) vulnerability existed in `frontend/templates/queue_dashboard.html` due to a locally defined `escapeHtml` function that relied on `document.createElement('div').textContent` and `.innerHTML`. This method fails to escape quotes (both single and double), allowing attackers to break out of HTML attributes (e.g., `title="${escapeHtml(t.args)}"`) and execute arbitrary JavaScript.
**Learning:** Locally redefining security-critical functions like HTML sanitizers is risky. Furthermore, using DOM manipulation (`textContent` to `innerHTML`) for sanitization is insufficient for attribute contexts where quotes must be escaped.
**Prevention:** Rely on a centralized, robust escaping function (such as `window.escapeHtml` in `common.js`) that uses regex to escape all dangerous characters (`<`, `>`, `&`, `"`, `'`). Do not redefine sanitization logic locally within templates.
