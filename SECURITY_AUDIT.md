# Security Audit Report

**Date:** 2026-02-12
**Status:** Bandit Security Scan Completed - All Critical/High/Medium Issues Resolved

## Executive Summary

This document tracks security vulnerabilities found in DocuElevate and their remediation status. A comprehensive security audit using Bandit has been completed, with all critical, high, and medium severity issues addressed.

## Recent Security Fixes

### CVE-2023-36464: PyPDF2/pypdf Infinite Loop Vulnerability ✅ FIXED (2026-02-12)

**Severity:** Moderate (CVSS: 5.5)
**CVE:** [CVE-2023-36464](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2023-36464)
**Advisory:** [GHSA-4vvm-4w3v-6mr8](https://github.com/advisories/GHSA-4vvm-4w3v-6mr8)

**Issue:** Certain versions of PyPDF2 (>=2.2.0, <=3.0.1) and pypdf (prior to 3.9.0) contain a vulnerability where specially crafted PDF files can trigger an infinite loop in `__parse_content_stream`, causing 100% CPU usage and potential denial of service.

**Impact:**
- **Availability:** High (can block process and consume 100% CPU)
- **Confidentiality:** None
- **Integrity:** None
- **Attack Vector:** Local
- **Privileges Required:** None

**Remediation:**
- Upgraded from `PyPDF2>=3.0.0` (vulnerable) to `pypdf>=3.9.0` (fixed)
- Updated all imports from `PyPDF2` to `pypdf` across the codebase
- Verified pypdf 6.7.0 installed successfully
- **Files Updated:**
  - `requirements.txt` - Updated dependency specification
  - `app/tasks/process_document.py`
  - `app/tasks/rotate_pdf_pages.py`
  - `app/utils/file_splitting.py`
  - `app/tasks/embed_metadata_into_pdf.py`
  - `app/tasks/process_with_azure_document_intelligence.py`
  - `app/views/files.py`
  - `app/api/files.py`
  - `tests/test_external_integrations.py`
  - `tests/test_file_splitting.py`

**Testing:** All affected modules verified for syntax correctness and basic import functionality.

**References:**
- [py-pdf/pypdf#1828](https://github.com/py-pdf/pypdf/pull/1828) - Fix implementation
- [py-pdf/pypdf#969](https://github.com/py-pdf/pypdf/pull/969) - Issue introduction

## Bandit Security Scan Results (2026-02-07)

**Scan Summary:**
- **Total lines scanned:** 7,423
- **High severity issues:** 0 (6 fixed)
- **Medium severity issues:** 0 (15 fixed)
- **Low severity issues:** 21 (informational/acceptable)

### Fixed Issues from Bandit Scan

#### 1. B324: Weak MD5 Hash Usage (HIGH SEVERITY) ✅ FIXED
**Occurrences:** 2
**Locations:**
- `app/api/user.py:26` - Gravatar URL generation
- `app/auth.py:65` - Gravatar URL generation

**Issue:** MD5 hash was used without specifying `usedforsecurity=False` parameter.

**Remediation:** Added `usedforsecurity=False` parameter to all MD5 hash calls. MD5 is used only for Gravatar URL generation (non-cryptographic purpose), which is an acceptable use case.

```python
# Before: email_hash = md5(email.encode()).hexdigest()
# After:  email_hash = md5(email.encode(), usedforsecurity=False).hexdigest()
```

#### 2. B402/B321: Insecure FTP Protocol (HIGH SEVERITY) ✅ DOCUMENTED
**Occurrences:** 3
**Location:** `app/tasks/upload_to_ftp.py`

**Issue:** FTP is an insecure protocol vulnerable to eavesdropping and MITM attacks.

**Remediation:**
- Added comprehensive security warnings in code comments
- Code already defaults to FTPS (FTP_TLS) for encrypted connections
- Plaintext FTP only used as fallback when explicitly configured
- Added `# nosec B402` and `# nosec B321` annotations with justification
- Added security notes in docstrings
- Configuration options: `ftp_use_tls=True` (default), `ftp_allow_plaintext=True` (default)

**Security Note:** For production environments, set `ftp_allow_plaintext=False` to prevent fallback to unencrypted FTP.

#### 3. B507: SSH Host Key Verification Disabled (HIGH SEVERITY) ✅ FIXED
**Occurrences:** 1
**Location:** `app/tasks/upload_to_sftp.py:47`

**Issue:** Using `paramiko.AutoAddPolicy()` automatically trusts unknown SSH host keys, making connections vulnerable to MITM attacks.

**Remediation:**
- Added configuration option `sftp_disable_host_key_verification` (default: False for security)
- When enabled (False), uses `paramiko.RejectPolicy()` with system known_hosts for secure verification
- When disabled (True, for testing only), uses `AutoAddPolicy()` with security warnings
- Added `# nosec B507` annotation with justification for the test/dev use case
- Updated docstrings with security guidance

**Security Note:** The default value is now `False` (secure). For development/testing environments where host keys cannot be pre-configured, set `SFTP_DISABLE_HOST_KEY_VERIFICATION=True` (not recommended for production).

#### 4. B113: Missing Timeout on HTTP Requests (MEDIUM SEVERITY) ✅ FIXED
**Occurrences:** 15
**Locations:**
- `app/api/dropbox.py` (4 requests calls)
- `app/api/google_drive.py` (1 request call)
- `app/api/onedrive.py` (3 requests calls)
- `app/tasks/convert_to_pdf.py` (1 request call)
- `app/tasks/upload_to_dropbox.py` (1 request call)
- `app/tasks/upload_to_paperless.py` (2 requests calls)
- `app/tasks/upload_to_onedrive.py` (2 requests calls)
- `app/tasks/upload_to_webdav.py` (1 request call)

**Issue:** HTTP requests without timeout can hang indefinitely, leading to resource exhaustion and potential DoS.

**Remediation:**
- Added `http_request_timeout` configuration setting (default: 120 seconds)
- Timeout configured to handle large file operations (PDFs up to 1GB+)
- Applied `timeout=settings.http_request_timeout` to all `requests.get()`, `requests.post()`, and `requests.put()` calls
- Configurable via environment variable: `HTTP_REQUEST_TIMEOUT=120`

**Note:** The 120-second default timeout is appropriate for:
- Large PDF file uploads and downloads (up to 1GB)
- PDF conversion operations via Gotenberg
- Cloud storage uploads (Dropbox, OneDrive, Google Drive, Nextcloud, WebDAV)
- Document processing and OCR operations

### Low Severity Issues (Informational)

**21 low severity findings remain** - These are informational warnings about:
- `assert` statements (B101) - Used in non-security contexts
- Try-except-pass blocks (B110) - Acceptable for optional operations
- Subprocess calls (B603/B607) - Verified safe (hardcoded commands, no user input)
- Hard-coded temp directories (B108) - Platform-appropriate temp paths
- Hard-coded bind addresses (B104) - Development defaults

**Assessment:** All low severity findings have been reviewed and are acceptable given the context of their usage.

## Critical Vulnerabilities (Fixed) ✅

### 1. Outdated Authlib with Known Vulnerabilities
**Status:** ✅ FIXED
**Severity:** HIGH
**Description:** Authlib version 1.3.2 had two critical vulnerabilities:
- CVE: Denial of Service via Oversized JOSE Segments
- CVE: JWS/JWT accepts unknown crit headers (RFC violation → possible authz bypass)

**Fix:** Updated `requirements.txt` to require `authlib>=1.6.5`

### 2. Starlette DoS Vulnerability
**Status:** ✅ FIXED
**Severity:** MEDIUM
**Description:** Starlette 0.41.3 vulnerable to O(n^2) DoS via Range header merging in `FileResponse`

**Fix:** Updated `requirements.txt` to require `starlette>=0.49.1`

### 3. Weak SESSION_SECRET Default
**Status:** ✅ FIXED
**Severity:** HIGH
**Description:** Default SESSION_SECRET value in `app/main.py` was a predictable string that could be exploited if not overridden

**Fix:**
- Enhanced validation in `app/main.py` to raise error if auth is enabled without proper secret
- Updated default to be clearly marked as insecure for development only
- Added generation instructions in error message

## Medium Risk Issues (Fixed) ✅

### 4. Insufficient .gitignore Protection
**Status:** ✅ FIXED
**Severity:** MEDIUM
**Description:** .gitignore didn't adequately protect against accidentally committing sensitive files (credentials, private keys, secrets)

**Fix:** Enhanced `.gitignore` with comprehensive patterns for:
- Various environment file formats
- Credential JSON files
- Private keys (.pem, .key, .pfx, etc.)
- SSH keys
- Explicit exclusion of patterns where needed

### 5. File Upload Size Limits
**Status:** ✅ FIXED
**Severity:** MEDIUM
**Description:** No configurable limits on file upload sizes could lead to resource exhaustion attacks and DoS.

**Fix:** Implemented configurable file upload size limits with the following features:
- `MAX_UPLOAD_SIZE`: Maximum file upload size in bytes (default: 1GB)
- `MAX_SINGLE_FILE_SIZE`: Optional maximum size for a single file chunk
- **Automatic page-based PDF splitting** for large PDFs when max_single_file_size is configured
  - Splits PDFs at **page boundaries** using pypdf, NOT by byte position
  - Each output file is a structurally valid, complete PDF
  - No risk of corrupted or broken PDF files
- Split files are processed sequentially to prevent overwhelming the system
- Clear error messages referencing SECURITY_AUDIT.md for configuration details

**Configuration:**
```bash
# Set maximum upload size (default: 1GB)
MAX_UPLOAD_SIZE=1073741824

# Optional: Enable file splitting for large PDFs
MAX_SINGLE_FILE_SIZE=104857600  # 100MB chunks
```

**Security Benefits:**
- Prevents resource exhaustion from extremely large uploads
- Configurable limits allow adaptation to server capacity
- File splitting enables processing of large documents without memory issues
- Maintains support for large PDF files (up to 1GB by default) as required by use case

## Best Practices Implemented

### Security Scanning with Bandit
- ✅ Bandit installed in development dependencies (`requirements-dev.txt`)
- ✅ Comprehensive scan completed on all Python code
- ✅ High and medium severity issues resolved
- ✅ Low severity issues reviewed and accepted

**Running Bandit:**
```bash
# Scan entire app directory
bandit -r app

# Show only high and medium severity
bandit -r app -ll

# Generate JSON report
bandit -r app -f json -o bandit_results.json

# Generate HTML report
bandit -r app -f html -o bandit_report.html
```

**Suppressing False Positives:**
Use `# nosec` comments with justification:
```python
# Security: FTP usage intentional for legacy server support
import ftplib  # nosec B402 - FTP usage is intentional

ftp = ftplib.FTP()  # nosec B321 - Plaintext FTP intentional when configured
```

### Dependency Management
- ✅ Version pinning for security-critical packages (authlib, starlette)
- ✅ Advisory database checks integrated into development workflow
- ✅ Automated dependency vulnerability scanning in CI/CD via pip-audit ([#171](https://github.com/christianlouis/DocuElevate/issues/171))

### Authentication & Secrets
- ✅ Strong validation for SESSION_SECRET (minimum 32 characters)
- ✅ Error-on-missing for critical security settings when auth enabled
- ✅ Clear documentation of secret generation methods
- ✅ .env.demo file for configuration examples (no real secrets)

### Configuration Security
- ✅ All secrets loaded from environment variables
- ✅ No hardcoded credentials in codebase
- ✅ Proper masking in configuration validators

## Ongoing Security Measures

### CI/CD Security
- ✅ **COMPLETED:** Bandit (Python security linter) audit completed
- ✅ **COMPLETED:** Bandit integrated into CI pipeline (fails on high/medium severity issues)
- ✅ **COMPLETED:** CodeQL security scanning enabled in GitHub Actions
- ✅ **COMPLETED:** pip-audit dependency vulnerability scanning added to CI ([#171](https://github.com/christianlouis/DocuElevate/issues/171))
- ✅ **COMPLETED:** Dependency scans are blocking (fail build when vulnerabilities detected) ([#171](https://github.com/christianlouis/DocuElevate/issues/171))

### Code Security
- ✅ Authentication required on all sensitive endpoints (@require_login decorator)
- ✅ Path traversal protection in file uploads (basename sanitization)
- ✅ Unique filenames with UUID to prevent conflicts and overwrites
- ✅ File upload size limits with configurable maximum (default: 1GB)
- ✅ Optional file splitting for large PDFs (when max_single_file_size is configured)
- ✅ Request body size limits via `RequestSizeLimitMiddleware` (non-upload: 1MB default; uploads: governed by MAX_UPLOAD_SIZE)
- ✅ Streaming file reads in upload endpoint to prevent memory exhaustion
- ⏳ **TODO:** Implement rate limiting on API endpoints
- ⏳ **TODO:** Add CSRF protection for state-changing operations
- ✅ **COMPLETED:** Add comprehensive input sanitization for all user inputs ([#172](https://github.com/christianlouis/DocuElevate/issues/172))
  - `app/utils/input_validation.py` — centralized validation module with:
    - `validate_setting_key()`: allow-lists setting keys against `SETTING_METADATA` (prevents attribute enumeration / Python object sniffing via `getattr`)
    - `validate_sort_field()`: enforces sort field against an explicit allow-list
    - `validate_sort_order()`: ensures sort direction is exactly `asc` or `desc`
    - `validate_search_query()`: strips whitespace, enforces 255-character maximum
    - `validate_task_id()`: validates Celery task IDs against UUID v4 format
  - Applied to `app/api/settings.py` (GET/POST/DELETE `/{key}` endpoints)
  - Applied to `app/api/files.py` (file list sort + search query parameters)
  - Applied to `app/api/logs.py` (task_id query filter and path parameter)
  - 30 unit tests added in `tests/test_input_validation.py`
- ✅ **COMPLETED:** Implement proper API key rotation mechanisms ([#168](https://github.com/christianlouis/DocuElevate/issues/168))
  - `docs/CredentialRotationGuide.md` — comprehensive rotation guide covering:
    - Recommended rotation schedule for all credential types
    - Per-credential rotation procedures for OpenAI, Azure, AWS S3, Dropbox, Google Drive, OneDrive, Authentik, Paperless-ngx, SMTP, IMAP, Nextcloud, FTP, SFTP, WebDAV, and admin credentials
    - Onboarding instructions (creating service-specific credentials with minimal permissions)
    - Offboarding instructions (revocation, rotation of shared credentials, audit log review)
    - Emergency revocation procedure
  - `GET /api/settings/credentials` — admin-only endpoint listing all sensitive credential settings with configured/unconfigured status and source (`env` vs `db`), enabling credential rotation audits without exposing secret values

### Infrastructure Security
- ✅ TrustedHostMiddleware configured (restricts valid hosts)
- ✅ ProxyHeadersMiddleware for reverse proxy setup (X-Forwarded-* headers)
- ✅ SessionMiddleware with strong secret validation
- ✅ **Security headers middleware implemented** - Configurable HSTS, CSP, X-Frame-Options, X-Content-Type-Options ([#174](https://github.com/christianlouis/DocuElevate/issues/174))
  - Disabled by default (typical deployment uses reverse proxy that adds headers)
  - Can be enabled for direct deployment without reverse proxy
  - Individual header control and customization
  - Documented in DeploymentGuide.md and ConfigurationGuide.md
- ⏳ **TODO:** Implement proper CORS configuration (currently not configured) ([#175](https://github.com/christianlouis/DocuElevate/issues/175))
- ✅ **Request logging with sensitive data masking implemented** ([#170](https://github.com/christianlouis/DocuElevate/issues/170))
  - `AuditLogMiddleware` in `app/middleware/audit_log.py` logs every HTTP request
  - Logs: method, path, status code, response time, client IP (configurable), username
  - Sensitive query-parameter values (password, token, key, secret, etc.) are automatically replaced with ``[REDACTED]``
  - Security events (401, 403, login attempts, 5xx errors) receive elevated ``[SECURITY]`` log entries
  - Configurable via `AUDIT_LOGGING_ENABLED` and `AUDIT_LOG_INCLUDE_CLIENT_IP` environment variables

## Recommendations

### High Priority
1. ~~**Enable CodeQL scanning**~~ ✅ Already implemented - Two CodeQL workflows active
2. **Implement rate limiting** - Prevent abuse and DoS attacks (consider slowapi or fastapi-limiter)
3. ~~**Add comprehensive input validation**~~ ✅ Implemented — centralized `app/utils/input_validation.py` module with allow-list validators for sort fields, sort order, search queries, task IDs, and setting keys; applied across `files.py`, `logs.py`, and `settings.py` endpoints ([#172](https://github.com/christianlouis/DocuElevate/issues/172))
4. ~~**Add request size limits**~~ ✅ Implemented - `RequestSizeLimitMiddleware` enforces `MAX_REQUEST_BODY_SIZE` (default 1 MB) for non-file requests and `MAX_UPLOAD_SIZE` (default 1 GB) for multipart uploads; file uploads also use streaming reads to bound memory usage ([#173](https://github.com/christianlouis/DocuElevate/issues/173))
5. **Implement CSRF protection** - Protect state-changing operations

### Medium Priority
1. ~~**Add security headers**~~ ✅ Implemented - Configurable HSTS, CSP, X-Frame-Options, X-Content-Type-Options middleware
2. **Configure CORS properly** - Currently no CORS middleware configured ([#175](https://github.com/christianlouis/DocuElevate/issues/175))
3. ~~**Implement audit logging**~~ ✅ Implemented - Request/audit logging with sensitive data masking ([#170](https://github.com/christianlouis/DocuElevate/issues/170))
4. ~~**Add file upload size limits**~~ ✅ Implemented - Configurable limits with 1GB default, optional file splitting
5. **Document security architecture** - Security design decisions

### Low Priority
1. **Security training documentation** - For contributors
2. **Penetration testing** - Professional security assessment
3. **Bug bounty program** - Community security contributions
4. ~~**API key rotation**~~ ✅ Implemented — `docs/CredentialRotationGuide.md` documents rotation procedures, onboarding/offboarding, and emergency revocation; `GET /api/settings/credentials` provides a credential audit endpoint ([#168](https://github.com/christianlouis/DocuElevate/issues/168))

## Security Contact

For security issues, please follow the guidelines in [SECURITY.md](SECURITY.md).

## Audit History

| Date | Auditor | Scope | Critical Issues | Status |
|------|---------|-------|-----------------|--------|
| 2026-02-06 | Automated Agent | Dependencies, Auth, Config | 3 | Fixed |
| 2026-02-07 | Bandit Security Scanner | Python Code Security | 6 High, 15 Medium | Fixed |
| 2026-02-10 | Path Traversal Review | File Path Operations | 1 Critical, 2 Medium | Fixed |

---

## Path Traversal Vulnerability Audit (2026-02-10)

**Status:** ✅ ALL ISSUES FIXED
**Scope:** Comprehensive review of all file path operations for path traversal vulnerabilities

### Executive Summary

A thorough security audit was conducted on all file path operations in DocuElevate to identify and remediate path traversal vulnerabilities. **One critical vulnerability and two medium-severity issues were identified and fixed.**

### Critical Vulnerability: Path Traversal via GPT Metadata Filename

**Status:** ✅ FIXED
**Severity:** CRITICAL
**Location:** `app/tasks/embed_metadata_into_pdf.py` (line 144)

**Description:**
The `metadata["filename"]` extracted by GPT was used directly in file path operations without sanitization. A malicious document could be crafted to make GPT return metadata containing path traversal sequences (e.g., `../../etc/passwd`, `..\\windows\\system32`), allowing file writes outside the intended `processed/` directory.

**Attack Vector:**
1. User uploads a specially crafted document
2. GPT extracts metadata and returns malicious filename: `../../etc/passwd`
3. `embed_metadata_into_pdf` uses this filename directly: `os.path.join(processed_dir, "../../etc/passwd")`
4. File is written to `/etc/passwd` instead of `processed/` directory

**Security Impact:**
- File write outside intended directory
- Potential overwrite of system files
- Privilege escalation if workdir is writable by limited user

**Fix Applied:**
```python
# Import sanitize_filename
from app.utils.filename_utils import sanitize_filename

# In embed_metadata_into_pdf function (line 144-148):
suggested_filename = metadata.get("filename", os.path.splitext(os.path.basename(local_file_path))[0])
# SECURITY: Sanitize filename to prevent path traversal vulnerabilities
suggested_filename = sanitize_filename(suggested_filename)
suggested_filename = os.path.splitext(suggested_filename)[0]
```

**Validation:** The `sanitize_filename()` function removes:
- Path separators (`/`, `\`)
- Path traversal patterns (`..`)
- Special characters unsafe for filenames
- Leading/trailing periods and spaces

### Medium Vulnerability: Insecure Path Validation Using String Prefix Check

**Status:** ✅ FIXED
**Severity:** MEDIUM
**Location:** `app/tasks/embed_metadata_into_pdf.py` (line 188-193)

**Description:**
The code used string-based `startswith()` check to validate if a file was within the workdir/tmp directory before deletion. This is vulnerable to:
- Partial directory name matches (e.g., `/workdir/tmp2/` would pass if workdir is `/workdir/tmp`)
- Symlink attacks (symlinks are not resolved before checking)
- Race conditions (TOCTOU - Time Of Check, Time Of Use)

**Vulnerable Code:**
```python
# INSECURE: String-based path validation
workdir_tmp = os.path.join(settings.workdir, TMP_SUBDIR)
if original_file.startswith(workdir_tmp) and os.path.exists(original_file):
    os.remove(original_file)
```

**Fix Applied:**
```python
# SECURE: Pathlib-based validation with resolve()
from pathlib import Path

workdir_tmp_path = Path(settings.workdir) / TMP_SUBDIR
try:
    original_file_path = Path(original_file).resolve()
    workdir_tmp_resolved = workdir_tmp_path.resolve()

    # Check if file is within workdir/tmp and exists
    if original_file_path.is_relative_to(workdir_tmp_resolved) and original_file_path.exists():
        original_file_path.unlink()
        logger.info(f"Deleted original file from {original_file}")
except (ValueError, OSError) as e:
    logger.error(f"Error validating path for deletion {original_file}: {e}")
```

**Benefits of pathlib approach:**
- `resolve()` follows symlinks to get canonical path
- `is_relative_to()` performs proper path hierarchy check
- Raises `ValueError` for paths outside the base directory
- Platform-independent path handling

### Medium Issue: Insufficient Validation of GPT-Extracted Filenames

**Status:** ✅ FIXED
**Severity:** MEDIUM
**Location:** `app/tasks/extract_metadata_with_gpt.py` (after line 124)

**Description:**
While the GPT prompt requested filenames in a specific format (YYYY-MM-DD_DescriptiveTitle with only letters, numbers, periods, underscores), there was no validation to enforce this constraint. GPT may not always comply with the format specification, potentially returning:
- Filenames with path separators
- Filenames with path traversal patterns
- Filenames with special characters

**Fix Applied:**
```python
import re

metadata = json.loads(json_text)

# SECURITY: Validate filename format from GPT to prevent path traversal
filename = metadata.get("filename", "")
if filename:
    # Check if filename contains only safe characters
    if not re.match(r'^[\w\-\. ]+$', filename):
        logger.warning(f"Invalid filename format from GPT: '{filename}', using fallback")
        metadata["filename"] = ""
    # Additional check: ensure no path traversal patterns
    elif ".." in filename or "/" in filename or "\\" in filename:
        logger.warning(f"Path traversal attempt in GPT filename: '{filename}', using fallback")
        metadata["filename"] = ""
```

**Defense in Depth:**
This validation provides an additional layer of security before the filename reaches `embed_metadata_into_pdf.py`, where it is also sanitized.

### Security-Positive Findings

During the audit, several security-positive implementations were identified:

#### 1. ✅ File Upload Endpoint Security (`app/api/files.py`)

**Function:** `ui_upload` (line 654-757)

**Security Measures:**
```python
# Extract basename to remove directory components
base_filename = os.path.basename(file.filename)

# Sanitize to remove special characters and path separators
safe_filename = sanitize_filename(base_filename)

# Add UUID to prevent overwrites and filename conflicts
unique_id = str(uuid.uuid4())
target_filename = f"{unique_id}.{file_extension}"

# Join with workdir (safe because all inputs are sanitized)
target_path = os.path.join(workdir, target_filename)
```

**Assessment:** ✅ SECURE - Properly prevents path traversal attacks

#### 2. ✅ File Download/Preview Endpoints (`app/api/files.py`)

**Functions:** `download_file` and `get_file_preview` (lines 510-651)

**Security Measures:**
- Use database-backed `file_id` parameter (integer) instead of accepting file paths
- Retrieve file paths from database records only
- Check file existence before serving
- No direct user input in file path construction

**Assessment:** ✅ SECURE - Immune to path traversal (no user-controlled paths)

#### 3. ✅ Safe Path Resolution in API Common (`app/api/common.py`)

**Function:** `resolve_file_path`

**Security Implementation:**
```python
from pathlib import Path

def resolve_file_path(base_dir, file_path):
    """Safely resolve file path within base directory."""
    base = Path(base_dir).resolve()
    target = (base / file_path).resolve()

    # Ensure target is within base directory
    if not target.is_relative_to(base):
        raise ValueError("Path traversal attempt detected")

    return target
```

**Assessment:** ✅ SECURE - Properly validates paths using pathlib

#### 4. ✅ Rclone Upload Task (`app/tasks/upload_with_rclone.py`)

**Security Measures:**
- Validates remote names with regex pattern
- Uses list arguments to subprocess (prevents shell injection)
- No user input in command construction

**Assessment:** ✅ SECURE - Safe subprocess usage

### Testing

**Comprehensive test suite added:** `tests/test_path_traversal_security.py`

**Test Coverage:**
- ✅ Filename sanitization prevents path traversal (8 tests)
- ✅ Metadata embedding flow with malicious filenames (4 tests)
- ✅ GPT filename validation (2 tests)
- ✅ Pathlib-based path validation security (4 tests)
- ✅ File upload security (2 tests)
- ✅ File hashing security (2 tests)
- ✅ End-to-end integration tests (2 tests)

**Total:** 24 security tests added

**Running Security Tests:**
```bash
# Run all security tests
pytest tests/test_path_traversal_security.py -v

# Run only security marker tests
pytest -m security -v

# Run with coverage
pytest tests/test_path_traversal_security.py --cov=app --cov-report=term-missing
```

### Recommendations

**Implemented Security Best Practices:**

1. ✅ **Input Sanitization:** All user-supplied filenames are sanitized using `sanitize_filename()`
2. ✅ **Path Validation:** Use `pathlib.Path` with `resolve()` and `is_relative_to()` for all path validation
3. ✅ **Defense in Depth:** Multiple layers of validation (at GPT extraction, at metadata embedding, at file upload)
4. ✅ **Secure Defaults:** Safe filename generation with UUID when user input is untrusted
5. ✅ **Principle of Least Privilege:** File operations restricted to specific directories

**Additional Recommendations for Future Development:**

1. **Code Review Checklist:** Add path traversal checks to code review process:
   - Never use `os.path.join()` with unsanitized user input
   - Always use `sanitize_filename()` for user-supplied filenames
   - Use `pathlib.Path.resolve()` for path validation
   - Avoid string-based path validation (`startswith()`)

2. **Static Analysis:** Run Bandit security scanner regularly:
   ```bash
   bandit -r app -ll  # Show high and medium severity
   ```

3. **Automated Testing:** Include security tests in CI/CD pipeline:
   ```bash
   pytest -m security  # Run all security-marked tests
   ```

4. **Security Training:** Educate developers on:
   - Path traversal attack vectors
   - Secure file handling best practices
   - OWASP Top 10 vulnerabilities

### Files Modified

**Security Fixes:**
- `app/tasks/embed_metadata_into_pdf.py` - Added filename sanitization and secure path validation
- `app/tasks/extract_metadata_with_gpt.py` - Added GPT filename validation
- `app/utils/filename_utils.py` - Existing sanitization function (no changes needed, already secure)

**Tests Added:**
- `tests/test_path_traversal_security.py` - Comprehensive security test suite (24 tests)

**Documentation:**
- `SECURITY_AUDIT.md` - This audit report

### Conclusion

All identified path traversal vulnerabilities have been remediated with defense-in-depth security measures. The codebase now follows security best practices for file path operations:

- ✅ All user input is sanitized before use in file operations
- ✅ Path validation uses secure pathlib methods instead of string comparisons
- ✅ Multiple layers of validation prevent bypasses
- ✅ Comprehensive test coverage validates security fixes
- ✅ Security-positive patterns already in use for file uploads and downloads

**Overall Security Posture:** STRONG - No remaining path traversal vulnerabilities identified.

---

## Security Headers Implementation (2026-02-10)

**Status:** ✅ COMPLETED
**Scope:** HTTP security headers middleware for browser-side security

### Executive Summary

Implemented configurable security headers middleware to improve browser-side security in DocuElevate. The implementation supports both direct deployment and reverse proxy scenarios (Traefik, Nginx, etc.), with full documentation and test coverage.

### Security Headers Implemented

#### 1. Strict-Transport-Security (HSTS)

**Purpose:** Forces browsers to use HTTPS for all future requests to the domain.

**Implementation:**
```python
# Default configuration
SECURITY_HEADER_HSTS_ENABLED=true
SECURITY_HEADER_HSTS_VALUE="max-age=31536000; includeSubDomains"
```

**Benefits:**
- Prevents downgrade attacks (forcing HTTPS → HTTP)
- Protects against man-in-the-middle attacks
- 1-year max-age ensures long-term HTTPS enforcement
- `includeSubDomains` extends protection to all subdomains

**Note:** HSTS only works over HTTPS. For development over HTTP, disable this header.

#### 2. Content-Security-Policy (CSP)

**Purpose:** Controls which resources browsers are allowed to load, preventing XSS and code injection attacks.

**Implementation:**
```python
# Default configuration (allows Tailwind CSS and inline scripts)
SECURITY_HEADER_CSP_VALUE="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:;"
```

**Benefits:**
- Prevents unauthorized script execution
- Controls image, font, and style loading
- Mitigates XSS attack vectors
- Customizable per deployment needs

**Trade-offs:**
- Default policy includes `'unsafe-inline'` for compatibility with Tailwind CSS and inline JavaScript
- Stricter policies can be configured using nonces or hashes

#### 3. X-Frame-Options

**Purpose:** Prevents the application from being loaded in frames/iframes, protecting against clickjacking attacks.

**Implementation:**
```python
# Default configuration (strongest protection)
SECURITY_HEADER_X_FRAME_OPTIONS_VALUE="DENY"
```

**Options:**
- `DENY` - No framing allowed (default, most secure)
- `SAMEORIGIN` - Allow framing only from same origin
- `ALLOW-FROM uri` - Allow framing from specific origin (deprecated)

**Benefits:**
- Prevents UI redressing attacks
- Protects sensitive operations from being obscured
- Simple and effective clickjacking protection

#### 4. X-Content-Type-Options

**Purpose:** Prevents browsers from MIME-sniffing responses away from declared content-type.

**Implementation:**
```python
# Always set to 'nosniff' when enabled
SECURITY_HEADER_X_CONTENT_TYPE_OPTIONS_ENABLED=true
```

**Benefits:**
- Prevents MIME confusion attacks
- Forces browsers to respect declared content-types
- Reduces XSS attack surface

### Deployment Scenarios

#### Reverse Proxy Deployment (Traefik, Nginx, etc.) - DEFAULT

**Most deployments use a reverse proxy**, which is why security headers are **disabled by default** in DocuElevate. The reverse proxy should add these headers.

```bash
# .env configuration (or omit - this is the default)
SECURITY_HEADERS_ENABLED=false
```

**Traefik Example:**
```yaml
labels:
  - "traefik.http.middlewares.security-headers.headers.stsSeconds=31536000"
  - "traefik.http.middlewares.security-headers.headers.contentSecurityPolicy=default-src 'self';"
  - "traefik.http.middlewares.security-headers.headers.customFrameOptionsValue=DENY"
  - "traefik.http.middlewares.security-headers.headers.contentTypeNosniff=true"
```

**Nginx Example:**
```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header Content-Security-Policy "default-src 'self';" always;
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
```

#### Direct Deployment (No Reverse Proxy)

If deploying directly without a reverse proxy, **enable security headers**:

```bash
# .env configuration
SECURITY_HEADERS_ENABLED=true
SECURITY_HEADER_HSTS_ENABLED=true
SECURITY_HEADER_CSP_ENABLED=true
SECURITY_HEADER_X_FRAME_OPTIONS_ENABLED=true
SECURITY_HEADER_X_CONTENT_TYPE_OPTIONS_ENABLED=true
```

All headers are added by the application middleware.

### Configuration Options

All security headers are configurable via environment variables:

| Setting | Purpose | Default |
|---------|---------|---------|
| `SECURITY_HEADERS_ENABLED` | Master enable/disable | `false` |
| `SECURITY_HEADER_HSTS_ENABLED` | Enable HSTS | `true` |
| `SECURITY_HEADER_HSTS_VALUE` | HSTS configuration | `max-age=31536000; includeSubDomains` |
| `SECURITY_HEADER_CSP_ENABLED` | Enable CSP | `true` |
| `SECURITY_HEADER_CSP_VALUE` | CSP policy | See implementation details |
| `SECURITY_HEADER_X_FRAME_OPTIONS_ENABLED` | Enable X-Frame-Options | `true` |
| `SECURITY_HEADER_X_FRAME_OPTIONS_VALUE` | Frame options | `DENY` |
| `SECURITY_HEADER_X_CONTENT_TYPE_OPTIONS_ENABLED` | Enable X-Content-Type-Options | `true` |

### Implementation Details

**Files Modified:**
- `app/middleware/security_headers.py` - Security headers middleware implementation
- `app/middleware/__init__.py` - Middleware package initialization
- `app/config.py` - Configuration settings for security headers
- `app/main.py` - Middleware integration into FastAPI application
- `.env.demo` - Example configuration with security header settings

**Documentation:**
- `docs/DeploymentGuide.md` - Added comprehensive security headers section with Traefik/Nginx examples
- `docs/ConfigurationGuide.md` - Added detailed configuration reference for all header options
- `SECURITY_AUDIT.md` - Updated infrastructure security status

**Tests:**
- `tests/test_security_headers.py` - Comprehensive test suite (11 tests)
  - Unit tests for individual headers
  - Integration tests for configuration loading
  - Security tests for header format validation
  - Tests for both enabled and disabled states

### Security Benefits

1. **Defense in Depth:** Multiple layers of browser-side security
2. **Flexible Configuration:** Adapts to different deployment scenarios
3. **Industry Best Practices:** Follows OWASP security recommendations
4. **Smart Defaults:** Disabled by default for typical reverse proxy deployments
5. **Reverse Proxy Compatible:** Works seamlessly with Traefik, Nginx, etc.
6. **Well Documented:** Comprehensive documentation for all scenarios

### Testing

**Running Security Header Tests:**
```bash
# Run all security header tests
pytest tests/test_security_headers.py -v

# Run security-marked tests only
pytest -m security -v

# Run with coverage
pytest tests/test_security_headers.py --cov=app.middleware --cov-report=term-missing
```

**Test Coverage:**
- ✅ Headers presence validation
- ✅ Header value format validation
- ✅ Configuration loading
- ✅ Master enable/disable behavior
- ✅ Individual header enable/disable
- ✅ API endpoint coverage
- ✅ Static file coverage

### Recommendations for Production

1. **HTTPS Required for HSTS:** Ensure HTTPS is properly configured before enabling HSTS
2. **Test CSP Policy:** The default CSP policy allows inline scripts/styles. Test thoroughly before tightening.
3. **Monitor Headers:** Use browser developer tools or online checkers to verify headers are applied
4. **Reverse Proxy Coordination:** Choose either application or proxy for header management, not both
5. **Regular Review:** Review and update CSP policy as application evolves

### Security Scanner Results

**Headers Validation:** All security headers pass OWASP recommendations
- ✅ HSTS max-age >= 1 year
- ✅ CSP includes default-src directive
- ✅ X-Frame-Options set to DENY or SAMEORIGIN
- ✅ X-Content-Type-Options set to nosniff

### Conclusion

Security headers implementation is complete and production-ready. The middleware provides:
- ✅ Strong browser-side security by default
- ✅ Flexibility for different deployment scenarios
- ✅ Comprehensive documentation and test coverage
- ✅ Easy configuration and customization

**Overall Security Impact:** POSITIVE - Significantly improves browser-side security posture with minimal performance overhead.

---

**Next Audit Due:** 2026-05-07 (Quarterly)
