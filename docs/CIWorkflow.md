# CI Workflow Guide

This document describes the CI/CD pipeline for DocuElevate, focusing on the **Run Tests & Linting** workflow.

## Overview

The CI workflow (`.github/workflows/tests.yaml`) runs automatically on every push and pull request. It is designed so that **each linter and the test suite run as independent jobs**, ensuring that a failure in one tool never blocks the results from another.

## Workflow Jobs

| Job | Tool | Purpose | Enforced |
|--------|--------|---------------------------------------------|----------|
| `test` | pytest | Unit/integration tests with coverage | ✅ |
| `flake8`| flake8 | PEP 8 style linting | ✅ |
| `black` | black | Code formatting check | ✅ |
| `mypy` | mypy | Static type checking | ✅ |
| `pylint`| pylint | Code quality analysis | ✅ |
| `bandit`| bandit | Security vulnerability scanning | ✅ |

All six jobs start **in parallel** as soon as the workflow is triggered. No job depends on or waits for any other job.

### Tests

- Runs pytest with coverage reporting (XML + terminal).
- Excludes E2E tests that require Docker-in-Docker (`-m "not e2e"`).
- Uses Redis and RabbitMQ service containers.
- Uploads coverage and JUnit XML results to Codecov.
- Uploads `junit.xml` and `coverage.xml` as workflow artifacts (always, even on failure).

### Flake8

- Checks `app/` against PEP 8 with `max-line-length=120`.
- Ignores `E203` (whitespace before `:`) and `W503` (line break before binary operator), matching the Black formatter.

### Black

- Verifies that all files in `app/` are formatted with `black --line-length=120`.
- Runs in `--check` mode (no files are modified).

### Mypy

- Type checks `app/` with `--ignore-missing-imports`.
- Requires full project dependencies (installs `requirements-dev.txt`).

### Pylint

- Analyzes `app/` with `max-line-length=120`.
- Disables `C0111` (missing docstrings), `C0103` (naming conventions), and `R0903` (too few public methods).
- Requires full project dependencies (installs `requirements-dev.txt`).

### Bandit

- Produces a full JSON report (`bandit-report.json`) uploaded as a workflow artifact.
- **Fails the job** if any high- or medium-severity issues are found (`-ll` flag).
- The JSON report is always uploaded, even if the severity check fails.

## Artifacts

The following artifacts are uploaded after every run:

| Artifact | Contents | Condition |
|------------------|--------------------------------------|----------------------|
| `test-results` | `junit.xml`, `coverage.xml` | Always (unless cancelled) |
| `bandit-report` | `bandit-report.json` | Always (unless cancelled) |

## Running Linters Locally

You can run the same checks locally before pushing:

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run each linter
flake8 app/ --max-line-length=120 --extend-ignore=E203,W503
black --check app/ --line-length=120
mypy app/ --ignore-missing-imports
pylint app/ --max-line-length=120 --disable=C0111,C0103,R0903
bandit -r app/ -ll

# Run tests
pytest tests/ -v --cov=app --cov-report=term -m "not e2e"
```

Or use pre-commit hooks to run checks automatically on each commit:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

## Design Decisions

### Why Separate Jobs Instead of Steps?

Previously, all linters ran as sequential steps in a single job. This meant:

- A failure in flake8 would prevent black, mypy, pylint, and bandit from running.
- Contributors only saw feedback from the **first** tool that failed, not all of them.

By splitting into independent jobs:

- **All tools always run** regardless of other failures.
- Contributors see **all** feedback in a single CI run.
- Jobs run **in parallel**, reducing total wall-clock time.

### Why Are All Linters Enforced?

All linters are set to fail the CI (no `continue-on-error`). This ensures:

- The codebase stays consistently formatted (Black).
- Style issues are caught early (Flake8).
- Type errors surface before merge (Mypy).
- Code quality standards are maintained (Pylint).
- Security issues are flagged immediately (Bandit).

## Copilot Code Compliance

All code — whether written by hand or suggested by GitHub Copilot — goes through the same CI pipeline. Copilot-generated code is linted, type-checked, and security-scanned identically to human-written code. Contributors using Copilot should ensure suggestions pass all checks before committing.
