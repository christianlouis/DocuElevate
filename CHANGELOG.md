# Changelog

All notable changes to DocuElevate will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.3] - 2026-02-08

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
- Updated MILESTONES.md with v0.3.3 release details

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

## [0.3.2] - 2026-02-06

### Added
- Comprehensive test infrastructure with pytest
- Security scanning workflows (CodeQL, Bandit)
- SECURITY_AUDIT.md documentation
- ROADMAP.md and MILESTONES.md planning documents
- Pre-commit hooks configuration

### Changed
- Updated authlib to 1.6.5+ (security fix)
- Updated starlette to 0.49.1+ (DoS vulnerability fix)
- Improved SESSION_SECRET validation and handling
- Enhanced .gitignore for security

### Fixed
- Critical security vulnerabilities in dependencies
- Session security issues

## [0.3.1] - 2026-01-15

### Added
- OAuth2 authentication with Authentik support
- Basic admin authentication
- Session management

### Changed
- Improved authentication flow
- Enhanced error handling

## [0.3.0] - 2026-01-01

### Added
- Multi-provider storage support (Dropbox, Google Drive, OneDrive, S3, FTP, SFTP, WebDAV)
- Document processing pipeline with OCR
- Metadata extraction with OpenAI
- Basic web UI with file listing
- REST API for document operations
- Celery task queue for async processing

### Changed
- Migrated from Flask to FastAPI
- Updated database schema
- Improved error handling

## [0.2.0] - 2025-12-01

### Added
- Initial document processing capabilities
- Basic storage integration
- Simple web interface

## [0.1.0] - 2025-11-01

### Added
- Initial project setup
- Basic FastAPI application structure
- Database models
- Docker configuration

---

## Version History Summary

- **v0.3.3** (2026-02-08): Settings management, encryption, setup wizard
- **v0.3.2** (2026-02-06): Security hardening, testing infrastructure
- **v0.3.1** (2026-01-15): OAuth2 authentication
- **v0.3.0** (2026-01-01): Multi-provider storage, OCR, metadata extraction
- **v0.2.0** (2025-12-01): Document processing
- **v0.1.0** (2025-11-01): Initial release

---

## Links

- [GitHub Repository](https://github.com/christianlouis/DocuElevate)
- [Documentation](https://docuelevate.readthedocs.io)
- [Issue Tracker](https://github.com/christianlouis/DocuElevate/issues)
- [Release Notes](https://github.com/christianlouis/DocuElevate/releases)
