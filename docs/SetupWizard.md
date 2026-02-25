# Setup Wizard Guide

DocuElevate includes a first-run Setup Wizard that guides you through configuring the essential settings needed for the system to operate.  The wizard is the recommended starting point for any new installation.

## Table of Contents

- [When the Wizard Appears](#when-the-wizard-appears)
- [Wizard Steps](#wizard-steps)
  - [Step 1 – Core Infrastructure](#step-1--core-infrastructure)
  - [Step 2 – Security](#step-2--security)
  - [Step 3 – AI Services](#step-3--ai-services)
- [Skipping and Resuming the Wizard](#skipping-and-resuming-the-wizard)
- [After the Wizard](#after-the-wizard)
- [Integration-Specific Setup Pages](#integration-specific-setup-pages)
- [Advanced: Settings Management](#advanced-settings-management)

---

## When the Wizard Appears

The wizard is shown automatically when DocuElevate detects that critical settings are still at their insecure defaults.  Specifically, it triggers when **either** of the following is true:

- `SESSION_SECRET` is still the built-in insecure placeholder
- `ADMIN_PASSWORD` is absent or set to a common placeholder value (`changeme`, `admin`, etc.)

Once both values have been configured — whether through the wizard or through environment variables — the wizard will no longer be shown on the home page.

> **Tip:** If you pre-populate all settings via environment variables before the first launch, the wizard will be skipped automatically.

---

## Wizard Steps

The wizard is divided into three focused steps, accessible at `/setup?step=<N>`.

### Step 1 – Core Infrastructure

Configure the services that DocuElevate depends on at the infrastructure level.

| Setting | Description | Default |
|---------|-------------|---------|
| `DATABASE_URL` | Database connection string. SQLite is fine for development; PostgreSQL is recommended for production. | `sqlite:///./app/database.db` |
| `REDIS_URL` | Redis connection URL used by the Celery task queue. | `redis://localhost:6379/0` |
| `WORKDIR` | Filesystem path where documents are staged during processing. Must be writable by the API and Worker containers. | `/workdir` |
| `GOTENBERG_URL` | URL of the Gotenberg service used for document-to-PDF conversion. | `http://gotenberg:3000` |

> For Docker Compose deployments the defaults work out of the box. You only need to change these if you are using external services or a custom topology.

### Step 2 – Security

Configure authentication and session security.

| Setting | Description | Notes |
|---------|-------------|-------|
| `SESSION_SECRET` | Secret key used to sign and encrypt session cookies. Minimum 32 characters. | Click **Auto-generate** to let the wizard create a cryptographically secure value for you. |
| `ADMIN_USERNAME` | Username for the built-in admin account. | Defaults to `admin`. |
| `ADMIN_PASSWORD` | Password for the built-in admin account. | Required. Must not be a placeholder value. |

> **Security note:** The auto-generated session secret is a 64-character hex string (32 bytes of entropy).  Store it somewhere safe — it cannot be recovered if lost. If you rotate the secret, all existing sessions will be invalidated.

### Step 3 – AI Services

Configure the AI provider used for metadata extraction and document understanding.

| Setting | Description | Notes |
|---------|-------------|-------|
| `AI_PROVIDER` | The AI backend to use. | Options: `openai`, `azure`, `anthropic`, `gemini`, `ollama`, `openrouter`, `portkey`, `litellm` |
| `OPENAI_API_KEY` | API key for OpenAI, Azure OpenAI, or LiteLLM-compatible endpoints. | Not required when using Ollama. |
| `OPENAI_MODEL` | Default model name (e.g. `gpt-4o-mini`, `claude-3-5-sonnet-20241022`, `llama3.2`). | Used when `AI_MODEL` is not explicitly set. |

> DocuElevate can operate without an AI provider — metadata extraction tasks will be skipped.  You can always add AI credentials later through the [Settings page](SettingsManagement.md).

---

## Skipping and Resuming the Wizard

### Skipping

If you are an advanced user who has already configured settings via environment variables, you can skip the wizard by clicking **Skip for now** or by visiting:

```
GET /setup/skip
```

This writes a `_setup_wizard_skipped` marker to the database so the wizard is not re-shown automatically.

### Resuming

To re-run the wizard after skipping it:

1. Navigate to **Settings → System** and click **Re-run Setup Wizard**, or
2. Visit `/setup/undo-skip` directly.

This removes the skip marker and redirects you to Step 1.

---

## After the Wizard

Once all three steps are complete you are redirected to the home page with a `?setup=complete` confirmation banner.  At that point DocuElevate is operational with the core settings in place.

**Recommended next steps:**

1. **Configure a storage destination** — Set up at least one output destination where processed documents will be sent:
   - [Dropbox Setup](DropboxSetup.md)
   - [Google Drive Setup](GoogleDriveSetup.md)
   - [OneDrive Setup](OneDriveSetup.md)
   - [Amazon S3 Setup](AmazonS3Setup.md)

2. **Configure notifications** — Set up Discord, Telegram, or email alerts:
   - [Notifications Setup](NotificationsSetup.md)

3. **Harden for production** — Follow the production readiness checklist:
   - [Production Readiness Guide](ProductionReadiness.md)

---

## Integration-Specific Setup Pages

Several cloud storage integrations include their own guided configuration pages that walk you through the OAuth app registration and token exchange process:

| Integration | Setup URL | Guide |
|-------------|-----------|-------|
| Dropbox | `/dropbox-setup` | [DropboxSetup.md](DropboxSetup.md) |
| Google Drive | `/google-drive-setup` | [GoogleDriveSetup.md](GoogleDriveSetup.md) |
| OneDrive / SharePoint | `/onedrive-setup` | [OneDriveSetup.md](OneDriveSetup.md) |
| Amazon S3 | Configured via settings | [AmazonS3Setup.md](AmazonS3Setup.md) |

These pages are accessed **after** the main Setup Wizard is complete and are independent wizard flows specific to each integration.

---

## Advanced: Settings Management

All settings — including those configured through the wizard — can be updated at any time through the Settings page (`/settings`).  Settings saved via the wizard are stored in the database and take precedence over the corresponding environment variables.

For the full list of every available configuration parameter, see the [Configuration Guide](ConfigurationGuide.md).

> **Precedence order:** Database value → Environment variable → Default
