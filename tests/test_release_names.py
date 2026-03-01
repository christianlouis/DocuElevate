"""Tests for release naming functionality in app/config.py and app/views/status.py."""

import json
import os
from unittest.mock import Mock, patch

import pytest


@pytest.mark.unit
class TestReleaseNameProperty:
    """Tests for the Settings.release_name property."""

    def test_release_name_returns_codename_for_minor_prefix(self, tmp_path):
        """Test release_name returns codename matching minor version prefix."""
        release_data = {
            "releases": {
                "0.5": {"codename": "Foundation", "description": "Core platform"},
            }
        }
        release_file = tmp_path / "release_names.json"
        release_file.write_text(json.dumps(release_data))

        from app.config import Settings

        s = Settings.__new__(Settings)
        with (
            patch.object(type(s), "version", new_callable=lambda: property(lambda self: "0.5.3")),
            patch("app.config.os.path.dirname"),
            patch("app.config.os.path.join", return_value=str(release_file)),
            patch("app.config.os.path.exists", return_value=True),
        ):
            result = s.release_name
            assert result == "Foundation"

    def test_release_name_returns_codename_for_exact_match(self, tmp_path):
        """Test release_name returns codename for exact version match."""
        release_data = {
            "releases": {
                "1.0.0": {"codename": "Summit"},
            }
        }
        release_file = tmp_path / "release_names.json"
        release_file.write_text(json.dumps(release_data))

        from app.config import Settings

        s = Settings.__new__(Settings)
        with (
            patch.object(type(s), "version", new_callable=lambda: property(lambda self: "1.0.0")),
            patch("app.config.os.path.dirname"),
            patch("app.config.os.path.join", return_value=str(release_file)),
            patch("app.config.os.path.exists", return_value=True),
        ):
            result = s.release_name
            assert result == "Summit"

    def test_release_name_returns_none_when_no_match(self, tmp_path):
        """Test release_name returns None when version has no codename."""
        release_data = {
            "releases": {
                "0.5": {"codename": "Foundation"},
            }
        }
        release_file = tmp_path / "release_names.json"
        release_file.write_text(json.dumps(release_data))

        from app.config import Settings

        s = Settings.__new__(Settings)
        with (
            patch.object(type(s), "version", new_callable=lambda: property(lambda self: "0.9.1")),
            patch("app.config.os.path.dirname"),
            patch("app.config.os.path.join", return_value=str(release_file)),
            patch("app.config.os.path.exists", return_value=True),
        ):
            result = s.release_name
            assert result is None

    def test_release_name_returns_none_when_file_missing(self):
        """Test release_name returns None when release_names.json doesn't exist."""
        from app.config import Settings

        s = Settings.__new__(Settings)
        with (
            patch.object(type(s), "version", new_callable=lambda: property(lambda self: "0.5.0")),
            patch("app.config.os.path.dirname"),
            patch("app.config.os.path.join", return_value="/nonexistent/release_names.json"),
            patch("app.config.os.path.exists", return_value=False),
        ):
            result = s.release_name
            assert result is None

    def test_release_name_returns_none_for_unknown_version(self):
        """Test release_name returns None when version is 'unknown'."""
        from app.config import Settings

        s = Settings.__new__(Settings)
        with patch.object(type(s), "version", new_callable=lambda: property(lambda self: "unknown")):
            result = s.release_name
            assert result is None

    def test_release_name_returns_none_for_empty_version(self):
        """Test release_name returns None when version is empty."""
        from app.config import Settings

        s = Settings.__new__(Settings)
        with patch.object(type(s), "version", new_callable=lambda: property(lambda self: "")):
            result = s.release_name
            assert result is None

    def test_release_name_handles_invalid_json(self, tmp_path):
        """Test release_name handles corrupt JSON gracefully."""
        release_file = tmp_path / "release_names.json"
        release_file.write_text("{invalid json")

        from app.config import Settings

        s = Settings.__new__(Settings)
        with (
            patch.object(type(s), "version", new_callable=lambda: property(lambda self: "0.5.0")),
            patch("app.config.os.path.dirname"),
            patch("app.config.os.path.join", return_value=str(release_file)),
            patch("app.config.os.path.exists", return_value=True),
        ):
            result = s.release_name
            assert result is None

    def test_release_name_handles_missing_releases_key(self, tmp_path):
        """Test release_name handles JSON without 'releases' key."""
        release_file = tmp_path / "release_names.json"
        release_file.write_text(json.dumps({"something_else": {}}))

        from app.config import Settings

        s = Settings.__new__(Settings)
        with (
            patch.object(type(s), "version", new_callable=lambda: property(lambda self: "0.5.0")),
            patch("app.config.os.path.dirname"),
            patch("app.config.os.path.join", return_value=str(release_file)),
            patch("app.config.os.path.exists", return_value=True),
        ):
            result = s.release_name
            assert result is None

    def test_release_name_prefers_exact_over_minor(self, tmp_path):
        """Test release_name prefers exact version match over minor prefix."""
        release_data = {
            "releases": {
                "0.5.0": {"codename": "ExactMatch"},
                "0.5": {"codename": "MinorMatch"},
            }
        }
        release_file = tmp_path / "release_names.json"
        release_file.write_text(json.dumps(release_data))

        from app.config import Settings

        s = Settings.__new__(Settings)
        with (
            patch.object(type(s), "version", new_callable=lambda: property(lambda self: "0.5.0")),
            patch("app.config.os.path.dirname"),
            patch("app.config.os.path.join", return_value=str(release_file)),
            patch("app.config.os.path.exists", return_value=True),
        ):
            result = s.release_name
            assert result == "ExactMatch"


@pytest.mark.unit
class TestReleaseNameInStatusView:
    """Tests for release name display in status dashboard."""

    @patch("app.views.status.get_provider_status")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @patch("app.views.status.os.path.exists")
    @pytest.mark.asyncio
    async def test_status_dashboard_includes_release_name(
        self, mock_exists, mock_settings, mock_templates, mock_providers
    ):
        """Test status dashboard passes release_name to template context."""
        from app.views.status import status_dashboard

        mock_exists.return_value = False
        mock_providers.return_value = {}
        mock_settings.version = "0.5.3"
        mock_settings.build_date = "2024-01-01"
        mock_settings.debug = False
        mock_settings.git_sha = "abc123"
        mock_settings.notification_urls = []
        mock_settings.release_name = "Foundation"

        mock_request = Mock()
        await status_dashboard(mock_request)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["release_name"] == "Foundation"

    @patch("app.views.status.get_provider_status")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @patch("app.views.status.os.path.exists")
    @pytest.mark.asyncio
    async def test_status_dashboard_handles_missing_release_name(
        self, mock_exists, mock_settings, mock_templates, mock_providers
    ):
        """Test status dashboard handles missing release_name attribute gracefully."""
        from app.views.status import status_dashboard

        mock_exists.return_value = False
        mock_providers.return_value = {}
        mock_settings.version = "0.9.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.debug = False
        mock_settings.git_sha = "abc123"
        mock_settings.notification_urls = []
        # Simulate settings without release_name attribute
        del mock_settings.release_name

        mock_request = Mock()
        await status_dashboard(mock_request)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["release_name"] is None


@pytest.mark.unit
class TestReleaseNamesJson:
    """Tests for the release_names.json data file."""

    def test_release_names_json_is_valid(self):
        """Test that release_names.json is valid JSON."""
        release_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "release_names.json")
        with open(release_file, "r") as f:
            data = json.load(f)

        assert "releases" in data
        assert isinstance(data["releases"], dict)

    def test_release_names_json_entries_have_codename(self):
        """Test that all entries in release_names.json have a codename."""
        release_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "release_names.json")
        with open(release_file, "r") as f:
            data = json.load(f)

        for version, entry in data["releases"].items():
            assert "codename" in entry, f"Missing codename for version {version}"
            assert isinstance(entry["codename"], str), f"Codename for {version} must be a string"
            assert len(entry["codename"]) > 0, f"Codename for {version} must not be empty"

    def test_release_names_json_codenames_are_unique(self):
        """Test that all codenames in release_names.json are unique."""
        release_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "release_names.json")
        with open(release_file, "r") as f:
            data = json.load(f)

        codenames = [entry["codename"] for entry in data["releases"].values()]
        assert len(codenames) == len(set(codenames)), "Codenames must be unique"
