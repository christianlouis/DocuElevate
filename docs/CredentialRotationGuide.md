# Credential Rotation Guide

This guide documents how to rotate API keys and credentials used by DocuElevate, along with onboarding and offboarding procedures for team members and service accounts.

## Overview

DocuElevate integrates with several external services that require API keys, tokens, or passwords. Regularly rotating these credentials limits the blast radius of a potential leak and is a security best practice.

Credentials fall into two categories:

| Category | Examples |
|---|---|
| **API keys** | OpenAI API key, Azure AI key, Paperless-ngx API token, AWS access keys |
| **OAuth tokens / secrets** | Dropbox, Google Drive, OneDrive, Authentik client secrets and refresh tokens |
| **Passwords** | Admin password, Nextcloud, Email (SMTP), IMAP, FTP, SFTP, WebDAV |
| **Private keys** | SFTP private key and passphrase |

All credentials are stored either in environment variables or, when set via the Settings UI, encrypted in the database using Fernet symmetric encryption (keyed from `SESSION_SECRET`).

---

## Recommended Rotation Schedule

| Credential Type | Recommended Rotation Interval |
|---|---|
| API keys (OpenAI, Azure, AWS, Paperless) | Every 90 days |
| OAuth client secrets | Every 180 days |
| OAuth refresh tokens | Rotate on revocation / after each re-authorization |
| Passwords (SMTP, IMAP, FTP, SFTP, Nextcloud, WebDAV) | Every 90 days or on personnel change |
| Admin password | Every 90 days or on personnel change |
| `SESSION_SECRET` | On suspected compromise; note all active sessions will be invalidated |

---

## How to Rotate a Credential

DocuElevate supports two rotation methods:

### Method 1 — Settings API (recommended, zero-downtime)

Use the Settings REST API to update individual credentials while the application is running. No restart is needed for most credentials (check `restart_required` in the response).

```bash
# Rotate the OpenAI API key
curl -X POST https://<your-host>/api/settings/openai_api_key \
  -H "Content-Type: application/json" \
  -b "session=<admin-session-cookie>" \
  -d '{"key": "openai_api_key", "value": "sk-new-key-here"}'
```

The endpoint returns `"restart_required": true` for settings that require an application restart to take effect (e.g., database URL, session secret). All AI-service and storage-provider credentials take effect immediately without a restart.

### Method 2 — Environment variable / `.env` file

1. Update the relevant variable in your `.env` file (or your container/Kubernetes secret).
2. Restart the application so the new value is loaded:

```bash
docker compose restart api worker
```

> **Note:** Settings stored in the database take precedence over environment variables. If you previously set a credential via the Settings UI, you must also update or delete it from the database (via the Settings API) to have the environment variable take effect.

---

## Per-Credential Rotation Procedures

### OpenAI API Key

1. Log in to [platform.openai.com](https://platform.openai.com) → **API keys**.
2. Create a new secret key and copy it.
3. Update in DocuElevate:
   ```
   POST /api/settings/openai_api_key  {"key": "openai_api_key", "value": "<new-key>"}
   ```
4. Verify document processing still works (upload a test file).
5. Delete the old key in the OpenAI dashboard.

### Azure Document Intelligence Key

1. Open [portal.azure.com](https://portal.azure.com) → your Document Intelligence resource → **Keys and Endpoint**.
2. Regenerate **Key 2** while **Key 1** is still live (avoids downtime).
3. Update `azure_ai_key` in DocuElevate with the new key.
4. Verify connectivity, then regenerate **Key 1** and optionally update again.

### AWS S3 Access Keys

1. In the **IAM Console**, create a new access key for the service user.
2. Update both `aws_access_key_id` and `aws_secret_access_key` in DocuElevate together (use the bulk-update endpoint or update both settings in sequence before verifying).
3. Test an S3 upload from DocuElevate.
4. Deactivate the old IAM access key, then delete it after 24 hours.

### Dropbox App Credentials & Refresh Token

Dropbox refresh tokens are long-lived; rotate them by re-authorizing the application:

1. In [dropbox.com/developers](https://www.dropbox.com/developers), revoke the existing token.
2. Follow the Dropbox OAuth flow documented in `docs/DropboxSetup.md` to obtain a new refresh token.
3. Update `dropbox_refresh_token` (and `dropbox_app_key` / `dropbox_app_secret` if also rotating those).

### Google Drive OAuth Credentials

1. In the [Google Cloud Console](https://console.cloud.google.com), navigate to **APIs & Services → Credentials**.
2. Rotate the OAuth client secret: delete the old secret and create a new one.
3. Update `google_drive_client_secret` in DocuElevate.
4. Re-authorize to obtain a fresh refresh token and update `google_drive_refresh_token`.

For service-account credentials (`google_drive_credentials_json`):

1. Create a new service-account key in the Google Cloud Console.
2. Update `google_drive_credentials_json` with the new JSON.
3. Verify access, then delete the old key.

### OneDrive (Microsoft OAuth)

1. In **Azure App Registrations**, navigate to **Certificates & secrets** for your app.
2. Add a new client secret.
3. Update `onedrive_client_secret` in DocuElevate.
4. Re-authorize via the OAuth flow to get a fresh `onedrive_refresh_token`.
5. Delete the old client secret in Azure.

### Authentik (OIDC)

1. In your Authentik admin panel, navigate to the DocuElevate application and regenerate the client secret.
2. Update `authentik_client_secret` in DocuElevate.
3. Restart the application (this setting requires a restart: `restart_required: true`).

### Paperless-ngx API Token

1. Log in to your Paperless-ngx instance → **Settings → API Tokens**.
2. Create a new token.
3. Update `paperless_ngx_api_token` in DocuElevate.
4. Verify document routing works, then revoke the old token.

### SMTP / Email Password

1. Rotate the password in your mail server or email provider.
2. Update `email_password` in DocuElevate.

### IMAP Passwords

Update `imap1_password` and/or `imap2_password` after rotating the credentials with your email provider.

### Nextcloud Password / App Password

1. In Nextcloud → **Settings → Security**, revoke the existing app password and create a new one.
2. Update `nextcloud_password` in DocuElevate.

### FTP / SFTP / WebDAV Passwords

1. Rotate the credential on the respective server.
2. Update `ftp_password`, `sftp_password`, or `webdav_password` in DocuElevate.

### SFTP Private Key

1. Generate a new key pair:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/docuelevate_sftp -C "docuelevate-sftp"
   ```
2. Install the new public key on the SFTP server.
3. Update `sftp_private_key` (and `sftp_private_key_passphrase` if encrypted) in DocuElevate.
4. Verify connectivity, then remove the old public key from the SFTP server.

### Admin Password

1. Update `admin_password` in DocuElevate (via the Settings UI or API).
2. Communicate the new password to any users who share it (discouraged; prefer individual accounts via OAuth).
3. Requires application restart.

### `SESSION_SECRET`

> **Warning:** Rotating `SESSION_SECRET` invalidates all active user sessions. All logged-in users will be signed out immediately.

1. Generate a new secret (minimum 32 characters):
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
2. Update the environment variable or `.env` file.
3. Restart the application.
4. Existing encrypted settings stored in the database **will no longer be readable** because the encryption key is derived from `SESSION_SECRET`. You must re-enter all sensitive settings that were stored via the UI after rotating this value.

---

## Bulk Credential Audit

Use the dedicated endpoint to list all credential settings and their configured/unconfigured status:

```bash
GET /api/settings/credentials
```

Example response:

```json
{
  "credentials": [
    {
      "key": "openai_api_key",
      "category": "AI Services",
      "description": "OpenAI API key for metadata extraction",
      "configured": true,
      "source": "env"
    },
    {
      "key": "azure_ai_key",
      "category": "AI Services",
      "description": "Azure AI key for document intelligence",
      "configured": true,
      "source": "db"
    },
    ...
  ],
  "total": 24,
  "configured_count": 8,
  "unconfigured_count": 16
}
```

The `source` field indicates whether the value comes from the **database** (`db`) or an **environment variable** (`env`).

---

## Onboarding a New Team Member or Service Account

1. **Identify required credentials** – Use `GET /api/settings/credentials` to see which credentials are active in the deployment.
2. **Create service-specific credentials** – For each external service (OpenAI, AWS, etc.) create a new API key or sub-account rather than sharing the existing one. This enables individual revocation without disrupting others.
3. **Set credentials via the Settings API** – Provide the new credential via `POST /api/settings/{key}`. The value is encrypted at rest.
4. **Restrict access** – Ensure the new service account has only the minimum permissions needed (e.g., an S3 IAM user with write access to the specific bucket only).
5. **Document the credential** – Record *which* system generated the credential and *when* it was created, so it can be identified during offboarding.

---

## Offboarding a Team Member or Decommissioning a Service Account

1. **Identify credentials tied to the departing user** – Review all third-party services for keys or OAuth authorizations issued under their account.
2. **Revoke credentials** – Delete or disable the API key/token in each third-party service immediately.
3. **Rotate shared credentials** – If any credential was shared (e.g., a team-wide admin password), rotate it now using the procedures above.
4. **Update DocuElevate** – Set the new credential via `POST /api/settings/{key}` or delete the old entry via `DELETE /api/settings/{key}` if the service is no longer used.
5. **Verify operations** – Trigger a test document processing run to confirm all integrations still work.
6. **Audit logs** – Review audit logs for any anomalous activity by the departing user before revoking access.

---

## Emergency Credential Revocation

If a credential is believed to be compromised:

1. **Revoke immediately** in the external service (do not wait to have a replacement ready).
2. **Review audit logs** for unauthorized usage.
3. **Generate and deploy a replacement** credential as soon as possible.
4. **Notify stakeholders** per your incident response plan (see [SECURITY.md](../SECURITY.md)).

---

## Related Documentation

- [Configuration Guide](ConfigurationGuide.md) — Full list of environment variables
- [Deployment Guide](DeploymentGuide.md) — Deployment and restart procedures
- [SECURITY_AUDIT.md](../SECURITY_AUDIT.md) — Security audit findings and status
- [SECURITY.md](../SECURITY.md) — Security contact and disclosure policy
