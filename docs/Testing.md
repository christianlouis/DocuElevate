# Testing Guide

This guide explains how to write, run, and configure tests for DocuElevate.

## Table of Contents

- [Overview](#overview)
- [Test Environment Setup](#test-environment-setup)
  - [Local Development](#local-development-envtest)
  - [GitHub Actions (CI/CD)](#github-actions-cicd-with-secrets)
- [Running Tests](#running-tests)
- [Writing Tests](#writing-tests)
- [Test Types and Markers](#test-types-and-markers)
- [Mocking External Services](#mocking-external-services)
- [Integration Testing with Real APIs](#integration-testing-with-real-apis)
- [Best Practices](#best-practices)

## Overview

DocuElevate uses **pytest** as its testing framework with the following features:

- **Test markers** to categorize tests (unit, integration, slow, etc.)
- **Code coverage** tracking with minimum thresholds
- **Fixtures** for common test setup (database, test files, etc.)
- **Mocking** for external services (OpenAI, Azure, storage providers)
- **Optional integration testing** with real API keys

> **🔑 Quick Start for GitHub Actions:** If you want to run integration tests in CI/CD, see the **[GitHub Secrets Setup Guide](./GitHubSecretsSetup.md)** for step-by-step instructions on securely storing API keys.

## Test Environment Setup

There are **two different approaches** for configuring test environments:

1. **Local Development** - Use `.env.test` file (gitignored, stays on your machine)
2. **GitHub Actions (CI/CD)** - Use GitHub Secrets (encrypted, stored in repository settings)

### Local Development (.env.test)

#### Basic Setup (No API Keys Required)

For running unit tests with mocked external services:

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Run tests (uses default mock values)
pytest
```

Tests will run successfully using mock values defined in `tests/conftest.py`. No additional configuration is needed.

#### Advanced Setup (Real API Keys for Integration Tests)

For running integration tests against real external services **on your local machine**:

#### Step 1: Create Test Environment File

```bash
# Copy the example file
cp .env.test.example .env.test
```

#### Step 2: Add Your Test Credentials

Edit `.env.test` and add your **test-only** API keys and credentials:

```bash
# Example .env.test file
OPENAI_API_KEY=sk-test-your-real-test-key-here
AZURE_AI_KEY=your-real-azure-test-key-here
AWS_ACCESS_KEY_ID=your-test-access-key
AWS_SECRET_ACCESS_KEY=your-test-secret-key
S3_BUCKET_NAME=docuelevate-test-bucket
```

> **⚠️ IMPORTANT SECURITY NOTES:**
> 
> - **Use separate test accounts/keys**, never production credentials
> - `.env.test` is gitignored and will **never be committed**
> - Create dedicated test resources (test S3 buckets, test Dropbox folders, etc.)
> - Use API keys with minimal permissions (read/write to test resources only)
> - Regularly rotate test credentials
> - Monitor test account usage for unexpected activity

#### Step 3: Verify Configuration

```bash
# Check that .env.test is gitignored
git status .env.test
# Should show: "On branch main, nothing to commit"

# Run tests with your configuration
pytest -m requires_external
```

### GitHub Actions (CI/CD) with Secrets

For running integration tests in **GitHub Actions** (automated CI/CD), you need to store secrets in your repository settings. **Do NOT use `.env.test` for CI/CD** - it's only for local development.

#### Step 1: Add Secrets to GitHub Repository

1. Go to your repository on GitHub
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **"New repository secret"**
4. Add each secret individually:

| Secret Name | Example Value | Purpose |
|-------------|---------------|---------|
| `TEST_OPENAI_API_KEY` | `sk-test-abc123...` | OpenAI API for integration tests |
| `TEST_AZURE_AI_KEY` | `abc123def456...` | Azure Document Intelligence |
| `TEST_AWS_ACCESS_KEY_ID` | `AKIAIOSFODNN7EXAMPLE` | AWS S3 integration tests |
| `TEST_AWS_SECRET_ACCESS_KEY` | `wJalrXUtnFEMI/...` | AWS S3 integration tests |
| `TEST_S3_BUCKET_NAME` | `docuelevate-test` | S3 test bucket name |
| `TEST_DROPBOX_REFRESH_TOKEN` | `sl.abcdef123...` | Dropbox integration tests |
| `TEST_GOOGLE_DRIVE_CREDENTIALS` | `{"type":"service_account"...}` | Google Drive integration |

> **💡 Tip:** Prefix all test secrets with `TEST_` to clearly distinguish them from production secrets.

#### Step 2: Update GitHub Actions Workflow

Edit `.github/workflows/tests.yaml` to use the secrets:

```yaml
- name: Run Tests
  env:
    # Core settings (from secrets)
    OPENAI_API_KEY: ${{ secrets.TEST_OPENAI_API_KEY }}
    AZURE_AI_KEY: ${{ secrets.TEST_AZURE_AI_KEY }}
    
    # Optional: Storage provider secrets for integration tests
    AWS_ACCESS_KEY_ID: ${{ secrets.TEST_AWS_ACCESS_KEY_ID }}
    AWS_SECRET_ACCESS_KEY: ${{ secrets.TEST_AWS_SECRET_ACCESS_KEY }}
    S3_BUCKET_NAME: ${{ secrets.TEST_S3_BUCKET_NAME }}
    
    DROPBOX_REFRESH_TOKEN: ${{ secrets.TEST_DROPBOX_REFRESH_TOKEN }}
    GOOGLE_DRIVE_CREDENTIALS_JSON: ${{ secrets.TEST_GOOGLE_DRIVE_CREDENTIALS }}
    
    # Other test settings (can be plain text)
    DATABASE_URL: sqlite:///:memory:
    REDIS_URL: redis://localhost:6379/0
    WORKDIR: /tmp
    AUTH_ENABLED: "False"
  run: pytest tests/ -v --cov=app
```

#### Step 3: Configure Integration Test Triggers

You have several options for when to run integration tests:

**Option A: Run on Every Push (Recommended for small projects)**
```yaml
on: [push, pull_request]
```

**Option B: Run on Schedule (Recommended to save API costs)**
```yaml
on:
  push:
    branches: [main]
  schedule:
    # Run integration tests daily at 2 AM UTC
    - cron: '0 2 * * *'
  workflow_dispatch:  # Allow manual triggering
```

**Option C: Separate Workflow for Integration Tests**

Create `.github/workflows/integration-tests.yaml`:

```yaml
name: Integration Tests

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM
  workflow_dispatch:  # Manual trigger

jobs:
  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      
      - name: Install Dependencies
        run: |
          pip install -r requirements-dev.txt
      
      - name: Run Integration Tests Only
        env:
          OPENAI_API_KEY: ${{ secrets.TEST_OPENAI_API_KEY }}
          AZURE_AI_KEY: ${{ secrets.TEST_AZURE_AI_KEY }}
          # ... other secrets ...
        run: |
          # Only run tests marked as requires_external
          pytest -m requires_external -v
```

#### Step 4: Verify GitHub Actions Setup

After configuring secrets:

1. Go to **Actions** tab in your GitHub repository
2. Manually trigger a workflow (if `workflow_dispatch` is enabled)
3. Check the logs to ensure tests are using the secrets
4. Verify integration tests are passing

> **🔒 Security Note:** GitHub encrypts secrets and masks them in logs. They are never exposed in workflow output.

#### Common GitHub Actions Configurations

**Skip integration tests if secrets are missing:**
```yaml
- name: Run Integration Tests
  if: ${{ secrets.TEST_OPENAI_API_KEY != '' }}
  env:
    OPENAI_API_KEY: ${{ secrets.TEST_OPENAI_API_KEY }}
  run: pytest -m requires_external
```

**Run unit and integration tests separately:**
```yaml
- name: Run Unit Tests (Always)
  run: pytest -m "unit" -v

- name: Run Integration Tests (If secrets exist)
  if: ${{ secrets.TEST_OPENAI_API_KEY != '' }}
  env:
    OPENAI_API_KEY: ${{ secrets.TEST_OPENAI_API_KEY }}
  run: pytest -m "requires_external" -v
```

### Environment Variable Loading Priority

The test environment loads configuration in this order:

1. **System environment variables** (highest priority) - Used by GitHub Actions
2. **`.env.test` file** (if exists) - Used for local development
3. **Default mock values** in `conftest.py` (fallback) - Used when no secrets configured

This means:
- GitHub Actions sets environment variables directly from Secrets
- Local developers use `.env.test` for convenience
- Tests run without any configuration in basic scenarios (using mocks)
- You can mix and match: set some vars in GitHub Secrets and let others use defaults

## Running Tests

### Run All Tests

```bash
pytest
```

### Run with Coverage Report

```bash
# Terminal output
pytest --cov=app --cov-report=term-missing

# HTML report (opens in browser)
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

### Run Specific Test Categories

```bash
# Unit tests only (fast, no external dependencies)
pytest -m unit

# Integration tests only
pytest -m integration

# Tests requiring external services (OpenAI, Azure, etc.)
pytest -m requires_external

# Tests requiring database
pytest -m requires_db

# All tests EXCEPT those requiring external services
pytest -m "not requires_external"
```

### Run Specific Test Files or Functions

```bash
# Single test file
pytest tests/test_api.py -v

# Specific test function
pytest tests/test_api.py::test_upload_document -v

# All tests matching a pattern
pytest -k "upload" -v
```

### Useful Pytest Options

```bash
# Verbose output
pytest -v

# Stop on first failure
pytest -x

# Show local variables on failure
pytest -l

# Run last failed tests only
pytest --lf

# Show print statements
pytest -s

# Run in parallel (requires pytest-xdist)
pytest -n auto
```

## Writing Tests

### Test Structure

Follow the **Arrange-Act-Assert** pattern:

```python
import pytest
from app.utils.document import validate_document

@pytest.mark.unit
def test_document_validation():
    """Test that invalid documents are rejected."""
    # Arrange - Set up test data
    invalid_document = {
        "filename": "",  # Empty filename
        "size": -1  # Invalid size
    }
    
    # Act - Execute the function being tested
    result = validate_document(invalid_document)
    
    # Assert - Verify the expected outcome
    assert result.is_valid is False
    assert "filename" in result.errors
    assert "size" in result.errors
```

### Using Fixtures

Fixtures provide reusable test setup:

```python
@pytest.mark.unit
def test_pdf_processing(sample_pdf_path):
    """Test PDF file processing."""
    # sample_pdf_path fixture provides a test PDF file
    result = process_pdf(sample_pdf_path)
    assert result.page_count > 0
```

Available fixtures in `conftest.py`:
- `db_session` - Fresh database session
- `client` - FastAPI test client
- `test_workdir` - Temporary directory
- `sample_pdf_path` - Test PDF file
- `sample_text_file` - Test text file
- `mock_openai_response` - Mock OpenAI response
- `mock_azure_response` - Mock Azure response

### API Testing Example

```python
import pytest

@pytest.mark.integration
def test_upload_document(client, sample_pdf_path):
    """Test document upload endpoint."""
    with open(sample_pdf_path, "rb") as f:
        response = client.post(
            "/api/documents/upload",
            files={"file": ("test.pdf", f, "application/pdf")}
        )
    
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["filename"] == "test.pdf"
```

## Test Types and Markers

Use pytest markers to categorize tests:

```python
import pytest

@pytest.mark.unit
def test_pure_function():
    """Fast unit test with no external dependencies."""
    pass

@pytest.mark.integration
def test_api_endpoint():
    """Integration test for API endpoints."""
    pass

@pytest.mark.requires_external
def test_openai_api():
    """Test that calls real OpenAI API (needs .env.test)."""
    pass

@pytest.mark.slow
def test_large_file_processing():
    """Test that takes significant time to run."""
    pass

@pytest.mark.security
def test_authentication():
    """Security-related test."""
    pass
```

### Available Markers

| Marker | Description | Run Command |
|--------|-------------|-------------|
| `unit` | Fast unit tests, no external deps | `pytest -m unit` |
| `integration` | API/workflow integration tests | `pytest -m integration` |
| `requires_external` | Needs external services (OpenAI, etc.) | `pytest -m requires_external` |
| `requires_db` | Needs database | `pytest -m requires_db` |
| `requires_redis` | Needs Redis | `pytest -m requires_redis` |
| `slow` | Takes significant time | `pytest -m "not slow"` to skip |
| `security` | Security-related tests | `pytest -m security` |

## Mocking External Services

For unit tests, mock external API calls to avoid real API usage:

### Mocking OpenAI

```python
import pytest
from unittest.mock import patch, MagicMock

@pytest.mark.unit
def test_metadata_extraction_with_mock():
    """Test metadata extraction with mocked OpenAI."""
    mock_response = {
        "document_type": "invoice",
        "amount": 100.00,
        "date": "2024-01-01"
    }
    
    with patch("app.utils.openai_client.extract_metadata") as mock_extract:
        mock_extract.return_value = mock_response
        
        result = extract_document_metadata("test.pdf")
        
        assert result["document_type"] == "invoice"
        assert result["amount"] == 100.00
        mock_extract.assert_called_once()
```

### Mocking Azure Document Intelligence

```python
@pytest.mark.unit
def test_ocr_with_mock():
    """Test OCR with mocked Azure service."""
    mock_text = "Sample extracted text"
    
    with patch("app.utils.azure_client.extract_text") as mock_ocr:
        mock_ocr.return_value = mock_text
        
        result = perform_ocr("test.pdf")
        
        assert result == mock_text
        mock_ocr.assert_called_once_with("test.pdf")
```

### Using pytest-mock (Recommended)

The `pytest-mock` plugin provides a cleaner syntax:

```python
@pytest.mark.unit
def test_with_mocker(mocker):
    """Test using pytest-mock's mocker fixture."""
    mock_response = {"status": "success"}
    
    mocker.patch(
        "app.utils.storage.upload_to_s3",
        return_value=mock_response
    )
    
    result = upload_document("test.pdf", "s3")
    assert result["status"] == "success"
```

## Integration Testing with Real APIs

### When to Use Real APIs

Use real API integration tests for:
- **Critical paths** that must work end-to-end
- **Complex integrations** that are hard to mock accurately
- **Periodic validation** that your code works with current API versions
- **Pre-release testing** before major deployments

### Setting Up Integration Tests

1. **Create test resources:**
   - Separate test accounts (e.g., test OpenAI account)
   - Dedicated test buckets/folders (e.g., `docuelevate-test-bucket` on S3)
   - Test API keys with minimal permissions

2. **Configure `.env.test`:**
   ```bash
   cp .env.test.example .env.test
   # Edit .env.test with your test credentials
   ```

3. **Mark tests appropriately:**
   ```python
   @pytest.mark.requires_external
   def test_real_openai_api():
       """Integration test with real OpenAI API."""
       # This test will use the OPENAI_API_KEY from .env.test
       pass
   ```

4. **Run integration tests:**
   ```bash
   # Run only integration tests
   pytest -m requires_external
   
   # Run all tests including integration
   pytest
   ```

### Example: Real OpenAI Integration Test

```python
import pytest
import os

@pytest.mark.requires_external
def test_real_openai_metadata_extraction(sample_pdf_path):
    """
    Integration test for OpenAI metadata extraction.
    
    Requires OPENAI_API_KEY in .env.test.
    Uses real API - may incur costs and requires network.
    """
    # Skip if using mock key
    if os.getenv("OPENAI_API_KEY") == "test-key":
        pytest.skip("Real OpenAI API key not configured")
    
    # Call real API
    result = extract_metadata_with_openai(sample_pdf_path)
    
    # Validate response structure
    assert "document_type" in result
    assert "summary" in result
    assert isinstance(result["tags"], list)
```

### Best Practices for Integration Tests

- **Skip gracefully** if real credentials aren't available
- **Test small files** to minimize API costs
- **Add timeouts** for network operations
- **Clean up** test resources after tests
- **Rate limit** to avoid hitting API quotas
- **Monitor costs** of test runs
- **Document requirements** in test docstrings

## Best Practices

### General Guidelines

1. **Write descriptive test names**
   ```python
   # Good
   def test_upload_fails_when_file_exceeds_size_limit():
       pass
   
   # Bad
   def test_upload():
       pass
   ```

2. **One assertion concept per test**
   ```python
   # Good - focused test
   def test_document_has_correct_filename():
       doc = create_document("test.pdf")
       assert doc.filename == "test.pdf"
   
   # Avoid - testing multiple concepts
   def test_document():
       doc = create_document("test.pdf")
       assert doc.filename == "test.pdf"
       assert doc.size > 0
       assert doc.status == "pending"
   ```

3. **Use fixtures for setup/teardown**
   ```python
   @pytest.fixture
   def temp_file():
       """Create temporary file, clean up after test."""
       file_path = "/tmp/test.txt"
       with open(file_path, "w") as f:
           f.write("test content")
       
       yield file_path
       
       # Cleanup
       if os.path.exists(file_path):
           os.remove(file_path)
   ```

4. **Test edge cases and errors**
   ```python
   def test_upload_rejects_empty_file():
       with pytest.raises(ValueError, match="File is empty"):
           upload_document(empty_file)
   ```

5. **Keep tests independent**
   - Tests should not depend on each other
   - Each test should set up its own data
   - Use separate database sessions per test

6. **Mock external dependencies in unit tests**
   - Don't call real APIs in unit tests
   - Use `@pytest.mark.requires_external` for real API tests
   - Mock file system operations when possible

7. **Write clear docstrings**
   ```python
   def test_document_metadata_extraction():
       """
       Test that document metadata is correctly extracted.
       
       Verifies that the extract_metadata function:
       - Returns a dict with required keys
       - Handles missing metadata gracefully
       - Parses dates correctly
       """
       pass
   ```

### Coverage Guidelines

- Target **80% code coverage** for new code
- Focus on critical paths and complex logic
- Don't obsess over 100% coverage
- Exclude test files from coverage reports
- Review coverage reports regularly:
  ```bash
  pytest --cov=app --cov-report=html
  open htmlcov/index.html
  ```

### Continuous Integration

Tests run automatically on:
- Every pull request
- Commits to main branch
- Release builds

CI uses mock values (no `.env.test` file) to ensure:
- Tests don't require secrets to pass
- Tests run quickly without real API calls
- Tests are reproducible and reliable

## Troubleshooting

### Tests Can't Find Modules

```bash
# Install package in editable mode
pip install -e .

# Or add to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:/path/to/DocuElevate"
```

### Database Errors in Tests

```bash
# Clear pytest cache
pytest --cache-clear

# Drop and recreate test database
rm -f app/test.db
pytest
```

### Import Errors in conftest.py

The test environment must be configured **before** importing app modules.
Check that `conftest.py` sets environment variables at the top.

### Integration Tests Not Using .env.test

Verify the file exists and has correct format:
```bash
# Check file exists
ls -la .env.test

# Check format (KEY=VALUE, no spaces)
cat .env.test

# Run with verbose output
pytest -v -s -m requires_external
```

### Mock Not Working

Ensure you're patching the correct import path:
```python
# Patch where it's used, not where it's defined
# If app/api/documents.py imports: from app.utils.openai_client import extract
# Patch: "app.api.documents.extract"

with patch("app.api.documents.extract_metadata") as mock:
    pass
```

## Additional Resources

- [GitHub Secrets Setup Guide](./GitHubSecretsSetup.md) - **Detailed guide for CI/CD secrets configuration**
- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [pytest-mock](https://pytest-mock.readthedocs.io/)
- [Coverage.py](https://coverage.readthedocs.io/)
- [GitHub Actions: Encrypted Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets)

## Questions?

- Check [GitHubSecretsSetup.md](./GitHubSecretsSetup.md) for CI/CD secrets configuration
- Check [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines
- Review existing tests in `tests/` for examples
- Open an issue on GitHub for test-related questions
