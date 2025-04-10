# Setting up Google Drive Integration

This guide explains how to set up the Google Drive integration for DocuElevate.

## Required Configuration Parameters

| **Variable**                    | **Description**                                       |
|---------------------------------|-------------------------------------------------------|
| `GOOGLE_DRIVE_USE_OAUTH`        | Set to `true` to use OAuth flow (recommended)         |
| `GOOGLE_DRIVE_CLIENT_ID`        | OAuth Client ID (required if using OAuth flow)        |
| `GOOGLE_DRIVE_CLIENT_SECRET`    | OAuth Client Secret (required if using OAuth flow)    |
| `GOOGLE_DRIVE_REFRESH_TOKEN`    | OAuth Refresh Token (required if using OAuth flow)    |
| `GOOGLE_DRIVE_FOLDER_ID`        | Google Drive folder ID for file uploads               |
| `GOOGLE_DRIVE_CREDENTIALS_JSON` | JSON string containing service account credentials (alternative method) |
| `GOOGLE_DRIVE_DELEGATE_TO`      | Email address to delegate permissions (optional for service accounts) |

For a complete list of configuration options, see the [Configuration Guide](ConfigurationGuide.md).

## Authentication Methods

DocuElevate supports two authentication methods for Google Drive:

1. **OAuth Authentication (Recommended)** - User-based authentication that provides better security and control. Recommended for most deployments.
2. **Service Account Authentication** - Server-to-server authentication that doesn't require user interaction. Useful for specific enterprise deployments.

## Method 1: OAuth Authentication Setup (Recommended)

The OAuth method is preferred as it:
- Provides better security with token expiration and refresh
- Integrates with personal Google accounts more seamlessly
- Doesn't require manual folder sharing
- Offers a streamlined setup process with our setup wizard

### 1. Create a Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Navigate to "APIs & Services" > "Library"
4. Search for and enable the "Google Drive API"

### 2. Configure OAuth Consent Screen

1. In "APIs & Services", go to "OAuth consent screen"
2. Select "External" user type (or "Internal" if this is for an organization)
3. Fill out the required application information:
   - App name: "DocuElevate" (or your preferred name)
   - User support email: Your email
   - Application homepage link: Your application URL
   - Authorized domains: Your domain
   - Developer contact information: Your email
4. Click "Save and Continue"
5. On the Scopes screen, click "Add or Remove Scopes" and add:
   - `https://www.googleapis.com/auth/drive.file` (allows access to files created or opened by the app)
6. Click "Save and Continue" through the rest of the setup

### 3. Create OAuth Credentials

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth client ID"
3. Select "Web application" for Application type
4. Add a name (e.g., "DocuElevate Web Client")
5. Under "Authorized JavaScript origins" add your application URL (e.g., `https://your-docuelevate-instance.com`)
6. Under "Authorized redirect URIs" add:
   - `https://your-docuelevate-instance.com/google-drive-callback`
7. Click "Create"
8. Note down your Client ID and Client Secret

### 4. Use the OAuth Setup Wizard

DocuElevate includes a built-in OAuth setup wizard that makes configuration simple:

1. Go to your DocuElevate instance and navigate to Settings > Google Drive Setup
2. Select the OAuth method tab (selected by default)
3. Enter your Client ID and Client Secret
4. Click "Start Authentication Flow"
5. Follow the prompts to authenticate and select a folder
6. The wizard will automatically save your settings and generate the required environment variables

### 5. Manual OAuth Configuration

If you prefer to set up OAuth manually, you'll need to:

1. Set `GOOGLE_DRIVE_USE_OAUTH=true` in your configuration
2. Set `GOOGLE_DRIVE_CLIENT_ID` and `GOOGLE_DRIVE_CLIENT_SECRET` from the credentials you created
3. Obtain a refresh token using OAuth2 authorization flow (outside the scope of this document)
4. Set `GOOGLE_DRIVE_REFRESH_TOKEN` with the obtained refresh token
5. Set `GOOGLE_DRIVE_FOLDER_ID` to your desired folder ID

## OAuth Token Expiration Notice

When using the OAuth method with Google Drive, there are important limitations to be aware of:

### Non-Verified Apps

If your Google Cloud project is not verified by Google (displayed as "unverified" during the OAuth consent screen):

- **Refresh tokens expire after 7 days** for test/development applications
- You will need to re-authenticate every 7 days
- The application will show "This app isn't verified" warning during authentication

This limitation primarily affects development environments. For production use, you should:

1. Complete the Google OAuth verification process
2. Submit your app for verification in the Google Cloud Console
3. Provide the required information including privacy policy and application testing instructions

### Verified Apps

Once your app is verified by Google:

- Refresh tokens remain valid until explicitly revoked
- Users won't see the "unverified app" warning
- You can request access to more sensitive scopes

For internal applications within your organization, consider using the Service Account method instead, which doesn't have the 7-day token expiration limitation.

## Folder Selection

DocuElevate provides two ways to select your Google Drive destination folder:

### 1. Web Interface Folder Picker

The DocuElevate web interface includes an integrated Google Drive folder picker that allows you to:

- Browse your Google Drive folders visually
- Select the destination folder through a user-friendly interface
- Automatically save the selected folder ID to your configuration

To use the folder picker:

1. Complete the OAuth authentication flow
2. On the Google Drive setup page, click the "Select Folder with Picker" button
3. Browse and select your desired folder in the popup window
4. The folder ID will be automatically filled in and saved

### 2. Manual Folder ID Entry

You can also manually specify the folder ID:

1. Navigate to the desired folder in Google Drive
2. Extract the folder ID from the URL: `https://drive.google.com/drive/folders/YOUR_FOLDER_ID`
3. Enter this ID in the "Folder ID" field in the DocuElevate setup page

For the root folder of your Google Drive, use `root` as the folder ID.

**Note:** The folder selector requires that you've already authenticated with OAuth. It's not available when using the Service Account method, as it requires user interaction.

## Method 2: Service Account Setup (Alternative)

Service accounts are useful for specific enterprise deployments where interactive login is not possible or when you need to access shared drives with domain-wide delegation.

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
6. Note down the service account's email address (it will look like: `service-name@project-id.iam.gserviceaccount.com`)

### 3. Generate Service Account Key

1. Find your service account in the list and click on it
2. Go to the "Keys" tab
3. Click "Add Key" > "Create New Key"
4. Choose JSON format and click "Create"
5. The key file will be downloaded automatically

### 4. Share Your Google Drive Folder with the Service Account

1. Navigate to the desired folder in Google Drive
2. Right-click on the folder and select "Share"
3. Enter the service account's email address that you noted down in step 2
4. Set the permission to "Editor" (to allow the service account to create/upload files)
5. Click "Send" to share the folder (you can uncheck "Notify people" as the service account won't receive emails)

### 5. Get Google Drive Folder ID

To find your Google Drive folder ID:

1. Navigate to the desired folder in Google Drive web interface
2. The URL will look like: `https://drive.google.com/drive/folders/1a2b3c4d5e6f7g8h9i0j`
3. The string after "folders/" is your folder ID (in this example: `1a2b3c4d5e6f7g8h9i0j`)
4. Set this value as `GOOGLE_DRIVE_FOLDER_ID` in your configuration

### 6. Configure DocuElevate

1. Open the downloaded JSON key file
2. Set the entire JSON content as the `GOOGLE_DRIVE_CREDENTIALS_JSON` environment variable
3. For security, ensure the JSON is properly escaped if your deployment method requires it
4. Make sure `GOOGLE_DRIVE_USE_OAUTH` is set to `false`

## Domain-Wide Delegation (Optional, for Service Accounts)

If you need the service account to access files on behalf of users in your Google Workspace:

1. In your [Google Workspace Admin Console](https://admin.google.com/), go to:
   - Security > API Controls > Domain-wide Delegation
2. Click "Add new" and provide:
   - Client ID: your service account's client ID (found in the JSON credentials file)
   - OAuth Scopes: `https://www.googleapis.com/auth/drive`
3. Set `GOOGLE_DRIVE_DELEGATE_TO` to the email address of the user to impersonate

This setup is only relevant for Google Workspace environments where you need the service account to access user-specific files.

## Troubleshooting

### Authentication Issues

- **Error: "The caller does not have permission"**
  - For OAuth: Make sure you're signed in with an account that has access to the folder
  - For Service Account: Ensure you've properly shared the target folder with the service account email
  - Check that you've enabled the Google Drive API in your project

- **Error: "Invalid credentials"**
  - For OAuth: Your tokens may have expired. Try refreshing authentication in the setup wizard
  - For Service Account: Verify that your JSON credentials are properly formatted and not corrupted
  - Check that the account has not been deleted or disabled

- **OAuth Errors**
  - Ensure your redirect URIs exactly match your application URL
  - Check that you've added the correct scopes
  - Make sure your OAuth consent screen is properly configured

### File Upload Issues

- **Error: "File not found"**
  - Verify your folder ID is correct
  - Make sure the folder still exists and hasn't been deleted

- **Error: "Insufficient permissions"**
  - For OAuth: Ensure you've granted the necessary permissions during authorization
  - For Service Account: Ensure the service account has "Editor" permissions on the folder

### Testing Your Setup

To test if your Google Drive integration is working:

1. Go to your DocuElevate instance and navigate to Settings > Google Drive Setup
2. Click the "Test Connection" button
3. If the test is successful, your integration is properly configured

For further assistance, see the [Troubleshooting Guide](Troubleshooting.md).
