"""Tests for app/views/onedrive.py module."""

import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException

from app.models import UserIntegration
from app.utils.encryption import decrypt_value, encrypt_value
from app.views.base import settings


def _pending_transaction_store():
    transactions = {}

    def store(state, transaction):
        transactions[state] = transaction

    def consume(state):
        return transactions.pop(state, None)

    return transactions, store, consume


@pytest.mark.integration
class TestOnedriveViews:
    """Tests for OneDrive view routes."""

    def test_onedrive_setup_page(self, client):
        """Test the OneDrive setup page."""
        with patch("app.views.onedrive.get_current_user", return_value={"is_admin": True}):
            response = client.get("/onedrive-setup")
        assert response.status_code == 200
        assert "const integrationId" in response.text

    def test_onedrive_callback_no_code(self, client):
        """Test the OneDrive OAuth callback without code."""
        response = client.get("/onedrive-callback", follow_redirects=False)
        assert response.status_code == 200

    def test_onedrive_callback_with_error(self, client):
        """Test the OneDrive OAuth callback with error."""
        response = client.get("/onedrive-callback?error=access_denied")
        assert response.status_code == 200

    def test_onedrive_callback_with_code(self, client):
        """Test the OneDrive OAuth callback with auth code."""
        response = client.get("/onedrive-callback?code=test_code")
        assert response.status_code == 200
        assert "client_secret" not in response.text
        assert "sessionStorage" not in response.text

    def test_personal_oauth_start_uses_server_credentials_without_rendering_secret(self, client, db_session):
        _, store, _ = _pending_transaction_store()
        owner_id = "onedrive-owner@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="DESTINATION",
            integration_type="ONEDRIVE",
            name="Personal OneDrive",
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)
        with (
            patch("app.views.onedrive.get_current_owner_id", return_value=owner_id),
            patch("app.views.onedrive.store_pending_onedrive_oauth", side_effect=store),
            patch.object(settings, "onedrive_client_id", "server-client"),
            patch.object(settings, "onedrive_client_secret", "server-secret"),
        ):
            response = client.post("/onedrive-auth-start", data={"integration_id": integration.id})
        assert response.status_code == 200
        query = parse_qs(urlparse(response.json()["authorize_url"]).query)
        assert query["client_id"] == ["server-client"]
        assert "server-secret" not in response.text
        assert "server-secret" not in str(client.cookies)

    def test_personal_oauth_start_rejects_foreign_integration(self, client, db_session):
        integration = UserIntegration(
            owner_id="actual-owner@example.com",
            direction="DESTINATION",
            integration_type="ONEDRIVE",
            name="Personal OneDrive",
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)
        with patch("app.views.onedrive.get_current_owner_id", return_value="other-owner@example.com"):
            response = client.post("/onedrive-auth-start", data={"integration_id": integration.id})
        assert response.status_code == 404

    def test_global_oauth_start_requires_admin(self, client):
        with patch("app.views.onedrive.get_current_user", return_value={"is_admin": False}):
            response = client.post("/onedrive-auth-start", data={})
        assert response.status_code == 403

    def test_exchange_rejects_state_mismatch(self, client, db_session):
        _, store, _ = _pending_transaction_store()
        owner_id = "state-owner@example.com"
        integration = UserIntegration(
            owner_id=owner_id, direction="DESTINATION", integration_type="ONEDRIVE", name="OneDrive", is_active=True
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)
        with (
            patch("app.views.onedrive.get_current_owner_id", return_value=owner_id),
            patch("app.views.onedrive.store_pending_onedrive_oauth", side_effect=store),
            patch.object(settings, "onedrive_client_id", "server-client"),
            patch.object(settings, "onedrive_client_secret", "server-secret"),
        ):
            assert client.post("/onedrive-auth-start", data={"integration_id": integration.id}).status_code == 200
        response = client.post(
            "/api/onedrive/exchange-token",
            data={
                "code": "code",
                "redirect_uri": "http://localhost/onedrive-callback",
                "tenant_id": "common",
                "state": "wrong",
                "integration_id": integration.id,
            },
        )
        assert response.status_code == 400

    def test_personal_exchange_persists_owned_credentials_and_is_single_use(self, client, db_session):
        _, store, consume = _pending_transaction_store()
        owner_id = "exchange-owner@example.com"
        integration = UserIntegration(
            owner_id=owner_id, direction="DESTINATION", integration_type="ONEDRIVE", name="OneDrive", is_active=True
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)
        with (
            patch("app.views.onedrive.get_current_owner_id", return_value=owner_id),
            patch("app.api.onedrive.get_current_owner_id", return_value=owner_id),
            patch("app.views.onedrive.store_pending_onedrive_oauth", side_effect=store),
            patch("app.api.onedrive.consume_pending_onedrive_oauth", side_effect=consume),
        ):
            start = client.post(
                "/onedrive-auth-start",
                data={
                    "integration_id": integration.id,
                    "client_id": "personal-client",
                    "client_secret": "personal-secret",
                    "tenant_id": "common",
                },
            )
            state = parse_qs(urlparse(start.json()["authorize_url"]).query)["state"][0]
            with patch(
                "app.api.onedrive.exchange_oauth_token",
                return_value={"refresh_token": "refresh", "access_token": "access"},
            ):
                response = client.post(
                    "/api/onedrive/exchange-token",
                    data={
                        "code": "code",
                        "redirect_uri": "http://localhost/onedrive-callback",
                        "tenant_id": "common",
                        "state": state,
                        "integration_id": integration.id,
                    },
                )
        assert response.status_code == 200
        stored = json.loads(decrypt_value(integration.credentials))
        assert stored["client_id"] == "personal-client"
        assert stored["refresh_token"] == "refresh"
        replay = client.post(
            "/api/onedrive/exchange-token",
            data={
                "code": "code",
                "redirect_uri": "http://localhost/onedrive-callback",
                "tenant_id": "common",
                "state": state,
                "integration_id": integration.id,
            },
        )
        assert replay.status_code == 400

    def test_global_custom_credentials_are_used_and_saved_server_side(self, client, db_session):
        _, store, consume = _pending_transaction_store()
        owner_id = "admin@example.com"
        with (
            patch.object(settings, "onedrive_client_id", None),
            patch.object(settings, "onedrive_client_secret", None),
            patch("app.views.onedrive.get_current_owner_id", return_value=owner_id),
            patch("app.api.onedrive.get_current_owner_id", return_value=owner_id),
            patch("app.views.onedrive.get_current_user", return_value={"is_admin": True}),
            patch("app.api.onedrive._require_admin", return_value={"is_admin": True}),
            patch("app.views.onedrive.store_pending_onedrive_oauth", side_effect=store),
            patch("app.api.onedrive.consume_pending_onedrive_oauth", side_effect=consume),
            patch("app.api.onedrive.update_env_file"),
            patch("app.api.onedrive.notify_settings_updated"),
        ):
            start = client.post(
                "/onedrive-auth-start",
                data={"client_id": "chosen-client", "client_secret": "chosen-secret", "tenant_id": "tenant-a"},
            )
            assert start.status_code == 200
            state = parse_qs(urlparse(start.json()["authorize_url"]).query)["state"][0]
            with patch(
                "app.api.onedrive.exchange_oauth_token",
                return_value={"refresh_token": "refresh", "access_token": "access"},
            ) as exchange:
                response = client.post(
                    "/api/onedrive/exchange-token",
                    data={"code": "code", "redirect_uri": "ignored", "tenant_id": "ignored", "state": state},
                )
        assert response.status_code == 200
        assert response.json() == {"status": "success", "access_token": ""}
        assert exchange.call_args.kwargs["payload"]["client_id"] == "chosen-client"
        assert exchange.call_args.kwargs["payload"]["client_secret"] == "chosen-secret"

    def test_global_existing_credentials_complete_without_browser_secret(self, client, db_session):
        _, store, consume = _pending_transaction_store()
        owner_id = "admin@example.com"
        with (
            patch.object(settings, "onedrive_client_id", "server-client"),
            patch.object(settings, "onedrive_client_secret", "server-secret"),
            patch("app.views.onedrive.get_current_owner_id", return_value=owner_id),
            patch("app.api.onedrive.get_current_owner_id", return_value=owner_id),
            patch("app.views.onedrive.get_current_user", return_value={"is_admin": True}),
            patch("app.api.onedrive._require_admin", return_value={"is_admin": True}),
            patch("app.views.onedrive.store_pending_onedrive_oauth", side_effect=store),
            patch("app.api.onedrive.consume_pending_onedrive_oauth", side_effect=consume),
            patch("app.api.onedrive.update_env_file"),
            patch("app.api.onedrive.notify_settings_updated"),
        ):
            start = client.post("/onedrive-auth-start", data={})
            assert start.status_code == 200
            state = parse_qs(urlparse(start.json()["authorize_url"]).query)["state"][0]
            with patch(
                "app.api.onedrive.exchange_oauth_token",
                return_value={"refresh_token": "refresh", "access_token": "access"},
            ) as exchange:
                response = client.post(
                    "/api/onedrive/exchange-token",
                    data={"code": "code", "redirect_uri": "ignored", "tenant_id": "ignored", "state": state},
                )
        assert response.status_code == 200
        assert exchange.call_args.kwargs["payload"]["client_secret"] == "server-secret"

    def test_exchange_rejects_foreign_owner_before_consuming_transaction(self, client, db_session):
        transactions, store, consume = _pending_transaction_store()
        owner_id = "owner@example.com"
        integration = UserIntegration(
            owner_id=owner_id, direction="DESTINATION", integration_type="ONEDRIVE", name="OneDrive", is_active=True
        )
        db_session.add(integration)
        db_session.commit()
        with (
            patch("app.views.onedrive.get_current_owner_id", return_value=owner_id),
            patch("app.views.onedrive.store_pending_onedrive_oauth", side_effect=store),
        ):
            start = client.post(
                "/onedrive-auth-start",
                data={"integration_id": integration.id, "client_id": "id", "client_secret": "secret"},
            )
        state = parse_qs(urlparse(start.json()["authorize_url"]).query)["state"][0]
        with (
            patch("app.api.onedrive.get_current_owner_id", return_value="attacker@example.com"),
            patch("app.api.onedrive.consume_pending_onedrive_oauth", side_effect=consume) as mocked_consume,
        ):
            response = client.post(
                "/api/onedrive/exchange-token",
                data={
                    "code": "code",
                    "redirect_uri": "ignored",
                    "tenant_id": "ignored",
                    "state": state,
                    "integration_id": integration.id,
                },
            )
        assert response.status_code == 400
        mocked_consume.assert_not_called()
        assert state in transactions

    def test_exchange_failure_preserves_existing_integration_credentials(self, client, db_session):
        _, store, consume = _pending_transaction_store()
        owner_id = "owner@example.com"
        existing = encrypt_value(
            json.dumps({"client_id": "old", "client_secret": "old-secret", "refresh_token": "old-refresh"})
        )
        integration = UserIntegration(
            owner_id=owner_id,
            direction="DESTINATION",
            integration_type="ONEDRIVE",
            name="OneDrive",
            is_active=True,
            credentials=existing,
        )
        db_session.add(integration)
        db_session.commit()
        with (
            patch("app.views.onedrive.get_current_owner_id", return_value=owner_id),
            patch("app.api.onedrive.get_current_owner_id", return_value=owner_id),
            patch("app.views.onedrive.store_pending_onedrive_oauth", side_effect=store),
            patch("app.api.onedrive.consume_pending_onedrive_oauth", side_effect=consume),
        ):
            start = client.post(
                "/onedrive-auth-start",
                data={"integration_id": integration.id, "client_id": "new", "client_secret": "new-secret"},
            )
            state = parse_qs(urlparse(start.json()["authorize_url"]).query)["state"][0]
            with patch(
                "app.api.onedrive.exchange_oauth_token",
                side_effect=HTTPException(status_code=400, detail="provider failed"),
            ):
                response = client.post(
                    "/api/onedrive/exchange-token",
                    data={
                        "code": "code",
                        "redirect_uri": "ignored",
                        "tenant_id": "ignored",
                        "state": state,
                        "integration_id": integration.id,
                    },
                )
        assert response.status_code == 400
        assert integration.credentials == existing

    def test_onedrive_setup_page_with_integration_id(self, client):
        """Test the OneDrive setup page accepts integration_id query param."""
        response = client.get("/onedrive-setup?integration_id=77")
        assert response.status_code == 404

    def test_onedrive_setup_page_without_integration_id(self, client):
        """Test the OneDrive setup page works without integration_id (global flow)."""
        with patch("app.views.onedrive.get_current_user", return_value={"is_admin": True}):
            response = client.get("/onedrive-setup")
        assert response.status_code == 200
        body = response.text
        assert "sessionStorage" not in body
        assert 'const integrationId = ""' in body

    def test_onedrive_setup_user_mode_invalid_json_config(self, client, db_session):
        """Test user-mode renders correctly when integration.config is invalid JSON."""
        owner_id = "user_od_invalid_json@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="DESTINATION",
            integration_type="ONEDRIVE",
            name="My OneDrive (bad cfg)",
            config="{INVALID JSON}",
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        with patch("app.views.onedrive.get_current_owner_id", return_value=owner_id):
            response = client.get(f"/onedrive-setup?integration_id={integration.id}")

        assert response.status_code == 200
        # Should render user mode without errors despite the bad config
        assert b"Back to Integrations" in response.content

    def test_onedrive_setup_user_mode_none_config(self, client, db_session):
        """Test user-mode renders correctly when integration.config is None (no folder path)."""
        owner_id = "user_od_none_cfg@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="DESTINATION",
            integration_type="ONEDRIVE",
            name="My OneDrive (no cfg)",
            config=None,
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        with patch("app.views.onedrive.get_current_owner_id", return_value=owner_id):
            response = client.get(f"/onedrive-setup?integration_id={integration.id}")

        assert response.status_code == 200
        # Should render user mode without errors, with empty folder_path
        assert b"Back to Integrations" in response.content

    def test_onedrive_setup_user_mode_watchfolder_config(self, client, db_session):
        """Test user-mode correctly loads folder_path from WATCH_FOLDER source config."""
        owner_id = "user_od_wf_cfg@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="SOURCE",
            integration_type="WATCH_FOLDER",
            name="My OneDrive Watch",
            config=json.dumps({"source_type": "onedrive", "folder_path": "Work/Inbox"}),
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        with patch("app.views.onedrive.get_current_owner_id", return_value=owner_id):
            response = client.get(f"/onedrive-setup?integration_id={integration.id}")

        assert response.status_code == 200
        assert b"Work/Inbox" in response.content
        assert b"Back to Integrations" in response.content

    def test_onedrive_setup_user_mode_integration_not_found(self, client, db_session):
        """An unknown or foreign integration cannot fall back to global settings."""
        with patch("app.views.onedrive.get_current_owner_id", return_value="other_user@example.com"):
            response = client.get("/onedrive-setup?integration_id=999999")

        assert response.status_code == 404

    def test_onedrive_setup_user_mode_valid_config(self, client, db_session):
        """Test user-mode correctly loads folder path from integration config."""
        owner_id = "user_od_valid_cfg@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="DESTINATION",
            integration_type="ONEDRIVE",
            name="My OneDrive",
            config=json.dumps({"folder_path": "Documents/Archive"}),
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        with patch("app.views.onedrive.get_current_owner_id", return_value=owner_id):
            response = client.get(f"/onedrive-setup?integration_id={integration.id}")

        assert response.status_code == 200
        assert b"Documents/Archive" in response.content
        assert b"Back to Integrations" in response.content
