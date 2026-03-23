"""Tests for dark mode support.

Covers:
- ui_default_color_scheme setting in config
- Setting metadata entry in settings_service
- ui_default_color_scheme injected into template context via views/base.py
- base.html renders data-color-scheme-default attribute and toggle button
"""

import pytest

from app.config import settings
from app.utils.settings_service import SETTING_METADATA


@pytest.mark.unit
class TestDarkModeConfig:
    """Tests for the ui_default_color_scheme configuration field."""

    def test_default_is_system(self):
        """ui_default_color_scheme should default to 'system'."""
        assert settings.ui_default_color_scheme == "system"

    def test_valid_values_documented(self):
        """Setting metadata should list valid options."""
        meta = SETTING_METADATA.get("ui_default_color_scheme", {})
        assert "options" in meta
        assert set(meta["options"]) == {"system", "light", "dark"}

    def test_metadata_category(self):
        """Setting should belong to the 'UI' category."""
        meta = SETTING_METADATA.get("ui_default_color_scheme", {})
        assert meta.get("category") == "UI"

    def test_metadata_not_sensitive(self):
        """Color scheme preference is not a sensitive setting."""
        meta = SETTING_METADATA.get("ui_default_color_scheme", {})
        assert meta.get("sensitive") is False

    def test_metadata_no_restart_required(self):
        """Changing the color scheme should not require a restart."""
        meta = SETTING_METADATA.get("ui_default_color_scheme", {})
        assert meta.get("restart_required") is False


@pytest.mark.unit
class TestDarkModeTemplateInjection:
    """Tests for ui_default_color_scheme being injected into template context."""

    def test_default_injected_when_missing(self):
        """Wrapper should inject ui_default_color_scheme when absent from context."""
        from unittest.mock import MagicMock, patch

        from app.views.base import template_response_with_version

        captured = {}

        def fake_original(name, ctx, **kw):
            captured.update(ctx)

        with patch("app.views.base.original_template_response", side_effect=fake_original):
            mock_request = MagicMock()
            mock_request.state = MagicMock(spec=[])  # no csrf_token attr
            template_response_with_version("page.html", {"request": mock_request})

        assert "ui_default_color_scheme" in captured

    def test_existing_value_not_overridden(self):
        """Wrapper must NOT overwrite an explicitly supplied value."""
        from unittest.mock import MagicMock, patch

        from app.views.base import template_response_with_version

        captured = {}

        def fake_original(name, ctx, **kw):
            captured.update(ctx)

        with patch("app.views.base.original_template_response", side_effect=fake_original):
            mock_request = MagicMock()
            mock_request.state = MagicMock(spec=[])
            template_response_with_version(
                "page.html",
                {"request": mock_request, "ui_default_color_scheme": "dark"},
            )

        assert captured["ui_default_color_scheme"] == "dark"


@pytest.mark.integration
class TestDarkModeHtml:
    """Integration tests verifying the rendered HTML contains dark mode elements."""

    def test_about_page_contains_color_scheme_attribute(self, client):
        """The <html> element should carry a data-color-scheme-default attribute."""
        response = client.get("/about")
        assert response.status_code == 200
        assert b"data-color-scheme-default=" in response.content

    def test_about_page_contains_dark_mode_toggle(self, client):
        """The navbar should contain a dark mode toggle button."""
        response = client.get("/about")
        assert response.status_code == 200
        assert b"darkModeToggle" in response.content

    def test_about_page_contains_anti_flash_script(self, client):
        """The page should include the anti-flash colour scheme detection script."""
        response = client.get("/about")
        assert response.status_code == 200
        assert b"colorScheme" in response.content
        assert b"prefers-color-scheme" in response.content

    def test_about_page_contains_toggle_dark_mode_function(self, client):
        """The page should reference toggleDarkMode via common.js."""
        response = client.get("/about")
        assert response.status_code == 200
        assert b"toggleDarkMode" in response.content
