# Setting up System Notifications

This guide explains how to set up the notification system for DocuElevate, which allows you to receive alerts about important system events.

## Required Configuration Parameters

| **Variable**                | **Description**                                           |
|----------------------------|----------------------------------------------------------|
| `NOTIFICATION_URLS`        | Comma-separated list of Apprise notification URLs         |
| `NOTIFY_ON_TASK_FAILURE`   | Send notifications on task failures (`True`/`False`)     |
| `NOTIFY_ON_CREDENTIAL_FAILURE` | Send notifications on credential failures (`True`/`False`) |
| `NOTIFY_ON_STARTUP`        | Send notification when system starts (`True`/`False`)    |
| `NOTIFY_ON_SHUTDOWN`       | Send notification when system shuts down (`True`/`False`)|

For a complete list of configuration options, see the [Configuration Guide](ConfigurationGuide.md).

## Overview

DocuElevate uses the Apprise library to provide a flexible notification system that supports over 70 different notification services, including:

- Email
- SMS
- Messaging apps (Telegram, Discord, Slack, Matrix, etc.)
- Push notification services (Pushover, Pushbullet, etc.)
- Web hooks
- And many more

## Setting up Notifications

### 1. Choose Your Notification Services

First, decide which notification services you want to use. The Apprise library supports a wide range of services, each with its own URL format. Here are some common examples:

- **Discord**: `discord://webhook_id/webhook_token`
- **Telegram**: `tgram://bot_token/chat_id`
- **Email**: `mailto://user:pass@example.com`
- **Pushover**: `pover://user_key/app_token`
- **Slack**: `slack://tokenA/tokenB/tokenC`
- **Matrix**: `matrix://username:password@domain/#room`
- **Microsoft Teams**: `msteams://token_a/token_b/token_c`
- **Gotify**: `gotify://hostname/token`

For a complete list of supported services and their URL formats, see the [Apprise Wiki](https://github.com/caronc/apprise/wiki).

### 2. Configure Your Notification URLs

Set the `NOTIFICATION_URLS` environment variable with a comma-separated list of your notification service URLs:

```dotenv
NOTIFICATION_URLS=discord://webhook_id/webhook_token,mailto://user:pass@gmail.com,tgram://bot_token/chat_id
```

You can specify as many notification services as you need.

### 3. Configure Notification Triggers

DocuElevate can send notifications for various system events. Configure which events should trigger notifications:

```dotenv
NOTIFY_ON_TASK_FAILURE=True        # Notify when background tasks fail
NOTIFY_ON_CREDENTIAL_FAILURE=True  # Notify when service credentials fail (e.g. API token expired)
NOTIFY_ON_STARTUP=True             # Notify when the system starts
NOTIFY_ON_SHUTDOWN=False           # Notify when the system shuts down
```

## Automated Credential Checking

DocuElevate includes a powerful credential monitoring system that regularly checks the validity of your configured service credentials. This helps you proactively address authentication issues before they affect your document processing workflows.

### How Credential Checking Works

1. **Regular Monitoring**: The system automatically checks all configured service credentials at regular intervals (every 5 minutes) and at startup.

2. **Smart Notifications**: When credential failures are detected, the system sends notifications through your configured notification channels.

3. **Notification Rate Limiting**: To prevent notification spam, alerts follow a progressive notification strategy:
   - First 3 failures: Notification sent for each failure
   - Subsequent failures: Notifications suppressed until credential is restored
   - Recovery: Notification sent when credentials are working again

4. **Services Monitored**:
   - OpenAI API
   - Azure Document Intelligence
   - Dropbox
   - Google Drive
   - OneDrive/Microsoft Graph
   - Other configured storage providers

### Notification Content

When a credential failure is detected, the notification includes:
- The affected service name
- The specific error message
- A reminder to check and update credentials

Example notification:
```
Subject: Credential Failure: Dropbox

The credentials for Dropbox have failed:
Invalid refresh token: Token has been revoked or expired.

Please check and update the credentials in the system settings.
```

### Configuration Options

To control credential check notifications:

```dotenv
# Enable/disable credential failure notifications
NOTIFY_ON_CREDENTIAL_FAILURE=True
```

When set to `False`, the system will still perform the checks but won't send notifications about failures.

### Troubleshooting Credential Issues

If you receive credential failure notifications:

1. **Check token expiration**: For OAuth-based services (Google Drive, OneDrive, Dropbox), refresh tokens may have expired.

2. **Verify API keys**: Ensure your API keys for services like OpenAI and Azure Document Intelligence are still valid.

3. **Check service status**: The service itself might be experiencing downtime.

4. **Review quota limits**: Some services have usage quotas that might have been exceeded.

5. **Regenerate credentials**: Use the built-in auth wizards to generate new tokens:
   - Go to Settings > [Service Name] Setup
   - Click "Refresh Token" or "Start Authentication Flow"
   - Complete the authentication process to generate new credentials

### Viewing Credential Status

You can view the current status of your service credentials in the system dashboard:

1. Navigate to the Status page in the DocuElevate interface
2. Check the Service Status section
3. Each service will show its current status (Valid, Invalid, or Not Configured)

## Service-Specific Setup Instructions

### Discord Notifications

1. Go to your Discord server
2. Select a channel or create a new one for notifications
3. Go to Server Settings > Integrations > Webhooks
4. Click "New Webhook" and set up a webhook for your channel
5. Copy the webhook URL (it will look like `https://discord.com/api/webhooks/123456789/abcdefg`)
6. Extract the webhook ID and token (the parts after `webhooks/`)
7. Format your Apprise URL as: `discord://123456789/abcdefg`

### Telegram Notifications

1. Start a chat with [@BotFather](https://t.me/botfather) on Telegram
2. Create a new bot using the `/newbot` command
3. Note the bot token provided by BotFather
4. Start a chat with your new bot or add it to a group
5. Get the chat ID:
   - For direct messages: send a message to the bot, then visit `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - For group chats: add the bot to the group, send a message mentioning the bot, then check the same URL
6. Format your Apprise URL as: `tgram://bot_token/chat_id`

### Email Notifications

To send notifications via email, configure the Apprise URL with your SMTP server details:

```
# Gmail example
mailto://your-email@gmail.com:password@smtp.gmail.com?smtp=587
```

For Gmail, you'll need to use an app password if you have 2FA enabled.

## Task Failure Notifications

In addition to credential monitoring, DocuElevate can notify you about background task failures. When enabled, the system will send notifications whenever a background processing task encounters an error.

To configure task failure notifications:

```dotenv
# Enable/disable task failure notifications
NOTIFY_ON_TASK_FAILURE=True
```

Task failure notifications include:
- Task name and ID
- Error type and message
- Task arguments (for debugging)

## Testing Your Notification Setup

To test your notification setup once configured:

1. Start the DocuElevate application
2. If `NOTIFY_ON_STARTUP=True`, you should receive a notification when the system starts
3. Check the application logs for any errors related to notifications

## Security Considerations

When setting up notifications:

1. **Protect your credentials**: Keep your notification URLs secure, as they often contain access tokens or passwords.
2. **Use environment variables**: Store notification URLs in environment variables rather than hard-coding them.
3. **Limit notification content**: Be mindful of sending sensitive information in notifications.
4. **Consider encryption**: For highly sensitive environments, consider using encrypted notification channels.

## Troubleshooting

If you're not receiving notifications:

1. **Check service connectivity**: Ensure the DocuElevate server can access the notification services.
2. **Verify URL format**: Double-check the format of your notification URLs.
3. **Check application logs**: Look for errors related to the notification system in logs.
4. **Test services individually**: Try configuring one notification service at a time to isolate issues.
5. **Check service-specific limits**: Some services have rate limits on notifications.

For more general configuration issues, see the [Configuration Troubleshooting Guide](ConfigurationTroubleshooting.md).
