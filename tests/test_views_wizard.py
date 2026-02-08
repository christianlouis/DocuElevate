"""
Tests for setup wizard views
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestSetupWizard:
    """Tests for setup wizard views."""

    def test_setup_wizard_step_1(self, client: TestClient):
        """Test accessing setup wizard step 1."""
        with patch("app.utils.setup_wizard.get_wizard_steps") as mock_steps:
            mock_steps.return_value = {
                1: [{"key": "workdir", "label": "Work Directory", "wizard_category": "Basic"}],
                2: [{"key": "openai_api_key", "label": "OpenAI Key", "wizard_category": "AI"}],
            }

            response = client.get("/setup?step=1")
            assert response.status_code == 200
            assert b"setup" in response.content.lower() or b"wizard" in response.content.lower()

    def test_setup_wizard_invalid_step_negative(self, client: TestClient):
        """Test setup wizard with negative step number."""
        with patch("app.utils.setup_wizard.get_wizard_steps") as mock_steps:
            mock_steps.return_value = {
                1: [{"key": "workdir", "label": "Work Directory", "wizard_category": "Basic"}],
            }

            response = client.get("/setup?step=-1")
            # Should clamp to step 1
            assert response.status_code == 200

    def test_setup_wizard_invalid_step_too_high(self, client: TestClient):
        """Test setup wizard with step number beyond max."""
        with patch("app.utils.setup_wizard.get_wizard_steps") as mock_steps:
            mock_steps.return_value = {
                1: [{"key": "workdir", "label": "Work Directory", "wizard_category": "Basic"}],
            }

            response = client.get("/setup?step=999")
            # Should clamp to max step
            assert response.status_code == 200

    def test_setup_wizard_save_step(self, client: TestClient, db_session):
        """Test saving setup wizard step."""
        with patch("app.utils.setup_wizard.get_wizard_steps") as mock_steps:
            with patch("app.utils.settings_service.save_setting_to_db") as mock_save:
                mock_steps.return_value = {
                    1: [{"key": "workdir", "label": "Work Directory", "wizard_category": "Basic"}],
                    2: [{"key": "openai_api_key", "label": "OpenAI Key", "wizard_category": "AI"}],
                }
                mock_save.return_value = True

                response = client.post(
                    "/setup",
                    data={"step": "1", "workdir": "/tmp/test"},
                    follow_redirects=False
                )

                # Should redirect to next step
                assert response.status_code in [303, 307, 302]

    def test_setup_wizard_save_final_step(self, client: TestClient, db_session):
        """Test saving final step of setup wizard."""
        with patch("app.utils.setup_wizard.get_wizard_steps") as mock_steps:
            with patch("app.utils.settings_service.save_setting_to_db") as mock_save:
                mock_steps.return_value = {
                    1: [{"key": "workdir", "label": "Work Directory", "wizard_category": "Basic"}],
                }
                mock_save.return_value = True

                response = client.post(
                    "/setup",
                    data={"step": "1", "workdir": "/tmp/test"},
                    follow_redirects=False
                )

                # Should redirect to home with setup=complete
                assert response.status_code in [303, 307, 302]
                if "location" in response.headers:
                    assert "setup=complete" in response.headers["location"]

    def test_setup_wizard_save_error(self, client: TestClient, db_session):
        """Test setup wizard save with error."""
        with patch("app.utils.setup_wizard.get_wizard_steps") as mock_steps:
            mock_steps.return_value = {
                1: [{"key": "workdir", "label": "Work Directory", "wizard_category": "Basic"}],
            }

            # Simulate error by making get_wizard_steps raise exception during save
            with patch("app.utils.settings_service.save_setting_to_db", side_effect=Exception("DB Error")):
                response = client.post(
                    "/setup",
                    data={"step": "1", "workdir": "/tmp/test"},
                    follow_redirects=False
                )

                # Should redirect with error
                assert response.status_code in [303, 307, 302, 500]

    def test_setup_wizard_skip(self, client: TestClient):
        """Test skipping setup wizard."""
        with patch("app.views.wizard.get_db") as mock_get_db:
            with patch("app.utils.settings_service.save_setting_to_db") as mock_save:
                mock_db = MagicMock()
                mock_get_db.return_value = iter([mock_db])
                mock_save.return_value = True

                response = client.get("/setup/skip", follow_redirects=False)

                # Should redirect to home
                assert response.status_code in [303, 307, 302]

    def test_setup_wizard_auto_generate_secret(self, client: TestClient, db_session):
        """Test auto-generating session secret in wizard."""
        with patch("app.utils.setup_wizard.get_wizard_steps") as mock_steps:
            with patch("app.utils.settings_service.save_setting_to_db") as mock_save:
                mock_steps.return_value = {
                    1: [{"key": "session_secret", "label": "Session Secret", "wizard_category": "Security"}],
                }
                mock_save.return_value = True

                response = client.post(
                    "/setup",
                    data={"step": "1", "session_secret": "auto-generate"},
                    follow_redirects=False
                )

                assert response.status_code in [303, 307, 302]
                # Verify that save was called (would have generated a secret)
                assert mock_save.called
