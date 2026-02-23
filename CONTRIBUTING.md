# Contributing to DocuElevate

Thank you for your interest in contributing to DocuElevate! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

By participating in this project, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).

## How to Contribute

### Reporting Bugs

If you find a bug in the codebase, please submit an issue on GitHub with:

1. A clear title and description
2. Steps to reproduce the issue
3. Expected behavior
4. Actual behavior
5. Environment information (OS, Docker version, etc.)

### Feature Requests

We welcome feature requests! Please submit an issue with:

1. A clear title and description
2. The problem the feature would solve
3. Any ideas you have for implementing the feature

### Pull Requests

1. Fork the repository
2. Create a new branch for your changes
3. Make your changes
4. **Follow conventional commit format** (see below)
5. Run the tests to ensure everything works
6. Submit a pull request with a clear description of the changes

## Commit Message Format

DocuElevate follows the [Conventional Commits](https://www.conventionalcommits.org/) specification for commit messages. This enables automatic version bumping and changelog generation.

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type

Must be one of the following:

- **feat**: A new feature (triggers minor version bump)
- **fix**: A bug fix (triggers patch version bump)
- **docs**: Documentation only changes
- **style**: Changes that don't affect code meaning (formatting, etc.)
- **refactor**: Code change that neither fixes a bug nor adds a feature
- **perf**: Performance improvement (triggers patch version bump)
- **test**: Adding or updating tests
- **build**: Changes to build system or dependencies
- **ci**: Changes to CI configuration files and scripts
- **chore**: Other changes that don't modify src or test files

### Scope (Optional)

The scope should be the name of the affected module or area:
- `api` - REST API changes
- `ui` - Frontend/UI changes
- `auth` - Authentication changes
- `storage` - Storage provider changes
- `ocr` - OCR processing changes
- `tasks` - Celery task changes
- `config` - Configuration changes

### Subject

The subject contains a succinct description of the change:
- Use imperative, present tense: "change" not "changed" nor "changes"
- Don't capitalize first letter
- No period (.) at the end

### Breaking Changes

For breaking changes, add `!` after the type/scope or include `BREAKING CHANGE:` in the footer:

```
feat!: redesign authentication API

BREAKING CHANGE: The /api/auth endpoint now requires OAuth2 tokens instead of API keys.
```

This triggers a major version bump.

### Examples

```
feat(storage): add support for Amazon S3 storage provider

Add S3StorageProvider class with upload, download, and delete operations.
Includes configuration options for bucket name, region, and credentials.

Closes #123
```

```
fix(ocr): handle PDF files without text layer

Previously, PDFs without existing text layers would fail silently.
Now properly processes them through Azure Document Intelligence.

Fixes #456
```

```
docs: update deployment guide with Docker Compose setup

Added step-by-step instructions for deploying with Docker Compose,
including environment variable configuration and service dependencies.
```

```
chore: update dependencies to fix security vulnerabilities

Updated authlib to 1.6.5+ and starlette to 0.49.1+
```

## Versioning and Releases

DocuElevate uses [semantic-release](https://github.com/semantic-release/semantic-release) for automated version management and releases:

- **Releases are automated**: When PRs are merged to `main`, semantic-release analyzes commit messages and automatically:
  - Determines the next version number
  - Updates the `VERSION` file
  - Generates/updates `CHANGELOG.md`
  - Creates a Git tag with `v` prefix (e.g., `v0.6.0`)
  - Creates a GitHub Release with auto-generated notes
  - Triggers Docker image builds with the new version tag

- **Version Bumps**:
  - `feat:` commits → minor version bump (0.5.0 → 0.6.0)
  - `fix:` or `perf:` commits → patch version bump (0.5.0 → 0.5.1)
  - `feat!:` or `BREAKING CHANGE:` → major version bump (0.5.0 → 1.0.0)
  - Other commit types (docs, chore, etc.) → no version bump

- **Manual Version Changes**: Do NOT manually edit `VERSION` or `CHANGELOG.md` - these are managed by semantic-release

## Documentation-First Development

Documentation is a first-class citizen in DocuElevate. Every contribution **must** include relevant documentation updates. This is not optional.

### What Requires Documentation

| Change Type | Required Documentation |
|-------------|----------------------|
| New feature | User Guide + API docs (if API change) + Configuration Guide (if new config) |
| Bug fix | Troubleshooting guide (if user-facing) |
| New config option | ConfigurationGuide.md + `.env.demo` example |
| New API endpoint | docs/API.md |
| Deployment change | DeploymentGuide.md |
| Security change | SECURITY_AUDIT.md |
| Breaking change | CHANGELOG.md note + migration instructions |

### Documentation Standards

- Keep `docs/` files in sync with code changes in the same PR
- Update `TODO.md` when completing or adding tasks
- `CHANGELOG.md` is generated automatically—**do not add regular release entries manually**. Retroactive corrections to historical entries are the only acceptable exception.
- Screenshots in README and docs should reflect current UI; update them when the UI changes significantly
- Use present tense and second person ("you") in user-facing docs

### Automated Changelog

`CHANGELOG.md` is generated automatically by [python-semantic-release](https://github.com/python-semantic-release/python-semantic-release) on every merge to `main`. **Do not edit it manually.** Your commit messages (following Conventional Commits) drive the changelog content.

---

## Pull Request Checklist

Before submitting a pull request:

- [ ] Code follows the project style guide (Ruff)
- [ ] Commit messages follow conventional commit format
- [ ] Pre-commit hooks installed and passing (see below)
- [ ] Tests added/updated for new functionality
- [ ] **Documentation updated** for any user-facing, API, or configuration changes
- [ ] No manual edits to `VERSION` or `CHANGELOG.md`
- [ ] All tests pass locally
- [ ] Security scan passes (if applicable)

## Development Environment

### Setting Up Your Environment

```bash
# Clone the repository
git clone https://github.com/christianlouis/DocuElevate.git
cd DocuElevate

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install pre-commit hooks (recommended)
pre-commit install
```

### Pre-commit Hooks

Pre-commit hooks automatically check your code before each commit, catching issues early:

```bash
# Install the hooks (one-time setup)
pre-commit install

# Run hooks manually on all files
pre-commit run --all-files

# Run hooks on staged files (happens automatically on commit)
pre-commit run
```

The pre-commit hooks include:
- **Ruff** - Linting and formatting (with auto-fix)
- **Mypy** - Type checking
- **detect-secrets** - Secret detection
- **Conventional commits** - Commit message validation
- File checks (trailing whitespace, large files, etc.)

### Running Tests

DocuElevate has comprehensive test coverage including unit tests, integration tests, and end-to-end tests. Tests are automatically configured with the necessary environment variables.

#### Quick Test Commands

```bash
# Run all tests (default configuration)
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=app --cov-report=term-missing

# Run only unit tests (fast, no Docker required)
pytest -m unit

# Run only integration tests
pytest -m integration

# Run specific test file
pytest tests/test_api.py -v
```

#### Test Environment Configuration

Tests automatically configure the required environment variables in `tests/conftest.py`:

- `DATABASE_URL`: Uses SQLite in-memory database for fast, isolated tests
- `AUTH_ENABLED`: Set to `False` by default for simpler unit tests
- `SESSION_SECRET`: Pre-configured with a valid 32+ character secret for tests that need it
- `OPENAI_API_KEY`, `AZURE_AI_KEY`, etc.: Pre-configured with test values

**No manual environment setup is needed to run tests!**

#### Testing with Authentication Enabled

Some tests specifically verify authentication behavior with `AUTH_ENABLED=True`. These tests:

1. Use `@patch("app.auth.AUTH_ENABLED", True)` to enable auth for specific tests
2. Properly configure `SESSION_SECRET` (already set in conftest.py)
3. Mock user sessions to test protected endpoints
4. Verify login redirects and access control

Example:
```python
from unittest.mock import patch

@pytest.mark.integration
def test_protected_endpoint_with_auth(client):
    """Test endpoint requires authentication when auth is enabled."""
    with patch("app.auth.AUTH_ENABLED", True):
        # Test will verify redirect to /login
        response = client.get("/protected-page")
        assert response.status_code == 302
```

#### Integration Tests with Docker

Some tests require Docker to spin up real infrastructure (PostgreSQL, Redis, WebDAV, etc.):

```bash
# Run integration tests that need Docker
pytest -m requires_docker -v

# Run end-to-end tests with full stack
pytest -m e2e -v
```

See [tests/README_INTEGRATION_TESTS.md](tests/README_INTEGRATION_TESTS.md) for detailed information about integration testing.

#### Test Markers

Tests are organized using pytest markers:

- `@pytest.mark.unit` - Fast unit tests with mocks
- `@pytest.mark.integration` - Integration tests with some real services
- `@pytest.mark.e2e` - Full end-to-end tests
- `@pytest.mark.requires_docker` - Requires Docker to run
- `@pytest.mark.slow` - Tests that take significant time
- `@pytest.mark.security` - Security-related tests

#### Running Tests in CI

Tests run automatically in GitHub Actions for all pull requests. The CI workflow is organized in stages:

**Stage 1: Ruff Lint & Format** (runs first, in parallel with dependency scan)
- Checks code style, formatting, and basic security issues
- Must pass before tests run

**Stage 1b: Dependency Vulnerability Scan** (runs in parallel with lint)
- Runs `pip-audit` against `requirements.txt` and `requirements-dev.txt`
- Fails the build if any known vulnerabilities are detected
- Checks the OSV and PyPA advisory databases
- Runs independently at the same time as Stage 1 so it does not add to total pipeline time

**Stage 2: Tests & Type Checking** (runs after lint and dependency scan both pass)

| Job | Tool | What it checks |
|--------|--------|--------------------------------------|
| `test` | pytest | Unit/integration tests + coverage |
| `mypy` | mypy | Static type checking |

**Stage 3: Docker Build** (runs after all checks pass)
- Builds and pushes Docker images

**Stage 4: Deploy** (only on main branch)
- Deploys to production

**Auto-fix Workflow:**
- A separate `ruff-auto-fix` workflow automatically fixes formatting issues on PRs
- Commits fixes back to the PR branch
- Only runs on PRs from the same repository (not forks)

For full details see [docs/CIWorkflow.md](docs/CIWorkflow.md) and [docs/CIToolsGuide.md](docs/CIToolsGuide.md).

### Code Style

DocuElevate uses **Ruff** for all Python code quality checks:

- **Linting** - PEP 8 style, code quality, and security checks
- **Formatting** - Consistent code formatting (120 character line length)
- **Import sorting** - Organized imports

```bash
# Check for linting issues
ruff check app/ tests/

# Auto-fix linting issues
ruff check app/ tests/ --fix

# Check formatting
ruff format --check app/ tests/

# Auto-format code
ruff format app/ tests/
```

**Note:** The pre-commit hooks and CI pipeline will automatically check (and optionally fix) these for you.

### Dependency Vulnerability Scanning

DocuElevate uses **pip-audit** to scan dependencies for known security vulnerabilities. The CI pipeline runs this automatically and **blocks builds** if any vulnerabilities are found.

To run locally before pushing:

```bash
# Scan production dependencies
pip-audit -r requirements.txt --desc on

# Scan all dependencies (including dev)
pip-audit -r requirements-dev.txt --desc on
```

If pip-audit is not installed, add it with:

```bash
pip install pip-audit
```

## Project Structure

```
DocuElevate/
├── app/               # Main application code
│   ├── api/          # REST API endpoints (organized by feature)
│   ├── tasks/        # Celery background tasks
│   ├── views/        # UI routes and template rendering
│   ├── utils/        # Utility functions and helpers
│   ├── config.py     # Configuration management (Pydantic)
│   ├── database.py   # Database setup and session management
│   ├── models.py     # SQLAlchemy models
│   ├── main.py       # FastAPI app initialization
│   └── auth.py       # Authentication logic
├── frontend/         # Frontend assets
│   ├── static/       # CSS, JavaScript, images
│   └── templates/    # Jinja2 HTML templates
├── tests/            # Test suite
├── docs/             # User and developer documentation
├── migrations/       # Alembic database migrations
└── docker/           # Docker configuration files
```

## 📚 Additional Resources

### Documentation
- **[AGENTIC_CODING.md](AGENTIC_CODING.md)** - Comprehensive guide for AI agents and developers
- **[README.md](README.md)** - Project overview and quickstart
- **[docs/CIWorkflow.md](docs/CIWorkflow.md)** - CI pipeline and linter details for maintainers
- **[ROADMAP.md](ROADMAP.md)** - Future features and long-term vision
- **[MILESTONES.md](MILESTONES.md)** - Release planning and versioning
- **[TODO.md](TODO.md)** - Current tasks and priorities
- **[SECURITY.md](SECURITY.md)** - Security policy
- **[SECURITY_AUDIT.md](SECURITY_AUDIT.md)** - Security findings and improvements

### Testing
- All new features must include tests
- Aim for 80% code coverage
- See [AGENTIC_CODING.md#testing-strategy](AGENTIC_CODING.md#testing-strategy) for detailed testing guidelines

### Security
- Never commit secrets or credentials
- Follow guidelines in [SECURITY_AUDIT.md](SECURITY_AUDIT.md)
- Report security issues per [SECURITY.md](SECURITY.md)

## 🤝 Getting Help

- **GitHub Issues:** Bug reports and feature requests
- **GitHub Discussions:** Questions and community support
- **Documentation:** Check `docs/` directory for guides

Thank you for contributing to DocuElevate!
