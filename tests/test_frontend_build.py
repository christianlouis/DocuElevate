"""Tests for frontend build configuration and Docker build consistency.

Validates that the frontend build toolchain (Tailwind CSS) is correctly
configured in package.json and that the Dockerfile installs all required
dependencies for the build step.
"""

import json
import re
from pathlib import Path

import pytest

# Resolve the project root from the test file location
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DOCKERFILE_PATH = PROJECT_ROOT / "Dockerfile"


@pytest.mark.unit
class TestFrontendPackageJson:
    """Validate frontend/package.json structure and scripts."""

    def test_package_json_exists(self) -> None:
        """package.json must exist in the frontend directory."""
        pkg_path = FRONTEND_DIR / "package.json"
        assert pkg_path.exists(), "frontend/package.json not found"

    def test_package_json_is_valid_json(self) -> None:
        """package.json must be parseable JSON."""
        pkg_path = FRONTEND_DIR / "package.json"
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), "package.json must be a JSON object"

    def test_build_script_defined(self) -> None:
        """A 'build' script must be defined in package.json."""
        pkg_path = FRONTEND_DIR / "package.json"
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})
        assert "build" in scripts, "Missing 'build' script in package.json"

    def test_build_script_uses_tailwindcss(self) -> None:
        """The build script must invoke the tailwindcss CLI."""
        pkg_path = FRONTEND_DIR / "package.json"
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        build_cmd = data["scripts"]["build"]
        assert "tailwindcss" in build_cmd, f"Build script does not reference tailwindcss: {build_cmd}"

    def test_tailwindcss_listed_as_dependency(self) -> None:
        """tailwindcss must be listed in dependencies or devDependencies."""
        pkg_path = FRONTEND_DIR / "package.json"
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        deps = data.get("dependencies", {})
        dev_deps = data.get("devDependencies", {})
        all_deps = {**deps, **dev_deps}
        assert "tailwindcss" in all_deps, "tailwindcss is not listed in dependencies or devDependencies"


@pytest.mark.unit
class TestFrontendBuildAssets:
    """Validate that required frontend build source files exist."""

    def test_input_css_exists(self) -> None:
        """The Tailwind CSS input file must exist."""
        input_css = FRONTEND_DIR / "input.css"
        assert input_css.exists(), "frontend/input.css not found"

    def test_input_css_has_tailwind_directives(self) -> None:
        """input.css must include Tailwind CSS directives."""
        input_css = FRONTEND_DIR / "input.css"
        content = input_css.read_text(encoding="utf-8")
        assert "@tailwind base" in content, "Missing @tailwind base directive"
        assert "@tailwind components" in content, "Missing @tailwind components directive"
        assert "@tailwind utilities" in content, "Missing @tailwind utilities directive"

    def test_tailwind_config_exists(self) -> None:
        """tailwind.config.js must exist in the frontend directory."""
        config_path = FRONTEND_DIR / "tailwind.config.js"
        assert config_path.exists(), "frontend/tailwind.config.js not found"

    def test_package_lock_exists(self) -> None:
        """package-lock.json must exist for reproducible installs."""
        lock_path = FRONTEND_DIR / "package-lock.json"
        assert lock_path.exists(), "frontend/package-lock.json not found"


@pytest.mark.unit
class TestDockerfileFrontendBuilder:
    """Validate the Dockerfile frontend-builder stage installs build dependencies."""

    def test_dockerfile_exists(self) -> None:
        """Production Dockerfile must exist at the project root."""
        assert DOCKERFILE_PATH.exists(), "Dockerfile not found at project root"

    def test_dockerfile_has_frontend_builder_stage(self) -> None:
        """Dockerfile must define a frontend-builder stage."""
        content = DOCKERFILE_PATH.read_text(encoding="utf-8")
        assert "AS frontend-builder" in content, "Dockerfile does not define a frontend-builder stage"

    def test_dockerfile_npm_ci_does_not_omit_dev(self) -> None:
        """npm ci must NOT use --omit=dev in the frontend-builder stage.

        The tailwindcss CLI is a devDependency required at build time.
        Using --omit=dev would skip installing it, causing the build to
        fail with 'tailwindcss: not found'.
        """
        content = DOCKERFILE_PATH.read_text(encoding="utf-8")

        # Extract the frontend-builder stage content
        # Look for the stage start and the next stage (or end of file)
        stage_pattern = re.compile(
            r"FROM\s+\S+\s+AS\s+frontend-builder\b(.*?)(?=FROM\s|\Z)",
            re.DOTALL,
        )
        match = stage_pattern.search(content)
        assert match is not None, "Could not find frontend-builder stage in Dockerfile"

        stage_content = match.group(1)
        assert "--omit=dev" not in stage_content, (
            "Dockerfile frontend-builder stage uses 'npm ci --omit=dev' which "
            "excludes tailwindcss (a devDependency) needed for the build step. "
            "Use 'npm ci' instead to install all dependencies."
        )

    def test_dockerfile_runs_npm_build(self) -> None:
        """Dockerfile frontend-builder stage must run npm run build."""
        content = DOCKERFILE_PATH.read_text(encoding="utf-8")

        stage_pattern = re.compile(
            r"FROM\s+\S+\s+AS\s+frontend-builder\b(.*?)(?=FROM\s|\Z)",
            re.DOTALL,
        )
        match = stage_pattern.search(content)
        assert match is not None, "Could not find frontend-builder stage in Dockerfile"

        stage_content = match.group(1)
        assert "npm run build" in stage_content, "Dockerfile frontend-builder stage does not run 'npm run build'"

    def test_dockerfile_copies_compiled_css(self) -> None:
        """Dockerfile must copy the compiled styles.css from the frontend-builder stage."""
        content = DOCKERFILE_PATH.read_text(encoding="utf-8")
        assert "COPY --from=frontend-builder" in content, (
            "Dockerfile does not copy assets from the frontend-builder stage"
        )
        assert "styles.css" in content, "Dockerfile does not reference the compiled styles.css"
