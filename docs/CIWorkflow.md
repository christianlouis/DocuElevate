# CI Workflow Guide

This document describes the CI/CD pipeline for DocuElevate, focusing on the **Run Tests & Linting** workflow.

## Overview

The CI workflow (`.github/workflows/tests.yaml`) runs automatically on every push and pull request. It is designed so that **each linter and the test suite run as independent jobs**, ensuring that a failure in one tool never blocks the results from another.

## Workflow Jobs

| Job | Tool | Purpose | Enforced |
|--------|--------|---------------------------------------------|----------|
| `lint` | Ruff | Fast Python linter (replaces Flake8, Black, isort, Bandit) | ✅ |
| `html-lint` | djLint | HTML template accessibility linter | ✅ |
| `dependency-scan` | pip-audit | Dependency vulnerability scanning against OSV/PyPA advisories | ✅ |
| `test-quick` | pytest | Unit + basic integration tests with coverage (~2 min) | ✅ |
| `test-integration` | pytest | Docker container and external service tests (~5 min) | ✅ |
| `mypy` | mypy | Static type checking | ✅ |

### Pipeline Flow

```
Stage 1 (parallel):  lint, html-lint, dependency-scan
                          │
Stage 2 (parallel):  test-quick + mypy
                          │
Stage 3:             test-integration  (only after test-quick passes)
                          │
Stage 4:             build  (only after all above pass)
```

The pipeline follows a **fail-early** strategy: fast linters and quick tests run first to catch regressions early. Heavier integration tests only run after the quick tests pass, saving CI time when basic issues are present.

> **Note:** DocuElevate uses Ruff, a modern all-in-one Python linter that consolidates the functionality of Flake8, Black, isort, and Bandit. This streamlined approach reduces CI complexity while maintaining code quality and security standards.

### Quick Tests (`test-quick`)

- **Timeout:** 10 minutes (job), 120 seconds (per test via `pytest-timeout`)
- Runs the majority of tests (~2,790 unit + basic integration tests)
- Excludes tests marked `e2e`, `requires_docker`, `requires_external`, or `slow`
- Uses a Redis service container for tests that need it
- Collects coverage and uploads to Codecov
- Uploads `junit.xml` and `coverage.xml` as workflow artifacts

### Integration Tests (`test-integration`)

- **Timeout:** 20 minutes (job), 300 seconds (per test via `pytest-timeout`)
- Runs tests marked `requires_docker`, `requires_external`, or `slow` (excluding `e2e`)
- Uses Redis and RabbitMQ service containers
- Docker daemon available for testcontainers (WebDAV, OAuth mock server, etc.)
- Only runs after quick tests pass (fail-early gate)
- Uploads `junit-integration.xml` as a workflow artifact

### Ruff Lint & Format

- **Linting**: Checks `app/` and `tests/` for code quality issues
  - Enforces PEP 8 style with `line-length=120`
  - Includes security checks (replaces Bandit)
  - Checks import order (replaces isort)
  - Catches common bugs (replaces Flake8 + Pylint patterns)
- **Formatting**: Verifies code is formatted consistently (replaces Black)
  - Runs in check mode (no files are modified)
  - Automatically fixable with `ruff format`

### Mypy

- Type checks `app/` with appropriate configuration from `pyproject.toml`.
- Requires full project dependencies (installs `requirements-dev.txt`).

## Artifacts

The following artifacts are uploaded after every run:

| Artifact | Contents | Condition |
|-------------------------------|--------------------------------------|----------------------|
| `test-results-quick` | `junit.xml`, `coverage.xml` | Always (unless cancelled) |
| `test-results-integration` | `junit-integration.xml` | Always (unless cancelled) |

## Running Linters Locally

You can run the same checks locally before pushing:

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run Ruff linting
ruff check app/ tests/

# Run Ruff formatting check
ruff format --check app/ tests/

# Run type checking
mypy app/

# Run quick tests (same as CI quick stage)
pytest tests/ -v --timeout=120 --cov=app --cov-report=term -m "not e2e and not requires_docker and not requires_external and not slow"

# Run integration tests (requires Docker)
pytest tests/ -v --timeout=300 -m "(requires_docker or requires_external or slow) and not e2e"

# Run all tests except e2e
pytest tests/ -v --timeout=120 -m "not e2e"
```

Or use pre-commit hooks to run checks automatically on each commit (recommended):

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

Pre-commit hooks include Ruff linting/formatting, Mypy type checking, secret detection, and conventional commit validation.

## Additional Security Scanning

Beyond the linting and testing workflows, DocuElevate uses additional security tools:

### CodeQL (`.github/workflows/codeql.yml`)

- **Purpose**: Advanced security scanning for code vulnerabilities
- **Frequency**: Runs on push to main, pull requests, and weekly schedule
- **Languages**: Python, JavaScript, GitHub Actions
- **Coverage**: Detects security vulnerabilities, bugs, and code quality issues
- **Native GitHub integration**: Results appear in the Security tab

### Codecov

- **Purpose**: Test coverage tracking and visualization
- **Integration**: Automatically receives coverage reports from test workflow
- **Features**: Coverage trends, PR comments, coverage diffs

## Design Decisions

### Why Separate Jobs Instead of Steps?

Previously, all linters ran as sequential steps in a single job. This meant:

- A failure in one tool would prevent others from running.
- Contributors only saw feedback from the **first** tool that failed, not all of them.

By splitting into independent jobs:

- **All tools always run** regardless of other failures.
- Contributors see **all** feedback in a single CI run.
- Jobs run **in parallel**, reducing total wall-clock time.

### Why Ruff Instead of Multiple Tools?

DocuElevate uses Ruff as an all-in-one linting solution, replacing:
- **Flake8** (PEP 8 style checking)
- **Black** (code formatting)
- **isort** (import sorting)
- **Bandit** (security linting)
- **Pylint** (some code quality checks)

**Benefits:**
- 10-100x faster than traditional tools
- Single configuration in `pyproject.toml`
- Consistent behavior across all checks
- Auto-fix capability for most issues
- Active development and modern Python support

### Why Are All Checks Enforced?

All checks are set to fail the CI (no `continue-on-error`). This ensures:

- The codebase stays consistently formatted (Ruff format).
- Style and quality issues are caught early (Ruff check).
- Type errors surface before merge (Mypy).
- Security issues are flagged immediately (Ruff security rules + CodeQL).

## Tool Comparison & Rationale

This project previously used multiple overlapping tools. Here's why the current setup was chosen:

| Tool Category | Current Tool | Replaced Tools | Rationale |
|---------------|--------------|----------------|-----------|
| Linting & Formatting | **Ruff** | Flake8, Black, isort, Bandit, Pylint | Modern, fast, comprehensive, single tool |
| Type Checking | **Mypy** | - | Industry standard, unique value |
| Security Scanning | **CodeQL** | - | GitHub native, free, enterprise-grade |
| Coverage Tracking | **Codecov** | - | Excellent visualization and PR integration |

**Rejected/Removed:**
- **DeepSource**: Redundant with Ruff + CodeQL (removed in this update)
- **SonarQube**: Not configured, enterprise-focused, redundant with current tools
- **Snyk**: Not configured, CodeQL provides adequate security scanning

## Copilot Code Compliance

All code — whether written by hand or suggested by GitHub Copilot — goes through the same CI pipeline. Copilot-generated code is linted, type-checked, and security-scanned identically to human-written code. Contributors using Copilot should ensure suggestions pass all checks before committing.
