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

## Pull Request Checklist

Before submitting a pull request:

- [ ] Code follows the project style guide (Black, isort, flake8)
- [ ] Commit messages follow conventional commit format
- [ ] Tests added/updated for new functionality
- [ ] Documentation updated if user-facing changes
- [ ] No manual edits to `VERSION` or `CHANGELOG.md`
- [ ] All tests pass locally
- [ ] Pre-commit hooks pass
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
```

### Running Tests

```bash
pytest
```

### Code Style

We use:
- Black for Python code formatting
- Flake8 for linting
- isort for import sorting

```bash
# Format code
black .

# Check linting
flake8

# Sort imports
isort .
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