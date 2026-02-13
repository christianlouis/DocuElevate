---
applyTo: "tests/**/*.py"
---

# Testing Instructions

These instructions apply to all test files in the `tests/` directory.

## Test Organization
- Mirror the structure of `app/` directory in `tests/`
- Name test files with `test_` prefix (e.g., `test_api.py`)
- Group related tests in classes with `Test` prefix
- Use descriptive test function names: `test_<what>_<condition>_<expected>`

## Pytest Configuration
- Configuration in `pytest.ini`
- Run tests: `pytest -v`
- With coverage: `pytest --cov=app --cov-report=term-missing`
- Run specific markers: `pytest -m unit` or `pytest -m integration`

## Test Markers
Use pytest markers to categorize tests:
```python
import pytest

@pytest.mark.unit
def test_document_validation():
    """Test document validation logic."""
    pass

@pytest.mark.integration
def test_document_upload_api():
    """Test document upload endpoint."""
    pass

@pytest.mark.slow
def test_large_file_processing():
    """Test processing of large files."""
    pass

@pytest.mark.requires_external
def test_openai_integration():
    """Test OpenAI API integration."""
    pass
```

Available markers:
- `unit` - Unit tests for individual functions/methods
- `integration` - Integration tests for API endpoints and workflows
- `slow` - Tests that take significant time to run
- `security` - Security-related tests
- `requires_external` - Tests requiring external services (OpenAI, Azure, etc.)
- `requires_db` - Tests requiring database
- `requires_redis` - Tests requiring Redis

## Fixtures
Use pytest fixtures for test setup and teardown:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base

@pytest.fixture
def db_session():
    """Provide a database session for tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()
    Base.metadata.drop_all(engine)

@pytest.fixture
def sample_document():
    """Provide a sample document for tests."""
    return {
        "filename": "test.pdf",
        "content_type": "application/pdf",
        "size": 1024
    }
```

## API Testing with FastAPI
Use `TestClient` from FastAPI:
```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_upload_document():
    """Test document upload endpoint."""
    with open("tests/fixtures/sample.pdf", "rb") as f:
        response = client.post(
            "/api/documents/upload",
            files={"file": ("test.pdf", f, "application/pdf")}
        )

    assert response.status_code == 201
    assert "id" in response.json()
```

## Async Testing
For async code, use `pytest-asyncio`:
```python
import pytest
import httpx

@pytest.mark.asyncio
async def test_async_document_processing():
    """Test async document processing."""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/documents/1")
        assert response.status_code == 200
```

## Mocking External Services
Always mock external services in tests:
```python
from unittest.mock import Mock, patch

@pytest.mark.unit
def test_openai_metadata_extraction(mocker):
    """Test metadata extraction with mocked OpenAI."""
    mock_response = {
        "document_type": "invoice",
        "amount": 100.00,
        "date": "2024-01-01"
    }

    mocker.patch(
        "app.utils.openai_client.extract_metadata",
        return_value=mock_response
    )

    result = extract_document_metadata("test.pdf")
    assert result["document_type"] == "invoice"

@pytest.mark.unit
def test_azure_ocr_processing(mocker):
    """Test OCR with mocked Azure service."""
    mock_text = "Sample extracted text"

    mocker.patch(
        "app.utils.azure_client.extract_text",
        return_value=mock_text
    )

    result = perform_ocr("test.pdf")
    assert result == mock_text
```

## Database Testing
```python
@pytest.mark.requires_db
def test_create_document(db_session):
    """Test document creation in database."""
    from app.models import Document

    doc = Document(
        filename="test.pdf",
        user_id=1,
        file_path="/tmp/test.pdf"
    )
    db_session.add(doc)
    db_session.commit()

    assert doc.id is not None
    assert doc.filename == "test.pdf"
```

## Test Coverage Goals
- Aim for **80% code coverage** for all new code
- Focus on critical paths and error handling
- Test both success and failure scenarios
- Don't test third-party library code

## Test Structure
Follow the Arrange-Act-Assert pattern:
```python
def test_document_validation():
    """Test that invalid documents are rejected."""
    # Arrange
    invalid_document = {
        "filename": "",  # Empty filename
        "size": -1  # Invalid size
    }

    # Act
    result = validate_document(invalid_document)

    # Assert
    assert result.is_valid is False
    assert "filename" in result.errors
    assert "size" in result.errors
```

## Parameterized Tests
Use `pytest.mark.parametrize` for multiple test cases:
```python
@pytest.mark.parametrize("filename,expected", [
    ("document.pdf", True),
    ("image.jpg", True),
    ("script.exe", False),
    ("", False),
])
def test_allowed_file_types(filename, expected):
    """Test file type validation."""
    result = is_allowed_file(filename)
    assert result == expected
```

## Test Data
- Place test fixtures in `tests/fixtures/` directory
- Use small sample files for testing
- Don't commit large test files
- Clean up test files in teardown

## Error Testing
Always test error conditions:
```python
def test_missing_file_raises_error():
    """Test that missing files raise appropriate error."""
    with pytest.raises(FileNotFoundError):
        process_document("/nonexistent/file.pdf")

def test_invalid_api_request():
    """Test API error handling."""
    response = client.post("/api/documents/", json={})
    assert response.status_code == 422  # Validation error
```

## Best Practices
- Test one thing per test function
- Use descriptive test names
- Keep tests independent (no dependencies between tests)
- Use fixtures for common setup
- Mock external dependencies
- Test edge cases and error conditions
- Keep tests fast (use mocks for slow operations)
- Clean up resources after tests
