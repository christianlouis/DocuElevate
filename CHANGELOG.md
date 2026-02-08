# Changelog

All notable changes to DocuElevate will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Fixed
- N/A

### Security
- Continued security improvements from v0.3.2 (authlib, starlette updates)

## [0.3.2] - 2026-02-06

### Added
- Comprehensive test infrastructure with pytest
- Security scanning with CodeQL and Bandit
- SECURITY_AUDIT.md documentation
- API integration tests
- Configuration validation tests
- Enhanced CI/CD workflows
- Pre-commit hooks configuration

### Changed
- Updated README with improved documentation structure
- Enhanced .gitignore for better security

### Fixed
- Critical security vulnerabilities in authlib (upgraded to 1.6.5+)
- Critical DoS vulnerability in starlette (upgraded to 0.49.1+)

### Security
- Improved SESSION_SECRET validation and handling
- Enhanced security practices documentation

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

[Unreleased]: https://github.com/christianlouis/DocuElevate/compare/v0.3.3...HEAD
[0.3.3]: https://github.com/christianlouis/DocuElevate/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/christianlouis/DocuElevate/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/christianlouis/DocuElevate/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/christianlouis/DocuElevate/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/christianlouis/DocuElevate/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/christianlouis/DocuElevate/releases/tag/v0.1.0
