"""Tests for scripts/check_alembic_migrations.py."""

# The script lives outside of the ``app`` package, so we import it by path.
import importlib.util
import textwrap
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_alembic_migrations.py"
_spec = importlib.util.spec_from_file_location("check_alembic_migrations", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

check_migrations = _mod.check_migrations
main = _mod.main


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_migration(
    directory: Path, filename: str, revision: str, down_revision: str | tuple[str, ...] | None
) -> Path:
    """Helper to create a minimal migration file."""
    if down_revision is None:
        down_rev_str = "None"
    elif isinstance(down_revision, tuple):
        down_rev_str = repr(down_revision)
    else:
        down_rev_str = f'"{down_revision}"'

    content = textwrap.dedent(f'''\
        """Test migration."""
        from typing import Union
        revision: str = "{revision}"
        down_revision: Union[str, None] = {down_rev_str}
        depends_on: Union[str, None] = None
        def upgrade() -> None:
            pass
        def downgrade() -> None:
            pass
    ''')
    path = directory / filename
    path.write_text(content)
    return path


@pytest.fixture
def versions_dir(tmp_path: Path) -> Path:
    """Return a temporary versions directory."""
    d = tmp_path / "versions"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckMigrations:
    """Tests for the check_migrations function."""

    def test_valid_linear_chain(self, versions_dir: Path) -> None:
        """A simple linear chain should pass with no errors."""
        _write_migration(versions_dir, "001_initial.py", "001_initial", None)
        _write_migration(versions_dir, "002_add_col.py", "002_add_col", "001_initial")
        _write_migration(versions_dir, "003_add_table.py", "003_add_table", "002_add_col")

        errors = check_migrations(versions_dir)
        assert errors == []

    def test_valid_merge_migration(self, versions_dir: Path) -> None:
        """A chain with a merge point should pass."""
        _write_migration(versions_dir, "001_base.py", "001_base", None)
        _write_migration(versions_dir, "002_a.py", "002_a", "001_base")
        _write_migration(versions_dir, "002_b.py", "002_b", "001_base")

        # Merge file with tuple down_revision
        content = textwrap.dedent('''\
            """Merge."""
            from typing import Union
            revision: str = "003_merge"
            down_revision: Union[str, tuple] = ("002_a", "002_b")
            depends_on: Union[str, None] = None
            def upgrade() -> None:
                pass
            def downgrade() -> None:
                pass
        ''')
        (versions_dir / "003_merge.py").write_text(content)

        errors = check_migrations(versions_dir)
        assert errors == []

    def test_multiple_heads_detected(self, versions_dir: Path) -> None:
        """Two unmerged branches should report multiple heads."""
        _write_migration(versions_dir, "001_base.py", "001_base", None)
        _write_migration(versions_dir, "002_a.py", "002_a", "001_base")
        _write_migration(versions_dir, "002_b.py", "002_b", "001_base")

        errors = check_migrations(versions_dir)
        assert len(errors) == 1
        assert "Multiple migration heads" in errors[0]
        assert "002_a" in errors[0]
        assert "002_b" in errors[0]

    def test_broken_down_revision(self, versions_dir: Path) -> None:
        """A migration pointing to a non-existent parent should be flagged."""
        _write_migration(versions_dir, "001_base.py", "001_base", None)
        _write_migration(versions_dir, "002_orphan.py", "002_orphan", "NONEXISTENT")

        errors = check_migrations(versions_dir)
        assert any("Broken chain" in e for e in errors)
        assert any("NONEXISTENT" in e for e in errors)

    def test_duplicate_revision(self, versions_dir: Path) -> None:
        """Two files declaring the same revision should be flagged."""
        _write_migration(versions_dir, "001_base.py", "001_base", None)
        _write_migration(versions_dir, "002_first.py", "002_dup", "001_base")
        _write_migration(versions_dir, "002_second.py", "002_dup", "001_base")

        errors = check_migrations(versions_dir)
        assert any("Duplicate revision" in e for e in errors)

    def test_filename_mismatch(self, versions_dir: Path) -> None:
        """A file whose revision doesn't match its filename should be flagged."""
        _write_migration(versions_dir, "001_base.py", "001_base", None)
        # filename stem is "002_wrong_name" but revision says "002_correct_name"
        _write_migration(versions_dir, "002_wrong_name.py", "002_correct_name", "001_base")

        errors = check_migrations(versions_dir)
        assert any("Filename mismatch" in e for e in errors)

    def test_empty_directory(self, versions_dir: Path) -> None:
        """An empty versions directory should report an error."""
        errors = check_migrations(versions_dir)
        assert len(errors) == 1
        assert "No migration files found" in errors[0]

    def test_init_py_is_skipped(self, versions_dir: Path) -> None:
        """__init__.py files should be ignored."""
        (versions_dir / "__init__.py").write_text("")
        _write_migration(versions_dir, "001_base.py", "001_base", None)

        errors = check_migrations(versions_dir)
        assert errors == []

    def test_non_migration_file_skipped(self, versions_dir: Path) -> None:
        """A .py file without a revision variable should be silently skipped."""
        (versions_dir / "helper.py").write_text("# just a helper\nx = 1\n")
        _write_migration(versions_dir, "001_base.py", "001_base", None)

        errors = check_migrations(versions_dir)
        assert errors == []


@pytest.mark.unit
class TestMainCLI:
    """Tests for the CLI entry-point."""

    def test_success_returns_zero(self, versions_dir: Path) -> None:
        """Valid chain should exit 0."""
        _write_migration(versions_dir, "001_base.py", "001_base", None)
        rc = main(["--versions-dir", str(versions_dir)])
        assert rc == 0

    def test_failure_returns_one(self, versions_dir: Path) -> None:
        """Invalid chain should exit 1."""
        _write_migration(versions_dir, "001_base.py", "001_base", None)
        _write_migration(versions_dir, "002_a.py", "002_a", "001_base")
        _write_migration(versions_dir, "002_b.py", "002_b", "001_base")

        rc = main(["--versions-dir", str(versions_dir)])
        assert rc == 1

    def test_missing_directory_returns_two(self, tmp_path: Path) -> None:
        """Non-existent versions directory should exit 2."""
        rc = main(["--versions-dir", str(tmp_path / "does_not_exist")])
        assert rc == 2

    def test_verbose_flag(self, versions_dir: Path) -> None:
        """The --verbose flag should not crash."""
        _write_migration(versions_dir, "001_base.py", "001_base", None)
        rc = main(["--versions-dir", str(versions_dir), "--verbose"])
        assert rc == 0

    def test_real_migrations(self) -> None:
        """Smoke test against the actual project migrations."""
        real_dir = Path(__file__).resolve().parent.parent / "migrations" / "versions"
        if not real_dir.is_dir():
            pytest.skip("migrations/versions directory not found in working tree")
        rc = main(["--versions-dir", str(real_dir)])
        assert rc == 0
