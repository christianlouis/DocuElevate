# Changelog

All notable changes to DocuElevate will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **This CHANGELOG is automatically generated and maintained by [python-semantic-release](https://github.com/python-semantic-release/python-semantic-release). Do not edit it manually.**
> New entries are prepended automatically on every merge to `main` that triggers a version bump.

<!-- version list -->

## v0.42.2 (2026-02-23)

### Bug Fixes

- **api**: Pass base_url to OpenAI client in test endpoint to prevent UnsupportedProtocol error
  ([`d885b63`](https://github.com/christianlouis/DocuElevate/commit/d885b63d38ff151c5dc3e70ad51fbf1d56a5f7df))


## v0.42.1 (2026-02-23)

### Bug Fixes

- Fix automatic changelog creation with PSR v10
  ([`7f3e831`](https://github.com/christianlouis/DocuElevate/commit/7f3e8312de33b44eba3c021ac4cf58e504528b85))


## [0.40.0] - 2026-02-23

> **Retroactive summary.** Releases v0.6.0 through v0.40.0 were cut automatically by
> `python-semantic-release` from conventional commits, but the CHANGELOG was not updated
> at the time due to a configuration bug (`autoescape = true`). This section documents all
> known changes made after v0.5.0.

### Added

#### Security Middleware Stack
- **CSRF Protection** (`app/middleware/csrf.py`): Per-session cryptographic tokens validated on all state-changing requests (POST/PUT/DELETE/PATCH). Token delivered via `X-CSRF-Token` header or `csrf_token` form field. No-op when `AUTH_ENABLED=False`.
- **Rate Limiting** (`app/middleware/rate_limit.py`): SlowAPI + Redis-backed rate limiting. Configurable defaults: 100 req/min (API), 600 req/min (uploads), 10 req/min (auth). Falls back to in-memory for development.
- **Rate Limit Decorators** (`app/middleware/rate_limit_decorators.py`): Convenience `@limit("N/period")` decorators for per-endpoint overrides.
- **Security Headers** (`app/middleware/security_headers.py`): Configurable HSTS, CSP, `X-Frame-Options`, and `X-Content-Type-Options` headers. Each header individually togglable for reverse-proxy deployments.
- **Audit Logging** (`app/middleware/audit_log.py`): Per-request structured log entries with sensitive-value masking. Elevated `[SECURITY]` log level for 401/403/login/5xx events.
- **Request Size Limiting** (`app/middleware/request_size_limit.py`): Separate limits for JSON/form bodies (`MAX_REQUEST_BODY_SIZE`, default 1 MB) and file upload multipart bodies (`MAX_UPLOAD_SIZE`, default 1 GB). Returns HTTP 413 immediately without reading the full body.
- **CORS** (`main.py`): Configurable CORS policy via `CORS_ENABLED`, `CORS_ALLOWED_ORIGINS`, `CORS_ALLOW_CREDENTIALS`, `CORS_ALLOWED_METHODS`, and `CORS_ALLOWED_HEADERS`.

#### New Storage Providers
- **Amazon S3** (`app/tasks/upload_to_s3.py`): Upload to S3-compatible buckets. Configured via `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and `S3_BUCKET_NAME`.
- **SFTP** (`app/tasks/upload_to_sftp.py`): Secure file transfer with password or private-key authentication. Supports `SFTP_DISABLE_HOST_KEY_VERIFICATION` flag.
- **FTP/FTPS** (`app/tasks/upload_to_ftp.py`): FTP with automatic FTPS upgrade attempt; plaintext fallback configurable via `FTP_ALLOW_PLAINTEXT`.
- **WebDAV** (`app/tasks/upload_to_webdav.py`): HTTP Basic auth, configurable SSL verification (`WEBDAV_VERIFY_SSL`).
- **Email/SMTP** (`app/tasks/upload_to_email.py`): Send processed documents as email attachments. Supports TLS, configurable sender, and default recipient.
- **rclone** (`app/tasks/upload_with_rclone.py`): Delegate uploads to a locally configured `rclone` binary, enabling support for any of rclone's 40+ cloud providers.

#### File Processing Improvements
- **PDF Page Rotation** (`app/tasks/rotate_pdf_pages.py`): Detects and corrects skewed pages using Azure Document Intelligence angle metadata.
- **Metadata Embedding** (`app/tasks/embed_metadata_into_pdf.py`): Writes GPT-extracted metadata as PDF document properties using pypdf.
- **PDF Splitting** (`app/utils/file_splitting.py`): Splits oversized PDFs at page boundaries into chunks ≤ `MAX_SINGLE_FILE_SIZE` bytes. Each chunk is a valid, readable PDF.
- **Document Deduplication**: SHA-256 hash-based duplicate detection. Controlled by `ENABLE_DEDUPLICATION` and `SHOW_DEDUPLICATION_STEP` settings.
- **Forced Cloud OCR**: `force_cloud_ocr` flag on `process_document` task to bypass local text extraction and always use Azure Document Intelligence. Useful for reprocessing.
- **pypdf migration**: Replaced PyPDF2 with pypdf (actively maintained fork); fixes CVE-2023-36464.

#### Processing Status Tracking (Dual-Table Architecture)
- **`FileProcessingStep` model**: New DB table; single row per (file, step) pair tracking current state (`pending`, `in_progress`, `success`, `failure`, `skipped`). Replaces log-scanning for status queries.
- **Step Manager** (`app/utils/step_manager.py`): Initialises, updates, and queries processing steps. Supports `ENABLE_DEDUPLICATION` conditional step inclusion.
- **Step Timeout Detection** (`app/utils/step_timeout.py`): Marks steps stuck in `in_progress` as `failure` after configurable `STEP_TIMEOUT` seconds (default 600).
- **Stalled Step Monitor** (`app/tasks/monitor_stalled_steps.py`): Periodic Celery task (runs every minute) that calls the timeout detection logic.
- **Log Migration Utility** (`app/utils/migrate_logs_to_steps.py`): Back-fills `FileProcessingStep` from existing `ProcessingLog` entries for files processed before the new table existed.

#### New API Endpoints
- **`POST /api/upload-from-url`** (`app/api/url_upload.py`): Upload a document from a remote URL. Includes SSRF protection (blocks private IPs and loopback addresses).
- **`GET /api/logs`** (`app/api/logs.py`): Paginated, filterable list of `ProcessingLog` entries; filterable by `file_id` and `task_name`.
- **`GET /api/diagnostic/settings`** (`app/api/diagnostic.py`): Admin-only endpoint that dumps non-sensitive configuration to logs and returns summary info.
- **`GET /api/whoami`** (`app/api/user.py`): Returns session user info including a Gravatar URL derived from the authenticated user's email.

#### Notification System
- **Apprise integration** (`app/utils/notification.py`): Multi-channel notifications via the Apprise library (70+ services: Slack, email, Telegram, PushOver, etc.). Configured via `NOTIFICATION_URLS`.
- **Configurable triggers**: `NOTIFY_ON_TASK_FAILURE`, `NOTIFY_ON_CREDENTIAL_FAILURE`, `NOTIFY_ON_STARTUP`, `NOTIFY_ON_SHUTDOWN`, `NOTIFY_ON_FILE_PROCESSED`.
- **Uptime Kuma integration** (`app/tasks/uptime_kuma_tasks.py`): Periodic heartbeat ping to a configured Uptime Kuma push URL (`UPTIME_KUMA_URL`, `UPTIME_KUMA_PING_INTERVAL`).

#### Admin & Operations
- **Admin File Manager** (`app/views/filemanager.py`): Three-pane admin view at `/filemanager`:
  - *Filesystem view*: Browse `workdir` tree with DB cross-reference per file.
  - *Database view*: List all `FileRecord` rows with on-disk existence flag.
  - *Reconcile view*: Delta view showing orphan disk files and ghost DB records.
- **Credential Checker Task** (`app/tasks/check_credentials.py`): Periodic Celery task that validates all configured provider credentials (OpenAI, Azure, Dropbox, Google Drive, OneDrive) and sends a notification on failure.
- **Settings Audit Log** (`ApplicationSettings` + `SettingsAuditLog` models): Every settings change is recorded with timestamp, user, and before/after values.
- **ProcessAll Throttling**: Configurable `PROCESSALL_THROTTLE_THRESHOLD` and `PROCESSALL_THROTTLE_DELAY` to prevent flooding the task queue during bulk reprocessing.
- **Worker Settings Sync** (`app/utils/settings_sync.py`): Publishes a version token to Redis whenever settings change; Celery workers reload settings from DB before each task, ensuring config changes propagate without a restart.

#### Browser Extension (v1.1.0)
- Send files and web pages from the browser directly to DocuElevate with one click.
- Context menu integration on links, images, and pages.
- Manifest v3 compatible; works with Chrome, Firefox, Edge, and Chromium-based browsers.
- In-browser notifications for upload status.

#### OpenAI Customization
- `OPENAI_BASE_URL` setting (default `https://api.openai.com/v1`): Enables use of OpenAI-compatible endpoints (Azure OpenAI, local models, etc.).
- `OPENAI_MODEL` setting (default `gpt-4o-mini`): Model selection without code changes.

#### Configuration & Developer Experience
- **Config Loader** (`app/utils/config_loader.py`): Hot-reload of settings from DB without service restart.
- **Config Validator** (`app/utils/config_validator/`): Modular validation with provider status, masked display, and per-provider readiness checks.
- **Input Validation** (`app/utils/input_validation.py`): Centralised validators for sort fields, sort order, search query length, task ID format (UUID v4), and settings key format.
- **Filename Utilities** (`app/utils/filename_utils.py`): `sanitize_filename`, `get_unique_filename`, and `extract_remote_path` helpers shared across upload tasks.
- **OAuth Helper** (`app/utils/oauth_helper.py`): Shared token-exchange logic reused by Dropbox, Google Drive, and OneDrive OAuth flows.
- **Retry Configuration** (`app/tasks/retry_config.py`): `BaseTaskWithRetry` base class with auto-retry (3 attempts, 10 s initial delay, exponential backoff) shared by all upload tasks.
- **HTTP Request Timeout**: Configurable `HTTP_REQUEST_TIMEOUT` (default 120 s) to handle large file operations gracefully.
- **File Deletion Toggle**: `ALLOW_FILE_DELETE` setting to prevent accidental deletions in production.

### Changed
- Docker image renamed from `christianlouis/document-processor` to `christianlouis/docuelevate`
- `app/routes/` deprecated; all endpoints migrated to `app/api/` and `app/views/`
- `FileRecord` status now derived from `FileProcessingStep` rows instead of scanning `ProcessingLog`
- Settings changes now propagated to Celery workers via Redis version key (no restart required)
- Dependency scanner switched from `safety` to `pip-audit` in CI pipeline
- CI pipeline streamlined: removed redundant DeepSource integration (40–50% faster CI runs)
- `app/utils/logging.py` introduced as canonical import point for `log_task_progress`

### Fixed
- **Critical: Path Traversal via GPT Metadata Filename** — GPT-extracted `filename` metadata was used directly in file path construction. Fixed by running all GPT-suggested filenames through `sanitize_filename` before use.
- **Medium: Path Traversal in File API** — `file_path` query parameters sanitised to block `../` sequences.
- **Medium: Unvalidated Sort Parameters** — sort field and order inputs in file list endpoint now validated against an allowlist.
- OAuth admin group detection now correctly handles groups list from Authentik userinfo response.
- Session secret validation raises a clear error at startup instead of silently using an insecure default.
- Redirect loop for logged-in non-admin users on `/settings` route resolved.

### Security
- CSRF protection added to all state-changing endpoints
- Rate limiting prevents brute-force and DoS attacks on auth and upload endpoints
- Security response headers (HSTS, CSP, X-Frame-Options, X-Content-Type-Options) enabled by default
- Audit log records all HTTP requests with sensitive-value masking
- Request body size limits prevent memory-exhaustion attacks
- Path traversal vulnerabilities in file path handling remediated (see security audit `docs/security/PATH_TRAVERSAL_AUDIT_2026-02-10.md`)
- Host key verification enforced for SFTP by default (`SFTP_DISABLE_HOST_KEY_VERIFICATION=False`)
- FTPS attempted by default for FTP connections; plaintext requires explicit opt-in
- SSRF protection on URL-upload endpoint (blocks private IP ranges and loopback)
- Input validation on all user-controlled sort/search/key parameters

### Documentation
- Added `docs/RateLimitingStrategy.md` — rate limiting configuration guide
- Added `docs/FileProcessingStatusArchitecture.md` — dual-table architecture explanation
- Added `docs/NotificationsSetup.md` — Apprise notification setup guide
- Added `docs/StorageArchitecture.md` — document storage directory layout
- Added `docs/AuthenticationSetup.md` — OAuth2 / Basic Auth configuration
- Added `docs/AmazonS3Setup.md`, `docs/DropboxSetup.md`, `docs/GoogleDriveSetup.md`, `docs/OneDriveSetup.md` — per-provider setup guides
- Added `docs/CredentialRotationGuide.md` — how to rotate API keys and credentials
- Added `docs/ConfigurationTroubleshooting.md` — common configuration problems
- Added `docs/security/PATH_TRAVERSAL_AUDIT_2026-02-10.md` — security audit findings
- Added `docs/BrowserExtension.md` — browser extension installation and usage
- Added `docs/CIToolsGuide.md` and `docs/CIWorkflow.md` — CI pipeline documentation
- Added `docs/BuildMetadata.md` — build metadata file documentation
- CI de-duplication summary archived in `docs/CI_DEDUPLICATION_SUMMARY.md`
- OAuth testing summary archived in `OAUTH_IMPLEMENTATION_SUMMARY.md`
- WebDAV testing summary archived in `WEBDAV_TESTING_SUMMARY.md`

---

## [0.5.0] - 2026-02-08

### Added
- **Settings Management System**: Database-backed configuration management with web UI
  - Admin-only settings page at `/settings` with 102 settings across 10 categories
  - REST API endpoints: `GET/POST /api/settings/{key}`, `POST /api/settings/bulk-update`, `DELETE /api/settings/{key}`
  - Settings organized by category: Core, Authentication, AI Services, Storage Providers, Email, IMAP, Monitoring, Processing, Notifications, Feature Flags
  - Form pre-filled with current values, all fields optional for flexible editing
  - Bulk update support for changing multiple settings at once
- **Encryption for Sensitive Settings**: Fernet symmetric encryption for database storage
  - Automatic encryption/decryption for passwords, API keys, tokens, and secrets
  - Encryption key derived from `SESSION_SECRET` via SHA256
  - Values prefixed with `enc:` in database to identify encrypted data
  - Graceful fallback if cryptography library unavailable (logs warning)
  - Lock icon (🔒) in UI indicates encrypted fields
- **Setup Wizard**: First-time configuration wizard for fresh installations
  - 3-step wizard: Infrastructure → Security → AI Services
  - Auto-detects missing critical settings and redirects from homepage
  - Beautiful UI with progress indicators and step navigation
  - Auto-generate option for session secrets
  - Skippable for advanced users
  - Settings saved encrypted to database
- **Settings Precedence System**: Clear resolution order with visual indicators
  - Precedence: Database > Environment Variables > Defaults
  - Color-coded badges in UI: 🟢 DB (green), 🔵 ENV (blue), ⚪ DEFAULT (gray)
  - Source detection for each setting shows where value originates
  - Info section explaining precedence order
- **OAuth Admin Support**: Enhanced authentication for settings access
  - Admin flag set from OAuth group membership (`admin` or `administrators`)
  - Proper decorator pattern for admin access control
  - Session-based authorization with redirect on unauthorized access

### Changed
- Updated `requirements.txt` to include `cryptography>=41.0.0` for encryption
- Enhanced settings service to auto-encrypt/decrypt sensitive values transparently
- Improved `/settings` route with proper admin decorator (fixes redirect loop)
- Updated settings template with enhanced UI: source badges, encryption indicators, show/hide toggles
- Modified `app/views/general.py` to redirect to wizard when setup required

### Fixed
- Fixed `/settings` endpoint returning 301 redirect to `/` (converted to proper decorator)
- Resolved redirect loop for logged-in non-admin users
- Fixed OAuth users not receiving admin privileges from group membership

### Documentation
- Added [docs/SettingsManagement.md](docs/SettingsManagement.md) - Comprehensive user guide
- Added [SETTINGS_IMPLEMENTATION.md](SETTINGS_IMPLEMENTATION.md) - Technical documentation
- Added [FRAMEWORK_ANALYSIS.md](FRAMEWORK_ANALYSIS.md) - Research on existing frameworks
- Added [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md) - Feature tracking
- Updated TODO.md with completed features
- Updated MILESTONES.md with release details

### Technical Details
- New files:
  - `app/utils/encryption.py` - Fernet encryption utilities
  - `app/utils/setup_wizard.py` - Wizard detection and logic
  - `app/views/wizard.py` - Wizard routes (GET/POST /setup)
  - `frontend/templates/setup_wizard.html` - Wizard UI
  - `frontend/templates/settings.html` - Enhanced settings page
- Modified files:
  - `app/utils/settings_service.py` - Encryption integration, 102 setting metadata
  - `app/views/settings.py` - Fixed decorator, source detection
  - `app/auth.py` - OAuth admin support
  - `app/api/settings.py` - Enhanced admin checks
  - `tests/test_settings.py` - Comprehensive test coverage

### Security
- Sensitive settings encrypted at rest in database using Fernet (AES-128-CBC + HMAC)
- Encryption key derived from `SESSION_SECRET` (minimum 32 characters required)
- Admin-only access enforced on all settings operations
- Visual masking of sensitive values in UI by default
- CodeQL security scan: 0 alerts

## [0.3.3] - 2026-02-08

### Added
- **Drag-and-drop file upload on Files page**: You can now drag and drop files anywhere on the Files view (`/files`) to upload them, making it more convenient to add documents without navigating to the dedicated Upload page
- Visual drop overlay that appears when dragging files over the Files page
- Upload progress modal in bottom-right corner showing real-time upload status
- Reusable `upload.js` module extracted from upload page for better code maintainability
- Tests for drag-and-drop functionality presence in Files view
- Enhanced visual feedback with animations and improved styling

### Changed
- Refactored upload functionality into a shared JavaScript module (`/static/js/upload.js`)
- Updated Upload page to use the new shared upload module
- Improved drop zone visual styling with better colors and animations

### Security
- Continued security improvements from v0.3.2 (authlib, starlette updates)

## [0.3.2] - 2026-02-06

### Added
- Comprehensive test infrastructure with pytest
- Security scanning workflows (CodeQL, Bandit)
- SECURITY_AUDIT.md documentation
- ROADMAP.md and MILESTONES.md planning documents
- API integration tests and configuration validation tests
- Pre-commit hooks configuration

### Changed
- Updated authlib to 1.6.5+ (security fix)
- Updated starlette to 0.49.1+ (DoS vulnerability fix)
- Improved SESSION_SECRET validation and handling
- Enhanced .gitignore for security
- Updated README with improved documentation structure

### Fixed
- Critical security vulnerabilities in dependencies
- Session security issues

## [0.3.1] - 2026-01-15

### Added
- Files view with sorting and filtering capabilities
- Bulk operations (delete, reprocess) for multiple files
- File detail view with processing history
- Processing flow visualization

### Changed
- Improved UI responsiveness
- Enhanced error handling and user feedback

### Fixed
- Various bug fixes in file processing pipeline

## [0.3.0] - 2025-12-20

### Added
- OAuth2 authentication support with Authentik
- Multi-provider storage support (Dropbox, Google Drive, OneDrive, S3, Nextcloud)
- Azure Document Intelligence integration for OCR
- OpenAI metadata extraction
- Gotenberg PDF conversion service integration
- IMAP integration for email attachment processing
- REST API with FastAPI
- Web UI for document management
- Celery task queue for asynchronous processing

### Changed
- Major architectural improvements
- Database schema optimizations

## [0.2.0] - 2025-11-01

### Added
- Basic document upload functionality
- Simple storage integration
- Basic metadata extraction

## [0.1.0] - 2025-10-01

### Added
- Initial release
- Core document processing framework
- Basic file handling

---

## Historical Release Links

**Note**: Tags v0.3.1, v0.3.2, v0.3.3, v0.5.0, and the retroactive v0.40.0 summary do not correspond
one-to-one with formal GitHub Releases from that period. Going forward all releases have corresponding
GitHub Releases and tags created automatically by `python-semantic-release`.

[Unreleased]: https://github.com/christianlouis/DocuElevate/compare/v0.40.0...HEAD
[0.40.0]: https://github.com/christianlouis/DocuElevate/compare/v0.5.0...v0.40.0
[0.5.0]: https://github.com/christianlouis/DocuElevate/compare/v0.3.3...v0.5.0
[0.3.3]: https://github.com/christianlouis/DocuElevate/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/christianlouis/DocuElevate/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/christianlouis/DocuElevate/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/christianlouis/DocuElevate/compare/0.2...0.3
[0.2.0]: https://github.com/christianlouis/DocuElevate/compare/0.1...0.2
[0.1.0]: https://github.com/christianlouis/DocuElevate/releases/tag/0.1
