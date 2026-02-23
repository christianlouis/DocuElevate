---
applyTo: "app/**/*.py"
---

# Python Backend Instructions

These instructions apply to all Python code in the `app/` directory.

## Code Style
- Use **Ruff** for all formatting, linting, import sorting, and security scanning — `ruff format app/ tests/ && ruff check app/ tests/ --fix`
- Line length: 120 characters (configured in `pyproject.toml` `[tool.ruff]`)
- All functions must have type hints for parameters and return values
- Use modern Python 3.10+ type hints: `list[str]`, `dict[str, Any]`, `str | None`
- Only import from `typing` for `Any`, `Callable`, `TypeVar`, `Protocol` (not `Dict`, `List`, `Optional`, `Union`)

## Import Order (enforced by Ruff `I` rules)
```python
# Standard library imports
import os
from pathlib import Path
from typing import Any  # Only for Any, Callable, TypeVar, Protocol

# Third-party imports
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

# Local application imports
from app.config import settings
from app.database import get_db
from app.models import Document, User
```

## Function Definitions
```python
def process_document(
    file_path: Path,
    user_id: int,
    metadata: dict[str, Any] | None = None
) -> DocumentMetadata:
    """
    Process a document and extract metadata.

    Args:
        file_path: Path to the document file
        user_id: ID of the user uploading the document
        metadata: Optional additional metadata

    Returns:
        DocumentMetadata object with extracted information

    Raises:
        FileNotFoundError: If file doesn't exist
        ProcessingError: If processing fails
    """
    pass
```

## FastAPI Endpoints
- Use dependency injection for DB sessions and auth
- Return Pydantic models for automatic validation
- Use proper status codes from `fastapi.status`
- Add detailed docstrings for OpenAPI docs
```python
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/documents", tags=["documents"])

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_document(
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> DocumentResponse:
    """Create and process a new document."""
    pass
```

## Error Handling
- Use custom exceptions from the application
- Log errors with context using `logging.getLogger(__name__)`
- Return user-friendly error messages
- Never expose internal details in production errors
```python
import logging

logger = logging.getLogger(__name__)

try:
    result = process_file(file_path)
except FileNotFoundError:
    logger.error(f"File not found: {file_path}")
    raise HTTPException(status_code=404, detail="File not found")
except Exception as e:
    logger.exception(f"Error processing file: {str(e)}")
    raise HTTPException(status_code=500, detail="Processing failed")
```

## Database Operations
- Use SQLAlchemy ORM, never raw SQL with user input
- Use `get_db()` dependency for sessions
- Always commit in try/except blocks
```python
from sqlalchemy.orm import Session
from app.database import get_db

def create_document(db: Session, document_data: dict) -> Document:
    """Create a new document in the database."""
    db_document = Document(**document_data)
    try:
        db.add(db_document)
        db.commit()
        db.refresh(db_document)
        return db_document
    except Exception as e:
        db.rollback()
        raise
```

## Celery Tasks
- Define in `app/tasks/` directory
- Use descriptive names: `module.action`
- Set retry policies
- Log progress and errors
```python
from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def process_ocr(self, document_id: int) -> dict[str, Any]:
    """Process OCR for a document."""
    try:
        # Processing logic
        logger.info(f"Processing OCR for document {document_id}")
        return {"status": "success"}
    except Exception as exc:
        logger.exception(f"OCR processing failed for {document_id}")
        raise self.retry(exc=exc, countdown=60)
```

## Configuration
- All settings in `app/config.py` using Pydantic Settings
- Use environment variables, never hardcode values
- Provide defaults when sensible
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str
    max_file_size: int = 10485760  # 10MB default

    class Config:
        env_file = ".env"
```

## Security (First and Foremost)
- **Security first**: treat every change as a potential attack surface — review `SECURITY_AUDIT.md` before making any security-related change
- Never commit secrets, tokens, or credentials
- Validate and sanitize all user inputs
- Use parameterized queries — never raw SQL with user data
- Sanitize file paths; check file permissions before access
- Security linting is built into Ruff via `S` rules — fix all `S`-prefixed findings before committing
- Run `safety check` before submitting any PR to catch dependency CVEs
