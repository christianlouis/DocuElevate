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

`DATABASE_URL` and `SESSION_SECRET` are bootstrap settings. They must be present in the deployment environment before the app starts; the wizard displays their status but deliberately does not copy either value into the database.

Once `SESSION_SECRET` is supplied by the deployment and the admin password has been configured in the database, the wizard will no longer be shown on the home page.

> **Tip:** If you pre-populate all settings via environment variables before the first launch, the wizard will be skipped automatically.

---

## Wizard Steps

The wizard is divided into three focused steps, accessible at `/setup?step=<N>`.

### Step 1 – Core Infrastructure

Configure the services that DocuElevate depends on at the infrastructure level.

| Setting | Description | Default |
|---------|-------------|---------|
| `DATABASE_URL` | Bootstrap database connection string. SQLite is fine for development; PostgreSQL is recommended for production. Read-only in the wizard because the app needs it before it can read settings. | Required deployment setting |
| `REDIS_URL` | Redis connection URL used by the Celery task queue. | `redis://redis:6379/0` |
| `WORKDIR` | Filesystem path where documents are staged during processing. Must be writable by the API and Worker containers. | `/workdir` |
| `GOTENBERG_URL` | URL of the Gotenberg service used for document-to-PDF conversion. | `http://gotenberg:3000` |

> For Docker Compose deployments the defaults work out of the box. You only need to change these if you are using external services or a custom topology.

### Step 2 – Security

Configure authentication and session security.

| Setting | Description | Notes |
|---------|-------------|-------|
| `SESSION_SECRET` | Stable deployment secret used for sessions and encryption of sensitive database settings. Minimum 32 characters. | Required deployment setting; read-only in the wizard. |
| `ADMIN_USERNAME` | Username for the built-in admin account. | Defaults to `admin`. |
| `ADMIN_PASSWORD` | Password for the built-in admin account. | Required. Must not be a placeholder value. |

> **Security note:** Keep `SESSION_SECRET` in your deployment secret manager and inject it into every API and worker process. If it changes, active sessions are invalidated and previously encrypted settings and OAuth tokens cannot be decrypted.

### Step 3 – AI Services

Configure the AI provider used for metadata extraction and document understanding.

| Setting | Description | Notes |
|---------|-------------|-------|
| `AI_PROVIDER` | The AI backend to use. | Options: `openai`, `azure`, `anthropic`, `gemini`, `ollama`, `openrouter`, `portkey`, `litellm` |
| `OPENAI_API_KEY` | API key for OpenAI, Azure OpenAI, or LiteLLM-compatible endpoints. | Optional during setup. Required later only when the selected backend needs it; Ollama and an unauthenticated local LiteLLM endpoint do not. |
| `OPENAI_MODEL` | Default model name (e.g. `gpt-4o-mini`, `claude-3-5-sonnet-20241022`, `llama3.2`). | Used when `AI_MODEL` is not explicitly set. |

> DocuElevate can operate without an AI provider — metadata extraction tasks will be skipped.  You can always add AI credentials later through the [Settings page](SettingsManagement.md).

---

## Skipping and Resuming the Wizard

### Skipping

An authenticated administrator who has already configured the installation by
other means can skip the wizard using the **Skip setup** action. This is a
state-changing POST action protected by the normal session and CSRF controls;
an unauthenticated first-run visitor cannot bypass the required security step.

This writes a `_setup_wizard_skipped` marker to the database so the wizard is not re-shown automatically.

### Resuming

To re-run the wizard after skipping it:

1. Navigate to **Settings → System** and click **Re-run Setup Wizard**, or
2. Use **Re-run setup** as an authenticated administrator.

This removes the skip marker and redirects you to Step 1.

---

## After the Wizard

Once all three steps are complete, DocuElevate records completion on the
server, closes the one-time bootstrap session and sends you to the login page.
The setup URL is administrator-only from then on. A URL query parameter cannot
bypass an incomplete installation.

**Recommended next steps:**

1. **Choose optional destinations** — Every processed document is retained in DocuElevate's built-in archive. Add external destinations only when you want another copy or an automated hand-off:
   - [Dropbox Setup](DropboxSetup.md)
   - [Google Drive Setup](GoogleDriveSetup.md)
   - [OneDrive Setup](OneDriveSetup.md)
   - [Amazon S3 Setup](AmazonS3Setup.md)

2. **Configure notifications** — Set up Discord, Telegram, or email alerts:
   - [Notifications Setup](NotificationsSetup.md)

3. **Harden for production** — Follow the production readiness checklist:
   - [Production Readiness Guide](ProductionReadiness.md)

### The per-user onboarding journey

After the operator bootstrap, each user gets a separate, resumable eight-step journey at `/onboarding`: identity and document space, plan, processing, document sources, destinations, automation/notifications, and review. The first step always creates an isolated personal Tribe. A user may also create a new shared Family/Team Tribe and becomes its administrator; an existing Tribe cannot be joined by entering or guessing its name and requires a later invitation flow. Optional integration steps can be skipped and resumed later. Progress and memberships belong to the database, so two users can be at different steps and no API or worker restart is required.

Self-hosted administrator accounts receive complimentary full access. Their
journey states that explicitly instead of presenting paid plan choices. The
processing step also distinguishes the core path from optional AI: uploads,
embedded-text extraction and OCR remain available without an AI credential;
metadata extraction and embeddings are shown as not configured rather than as
successful work.

Completion sends the user to `/upload?onboarding=first-document`, where a
first-document callout explains that AI metadata and external destinations are
optional. The processing detail page reports successful and skipped steps
separately, so a keyless fresh install can be accepted without disguising
skipped AI work as success.

The journey links to the personal Integrations dashboard. OAuth refresh tokens and other user credentials are encrypted in `user_integrations`; they are never written to environment variables or browser storage. On a preprod hostname, names and suggested folders created by the journey use the `DocuElevate Preprod` / `/DocuElevate Preprod` label to prevent accidental overlap with production resources.

---

## Integration-Specific Setup Pages

Several cloud storage integrations include their own guided configuration pages that walk you through the OAuth app registration and token exchange process:

| Integration | Setup URL | Guide |
|-------------|-----------|-------|
| Dropbox | `/dropbox-setup` | [DropboxSetup.md](DropboxSetup.md) |
| Google Drive | `/google-drive-setup` | [GoogleDriveSetup.md](GoogleDriveSetup.md) |
| OneDrive / SharePoint | `/onedrive-setup` | [OneDriveSetup.md](OneDriveSetup.md) |
| Amazon S3 | Configured via settings | [AmazonS3Setup.md](AmazonS3Setup.md) |
| Evernote | Configured via settings | [EvernoteSetup.md](EvernoteSetup.md) |

These pages are accessed **after** the main Setup Wizard is complete and are independent wizard flows specific to each integration.

---

## Advanced: Settings Management

All non-bootstrap settings configured through the wizard can be updated at any time through the Settings page (`/settings`). They are stored in the database and take precedence over corresponding environment values. `DATABASE_URL`, `SESSION_SECRET`, and provider-wide OAuth app credentials remain deployment-managed bootstrap values.

For the full list of every available configuration parameter, see the [Configuration Guide](ConfigurationGuide.md).

> **Precedence order for non-bootstrap settings:** Database value → Environment variable → Default

### Live configuration contract for workers

- The database is authoritative for settings and personal integrations.
- Saving a global setting updates the database and bumps `docuelevate:settings_version` in Redis.
- Before every Celery task, a worker compares that version and reloads global settings when it changed.
- If Redis is unavailable, the worker reloads directly from the database before the task. Redis is only an invalidation accelerator.
- Personal integrations are loaded by ID from the database at the beginning of every job; credentials are decrypted only inside the worker process. A reauthorization or edited folder therefore affects the next job without restarting any process.
- Adding a completely new configuration field still requires a code/schema deployment so API and worker agree on its meaning. Changing its value after deployment does not require a restart.
