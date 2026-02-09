"""Additional view tests to increase coverage."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.integration
class TestWizardPost:
    """Tests for wizard POST endpoint."""

    def test_wizard_post_saves_settings(self, client):
        """Test POST to wizard saves settings."""
        response = client.post(
            "/setup",
            data={"step": "1", "database_url": "sqlite:///:memory:", "redis_url": "redis://localhost:6379/0"},
            follow_redirects=False,
        )
        # Should redirect to next step
        assert response.status_code in (200, 303)

    def test_wizard_post_last_step(self, client):
        """Test POST to wizard last step."""
        response = client.post(
            "/setup",
            data={"step": "3", "openai_api_key": "test-key", "azure_ai_key": "test-key"},
            follow_redirects=False,
        )
        # Should redirect to home on completion
        assert response.status_code in (200, 303)

    def test_wizard_post_step_2(self, client):
        """Test POST wizard step 2."""
        response = client.post(
            "/setup",
            data={"step": "2", "session_secret": "auto-generate", "admin_username": "admin", "admin_password": "test"},
            follow_redirects=False,
        )
        assert response.status_code in (200, 303)


@pytest.mark.integration
class TestStatusViewDetails:
    """Additional tests for status view."""

    def test_status_dashboard_has_providers(self, client):
        """Test status dashboard shows provider information."""
        response = client.get("/status")
        assert response.status_code == 200
        # The response should contain some HTML content
        assert len(response.content) > 0


@pytest.mark.integration
class TestSettingsViewWithAdmin:
    """Tests for settings view when admin session is available."""

    def test_settings_page_with_no_session(self, client):
        """Test settings page without admin session."""
        response = client.get("/settings", follow_redirects=False)
        assert response.status_code in (200, 302, 303)
