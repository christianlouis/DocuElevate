# Changelog

All notable changes to DocuElevate will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Important Note

**As of v0.6.0**: This CHANGELOG is automatically generated and maintained by [python-semantic-release](https://github.com/python-semantic-release/python-semantic-release). Do not edit manually.

**Prior to v0.6.0**: This CHANGELOG was manually maintained. The transition to automated releases includes:
- Standardized tag format with `v` prefix (e.g., `v0.6.0`)
- Automated version bumping based on conventional commits
- Auto-generated release notes from commit messages

---

## [Unreleased]

### Added
- Automated semantic versioning with python-semantic-release
- Conventional commit validation via commitlint
- Automated CHANGELOG generation
- Automated GitHub Release creation with notes
- Documentation archive for one-off documents

### Changed
- Docker image name from `christianlouis/document-processor` to `christianlouis/docuelevate`
- GHCR image references updated to `docuelevate`
- Comprehensive documentation updates for versioning and release process

### Documentation
- Added conventional commits guide to CONTRIBUTING.md
- Updated AGENTIC_CODING.md with versioning/release process
- Updated .github/copilot-instructions.md with commit format rules
- Archived historical one-off documentation to docs/archive/

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

**Note**: Tags v0.3.1, v0.3.2, v0.3.3, and v0.5.0 do not exist as GitHub Releases. The features described in those versions were included in the codebase but not formally released. The latest actual release is 0.4.3. Going forward (v0.6.0+), all releases will have corresponding GitHub Releases and tags created automatically by semantic-release.

[Unreleased]: https://github.com/christianlouis/DocuElevate/compare/0.4.3...HEAD
[0.3.0]: https://github.com/christianlouis/DocuElevate/compare/0.2...0.3
[0.2.0]: https://github.com/christianlouis/DocuElevate/compare/0.1...0.2
[0.1.0]: https://github.com/christianlouis/DocuElevate/releases/tag/0.1