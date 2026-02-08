# Settings Management Guide

## Overview

DocuElevate now supports managing application settings through a web-based GUI. Settings can be configured, saved to the database, and will persist across application restarts with the following precedence:

**Database > Environment Variables > Defaults**

## Accessing the Settings Page

1. Navigate to `/settings` in your web browser
2. **Admin access required** - Only users with admin privileges can access this page
3. For local authentication: Use the admin username/password configured in environment variables
4. For OAuth/SSO: Users must be in the "admin" or "administrators" group

## Features

### Settings Organization

Settings are organized into logical categories for easy navigation:

- **Core**: Database, Redis, working directory, external hostname, debug mode
- **Authentication**: Login settings, session secrets, OAuth configuration
- **AI Services**: OpenAI and Azure AI configuration
- **Storage Providers**: Dropbox, Google Drive, OneDrive, S3, FTP, SFTP, WebDAV, Nextcloud, Paperless
- **Email**: SMTP configuration for sending emails
- **IMAP**: Email ingestion configuration (supports multiple accounts)
- **Monitoring**: Uptime Kuma integration
- **Notifications**: Apprise notification URLs and settings
- **Processing**: Batch processing and HTTP timeout settings
- **Feature Flags**: Enable/disable specific features

### Setting Types

- **String**: Text values (API keys, URLs, paths)
- **Boolean**: True/false toggles (enable/disable features)
- **Integer**: Numeric values (ports, timeouts, thresholds)
- **List**: Comma-separated values (notification URLs)

### Sensitive Data

Settings marked as sensitive (passwords, API keys, tokens) are:
- Masked in the UI by default (show ****key)
- Can be revealed temporarily using the eye icon
- Encrypted in session storage
- Never logged in plain text

### Restart Requirements

Settings are marked with 🔄 or a red asterisk (*) if they require an application restart to take effect. This includes:
- Database and Redis URLs
- Working directory
- Authentication settings
- Debug mode

Most runtime settings (API keys, storage credentials) can be changed without restarting.

## Using the Settings Page

### Viewing Settings

1. Navigate to `/settings`
2. Browse categories using the expandable sections
3. Each setting shows:
   - **Name**: The setting key
   - **Description**: What the setting does
   - **Current Value**: The active value (masked if sensitive)
   - **Type**: String, boolean, integer, or list
   - **Required**: Whether the setting must be configured
   - **Restart Required**: Whether changing this setting requires a restart

### Updating Settings

1. Modify the desired settings in the form
2. Click "Save Settings" at the bottom of the page
3. Settings are validated before saving
4. Success/error messages are displayed
5. If any changed setting requires a restart, you'll be notified

### Bulk Updates

The settings page supports updating multiple settings at once:
- Change as many settings as needed
- Click "Save Settings" once
- All valid changes are applied atomically
- Any validation errors are reported individually

### Resetting Changes

Click "Reset" to discard unsaved changes and return to the current values.

## API Endpoints

Settings can also be managed programmatically (admin auth required):

### Get All Settings
```bash
GET /api/settings/
```

Returns all settings with their metadata and current values.

### Get Specific Setting
```bash
GET /api/settings/{key}
```

Returns a single setting's value and metadata.

### Update Setting
```bash
POST /api/settings/{key}
{
  "key": "debug",
  "value": "true"
}
```

Updates a single setting. Returns whether a restart is required.

### Delete Setting
```bash
DELETE /api/settings/{key}
```

Removes a setting from the database (reverts to environment variable or default).

### Bulk Update
```bash
POST /api/settings/bulk-update
[
  {"key": "debug", "value": "true"},
  {"key": "openai_model", "value": "gpt-4"}
]
```

Updates multiple settings in one request.

## Settings Precedence

DocuElevate loads settings in this order (later sources override earlier ones):

1. **Defaults**: Hard-coded defaults in `app/config.py`
2. **Environment Variables**: From `.env` file or system environment
3. **Database**: Settings saved through the UI or API

### Example

If you have:
- Default: `debug = false`
- Environment: `DEBUG=true` in `.env`
- Database: `debug = false` (saved via UI)

The application will use `debug = false` (database wins).

## Database Storage

Settings are stored in the `application_settings` table with:
- `key`: Unique setting identifier
- `value`: Setting value (stored as string, converted on load)
- `created_at`: When the setting was first saved
- `updated_at`: When the setting was last modified

## Security Considerations

1. **Admin Access Only**: Settings page requires admin privileges
2. **Sensitive Data Masking**: Passwords and keys are masked in the UI
3. **Input Validation**: All setting values are validated before saving
4. **Audit Trail**: Database tracks when settings were created/updated
5. **Session Security**: Admin sessions require strong session secrets (min 32 chars)

## Troubleshooting

### Can't Access Settings Page

- **Check authentication**: Make sure you're logged in
- **Check admin status**: 
  - Local auth: Verify `ADMIN_USERNAME` and `ADMIN_PASSWORD` are correct
  - OAuth: Verify your user is in the admin group
- **Check logs**: Look for "Non-admin user attempted to access settings page" messages

### Settings Not Taking Effect

- **Check restart requirement**: Some settings require app restart
- **Check precedence**: Database settings override environment variables
- **Check validation**: Invalid values may not be saved (check error messages)
- **Check logs**: Application startup logs show which settings were loaded from database

### Settings Not Persisting

- **Check database**: Verify `DATABASE_URL` is configured correctly
- **Check permissions**: Ensure application can write to database
- **Check errors**: Look for SQLAlchemy errors in logs

## Development

### Adding New Settings

1. Add the setting to `app/config.py` in the `Settings` class
2. Add metadata to `SETTING_METADATA` in `app/utils/settings_service.py`
3. Include:
   - `category`: Logical grouping
   - `description`: Clear explanation
   - `type`: string, boolean, integer, or list
   - `sensitive`: True for secrets/passwords
   - `required`: True if the setting must be configured
   - `restart_required`: True if app restart needed

### Testing

Run the settings tests:
```bash
pytest tests/test_settings.py -v
```

Or run integration tests:
```bash
python3 test_integration.py
```

## Related Documentation

- [Configuration Guide](./ConfigurationGuide.md) - Environment variable reference
- [Deployment Guide](./DeploymentGuide.md) - Production deployment  
- [API Documentation](./API.md) - Full API reference
