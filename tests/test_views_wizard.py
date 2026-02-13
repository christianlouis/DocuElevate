"""Tests for app/views/wizard.py module."""

from unittest.mock import Mock, patch

import pytest


@pytest.mark.integration
class TestWizardViews:
    """Tests for wizard view routes."""

    def test_setup_wizard_step_1(self, client):
        """Test setup wizard first step."""
        response = client.get("/setup?step=1")
        assert response.status_code == 200

    def test_setup_wizard_step_2(self, client):
        """Test setup wizard second step."""
        response = client.get("/setup?step=2")
        assert response.status_code == 200

    def test_setup_wizard_step_3(self, client):
        """Test setup wizard third step."""
        response = client.get("/setup?step=3")
        assert response.status_code == 200

    def test_setup_wizard_invalid_step(self, client):
        """Test setup wizard with invalid step number."""
        response = client.get("/setup?step=0")
        assert response.status_code == 200

    def test_setup_wizard_high_step(self, client):
        """Test setup wizard with step higher than max."""
        response = client.get("/setup?step=999")
        assert response.status_code == 200

    def test_setup_wizard_skip(self, client):
        """Test skipping the setup wizard."""
        response = client.get("/setup/skip", follow_redirects=False)
        assert response.status_code in (200, 303)


@pytest.mark.integration
class TestWizardViewsPost:
    """Tests for wizard view POST routes."""

    @patch("app.views.wizard.save_setting_to_db")
    def test_setup_wizard_save_valid_data(self, mock_save, client):
        """Test saving valid wizard settings."""
        mock_save.return_value = True

        response = client.post(
            "/setup",
            data={
                "step": "1",
                "database_url": "sqlite:///test.db",
                "redis_url": "redis://localhost:6379/0",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "/setup?step=2" in response.headers["location"]
        # At least one save should have been called
        assert mock_save.call_count >= 1

    @patch("app.views.wizard.save_setting_to_db")
    def test_setup_wizard_save_empty_values_skipped(self, mock_save, client):
        """Test that empty values are skipped during save."""
        mock_save.return_value = True

        response = client.post(
            "/setup",
            data={
                "step": "1",
                "openai_api_key": "",  # Empty value should be skipped
                "azure_endpoint": "   ",  # Whitespace only should be skipped
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        # Should not have called save for empty values
        assert mock_save.call_count == 0

    @patch("app.views.wizard.save_setting_to_db")
    @patch("app.views.wizard.secrets.token_hex")
    def test_setup_wizard_auto_generate_session_secret(self, mock_token, mock_save, client):
        """Test auto-generation of session secret."""
        mock_token.return_value = "auto_generated_secret_token_12345678"
        mock_save.return_value = True

        response = client.post(
            "/setup",
            data={
                "step": "2",  # session_secret is in step 2
                "session_secret": "auto-generate",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        mock_token.assert_called_once_with(32)
        # Verify that the auto-generated token was saved
        mock_save.assert_called_once()
        call_args = mock_save.call_args[0]
        assert call_args[1] == "session_secret"
        assert call_args[2] == "auto_generated_secret_token_12345678"

    @patch("app.views.wizard.save_setting_to_db")
    def test_setup_wizard_save_last_step_redirects_home(self, mock_save, client):
        """Test that last step redirects to home."""
        mock_save.return_value = True

        # Step 3 is typically the last step
        response = client.post(
            "/setup",
            data={
                "step": "3",
                "some_setting": "value",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "/?setup=complete" in response.headers["location"]

    @patch("app.views.wizard.save_setting_to_db")
    def test_setup_wizard_save_failed_setting(self, mock_save, client):
        """Test handling when save_setting_to_db returns False."""
        mock_save.return_value = False

        response = client.post(
            "/setup",
            data={
                "step": "1",
                "some_key": "some_value",
            },
            follow_redirects=False,
        )

        # Should still continue even if save fails
        assert response.status_code == 303

    @patch("app.views.wizard.save_setting_to_db")
    def test_setup_wizard_save_exception_handling(self, mock_save, client):
        """Test exception handling in setup_wizard_save."""
        mock_save.side_effect = Exception("Database error")

        response = client.post(
            "/setup",
            data={
                "step": "1",
                "database_url": "sqlite:///test.db",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error=save_failed" in response.headers["location"]
        assert "step=1" in response.headers["location"]


@pytest.mark.integration
class TestWizardSkip:
    """Tests for wizard skip functionality."""

    @patch("app.views.wizard.save_setting_to_db")
    def test_setup_wizard_skip_success(self, mock_save, client):
        """Test successful skipping of setup wizard."""
        mock_save.return_value = True

        response = client.get("/setup/skip", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/"
        mock_save.assert_called_once()
        call_args = mock_save.call_args[0]
        assert call_args[1] == "_setup_wizard_skipped"
        assert call_args[2] == "true"

    @patch("app.views.wizard.save_setting_to_db")
    def test_setup_wizard_skip_exception_handling(self, mock_save, client):
        """Test exception handling when skipping wizard."""
        mock_save.side_effect = Exception("Database error")

        response = client.get("/setup/skip", follow_redirects=False)

        # Should still redirect to home even on error
        assert response.status_code == 303
        assert response.headers["location"] == "/"
