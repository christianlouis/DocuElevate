"""Integration coverage for release tag to image version resolution."""

import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()  # noqa: S603, S607


def _commit(repo: Path, message: str, filename: str) -> str:
    (repo / filename).write_text(message, encoding="utf-8")
    _git(repo, "add", filename)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "ci@example.invalid")
    _git(repo, "config", "user.name", "CI")
    return repo


@pytest.mark.integration
def test_release_version_matches_tag_created_for_merge_commit(git_repo: Path):
    _commit(git_repo, "initial", "VERSION")
    merge_sha = _commit(git_repo, "fix: searchable documents", "feature.txt")
    _commit(git_repo, "chore(release): 1.2.3", "CHANGELOG.md")
    _git(git_repo, "tag", "-a", "v1.2.3", "-m", "v1.2.3")
    _commit(git_repo, "newer metadata commit", "BUILD_DATE")

    script = Path(__file__).parents[1] / "scripts" / "resolve_release_version.sh"
    version = subprocess.check_output(  # noqa: S603
        ["/bin/bash", str(script), merge_sha[:8]], cwd=git_repo, text=True
    ).strip()

    assert version == "1.2.3"


@pytest.mark.integration
def test_release_version_is_empty_without_a_direct_release_child(git_repo: Path):
    unrelated_sha = _commit(git_repo, "docs: no release", "README.md")

    script = Path(__file__).parents[1] / "scripts" / "resolve_release_version.sh"
    version = subprocess.check_output(  # noqa: S603
        ["/bin/bash", str(script), unrelated_sha], cwd=git_repo, text=True
    ).strip()

    assert version == ""
