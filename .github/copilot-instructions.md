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

## Supported Runtimes

- **Python**: 3.11+ (3.11 and 3.12 specified in pyproject.toml)
- **Docker**: Production images use `python:3.14.1` / `python:3.14.1-slim`
- **Redis**: Alpine-based (`redis:alpine`)
- **Gotenberg**: `gotenberg/gotenberg:latest` for PDF conversion

## Build Commands

```bash
# Install production dependencies
pip install -r requirements.txt

# Install development dependencies (includes linters, test tools)
pip install -r requirements-dev.txt

# Run the FastAPI development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run the Celery worker (requires Redis)
celery -A app.celery_worker worker -B --loglevel=info -Q document_processor,default,celery

# Docker build and run
docker compose up -d

# Database migrations
alembic upgrade head                              # Apply all migrations
alembic revision --autogenerate -m "description"  # Create new migration
```

## Test Commands

```bash
# Run all tests with coverage (default via pyproject.toml addopts)
pytest

# Run tests by marker
pytest -m unit
pytest -m integration
pytest -m "not requires_external"

# Run a specific test file or test
pytest tests/test_api.py -v
pytest tests/test_api.py::test_function_name -v

# Coverage report
pytest --cov=app --cov-report=term-missing
pytest --cov=app --cov-report=html
```

## Lint / Format Commands

```bash
# Format and lint with Ruff (replaces Black, isort, Flake8, Bandit — all-in-one)
ruff format app/ tests/
ruff check app/ tests/ --fix

# Type checking with mypy
mypy app/

# Check for dependency vulnerabilities
safety check

# Run all pre-commit hooks at once (recommended — runs ruff, mypy, secret detection, etc.)
pre-commit run --all-files
```

## Agent Workflow (Follow for Every Task)

Follow these steps **in order** for every task — do not skip any:

1. **Understand** — read the issue/request in full before writing any code
2. **Explore** — search the codebase for existing patterns and relevant implementations
3. **Plan** — outline your changes as a checklist before starting
4. **Implement** — make the smallest correct change that solves the problem
5. **Test** — write or update tests; new code requires 100% test coverage
6. **Document** — update all relevant docs in `docs/`; this is mandatory, not optional
7. **Quality Gate** — run the single gate command below and fix every failure before committing:

```bash
ruff format app/ tests/ && \
ruff check app/ tests/ --fix && \
safety check && \
pytest --tb=short -q
```

8. **Review** — re-read your own diff; confirm it is clean, secure, minimal, and well-documented

> All commands in the quality gate must exit with code 0. Never submit with failures.

## Core Principles

### Code Quality
- **Security first**: treat security as a non-negotiable requirement, not an afterthought — review [SECURITY_AUDIT.md](../SECURITY_AUDIT.md) for every change
- Write **clean, modern, well-documented code** — prioritize readability, maintainability, and idiomatic Python
- Use **Ruff** for all formatting, linting, import sorting, and security scanning — `ruff format` + `ruff check --fix` (replaces Black, isort, Flake8, Bandit)
- Line length: 120 characters (configured in `pyproject.toml`)
- Use **type hints** for all function parameters and return values
- Write **docstrings** for all public functions, classes, and modules
- Maintain **100% test coverage** for new code

### Python Conventions
- Use descriptive variable names (e.g., `user_document_path`, not `udp`)
- Follow PEP 8 naming: `snake_case` for functions/variables, `PascalCase` for classes
- Use modern Python 3.10+ type hints: `list[str]`, `dict[str, Any]`, `str | None` — avoid `List`, `Dict`, `Optional` from `typing`
- Only import from `typing` for `Any`, `Callable`, `TypeVar`, `Protocol`, and other constructs unavailable natively
- Prefer `pathlib.Path` over string paths for file operations
- Use f-strings for string formatting, not `.format()` or `%`
- Handle exceptions explicitly - avoid bare `except:` clauses

### Security Best Practices
- **Never commit secrets or credentials** to the repository
- Use environment variables for sensitive configuration (see `.env.demo`)
- Validate and sanitize all user inputs
- Use parameterized queries with SQLAlchemy (never raw SQL with user input)
- Review [SECURITY_AUDIT.md](../SECURITY_AUDIT.md) before making security-related changes
- Security linting is built into Ruff via `S` rules — runs automatically with `ruff check`; fix all `S`-prefixed findings
- Run `safety check` to scan dependencies for known CVEs before submitting any PR

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
- **All tests must pass** before submitting changes — never leave failing tests
- **All linters must pass** before submitting — run `pre-commit run --all-files`

### Configuration
- All configuration is in `app/config.py` using Pydantic Settings
- Use environment variables for configuration (12-factor app)
- Provide sensible defaults when possible
- Document all configuration options in `docs/ConfigurationGuide.md`

### Documentation
- Keep documentation in `docs/` directory in Markdown format
- **Always update** relevant docs when adding or changing any feature — documentation updates are mandatory, never optional
- User-facing documentation should be clear and include examples
- Reference existing docs: `docs/UserGuide.md`, `docs/API.md`, `docs/DeploymentGuide.md`
- See [AGENTIC_CODING.md](../AGENTIC_CODING.md) for detailed development guide

### Error Handling
- Use custom exceptions defined in application (follow existing patterns)
- Log errors with context using Python's `logging` module
- Return user-friendly error messages in API responses
- Include error details in development, sanitize in production
- In API endpoints, raise `HTTPException` with appropriate status codes (400, 401, 403, 404, 500)
- In Celery tasks, use `self.retry(exc=e, countdown=60)` for transient errors; log and return error dict for permanent errors
- Never use bare `except:` — always catch specific exception types
- Wrap database operations in `try/except` with `db.rollback()` in the except block

### Logging Conventions
- Use Python's built-in `logging` module: `import logging; logger = logging.getLogger(__name__)`
- **Log levels**:
  - `logger.debug()` — detailed diagnostic information
  - `logger.info()` — general operational events (document processed, task started)
  - `logger.warning()` — recoverable issues (retrying, fallback used)
  - `logger.error()` — errors that need attention (failed operations)
  - `logger.critical()` — system-level failures requiring immediate action
- **Always include context** in log messages: `logger.info(f"Processing document: {file_id}, user: {user_id}")`
- **Never log sensitive data**: passwords, tokens, API keys, personal information
- Use f-strings in log messages (consistent with project style)

### Architectural Boundaries
- **`app/api/`** — REST API endpoints only; organize by feature
- **`app/tasks/`** — Celery background tasks only; keep idempotent
- **`app/views/`** — UI routes serving Jinja2 templates
- **`app/utils/`** — Shared utility functions and helpers
- **`app/routes/`** — **Deprecated**; being migrated to `app/api/` — do not add new code here
- **`app/models.py`** — All SQLAlchemy models (single file)
- **`app/config.py`** — All configuration via Pydantic Settings (single file)
- **`app/database.py`** — Database engine and session setup (single file)
- **`app/auth.py`** — Authentication logic (single file)
- **`frontend/templates/`** — Jinja2 templates; do not mix backend logic
- **`frontend/static/`** — CSS, JS, images; keep JavaScript minimal
- **`tests/`** — Test files mirroring `app/` structure
- **`migrations/`** — Alembic migration scripts; always auto-generate with `alembic revision --autogenerate`

### Don't Change Rules
These files and directories are managed by automation or are critical infrastructure — **do not manually edit**:
- **`VERSION`** — Managed by `python-semantic-release`; updated automatically on merge to main
- **`CHANGELOG.md`** — Auto-generated from conventional commit messages by semantic-release
- **`migrations/`** — Do not manually edit existing migration files; only create new ones via `alembic revision --autogenerate`
- **Git tags and GitHub Releases** — Created automatically by semantic-release; never create manually
- **`.pre-commit-config.yaml`** — Only change if adding/updating linting tools; do not remove existing hooks
- **`pyproject.toml` `[tool.semantic_release]`** — Release configuration; do not modify without explicit approval
- **`docker-compose.yaml` service names** — External systems depend on `api`, `worker`, `redis`, `gotenberg` names

### Dependencies
- Add new dependencies to `requirements.txt` (production) or `requirements-dev.txt` (development)
- Document any new dependencies and their licenses in README.md
- Check for security vulnerabilities with `safety check`
- Pin major versions, allow minor updates (e.g., `fastapi>=0.100.0,<1.0.0`)

### Git Workflow
- Write clear, descriptive commit messages
- **ALWAYS follow Conventional Commits format** (see below)
- Keep commits focused and atomic
- **All tests must pass** before committing — `pytest` must succeed with no failures
- **All linters must pass** before committing — `pre-commit run --all-files` must succeed
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
- Use modern Python 3.10+ type hints: `list[str]`, `dict[str, Any]`, `str | None`; only import from `typing` for `Any`, `Callable`, `TypeVar`, `Protocol`
- Import FastAPI dependencies: `from fastapi import Depends, HTTPException, status`
- Get DB session: `db: Session = Depends(get_db)`
- Current user: `current_user: User = Depends(get_current_user)`
- Logger: `import logging; logger = logging.getLogger(__name__)`

## Resources
- [AGENTIC_CODING.md](../AGENTIC_CODING.md) - Comprehensive development guide
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guidelines
- [SECURITY_AUDIT.md](../SECURITY_AUDIT.md) - Security considerations
- [README.md](../README.md) - Project overview and quickstart
