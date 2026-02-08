# Copilot Instructions for DocuElevate

## Project Overview

DocuElevate is an intelligent document processing system that automates handling, extraction, and processing of documents. It integrates with multiple cloud storage providers (Dropbox, Google Drive, OneDrive, S3, Nextcloud) and uses AI services (OpenAI, Azure Document Intelligence) for metadata extraction and OCR.

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, Celery, Redis
- **Frontend**: Jinja2 templates, Tailwind CSS
- **AI/ML**: OpenAI API, Azure Document Intelligence
- **Auth**: Authentik (OAuth2), Basic Auth
- **Infrastructure**: Docker, Docker Compose, Alembic (migrations)
- **Testing**: Pytest, pytest-asyncio, httpx

## Core Principles

### Code Quality
- Always use **Black** for formatting (line length: 120)
- Use **isort** with Black profile for import sorting
- Use **flake8** for linting (ignore E203, W503)
- Use **type hints** for all function parameters and return values
- Write **docstrings** for all public functions, classes, and modules
- Maintain **80% test coverage** for new code

### Python Conventions
- Use descriptive variable names (e.g., `user_document_path`, not `udp`)
- Follow PEP 8 naming: `snake_case` for functions/variables, `PascalCase` for classes
- Use type hints from `typing` module (Dict, List, Optional, etc.)
- Prefer `pathlib.Path` over string paths for file operations
- Use f-strings for string formatting, not `.format()` or `%`
- Handle exceptions explicitly - avoid bare `except:` clauses

### Security Best Practices
- **Never commit secrets or credentials** to the repository
- Use environment variables for sensitive configuration (see `.env.demo`)
- Validate and sanitize all user inputs
- Use parameterized queries with SQLAlchemy (never raw SQL with user input)
- Review [SECURITY_AUDIT.md](../SECURITY_AUDIT.md) before making security-related changes
- Run `bandit` to check for security issues in Python code

### FastAPI Patterns
- Organize endpoints by feature in `app/api/` directory
- Use dependency injection for database sessions and authentication
- Return Pydantic models from endpoints for automatic validation
- Use proper HTTP status codes (200, 201, 400, 401, 403, 404, 500)
- Document endpoints with docstrings for OpenAPI documentation
- Use `async def` for I/O-bound operations

### Database (SQLAlchemy)
- All models are defined in `app/models.py`
- Use Alembic for schema migrations (create migration for any model change)
- Use declarative base for models
- Define relationships with `relationship()` and proper `back_populates`
- Use database sessions from `app.database.get_db()` dependency
- Always close sessions in `finally` blocks or use context managers

### Celery Tasks
- Define tasks in `app/tasks/` directory, organized by feature
- Use descriptive task names: `module.action` (e.g., `document.process_ocr`)
- Set appropriate retry policies and error handling
- Log progress and errors using Python's `logging` module
- Use `bind=True` for tasks that need access to task instance
- Keep tasks idempotent when possible

### Frontend
- Templates are in `frontend/templates/` using Jinja2
- Static files (CSS, JS, images) in `frontend/static/`
- Use Tailwind CSS utility classes (already configured)
- Keep JavaScript minimal - prefer server-side rendering
- Follow existing template structure and patterns

### Testing
- Write tests in `tests/` directory, mirroring `app/` structure
- Use pytest markers: `@pytest.mark.unit`, `@pytest.mark.integration`, etc.
- Mock external services (OpenAI, Azure, cloud storage) in tests
- Use `pytest.fixture` for test setup and teardown
- Run tests with: `pytest -v`
- Check coverage with: `pytest --cov=app --cov-report=term-missing`

### Configuration
- All configuration is in `app/config.py` using Pydantic Settings
- Use environment variables for configuration (12-factor app)
- Provide sensible defaults when possible
- Document all configuration options in `docs/ConfigurationGuide.md`

### Documentation
- Keep documentation in `docs/` directory in Markdown format
- Update relevant docs when adding features or changing behavior
- User-facing documentation should be clear and include examples
- Reference existing docs: `docs/UserGuide.md`, `docs/API.md`, `docs/DeploymentGuide.md`
- See [AGENTIC_CODING.md](../AGENTIC_CODING.md) for detailed development guide

### Error Handling
- Use custom exceptions defined in application (follow existing patterns)
- Log errors with context using Python's `logging` module
- Return user-friendly error messages in API responses
- Include error details in development, sanitize in production

### Dependencies
- Add new dependencies to `requirements.txt` (production) or `requirements-dev.txt` (development)
- Document any new dependencies and their licenses in README.md
- Check for security vulnerabilities with `safety check`
- Pin major versions, allow minor updates (e.g., `fastapi>=0.100.0,<1.0.0`)

### Git Workflow
- Write clear, descriptive commit messages
- **ALWAYS follow Conventional Commits format** (see below)
- Keep commits focused and atomic
- Run tests and linters before committing
- Pre-commit hooks are configured (`.pre-commit-config.yaml`)

## Conventional Commits (REQUIRED)

All commit messages MUST follow the [Conventional Commits](https://www.conventionalcommits.org/) specification.

### Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

### Commit Types and Version Impact
- **feat**: New feature → minor version bump (0.5.0 → 0.6.0)
- **fix**: Bug fix → patch version bump (0.5.0 → 0.5.1)
- **perf**: Performance improvement → patch version bump
- **docs**: Documentation only → no version bump
- **style**: Formatting changes → no version bump
- **refactor**: Code refactoring → no version bump
- **test**: Test changes → no version bump
- **build**: Build system changes → no version bump
- **ci**: CI/CD changes → no version bump
- **chore**: Other changes → no version bump

### Breaking Changes
For breaking changes (major version bump), add `!` after type or include `BREAKING CHANGE:` in footer:
```
feat(api)!: redesign authentication endpoints

BREAKING CHANGE: OAuth2 tokens now required instead of API keys.
```
Result: 0.5.0 → 1.0.0

### Scope Examples
- `api` - REST API changes
- `ui` - Frontend changes
- `auth` - Authentication
- `storage` - Storage providers
- `ocr` - OCR processing
- `tasks` - Celery tasks
- `config` - Configuration
- `docs` - Documentation

### Commit Examples
```
feat(storage): add Amazon S3 storage provider
fix(ocr): handle PDFs without text layer
docs: update deployment guide with Docker setup
refactor(tasks): consolidate duplicate code
test: add integration tests for upload API
chore: update dependencies for security fixes
```

## Semantic Release Process

### Automated Versioning
DocuElevate uses `python-semantic-release` for automated version management:

1. **On merge to main**: semantic-release analyzes commit messages
2. **Automatic actions**:
   - Determines next version from commit types
   - Updates `VERSION` file
   - Generates/updates `CHANGELOG.md`
   - Creates Git tag with `v` prefix (e.g., `v0.6.0`)
   - Creates GitHub Release with auto-generated notes
   - Triggers Docker image builds with version tag

### Agent Rules for Versioning
- ✅ **DO**: Write conventional commit messages
- ✅ **DO**: Use appropriate commit types for your changes
- ✅ **DO**: Mark breaking changes explicitly
- ❌ **DON'T**: Manually edit `VERSION` file
- ❌ **DON'T**: Manually edit `CHANGELOG.md`
- ❌ **DON'T**: Create version tags or GitHub Releases manually

These files are managed entirely by the semantic-release automation.

### File Organization
- Place API endpoints in `app/api/` organized by feature
- Background tasks go in `app/tasks/`
- Utility functions in `app/utils/`
- UI routes in `app/views/`
- Database models in `app/models.py`
- Configuration in `app/config.py`

### Common Patterns
- Use `from typing import Optional, Dict, List, Any` for type hints
- Import FastAPI dependencies: `from fastapi import Depends, HTTPException, status`
- Get DB session: `db: Session = Depends(get_db)`
- Current user: `current_user: User = Depends(get_current_user)`
- Logger: `import logging; logger = logging.getLogger(__name__)`

## Resources
- [AGENTIC_CODING.md](../AGENTIC_CODING.md) - Comprehensive development guide
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guidelines
- [SECURITY_AUDIT.md](../SECURITY_AUDIT.md) - Security considerations
- [README.md](../README.md) - Project overview and quickstart
