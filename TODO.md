# DocuElevate TODO List

**Last Updated:** 2026-02-06  
**Current Version:** v0.3.2

This document tracks actionable tasks for the current development cycle. For long-term planning, see [ROADMAP.md](ROADMAP.md) and [MILESTONES.md](MILESTONES.md).

---

## 🔴 Critical Priority (This Week)

### Security
- [x] Fix authlib vulnerability (upgrade to 1.6.5+)
- [x] Fix starlette DoS vulnerability (upgrade to 0.49.1+)
- [x] Improve SESSION_SECRET validation
- [ ] Run security audit with Bandit
- [ ] Review all direct file path operations for path traversal vulnerabilities
- [ ] Add rate limiting middleware to API endpoints
- [ ] Implement CSRF token for state-changing operations

### Testing
- [x] Set up pytest infrastructure
- [x] Create test fixtures and conftest.py
- [x] Add basic API integration tests
- [x] Add configuration validation tests
- [ ] Fix API integration tests (auth configuration issues)
- [ ] Add tests for file upload functionality
- [ ] Add tests for OCR processing (mocked)
- [ ] Add tests for metadata extraction (mocked)
- [ ] Add tests for storage provider integrations (mocked)
- [ ] Achieve 60% code coverage

---

## 🟠 High Priority (This Sprint - 2 Weeks)

### Code Quality
- [ ] Fix all critical Flake8 violations
- [ ] Run Black formatter on entire codebase
- [ ] Add type hints to core modules (config.py, database.py, models.py)
- [ ] Refactor large functions in tasks/ directory
- [ ] Add docstrings to all public functions and classes
- [ ] Remove unused imports and dead code

### CI/CD
- [x] Enable tests in GitHub Actions
- [x] Add coverage reporting
- [x] Add CodeQL scanning
- [ ] Add dependency scanning (Dependabot or similar)
- [ ] Make linting checks blocking (once critical issues fixed)
- [ ] Add build status badges to README.md

### Documentation
- [x] Create ROADMAP.md
- [x] Create MILESTONES.md
- [x] Create TODO.md
- [x] Create SECURITY_AUDIT.md
- [ ] Create AGENTIC_CODING.md
- [ ] Update CONTRIBUTING.md with testing guidelines
- [ ] Add architecture diagram to docs/
- [ ] Document all environment variables in docs/ConfigurationGuide.md
- [ ] Add troubleshooting section for common test failures

---

## 🟡 Medium Priority (Next Month)

### Features
- [ ] Implement retry logic for failed Celery tasks
- [ ] Add pagination to file list endpoint
- [ ] Add bulk delete functionality
- [ ] Implement file download endpoint
- [ ] Add document preview functionality
- [ ] Add search/filter functionality to UI
- [ ] Implement notification system for task completion
- [ ] Add support for configuring custom metadata fields

### Refactoring
- [ ] Consolidate storage provider code (reduce duplication)
- [ ] Create base class for storage providers
- [ ] Standardize error responses across all API endpoints
- [ ] Move hardcoded strings to constants
- [ ] Extract common validation logic into utilities
- [ ] Optimize database queries (add indexes)
- [ ] Reduce Docker image size

### Testing
- [ ] Add end-to-end tests for complete workflows
- [ ] Add performance tests for large file processing
- [ ] Add tests for edge cases (empty files, corrupted PDFs, etc.)
- [ ] Add stress tests for concurrent uploads
- [ ] Set up test data fixtures
- [ ] Add mock servers for external APIs

---

## 🟢 Low Priority (Backlog)

### Features
- [ ] Add file versioning support
- [ ] Implement document tagging system
- [ ] Add custom metadata templates
- [ ] Support for additional storage providers (Box, Mega, etc.)
- [ ] Add support for zip file uploads
- [ ] Implement folder organization
- [ ] Add audit log viewer in UI
- [ ] Support for scheduled document processing

### UI/UX
- [ ] Improve mobile responsiveness
- [ ] Add dark mode
- [ ] Add loading spinners for async operations
- [ ] Improve error messages for users
- [x] Add drag-and-drop file upload (completed 2026-02-08)
- [ ] Add file type icons
- [ ] Implement toast notifications
- [ ] Add keyboard shortcuts

### Developer Experience
- [ ] Create development Docker Compose setup
- [ ] Add hot-reload for development
- [ ] Create seed data script for testing
- [ ] Add debug toolbar for FastAPI
- [ ] Create CLI tool for common operations
- [ ] Add profiling tools
- [ ] Create contributor onboarding guide

---

## 🐛 Known Bugs

### High Priority
- [ ] Investigate session timeout issues with Authentik
- [ ] Fix intermittent Redis connection failures
- [ ] Handle large file uploads (>100MB) gracefully
- [ ] Fix timezone handling in task scheduling

### Medium Priority
- [ ] PDF rotation not persisting in some cases
- [ ] Metadata extraction fails for non-English documents
- [ ] UI refresh needed after file upload
- [ ] Error messages not showing in UI sometimes

### Low Priority
- [ ] Static files caching issues in production
- [ ] Minor CSS alignment issues on some browsers
- [ ] Log files growing too large over time

---

## 📚 Documentation Tasks

### User Documentation
- [ ] Create video tutorial for basic usage
- [ ] Add screenshots to all documentation pages
- [ ] Create FAQ document
- [ ] Write integration guides for each storage provider
- [ ] Create quickstart guide (5 minutes to first document)
- [ ] Document all API endpoints with examples
- [ ] Add Postman collection

### Developer Documentation
- [ ] Document project architecture
- [ ] Create database schema diagram
- [ ] Document Celery task flow
- [ ] Add code comments for complex logic
- [ ] Create API versioning strategy document
- [ ] Document testing strategy
- [ ] Add examples for extending the system

---

## 🔧 Technical Debt

### Refactoring Needed
- [ ] Replace PyPDF2 with pypdf (modern maintained fork)
- [ ] Migrate from string-based task names to explicit imports in Celery
- [ ] Standardize logging format across all modules
- [ ] Remove duplicated configuration loading code
- [ ] Consolidate error handling patterns
- [ ] Extract magic numbers into constants
- [ ] Improve variable naming in legacy code sections

### Performance Optimization
- [ ] Profile slow API endpoints
- [ ] Optimize database queries (N+1 problem in file list)
- [ ] Implement caching for frequently accessed data
- [ ] Lazy-load heavy dependencies
- [ ] Optimize Docker image layers
- [ ] Reduce memory usage in OCR processing
- [ ] Add database connection pooling

---

## 📦 Dependencies to Update

### Security Updates
- [x] authlib → 1.6.5+
- [x] starlette → 0.49.1+
- [ ] Review all dependencies for known vulnerabilities
- [ ] Update pinned versions in requirements.txt

### Regular Updates
- [ ] fastapi → latest stable
- [ ] celery → latest stable
- [ ] sqlalchemy → latest stable
- [ ] pydantic → latest stable (check for breaking changes)
- [ ] Check all dependencies for major version updates

---

## ✅ Completed (Recent)

### 2026-02-08
- [x] Added drag-and-drop file upload to Files view
- [x] Extracted reusable upload.js module for code reuse
- [x] Enhanced UX with visual drop overlay and upload progress modal

### 2026-02-06
- [x] Created comprehensive test infrastructure
- [x] Fixed critical security vulnerabilities
- [x] Added security scanning workflows
- [x] Created ROADMAP.md and MILESTONES.md
- [x] Enhanced .gitignore for security
- [x] Improved SESSION_SECRET handling
- [x] Created SECURITY_AUDIT.md
- [x] Set up pytest with coverage
- [x] Added API and configuration tests
- [x] Updated CI/CD workflows
- [x] Added pre-commit hooks configuration
- [x] Created TODO.md (this file)

---

## 📋 How to Use This TODO

### For Contributors
1. Pick a task from the appropriate priority section
2. Check if there's a related GitHub issue; if not, create one
3. Assign yourself to the issue
4. Move task to "In Progress" (add your name)
5. Submit PR when complete
6. Move task to "Completed" section with date

### For Maintainers
- Review and update priorities weekly
- Add new tasks as they're identified
- Archive completed tasks monthly
- Link tasks to GitHub issues/PRs
- Update status in standups/meetings

### Task Status Notation
- `[ ]` - Not started
- `[~]` - In progress (add contributor name: `[~@username]`)
- `[x]` - Completed
- `[!]` - Blocked (add reason in note)

---

## 🔗 Related Documents

- [ROADMAP.md](ROADMAP.md) - Long-term vision and features
- [MILESTONES.md](MILESTONES.md) - Release planning and versions
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
- [SECURITY.md](SECURITY.md) - Security policy
- [SECURITY_AUDIT.md](SECURITY_AUDIT.md) - Security audit results
- [GitHub Issues](https://github.com/christianlouis/DocuElevate/issues) - Bug reports and feature requests
- [GitHub Projects](https://github.com/christianlouis/DocuElevate/projects) - Sprint boards

---

*This TODO list is reviewed and updated regularly. Last review: 2026-02-06*
