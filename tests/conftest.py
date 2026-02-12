"""
Pytest configuration and shared fixtures for DocuElevate tests.
"""

import os
import tempfile
from typing import Dict, Generator, Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Capture original environment variables before overriding with test defaults.
# This allows integration tests to detect when real API credentials are available
# (e.g., injected via GitHub Actions secrets) and run live API verification.
_EXTERNAL_API_ENV_KEYS = [
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "AZURE_AI_KEY",
    "AZURE_ENDPOINT",
    "AZURE_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "S3_BUCKET_NAME",
    "S3_FOLDER_PREFIX",
    "DROPBOX_APP_KEY",
    "DROPBOX_APP_SECRET",
    "DROPBOX_REFRESH_TOKEN",
    "ONEDRIVE_CLIENT_ID",
    "ONEDRIVE_CLIENT_SECRET",
    "ONEDRIVE_REFRESH_TOKEN",
    "ONEDRIVE_TENANT_ID",
    "ONEDRIVE_FOLDER_PATH",
    "GOOGLE_DRIVE_CREDENTIALS_JSON",
    "GOOGLE_DRIVE_FOLDER_ID",
    "AUTHENTIK_CLIENT_ID",
    "AUTHENTIK_CLIENT_SECRET",
    "AUTHENTIK_CONFIG_URL",
    "SESSION_SECRET",
]
_PLACEHOLDER_VALUES = {"test-key", "test", "", "NOT_SET"}
_original_env: Dict[str, Optional[str]] = {key: os.environ.get(key) for key in _EXTERNAL_API_ENV_KEYS}

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
def sample_pdf_file(test_workdir):
    """Create a sample PDF file for testing, returning Path object."""
    from pathlib import Path

    pdf_path = Path(test_workdir) / "test.pdf"

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

    pdf_path.write_bytes(pdf_content)
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


def has_real_env(*keys: str) -> bool:
    """Check if real (non-placeholder) environment variables were set before test overrides.

    Returns True only if ALL specified keys had non-placeholder values in the
    original environment.  Used by integration tests to decide whether to skip
    when real credentials are unavailable.
    """
    for key in keys:
        value = _original_env.get(key)
        if value is None or value in _PLACEHOLDER_VALUES:
            return False
    return True


@pytest.fixture(scope="session")
def original_env() -> Dict[str, Optional[str]]:
    """Provide access to the original environment variables captured before test overrides."""
    return dict(_original_env)


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
    config.addinivalue_line("markers", "requires_docker: Tests requiring Docker")
    config.addinivalue_line("markers", "e2e: End-to-end tests with full infrastructure")

# Import OAuth fixtures (must be at end to avoid circular imports)
try:
    from tests.conftest_oauth import (
        mock_oauth_server,
        oauth_config,
        oauth_enabled_app,
        oauth_test_token,
        test_user_info,
        use_real_oauth,
    )
    
    # Make fixtures available
    __all__ = [
        "mock_oauth_server",
        "oauth_config", 
        "oauth_enabled_app",
        "oauth_test_token",
        "test_user_info",
        "use_real_oauth",
    ]
except ImportError:
    # OAuth fixtures not available (testcontainers may not be installed)
    pass
