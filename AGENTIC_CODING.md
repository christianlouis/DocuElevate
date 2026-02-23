# Agentic Coding Guide for DocuElevate

**Version:** 1.0
**Last Updated:** 2026-02-06

This guide helps AI coding agents work effectively with the DocuElevate codebase. It provides context, conventions, and best practices for autonomous code contributions.

---

## 🎯 Project Overview

### What is DocuElevate?
DocuElevate is an intelligent document processing system that:
- Ingests documents from multiple sources (email, web upload, API)
- Processes documents (OCR, PDF conversion, metadata extraction)
- Stores documents in various cloud storage providers
- Uses AI (OpenAI, Azure) for intelligent document classification and metadata extraction

### Tech Stack
```
Backend:  FastAPI, SQLAlchemy, Celery, Redis
Frontend: Jinja2 templates, Tailwind CSS
AI/ML:    OpenAI API, Azure Document Intelligence
Storage:  Dropbox, Google Drive, OneDrive, S3, Nextcloud, Paperless-NGX
Auth:     Authentik (OAuth2), Basic Auth
Infra:    Docker, Docker Compose, Alembic (migrations)
```

### Key Directories
```
DocuElevate/
├── app/
│   ├── api/          # REST API endpoints
│   ├── tasks/        # Celery background tasks
│   ├── routes/       # Deprecated - being migrated to api/
│   ├── views/        # UI routes and templates
│   ├── utils/        # Utility functions
│   ├── config.py     # Configuration (Pydantic Settings)
│   ├── database.py   # SQLAlchemy setup
│   ├── models.py     # Database models
│   ├── main.py       # FastAPI app initialization
│   └── auth.py       # Authentication logic
├── frontend/
│   ├── static/       # CSS, JS, images
│   └── templates/    # Jinja2 HTML templates
├── tests/           # Pytest test suite
├── docs/            # User documentation
├── migrations/      # Alembic database migrations
└── docker/          # Docker configuration
```

---

## 🤖 Agent Guidelines

### Before Making Changes

1. **Understand the Context**
   - Read relevant documentation in `docs/`
   - Check `TODO.md` for current priorities
   - Review `SECURITY_AUDIT.md` for security considerations
   - Check `ROADMAP.md` for feature direction

2. **Check Existing Patterns**
   - Look at similar existing code first
   - Follow the established patterns in the codebase
   - Don't introduce new patterns without good reason

3. **Identify Dependencies**
   - Check if your change affects multiple modules
   - Ensure you understand the Celery task flow
   - Consider impact on database schema

### Documentation-First Principle

**Documentation is as important as tests and code.** Every change must include documentation updates in the same commit/PR.

| Change type | What to update |
|-------------|---------------|
| New feature | `docs/UserGuide.md`, `docs/API.md` (if API), `docs/ConfigurationGuide.md` (if config) |
| New config option | `docs/ConfigurationGuide.md` and `.env.demo` |
| New API endpoint | `docs/API.md` |
| Bug fix (user-visible) | `docs/Troubleshooting.md` |
| Deployment change | `docs/DeploymentGuide.md` |
| Security change | `SECURITY_AUDIT.md` |
| Breaking change | CHANGELOG (auto-generated) + migration notes in relevant docs |

**Never edit `CHANGELOG.md` or `VERSION` manually.** These are managed automatically by `python-semantic-release` on every merge to `main`.

### Code Conventions

#### Python Style
```python
# Use Ruff formatting (line length: 120)
# Use type hints
def process_document(file_path: str, metadata: Dict[str, Any]) -> DocumentMetadata:
    """
    Process a document and extract metadata.

    Args:
        file_path: Absolute path to the document file
        metadata: Additional metadata to include

    Returns:
        DocumentMetadata object with extracted information

    Raises:
        FileNotFoundError: If file doesn't exist
        ProcessingError: If processing fails
    """
    pass

# Use descriptive variable names
user_document_path = Path("/workdir/documents/invoice.pdf")
ocr_result = extract_text_from_pdf(user_document_path)

# Prefer explicit over implicit
if storage_provider == "dropbox":
    upload_to_dropbox(file_path, metadata)
elif storage_provider == "google_drive":
    upload_to_google_drive(file_path, metadata)
else:
    raise ValueError(f"Unknown storage provider: {storage_provider}")
```

#### Configuration
```python
# Always use settings from config.py
from app.config import settings

# Good
api_key = settings.openai_api_key

# Bad - never hardcode
api_key = "sk-abc123..."

# Check if optional services are configured
if settings.dropbox_app_key:
    # Dropbox is configured
    upload_to_dropbox()
```

#### Error Handling
```python
# Use appropriate exception types
from fastapi import HTTPException, status

# API endpoints should return HTTP errors
@router.get("/files/{file_id}")
async def get_file(file_id: int):
    file = get_file_from_db(file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID {file_id} not found"
        )
    return file

# Tasks should log and handle errors gracefully
@celery_app.task(bind=True, max_retries=3)
def process_document_task(self, file_path: str):
    try:
        result = process_document(file_path)
        return result
    except TemporaryError as e:
        logger.warning(f"Temporary error processing {file_path}: {e}")
        raise self.retry(exc=e, countdown=60)
    except PermanentError as e:
        logger.error(f"Permanent error processing {file_path}: {e}")
        # Don't retry permanent errors
        return {"error": str(e)}
```

#### Testing
```python
# Mark tests appropriately
@pytest.mark.unit
def test_hash_file():
    """Unit test for file hashing utility."""
    pass

@pytest.mark.integration
def test_upload_api_endpoint(client):
    """Integration test for upload API."""
    pass

@pytest.mark.requires_external
@pytest.mark.skip(reason="Requires OpenAI API key")
def test_openai_metadata_extraction():
    """Test actual OpenAI integration."""
    pass

# Use fixtures for common setup
def test_document_processing(sample_pdf_path, db_session):
    """Test uses fixtures from conftest.py"""
    pass
```

---

## 📝 Common Tasks

### Adding a New API Endpoint

1. Create endpoint in `app/api/`:
```python
# app/api/my_feature.py
from fastapi import APIRouter, HTTPException
from app.database import get_db
from app.models import MyModel

router = APIRouter(prefix="/api/my-feature", tags=["my-feature"])

@router.get("/")
async def list_items(db=Depends(get_db)):
    """List all items."""
    items = db.query(MyModel).all()
    return items
```

2. Register router in `app/api/__init__.py`:
```python
from app.api import my_feature

router.include_router(my_feature.router)
```

3. Add tests in `tests/test_api_my_feature.py`

### Adding a New Celery Task

1. Create task in `app/tasks/`:
```python
# app/tasks/my_task.py
from app.celery_app import celery_app
import logging

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3)
def my_background_task(self, param: str):
    """
    Description of what this task does.

    Args:
        param: Description of parameter
    """
    try:
        logger.info(f"Processing task with param: {param}")
        # Task logic here
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Task failed: {e}")
        raise self.retry(exc=e, countdown=60)
```

2. Import in `app/tasks/__init__.py`
3. Add tests in `tests/test_tasks.py`

### Adding a Database Model

1. Define model in `app/models.py`:
```python
class MyModel(Base):
    __tablename__ = "my_table"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
```

2. Create migration:
```bash
cd /path/to/DocuElevate
alembic revision --autogenerate -m "Add MyModel table"
alembic upgrade head
```

3. Add model to tests fixtures

### Adding a Storage Provider

1. Create provider module in `app/tasks/storage/`:
```python
# app/tasks/storage/my_provider.py
from app.config import settings
import logging

logger = logging.getLogger(__name__)

def upload_to_my_provider(file_path: str, metadata: dict) -> str:
    """
    Upload file to My Provider.

    Args:
        file_path: Local path to file
        metadata: Document metadata

    Returns:
        URL or ID of uploaded file

    Raises:
        ProviderError: If upload fails
    """
    if not settings.my_provider_api_key:
        raise ValueError("MY_PROVIDER_API_KEY not configured")

    # Implementation
    pass
```

2. Add configuration to `app/config.py`:
```python
class Settings(BaseSettings):
    # ... existing settings ...
    my_provider_api_key: Optional[str] = None
    my_provider_endpoint: Optional[str] = None
```

3. Add to `.env.demo`:
```bash
# My Provider
MY_PROVIDER_API_KEY=your_api_key_here
MY_PROVIDER_ENDPOINT=https://api.myprovider.com
```

4. Add validator in `app/utils/config_validator/`
5. Add tests with mocked API calls

---

## 🔒 Security Best Practices

### What to NEVER Do
- ❌ Hardcode API keys, passwords, or secrets
- ❌ Log sensitive data (passwords, tokens, API keys)
- ❌ Accept unsanitized user input for file paths
- ❌ Disable security features without documentation
- ❌ Commit `.env` files or credentials

### What to ALWAYS Do
- ✅ Use `settings` from `app/config.py` for all configuration
- ✅ Validate and sanitize all user inputs
- ✅ Use parameterized database queries (SQLAlchemy handles this)
- ✅ Check file paths for directory traversal (`Path.resolve()`)
- ✅ Use appropriate HTTP status codes (401, 403, 404, etc.)
- ✅ Log security-relevant events
- ✅ Add rate limiting for sensitive endpoints
- ✅ Use HTTPS in production (documented in deployment guide)

### Input Validation Example
```python
from pathlib import Path
from fastapi import HTTPException, status

def validate_file_path(file_path: str, base_dir: str = "/workdir") -> Path:
    """Validate file path is within allowed directory."""
    try:
        path = Path(file_path).resolve()
        base = Path(base_dir).resolve()

        # Ensure path is within base directory
        if not path.is_relative_to(base):
            raise ValueError("Path outside allowed directory")

        return path
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file path: {e}"
        )
```

---

## 🧪 Testing Strategy

### Test Coverage Goals
- **Target:** 80% overall coverage
- **Critical modules:** 90%+ (auth, config, database)
- **Tasks:** 70%+ (complex to test with external services)
- **API endpoints:** 85%+

### Test Types
```python
# Unit tests - fast, isolated, no external dependencies
@pytest.mark.unit
def test_hash_file_empty(tmp_path):
    """Test hashing an empty file."""
    file = tmp_path / "empty.txt"
    file.write_text("")
    assert hash_file(str(file)) == "expected_hash"

# Integration tests - test multiple components together
@pytest.mark.integration
def test_upload_and_process(client, sample_pdf):
    """Test full upload and processing flow."""
    response = client.post("/api/upload", files={"file": sample_pdf})
    assert response.status_code == 200

# External service tests - skipped by default
@pytest.mark.requires_external
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No API key")
def test_real_openai_extraction():
    """Test actual OpenAI API (skipped in CI)."""
    pass
```

### Running Tests
```bash
# All tests
pytest

# Specific category
pytest -m unit
pytest -m integration

# With coverage
pytest --cov=app --cov-report=html

# Specific file
pytest tests/test_api.py -v

# Skip external services
pytest -m "not requires_external"
```

---

## 🚀 Performance Considerations

### Async/Await
- FastAPI endpoints are async by default
- Use `async def` for I/O-bound operations
- Use regular `def` for CPU-bound operations

```python
# Good - async for I/O
@router.get("/files")
async def list_files(db: Session = Depends(get_db)):
    files = db.query(FileRecord).all()
    return files

# Also good - sync for CPU-heavy
@router.post("/hash")
def hash_large_file(file: UploadFile):
    return compute_hash(file.file.read())
```

### Database Queries
```python
# Good - single query with join
files = db.query(FileRecord).options(
    joinedload(FileRecord.metadata)
).filter(FileRecord.user_id == user_id).all()

# Bad - N+1 queries
files = db.query(FileRecord).filter(FileRecord.user_id == user_id).all()
for file in files:
    metadata = file.metadata  # Triggers separate query each time
```

### Celery Tasks
```python
# Long-running tasks should update progress
@celery_app.task(bind=True)
def process_large_batch(self, file_ids: List[int]):
    total = len(file_ids)
    for i, file_id in enumerate(file_ids):
        process_file(file_id)
        self.update_state(
            state='PROGRESS',
            meta={'current': i + 1, 'total': total}
        )
```

---

## 📚 Documentation Requirements

### Code Documentation
```python
def complex_function(param1: str, param2: int = 10) -> Dict[str, Any]:
    """
    One-line summary of what the function does.

    More detailed explanation if needed. Can span multiple
    lines and include examples.

    Args:
        param1: Description of param1
        param2: Description of param2, defaults to 10

    Returns:
        Dictionary containing:
            - key1: Description
            - key2: Description

    Raises:
        ValueError: If param1 is empty
        FileNotFoundError: If file doesn't exist

    Examples:
        >>> result = complex_function("test", 5)
        >>> print(result['key1'])
        'value'
    """
    pass
```

### API Documentation
- Use FastAPI's automatic OpenAPI generation
- Add descriptions to endpoints
- Document request/response models
- Include example requests/responses

```python
@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
    description="Upload a document for processing. Supports PDF, images, and Office documents.",
    responses={
        201: {"description": "Document uploaded successfully"},
        400: {"description": "Invalid file format"},
        413: {"description": "File too large"},
    }
)
async def upload_document(
    file: UploadFile = File(..., description="Document file to upload"),
    tags: List[str] = Query([], description="Optional tags for the document"),
):
    """Upload endpoint implementation."""
    pass
```

---

## 🐛 Debugging

### Logging
```python
import logging

logger = logging.getLogger(__name__)

# Use appropriate log levels
logger.debug("Detailed information for debugging")
logger.info("General information about operation")
logger.warning("Warning about potential issue")
logger.error("Error that needs attention")
logger.critical("Critical error that needs immediate attention")

# Include context in logs
logger.info(f"Processing document: {file_id}, user: {user_id}")

# Don't log sensitive data
logger.info(f"User authenticated")  # Good
logger.info(f"Password: {password}")  # BAD!
```

### Common Issues

1. **Import Errors**
   - Check if module is in `__init__.py`
   - Verify Python path includes project root
   - Look for circular imports

2. **Database Issues**
   - Check if migrations are up to date: `alembic upgrade head`
   - Verify DATABASE_URL is set correctly
   - Check if tables exist: `sqlite3 app/database.db .schema`

3. **Celery Issues**
   - Verify Redis is running: `redis-cli ping`
   - Check Celery worker logs
   - Ensure tasks are imported in `celery_worker.py`

4. **Test Failures**
   - Check if test database is clean (use fixtures)
   - Verify environment variables are set in `conftest.py`
   - Run single test to isolate issue: `pytest tests/test_file.py::test_name -v`

---

## 🔄 Git Workflow & Versioning

### Branch Names
- `feature/description` - New features
- `bugfix/description` - Bug fixes
- `hotfix/description` - Urgent production fixes
- `refactor/description` - Code refactoring
- `docs/description` - Documentation updates

### Conventional Commits (REQUIRED)

**All commit messages MUST follow the Conventional Commits specification for automated versioning.**

#### Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

#### Commit Types and Version Bumps
- **feat**: New feature → **minor version bump** (0.5.0 → 0.6.0)
- **fix**: Bug fix → **patch version bump** (0.5.0 → 0.5.1)
- **perf**: Performance improvement → **patch version bump**
- **docs**: Documentation only → **no version bump**
- **style**: Code style/formatting → **no version bump**
- **refactor**: Code refactoring → **no version bump**
- **test**: Test changes → **no version bump**
- **build**: Build system changes → **no version bump**
- **ci**: CI/CD changes → **no version bump**
- **chore**: Other changes → **no version bump**

#### Breaking Changes
Add `!` after type/scope or include `BREAKING CHANGE:` in footer for **major version bump**:
```
feat(api)!: redesign authentication endpoints

BREAKING CHANGE: OAuth2 tokens now required instead of API keys
```
Result: 0.5.0 → 1.0.0

#### Scope Examples
- `api` - REST API changes
- `ui` - Frontend/UI changes
- `auth` - Authentication
- `storage` - Storage providers
- `ocr` - OCR processing
- `tasks` - Celery tasks
- `config` - Configuration

#### Good Commit Examples
```
feat(storage): add Amazon S3 storage provider

Implements S3StorageProvider with upload, download, delete operations.
Includes configuration for bucket, region, and credentials.

Closes #123
```

```
fix(ocr): handle PDFs without text layer

Previously failed silently. Now properly processes through Azure.

Fixes #456
```

```
docs: update deployment guide with Docker Compose

Added step-by-step instructions for Docker Compose deployment.
```

### Semantic Release Automation

DocuElevate uses `python-semantic-release` for automated version management.

#### How It Works
1. **PR merges to main** with conventional commits
2. **semantic-release analyzes** commit messages
3. **Automatic updates**:
   - Bumps `VERSION` file
   - Updates `CHANGELOG.md`
   - Creates Git tag (e.g., `v0.6.0`)
   - Creates GitHub Release
   - Triggers Docker builds

#### Agent Rules
- ✅ **DO**: Write conventional commit messages
- ✅ **DO**: Use correct commit types
- ✅ **DO**: Include `BREAKING CHANGE:` when applicable
- ❌ **DON'T**: Manually edit `VERSION` file
- ❌ **DON'T**: Manually edit `CHANGELOG.md`
- ❌ **DON'T**: Create version tags or releases manually

### Pull Requests
1. Create PR with descriptive title (conventional format if single change)
2. Fill out PR template
3. Link related issues
4. Ensure CI passes
5. Request reviews
6. Address feedback
7. Merge when approved (commits retain conventional format)

---

## ✅ Pre-commit Checklist

Before submitting code:

- [ ] Code follows style guide (Ruff formatted)
- [ ] Commit messages use conventional commit format
- [ ] All tests pass (`pytest`)
- [ ] New code has tests
- [ ] Coverage doesn't decrease
- [ ] Documentation updated if needed
- [ ] No secrets or credentials in code
- [ ] Linting passes (`ruff check`)
- [ ] Type hints added (`mypy` clean)
- [ ] No manual edits to `VERSION` or `CHANGELOG.md`
- [ ] Security scan passed (included in `ruff check`)

Run full check:
```bash
pytest --cov=app
ruff check app/ tests/
ruff format --check app/ tests/
mypy app/
```

**Note:** This project uses Ruff, which replaces Black, Flake8, isort, and Bandit with a single, faster tool.

---

## 🤝 Agent Collaboration

### When to Ask for Help
- Breaking changes needed
- Unsure about architecture decision
- Security implications unclear
- Performance impact unknown
- Tests consistently failing

### How to Document Changes
1. Update relevant documentation
2. Add comments for complex logic
3. Update TODO.md if introducing tech debt
4. Note breaking changes in commit message
5. Update API documentation if endpoints changed

---

## 📞 Resources

- **Main README:** [README.md](README.md)
- **API Docs:** http://localhost:8000/docs (when running)
- **User Guide:** [docs/UserGuide.md](docs/UserGuide.md)
- **Deployment:** [docs/DeploymentGuide.md](docs/DeploymentGuide.md)
- **Troubleshooting:** [docs/Troubleshooting.md](docs/Troubleshooting.md)
- **GitHub Issues:** Track bugs and features
- **GitHub Discussions:** Questions and community

---

*This guide is a living document. Improvements welcome via PR!*
