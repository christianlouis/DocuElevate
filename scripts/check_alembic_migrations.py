#!/usr/bin/env python3
"""Validate Alembic migration chain integrity.

This script checks the migration files in ``migrations/versions/`` for
common problems that arise when multiple feature branches add migrations
in parallel and then get merged into *main*.

Checks performed
~~~~~~~~~~~~~~~~
1. **Multiple heads** – more than one migration without a child means the
   chain has diverged and a merge migration is needed.
2. **Broken down-revision references** – a migration points to a
   ``down_revision`` that does not exist.
3. **Duplicate revision IDs** – two files declare the same ``revision``.
4. **Revision / filename mismatch** – the ``revision`` variable inside a
   file does not match the stem of the filename (minus the numeric
   prefix).

Exit codes
~~~~~~~~~~
* **0** – all checks passed.
* **1** – one or more problems detected (details printed to *stderr*).
* **2** – unexpected runtime error.

Usage::

    python scripts/check_alembic_migrations.py          # from repo root
    python scripts/check_alembic_migrations.py --verbose # extra detail
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REVISION_RE = re.compile(r'^revision\s*(?::\s*str\s*)?=\s*["\'](.+?)["\']', re.MULTILINE)
_DOWN_REV_RE = re.compile(
    r"^down_revision\s*(?::\s*Union\[str,\s*(?:None|tuple)\]\s*)?=\s*(.+)",
    re.MULTILINE,
)


def _parse_down_revision(raw: str) -> list[str] | None:
    """Parse a ``down_revision`` value into a list of parent revisions.

    Returns ``None`` for the root migration (``down_revision = None``).
    Returns a list with one or more strings otherwise.  Tuples are
    returned for merge migrations (e.g. ``("017_a", "017_b")``).
    """
    raw = raw.strip().rstrip("#").strip()
    # Handle inline comments
    if "#" in raw:
        raw = raw[: raw.index("#")].strip()
    try:
        value = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return [raw.strip("\"' ")]

    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, (tuple, list)):
        return [str(v) for v in value]
    return [str(value)]


def _parse_migration(path: Path) -> dict | None:
    """Extract ``revision`` and ``down_revision`` from a migration file."""
    text = path.read_text(encoding="utf-8")

    rev_match = _REVISION_RE.search(text)
    down_match = _DOWN_REV_RE.search(text)

    if not rev_match:
        return None  # not a valid migration file

    revision = rev_match.group(1)
    down_revision = _parse_down_revision(down_match.group(1)) if down_match else None

    return {
        "path": path,
        "revision": revision,
        "down_revision": down_revision,
    }


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_migrations(versions_dir: Path, *, verbose: bool = False) -> list[str]:
    """Run all migration-chain checks and return a list of error messages."""
    errors: list[str] = []

    # Collect all migrations ------------------------------------------------
    migrations: dict[str, dict] = {}
    py_files = sorted(versions_dir.glob("*.py"))
    if not py_files:
        errors.append(f"No migration files found in {versions_dir}")
        return errors

    for path in py_files:
        if path.name == "__init__.py":
            continue
        info = _parse_migration(path)
        if info is None:
            if verbose:
                print(f"  SKIP {path.name} (no revision found)", file=sys.stderr)
            continue
        rev = info["revision"]

        # Check 1 – duplicate revision IDs
        if rev in migrations:
            errors.append(f"Duplicate revision '{rev}' in:\n  - {migrations[rev]['path'].name}\n  - {path.name}")
        else:
            migrations[rev] = info

        if verbose:
            parents = info["down_revision"] or ["(root)"]
            print(f"  {rev}  ←  {', '.join(parents)}", file=sys.stderr)

    # Build child map -------------------------------------------------------
    all_revisions = set(migrations.keys())
    children: dict[str, list[str]] = {rev: [] for rev in all_revisions}

    for rev, info in migrations.items():
        parents = info["down_revision"]
        if parents is None:
            continue
        for parent in parents:
            # Check 2 – broken down_revision references
            if parent not in all_revisions:
                errors.append(
                    f"Broken chain: '{rev}' ({info['path'].name}) references "
                    f"down_revision '{parent}' which does not exist."
                )
            else:
                children[parent].append(rev)

    # Check 3 – multiple heads (revisions with no children) -----------------
    heads = [rev for rev, kids in children.items() if not kids]
    if len(heads) > 1:
        head_details = "\n".join(f"  - {h} ({migrations[h]['path'].name})" for h in sorted(heads))
        errors.append(
            f"Multiple migration heads detected ({len(heads)}).  "
            f"Create a merge migration to resolve:\n{head_details}\n\n"
            f'  Fix: alembic merge heads -m "merge_parallel_branches"'
        )

    # Check 4 – revision / filename consistency -----------------------------
    for rev, info in migrations.items():
        stem = info["path"].stem  # e.g. "017_add_pipelines"
        if rev != stem:
            errors.append(
                f"Filename mismatch: file '{info['path'].name}' declares "
                f"revision='{rev}' but filename stem is '{stem}'."
            )

    return errors


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry-point.  Returns 0 on success, 1 on failure, 2 on error."""
    parser = argparse.ArgumentParser(description="Check Alembic migration chain integrity.")
    parser.add_argument(
        "--versions-dir",
        type=Path,
        default=Path("migrations/versions"),
        help="Path to Alembic versions directory (default: migrations/versions)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Print extra diagnostic info")
    args = parser.parse_args(argv)

    if not args.versions_dir.is_dir():
        print(f"ERROR: versions directory not found: {args.versions_dir}", file=sys.stderr)
        return 2

    if args.verbose:
        print("Scanning migrations…", file=sys.stderr)

    errors = check_migrations(args.versions_dir, verbose=args.verbose)

    if errors:
        print(f"\n{'=' * 60}", file=sys.stderr)
        print(f"  Migration chain problems found: {len(errors)}", file=sys.stderr)
        print(f"{'=' * 60}\n", file=sys.stderr)
        for i, err in enumerate(errors, 1):
            print(f"  [{i}] {err}\n", file=sys.stderr)
        return 1

    print("✓ Migration chain is valid.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
