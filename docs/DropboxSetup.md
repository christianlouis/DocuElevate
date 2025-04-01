# Setting up Dropbox Integration

This guide explains how to set up the Dropbox integration for DocuNova.

## Required Configuration Parameters

| **Variable**            | **Description**                                  |
|-------------------------|--------------------------------------------------|
| `DROPBOX_APP_KEY`       | Dropbox API app key                              |
| `DROPBOX_APP_SECRET`    | Dropbox API app secret                           |
| `DROPBOX_REFRESH_TOKEN` | OAuth2 refresh token for Dropbox                 |
| `DROPBOX_FOLDER`        | Default folder path for Dropbox uploads          |

For a complete list of configuration options, see the [Configuration Guide](ConfigurationGuide.md).

## Step-by-Step Setup Instructions

### 1. Create a Dropbox App

1. Go to the [Dropbox Developer Apps Console](https://www.dropbox.com/developers/apps)
2. Click "Create app"
3. Select "Scoped access" for API
4. Choose "Full Dropbox" access (or "App folder" for more restricted access)
5. Give your app a name (e.g., "DocuNova")
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

### 6. Configure DocuNova

1. Set `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, and `DROPBOX_REFRESH_TOKEN` with your values
2. Set `DROPBOX_FOLDER` to the path where files should be uploaded (e.g., `/Documents/Uploads`)

The system will use the refresh token to automatically generate short-lived access tokens when needed, so you shouldn't need to worry about token expiration.
