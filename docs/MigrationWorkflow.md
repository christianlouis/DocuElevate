# Migration Workflow

This guide explains how to create, test, and merge Alembic database migrations in DocuElevate — especially when **multiple feature branches** add migrations in parallel.

## Table of Contents

- [Quick Reference](#quick-reference)
- [Creating a New Migration](#creating-a-new-migration)
- [Migration Naming Convention](#migration-naming-convention)
- [Idempotent Migration Patterns](#idempotent-migration-patterns)
- [Parallel Branch Development](#parallel-branch-development)
- [Resolving Migration Conflicts](#resolving-migration-conflicts)
- [CI Validation](#ci-validation)
- [Pre-commit Hook](#pre-commit-hook)
- [Troubleshooting](#troubleshooting)

---

## Quick Reference

```bash
# Create a new migration after editing app/models.py
alembic revision --autogenerate -m "add_foobar_column"

# Apply all pending migrations
alembic upgrade head

# Check current database version
alembic current

# View migration history
alembic history --verbose

# Detect multiple heads (diverged branches)
alembic heads

# Create a merge migration to resolve multiple heads
alembic merge heads -m "merge_parallel_branches"

# Validate migration chain integrity (CI script)
python scripts/check_alembic_migrations.py
python scripts/check_alembic_migrations.py --verbose
```

---

## Creating a New Migration

1. **Edit `app/models.py`** — add or modify SQLAlchemy model classes.

2. **Generate the migration** from the repo root.  Use `--rev-id` to set the
   revision identifier directly (avoids renaming afterwards):

   ```bash
   alembic revision --autogenerate --rev-id 037_add_my_new_table -m "add my new table"
   ```

   This creates `migrations/versions/037_add_my_new_table_add_my_new_table.py`
   with `revision = "037_add_my_new_table"`.  Rename the file to match:

   ```bash
   mv migrations/versions/037_add_my_new_table_add_my_new_table.py \
      migrations/versions/037_add_my_new_table.py
   ```

   Alternatively, generate with the default hash and then rename:

   ```bash
   alembic revision --autogenerate -m "add_my_new_table"
   # Rename: mv migrations/versions/<hash>_add_my_new_table.py migrations/versions/037_add_my_new_table.py
   # Update revision inside the file to match the filename stem.
   ```

   Alembic uses the `migrations/script.py.mako` template to generate the file.  The template includes inline comments about idempotent patterns — read them.

3. **Review the generated code** — autogenerate is helpful but not perfect.  Check:
   - Are new tables and columns detected correctly?
   - Does the `downgrade()` reverse all changes?
   - Are SQLite-incompatible operations wrapped in `batch_alter_table()`?

4. **Test the migration** against a fresh database:

   ```bash
   # Apply
   alembic upgrade head

   # Rollback
   alembic downgrade -1

   # Re-apply
   alembic upgrade head
   ```

5. **Run the chain validation**:

   ```bash
   python scripts/check_alembic_migrations.py
   ```

---

## Migration Naming Convention

All migration files follow a **sequential numeric prefix** scheme:

```
NNN_short_description.py
```

| Component | Rule |
|-----------|------|
| `NNN` | Three-digit zero-padded number, incrementing from the previous migration |
| `short_description` | Lowercase snake_case summary of the change |

The **`revision`** variable inside the file **must match the filename stem** exactly:

```python
# File: migrations/versions/037_add_classification_rules.py
revision: str = "037_add_classification_rules"
down_revision: Union[str, None] = "036_add_document_translation_fields"
```

The CI check (`scripts/check_alembic_migrations.py`) enforces this consistency.

---

## Idempotent Migration Patterns

Migrations should be **idempotent** — safe to run even if the change already exists.  This is critical for SQLite compatibility and for recovering from partial failures.

### Add a Column (only if missing)

```python
def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "my_table" in inspector.get_table_names():
        existing = {c["name"] for c in inspector.get_columns("my_table")}
        if "new_col" not in existing:
            with op.batch_alter_table("my_table") as batch_op:
                batch_op.add_column(sa.Column("new_col", sa.String(128), nullable=True))
```

### Create a Table (only if missing)

```python
def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "new_table" not in inspector.get_table_names():
        op.create_table(
            "new_table",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
        )
```

### Drop a Column (only if present)

```python
def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "my_table" in inspector.get_table_names():
        existing = {c["name"] for c in inspector.get_columns("my_table")}
        if "new_col" in existing:
            with op.batch_alter_table("my_table") as batch_op:
                batch_op.drop_column("new_col")
```

### Use `batch_alter_table` for SQLite

SQLite does not support `ALTER TABLE DROP COLUMN` or `ALTER TABLE RENAME COLUMN` natively.  Alembic's `batch_alter_table` context manager works around this by recreating the table:

```python
with op.batch_alter_table("users") as batch_op:
    batch_op.add_column(sa.Column("phone", sa.String(20), nullable=True))
    batch_op.drop_column("fax")
```

---

## Parallel Branch Development

When two feature branches both add migrations from the same parent, the migration chain **diverges** into multiple heads.  This is normal and expected — Alembic supports it — but the heads must be merged before the code reaches `main`.

### Example

```
main:   001 → 002 → 003
                         ↘ Branch A: 004_add_widgets
                         ↘ Branch B: 004_add_gadgets   ← two heads!
```

### How to Avoid Conflicts

1. **Coordinate** — if two developers are both adding migrations, assign different sequence numbers (e.g., `037_` and `038_`).  Even if both depend on `036_`, different numbers prevent filename collisions.

2. **Rebase early** — before opening a PR, rebase your branch onto the latest `main`:

   ```bash
   git fetch origin main
   git rebase origin/main
   ```

   If `main` now has a new migration `037_*`, renumber yours to `038_*` and update `down_revision` to point at `037_*`.

3. **Check for multiple heads** locally:

   ```bash
   python scripts/check_alembic_migrations.py
   # or
   alembic heads
   ```

---

## Resolving Migration Conflicts

If your PR's CI check reports **"Multiple migration heads detected"**, follow these steps:

### Step 1 — Update Your Branch

```bash
git fetch origin main
git merge origin/main
# or
git rebase origin/main
```

### Step 2 — Check Heads

```bash
python scripts/check_alembic_migrations.py --verbose
```

The output lists the conflicting heads.

### Step 3 — Create a Merge Migration

```bash
alembic merge heads -m "merge_parallel_branches"
```

This generates a new migration with **two parents** (a merge point):

```python
down_revision = ("037_add_widgets", "037_add_gadgets")
```

### Step 4 — Rename and Validate

Rename the merge migration to the next sequence number:

```bash
mv migrations/versions/<hash>_merge_parallel_branches.py \
   migrations/versions/038_merge_parallel_branches.py
```

Update the `revision` inside to match, then validate:

```bash
python scripts/check_alembic_migrations.py
```

### Step 5 — Test

```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

---

## CI Validation

The CI pipeline (`.github/workflows/ci.yml`) includes a **migration-chain** job that runs:

```bash
python scripts/check_alembic_migrations.py
```

This script checks for:

| Check | Description |
|-------|-------------|
| Multiple heads | Diverged migration chains that need a merge migration |
| Broken references | A `down_revision` that points to a non-existent revision |
| Duplicate revisions | Two files declaring the same `revision` identifier |
| Filename mismatches | The `revision` variable doesn't match the filename stem |

The job runs in Stage 1 (fast-fail gates) alongside lint checks.  If it fails, the build is blocked until the migration chain is fixed.

---

## Pre-commit Hook

A local pre-commit hook is configured in `.pre-commit-config.yaml` that runs the same check whenever you commit a change to `migrations/versions/`:

```yaml
- repo: local
  hooks:
    - id: check-alembic-migrations
      name: Check Alembic migration chain
      entry: python scripts/check_alembic_migrations.py
      language: python
      pass_filenames: false
      files: ^migrations/versions/.*\.py$
```

Install the hook:

```bash
pip install pre-commit
pre-commit install
```

---

## Troubleshooting

### "Multiple migration heads detected"

See [Resolving Migration Conflicts](#resolving-migration-conflicts) above.

### "Broken chain: revision X references down_revision Y which does not exist"

You removed or renamed a migration that another migration depends on.  Either restore the missing file or update the dependent migration's `down_revision`.

### "Filename mismatch: file declares revision=X but filename stem is Y"

The `revision` string inside the Python file must match the filename (without `.py`).  Rename the file or update the variable.

### "relation already exists" when running `alembic upgrade head`

The database has a table that a pending migration tries to create.  Stamp the current state:

```bash
alembic stamp head
```

### Autogenerate doesn't detect my changes

Ensure all models are imported in `migrations/env.py`.  The `from app.models import ...` block at the top must include your new model class.

### SQLite "no such column" after downgrade

SQLite has limited `ALTER TABLE` support.  Always use `op.batch_alter_table()` for column operations on existing tables.

---

## Further Reading

- [Alembic Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Alembic Branch / Merge](https://alembic.sqlalchemy.org/en/latest/branches.html)
- [Database Configuration Guide](DatabaseConfiguration.md)
