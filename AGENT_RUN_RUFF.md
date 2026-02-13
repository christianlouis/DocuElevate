# Agent Pre-PR Ruff Policy

This document defines the policy for Copilot/AI Agents when creating or updating pull requests in the DocuElevate repository.

## Required Steps Before Creating/Updating a PR

### 1. Run the Ruff Auto-Fix Script

Before creating or updating a branch or opening a PR, **ALWAYS** run:

```bash
./scripts/run-ruff-and-fix.sh
```

### 2. Handle Script Exit Codes

**If the script exits with code 0 (success):**
- ✅ All ruff checks passed or were auto-fixed
- Continue with PR creation process
- Push the branch (including any auto-fix commits)

**If the script exits with code non-zero (failure):**
- ❌ Stop PR creation immediately
- Do NOT open the PR
- Report the ruff failures to the human user
- Include the full `ruff check` output in your response
- Create an issue or report the failures for manual resolution

### 3. Handle Auto-Fix Commits

If the script commits fixes:
- The script will automatically commit changes with message: `style: ruff auto-fixes`
- Push the branch with the commit(s) before continuing PR creation
- This ensures CI sees the fixed code when the PR is opened

## Example Agent Workflow

```
1. Clone repository and create feature branch
2. Make code changes to implement feature
3. Run: ./scripts/run-ruff-and-fix.sh
4. Check exit code:
   - If 0: Push branch and create PR
   - If non-zero: Report failures, do NOT create PR
5. Run project tests (if ruff passed)
6. If all checks pass: Create the PR
7. If any check fails: Report failures instead of creating PR
```

## Why This Policy Exists

1. **Prevent CI Failures**: Ensures PRs don't break ruff checks in CI
2. **Auto-Fix Minor Issues**: Automatically fixes formatting and simple linting issues
3. **Surface Manual Issues Early**: Identifies issues that need human attention before PR creation
4. **Maintain Code Quality**: Enforces consistent code style across the repository

## Integration with Existing CI

DocuElevate has two workflows that handle ruff:

1. **`.github/workflows/ci.yml`** (Lint Job)
   - Runs `ruff check` (without --fix) on all pushes and PRs
   - Fails CI if issues are found
   - Runs early in the pipeline to catch style issues before tests

2. **`.github/workflows/ruff-auto-fix.yml`**
   - Runs on PRs when Python files change
   - Automatically applies `ruff --fix` and `ruff format`
   - Commits fixes back to the PR branch
   - Posts a comment notifying the author

This agent script ensures that most issues are caught and fixed **before** the PR is created, reducing the need for the auto-fix workflow to intervene.

## Local Development

Developers should also use this script or set up pre-commit hooks:

```bash
# Install pre-commit hooks (recommended)
pip install pre-commit
pre-commit install

# Or run manually before committing
./scripts/run-ruff-and-fix.sh
```

## Troubleshooting

### Script fails with "ruff: command not found"

The script installs ruff automatically. If this fails:
```bash
pip install ruff
```

### Script fails with Git errors

Ensure you're in a Git repository with proper configuration:
```bash
git config user.name "Your Name"
git config user.email "your.email@example.com"
```

### Ruff issues remain after --fix

Some issues cannot be auto-fixed (e.g., unused imports, complex logic issues). These require manual resolution:
1. Review the ruff output
2. Fix the issues manually
3. Run the script again to verify

## Configuration

Ruff configuration is in `pyproject.toml` under `[tool.ruff]` and `[tool.ruff.lint]`.

Default settings:
- Line length: 120 characters
- Target Python version: 3.11+
- Enabled rules: Pyflakes (F), pycodestyle (E, W), isort (I), bandit (S), flake8-bugbear (B), pylint (PL)

## Questions?

See the [Contributing Guide](CONTRIBUTING.md) for more information on code quality standards and development workflow.
