# Setting up Google Drive Integration

This guide explains how to set up the Google Drive integration for DocuNova.

## Required Configuration Parameters

| **Variable**                    | **Description**                                       |
|---------------------------------|-------------------------------------------------------|
| `GOOGLE_DRIVE_CREDENTIALS_JSON` | JSON string containing service account credentials    |
| `GOOGLE_DRIVE_FOLDER_ID`        | Google Drive folder ID for file uploads               |
| `GOOGLE_DRIVE_DELEGATE_TO`      | Email address to delegate permissions (optional)      |

For a complete list of configuration options, see the [Configuration Guide](ConfigurationGuide.md).

## Step-by-Step Setup Instructions

### 1. Create a Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Navigate to "APIs & Services" > "Library"
4. Search for and enable the "Google Drive API"

### 2. Create Service Account

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "Service Account"
3. Fill in the service account details and click "Create"
4. Add appropriate roles (e.g., "Editor" for full access)
5. Click "Continue" and then "Done"

### 3. Generate Service Account Key

1. Find your service account in the list and click on it
2. Go to the "Keys" tab
3. Click "Add Key" > "Create New Key"
4. Choose JSON format and click "Create"
5. The key file will be downloaded automatically

### 4. Configure DocuNova

1. Open the downloaded JSON key file
2. Set the entire JSON content as the `GOOGLE_DRIVE_CREDENTIALS_JSON` environment variable
3. For security, ensure the JSON is properly escaped if your deployment method requires it

### Get Google Drive Folder ID

To find your Google Drive folder ID:

1. Navigate to the desired folder in Google Drive web interface
2. The URL will look like: `https://drive.google.com/drive/folders/1a2b3c4d5e6f7g8h9i0j`
3. The string after "folders/" is your folder ID (in this example: `1a2b3c4d5e6f7g8h9i0j`)
4. Set this value as `GOOGLE_DRIVE_FOLDER_ID` in your configuration

### Domain-Wide Delegation (Optional)

If you need the service account to access files on behalf of users in your Google Workspace:

1. In your [Google Workspace Admin Console](https://admin.google.com/), go to:
   - Security > API Controls > Domain-wide Delegation
2. Click "Add new" and provide:
   - Client ID: your service account's client ID (found in the JSON credentials file)
   - OAuth Scopes: `https://www.googleapis.com/auth/drive`
3. Set `GOOGLE_DRIVE_DELEGATE_TO` to the email address of the user to impersonate

This setup is only relevant for Google Workspace environments where you need the service account to access user-specific files.
