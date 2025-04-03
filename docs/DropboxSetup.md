# Setting up Dropbox Integration

This guide explains how to set up the Dropbox integration for DocuElevate.

## Required Configuration Parameters

| **Variable**            | **Description**                                  | 
|-------------------------|--------------------------------------------------|
| `DROPBOX_APP_KEY`       | Dropbox API app key                              |
| `DROPBOX_APP_SECRET`    | Dropbox API app secret                           |
| `DROPBOX_REFRESH_TOKEN` | OAuth2 refresh token for Dropbox                 |
| `DROPBOX_FOLDER`        | Default folder path for Dropbox uploads          |

For a complete list of configuration options, see the [Configuration Guide](ConfigurationGuide.md).

## Setup Methods

You can set up Dropbox integration in two ways:

1. **Using the Built-in Setup Wizard (Recommended)**: An interactive setup experience available at `/dropbox-setup` in the web interface
2. **Manual Setup**: Following the step-by-step instructions in this document

## Using the Setup Wizard

The easiest way to set up Dropbox integration is to use the built-in setup wizard:

1. Navigate to the `/dropbox-setup` page in your DocuElevate instance
2. Follow the on-screen instructions to create a Dropbox app
3. Enter your App Key and App Secret in the wizard
4. Optionally specify a custom folder path for uploads
5. Click "Start Authentication Flow" to begin the authorization process
6. Complete the Dropbox authentication process
7. The system will automatically exchange the authorization code for a refresh token
8. Copy the generated environment variables for your worker nodes

The wizard handles all the token exchange steps and provides you with the exact configuration needed for your environment.

## Step-by-Step Manual Setup Instructions

### 1. Create a Dropbox App

1. Go to the [Dropbox Developer Apps Console](https://www.dropbox.com/developers/apps)
2. Click "Create app"
3. Select "Scoped access" for API
4. Choose "Full Dropbox" access (or "App folder" for more restricted access)
5. Give your app a name (e.g., "DocuElevate")
6. Click "Create app"

### 2. Configure App Permissions

1. In your app's settings page, go to the "Permissions" tab
2. Enable the following permissions:
   - `files.content.write` (to upload files)
   - `files.content.read` (if you need to read file content)
3. Click "Submit" to save changes

### 3. Get App Key and Secret

1. On your app's settings page, find the "App key" and "App secret"
2. Set these as `DROPBOX_APP_KEY` and `DROPBOX_APP_SECRET` in your configuration

### 4. Generate a Refresh Token

1. Go to the "OAuth 2" tab in your app settings
2. Add a redirect URI: `http://localhost` (this is for the authorization flow)
3. Generate an authorization URL with these instructions:
   
   ```
   https://www.dropbox.com/oauth2/authorize?client_id=YOUR_APP_KEY&response_type=code&token_access_type=offline
   ```
   
4. Replace `YOUR_APP_KEY` with your app key
5. Open this URL in your browser
6. Authorize the app when prompted
7. You'll be redirected to `localhost` with a code parameter in the URL
8. Copy this code parameter

### 5. Exchange the Code for a Refresh Token

1. Use this curl command to exchange the code for tokens:
   
   ```bash
   curl -X POST https://api.dropboxapi.com/oauth2/token \
     -d code=YOUR_AUTH_CODE \
     -d grant_type=authorization_code \
     -d client_id=YOUR_APP_KEY \
     -d client_secret=YOUR_APP_SECRET \
     -d redirect_uri=http://localhost
   ```
   
2. From the response, copy the `refresh_token` value

### 6. Configure DocuElevate

1. Set `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, and `DROPBOX_REFRESH_TOKEN` with your values
2. Set `DROPBOX_FOLDER` to the path where files should be uploaded (e.g., `/Documents/Uploads`)

## Token Management

The system will use the refresh token to automatically generate short-lived access tokens when needed. Refresh tokens typically don't expire unless revoked.

### Testing Your Token

You can test if your token is working correctly:

1. Navigate to the `/dropbox-setup` page in your DocuElevate instance
2. Click the "Test Token" button to verify your credentials
3. If the test fails, click "Refresh Token" to obtain a new refresh token

## Troubleshooting

If you encounter issues with Dropbox integration:

1. **Authentication Errors**: Make sure your App Key and App Secret are correct
2. **Token Expired**: Click "Refresh Token" button on the setup page to obtain a new token
3. **Folder Permissions**: Ensure your app has the correct permissions enabled for file operations
4. **Invalid Redirect URI**: Verify that the redirect URI in your app settings matches the one used in the authentication flow
5. **Rate Limiting**: Dropbox API has rate limits; if exceeded, wait and try again

For more general configuration issues, see the [Configuration Troubleshooting Guide](ConfigurationTroubleshooting.md).
