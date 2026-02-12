"""Tests for app/views/wizard.py module."""

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
