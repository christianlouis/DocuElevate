"""
Pytest configuration and shared fixtures for DocuElevate tests.
"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment variables before importing app
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["AZURE_AI_KEY"] = "test-key"
os.environ["AZURE_REGION"] = "test"
os.environ["AZURE_ENDPOINT"] = "https://test.cognitiveservices.azure.com/"
os.environ["GOTENBERG_URL"] = "http://localhost:3000"
os.environ["WORKDIR"] = "/tmp"
os.environ["AUTH_ENABLED"] = "False"
os.environ["SESSION_SECRET"] = "test_secret_key_for_testing_must_be_at_least_32_characters_long"

from app.database import Base  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402

# Import models to register them with SQLAlchemy Base
from app.models import DocumentMetadata, FileRecord, ProcessingLog  # noqa: F401, E402


@pytest.fixture(scope="session")
def test_workdir() -> Generator[str, None, None]:
    """Create a temporary work directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    # Create an in-memory SQLite database
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create a session
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session) -> TestClient:
    """Create a test client with a fresh database."""

    # Import the canonical get_db function
    from app.database import get_db

    # Override the get_db dependency to use our test database
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    # Override the single canonical get_db dependency
    fastapi_app.dependency_overrides[get_db] = override_get_db

    # Use base_url to satisfy TrustedHostMiddleware
    with TestClient(fastapi_app, base_url="http://localhost") as test_client:
        yield test_client

    # Clean up
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def sample_pdf_path(test_workdir) -> str:
    """Create a sample PDF file for testing."""
    pdf_path = os.path.join(test_workdir, "test.pdf")

    # Create a minimal valid PDF
    pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
>>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<<
/Size 4
/Root 1 0 R
>>
startxref
197
%%EOF
"""

    with open(pdf_path, "wb") as f:
        f.write(pdf_content)

    return pdf_path


@pytest.fixture
def sample_text_file(test_workdir) -> str:
    """Create a sample text file for testing."""
    text_path = os.path.join(test_workdir, "test.txt")

    with open(text_path, "w") as f:
        f.write("This is a test document.\nWith multiple lines.\n")

    return text_path


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response for testing."""
    return {
        "choices": [
            {
                "message": {
                    "content": '{"document_type": "invoice", "summary": "Test invoice", "tags": ["test", "invoice"]}'
                }
            }
        ]
    }


@pytest.fixture
def mock_azure_response():
    """Mock Azure Document Intelligence API response for testing."""
    return {"analyzeResult": {"content": "Test document content extracted by OCR", "pages": [{"pageNumber": 1}]}}


# Markers for categorizing tests
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests for individual functions/methods")
    config.addinivalue_line("markers", "integration: Integration tests for API endpoints and workflows")
    config.addinivalue_line("markers", "slow: Tests that take significant time to run")
    config.addinivalue_line("markers", "security: Security-related tests")
    config.addinivalue_line("markers", "requires_external: Tests requiring external services")
    config.addinivalue_line("markers", "requires_db: Tests requiring database")
    config.addinivalue_line("markers", "requires_redis: Tests requiring Redis")
