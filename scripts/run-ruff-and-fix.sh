#!/usr/bin/env bash
set -euo pipefail

# Script for local/agent use before creating a PR.
# Installs ruff, checks, tries --fix, commits fixes, and fails if issues remain.

echo "Installing ruff..."
python -m pip install --upgrade pip --quiet
pip install ruff --quiet

echo "Running ruff check..."
if ruff check app/ tests/; then
  echo "✅ ruff: no issues found"
  exit 0
else
  echo "⚠️  ruff: issues found — running ruff --fix"
  ruff check app/ tests/ --fix
  
  # Check if there are any changes to commit
  git add -A
  if git diff --staged --quiet; then
    echo "ℹ️  No staged changes after ruff --fix"
  else
    git commit -m "style: ruff auto-fixes" || true
    echo "✅ Committed ruff fixes"
  fi
  
  echo "Re-running ruff check after fixes..."
  if ruff check app/ tests/; then
    echo "✅ ruff: all issues fixed"
    exit 0
  else
    echo "❌ ruff: issues remain after auto-fix" >&2
    echo ""
    echo "The following issues could not be auto-fixed and require manual intervention:"
    echo ""
    ruff check app/ tests/
    exit 1
  fi
fi
