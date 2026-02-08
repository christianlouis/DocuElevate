# Test Coverage TODO

This document tracks test coverage improvements for DocuElevate. The goal is to improve overall coverage from 45% to 60%+, then iterate in 10% steps.

## Current Status

**Initial Coverage**: 45.09%  
**Current Coverage**: 49.11%  
**Progress**: +4.02%  
**Target Coverage**: 60%+ (Phase 1), then 70%, 80%

## Completed Tests

### Phase 1: Low-Hanging Fruits (Target: 60%+)

#### Utility Modules (0% → High Coverage) ✅
- [x] `app/utils/encryption.py` (0% → 89.29%) ✅
  - Test encrypt_value with various inputs
  - Test decrypt_value with encrypted/plaintext values
  - Test is_encrypted function
  - Test is_encryption_available
  - Mock cryptography library for error cases
  
- [x] `app/celery_worker.py` (0% → 90.62%) ✅
  - Test task imports
  - Test module structure
  
- [x] `app/tasks/uptime_kuma_tasks.py` (0% → 100%) ✅
  - Test ping_uptime_kuma with valid URL
  - Test skipping when URL not configured
  - Test error handling for failed requests
  
- [x] `app/utils.py` (0% → Still 0%) ⚠️
  - Simple re-export module, coverage is from actual usage
  
- [x] `app/frontend.py` (0% → 100%) ✅
  - Simple re-export module, test imports work
  
- [x] `app/utils/config_validator.py` (0% → Still 0%) ⚠️
  - Re-export module, coverage is from actual usage

#### Low Coverage Modules (<30% → Improved)
- [x] `app/utils/filename_utils.py` (24.62% → 81.54%) ✅
  - Test sanitize_filename with special characters
  - Test get_unique_filename
  - Test extract_remote_path
  - Test filename validation functions
  
- [x] `app/utils/logging.py` (42.86% → 100%) ✅
  - Test log_task_progress function
  - Test various log message formats
  
- [ ] `app/utils/oauth_helper.py` (17.50% → Target 50%+)
  - Test OAuth URL generation
  - Test token refresh logic
  - Mock OAuth provider responses

### Files Improved
1. **app/utils/encryption.py**: 0% → 89.29% (+89.29%)
2. **app/celery_worker.py**: 0% → 90.62% (+90.62%)
3. **app/tasks/uptime_kuma_tasks.py**: 0% → 100% (+100%)
4. **app/frontend.py**: 0% → 100% (+100%)
5. **app/utils/filename_utils.py**: 24.62% → 81.54% (+56.92%)
6. **app/utils/logging.py**: 42.86% → 100% (+57.14%)
7. **app/tasks/check_credentials.py**: 0% → 23.13% (+23.13% from imports)
8. **app/tasks/imap_tasks.py**: 0% → 15.35% (+15.35% from imports)

## Phase 2: Medium Priority (Target: 70%+)

### API Routes with Low Coverage
- [ ] `app/api/azure.py` (23.08% → 60%+)
  - Test Azure connection
  - Test credential validation
  - Mock Azure API responses
  
- [ ] `app/api/dropbox.py` (16.94% → 50%+)
  - Test OAuth flow (mocked)
  - Test token validation
  - Test connection testing
  
- [ ] `app/api/google_drive.py` (12.94% → 50%+)
  - Test OAuth flow (mocked)
  - Test token validation
  - Test drive connection
  
- [ ] `app/api/onedrive.py` (13.83% → 50%+)
  - Test OAuth flow (mocked)
  - Test token validation
  - Test connection testing

### Task Modules with Low Coverage
- [ ] `app/tasks/convert_to_pdf.py` (13.41% → 50%+)
  - Test PDF conversion with various formats
  - Test Gotenberg integration (mocked)
  - Test error handling
  
- [ ] `app/tasks/embed_metadata_into_pdf.py` (19.05% → 50%+)
  - Test metadata embedding
  - Test PDF manipulation
  - Test error cases

## Phase 3: Complex Integration Tests (Target: 80%+)

### Upload Task Modules (Currently 13-36%)
These require complex external service mocking:
- [ ] `app/tasks/upload_to_dropbox.py` (13.45%)
- [ ] `app/tasks/upload_to_google_drive.py` (36.00%)
- [ ] `app/tasks/upload_to_onedrive.py` (26.32%)
- [ ] `app/tasks/upload_to_nextcloud.py` (15.19%)
- [ ] `app/tasks/upload_to_paperless.py` (18.60%)
- [ ] `app/tasks/upload_to_email.py` (36.08%)

### Complex Background Tasks (0-36%)
- [ ] `app/tasks/check_credentials.py` (0%)
  - Requires mocking multiple external services
  - Test credential validation for each provider
  - Test failure state management
  - Test notification system
  
- [ ] `app/tasks/imap_tasks.py` (0%)
  - Requires IMAP server mocking
  - Test email fetching
  - Test email parsing
  - Test lock management with Redis
  
- [ ] `app/tasks/upload_with_rclone.py` (0%)
  - Test rclone command execution
  - Test configuration management
  - Test error handling
  
- [ ] `app/tasks/extract_metadata_with_gpt.py` (28.79%)
  - Test GPT metadata extraction
  - Mock OpenAI API responses
  - Test various document types

### View Routes (25-61%)
- [ ] `app/views/status.py` (25.00%)
- [ ] `app/views/wizard.py` (38.98%)
- [ ] `app/views/settings.py` (42.86%)
- [ ] `app/views/google_drive.py` (42.42%)

## Testing Strategy

### For Low-Hanging Fruits (Phase 1)
1. Focus on pure functions with minimal dependencies
2. Mock external services (OpenAI, Azure, cloud storage)
3. Test error paths and edge cases
4. Use pytest fixtures for common setup

### For Integration Tests (Phases 2-3)
1. Create comprehensive mocks for external services
2. Use pytest-mock for patching
3. Test async functions with pytest-asyncio
4. Use TestClient for API endpoint tests
5. Mock Redis, database, and Celery for task tests

## Coverage Goals by Phase

| Phase | Target Coverage | Status |
|-------|----------------|--------|
| Phase 1: Low-Hanging Fruits | 60% | In Progress |
| Phase 2: Medium Priority | 70% | Not Started |
| Phase 3: Complex Integration | 80% | Not Started |

## Notes

- Files with 100% coverage: Keep them at 100%
- Files with 90%+ coverage: Low priority for improvement
- Focus on business logic, not simple re-exports
- Mock external dependencies to avoid flaky tests
- All tests must pass CI/CD pipeline
- Maintain test execution time under 2 minutes for fast feedback

## Files Excluded from Coverage

These files are infrastructure/configuration and don't require high coverage:
- `migrations/*` - Database migrations (excluded in pytest.ini)
- `app/__init__.py` - Empty init files
- `app/*/__init__.py` - Package init files

## Running Tests

```bash
# Run all tests with coverage
pytest --cov=app --cov-report=term-missing

# Run tests for specific module
pytest tests/test_encryption.py -v

# Run tests with coverage report
pytest --cov=app --cov-report=html
open htmlcov/index.html

# Run only unit tests (fast)
pytest -m unit

# Run integration tests
pytest -m integration
```

## Contributing

When adding new code:
1. Write tests for new functionality
2. Aim for 80%+ coverage on new files
3. Update this TODO when completing test coverage work
4. Run coverage report before submitting PR
