"""Remove legacy plaintext secrets from settings audit history.

Revision ID: 061_encrypt_sensitive_settings_audit
Revises: 060_add_tenant_tribe_foundation
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "061_encrypt_sensitive_settings_audit"
down_revision: Union[str, None] = "060_add_tenant_tribe_foundation"
branch_labels = None
depends_on = None

SENSITIVE_SETTING_KEYS = (
    "admin_password",
    "anthropic_api_key",
    "audit_siem_http_token",
    "authentik_client_secret",
    "aws_access_key_id",
    "aws_secret_access_key",
    "azure_ai_key",
    "database_url",
    "dest_email_password",
    "document_bridge_bearer_token",
    "document_bridge_shared_secret",
    "document_intake_shared_secret",
    "dropbox_app_secret",
    "dropbox_refresh_token",
    "email_password",
    "evernote_auth_token",
    "ftp_password",
    "gemini_api_key",
    "google_docai_credentials_json",
    "google_drive_client_secret",
    "google_drive_credentials_json",
    "google_drive_refresh_token",
    "icloud_password",
    "imap1_password",
    "imap2_password",
    "meilisearch_api_key",
    "mistral_api_key",
    "nextcloud_password",
    "notification_urls",
    "onedrive_client_secret",
    "onedrive_refresh_token",
    "openai_api_key",
    "openrouter_api_key",
    "paperless_ngx_api_token",
    "portkey_api_key",
    "portkey_virtual_key",
    "sentry_dsn",
    "session_secret",
    "sftp_password",
    "sftp_private_key",
    "sftp_private_key_passphrase",
    "sharepoint_client_secret",
    "sharepoint_refresh_token",
    "social_auth_apple_private_key",
    "social_auth_dropbox_client_secret",
    "social_auth_generic_oauth2_client_secret",
    "social_auth_github_client_secret",
    "social_auth_google_client_secret",
    "social_auth_keycloak_client_secret",
    "social_auth_microsoft_client_secret",
    "social_auth_saml2_certificate",
    "stripe_secret_key",
    "stripe_webhook_secret",
    "telegram_bot_token",
    "vector_index_api_key",
    "webdav_password",
)


def upgrade() -> None:
    bind = op.get_bind()
    if "settings_audit_log" not in sa.inspect(bind).get_table_names():
        return
    statement = sa.text(
        "UPDATE settings_audit_log SET old_value = NULL, new_value = NULL WHERE key IN :keys"
    ).bindparams(sa.bindparam("keys", expanding=True))
    bind.execute(statement, {"keys": SENSITIVE_SETTING_KEYS})


def downgrade() -> None:
    # Redacted plaintext secrets cannot and must not be reconstructed.
    pass
