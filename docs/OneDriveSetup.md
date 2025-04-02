# Setting up OneDrive Integration

This guide explains how to set up the Microsoft OneDrive integration for DocuNova.

## Required Configuration Parameters

| **Variable**                    | **Description**                                       |
|---------------------------------|-------------------------------------------------------|
| `ONEDRIVE_CLIENT_ID`            | Azure AD application client ID                        |
| `ONEDRIVE_CLIENT_SECRET`        | Azure AD application client secret                    |
| `ONEDRIVE_TENANT_ID`            | Azure AD tenant ID: use "common" for personal accounts or your tenant ID for corporate accounts |
| `ONEDRIVE_REFRESH_TOKEN`        | OAuth 2.0 refresh token (required for personal accounts) |
| `ONEDRIVE_FOLDER_PATH`          | Folder path in OneDrive for storing documents         |

For a complete list of configuration options, see the [Configuration Guide](ConfigurationGuide.md).

## Setup Methods

You can set up OneDrive integration in two ways:

1. **Using the Auth Wizard (Recommended)**: An interactive setup experience available at `/onedrive-setup` in the web interface
2. **Manual Setup**: Following the step-by-step instructions in this document

## Using the Auth Wizard

The easiest way to set up OneDrive integration is to use the built-in auth wizard:

1. Register an application in Azure AD (see steps below)
2. Navigate to the OneDrive Setup page at `/onedrive-setup`
3. Enter your Client ID and other required information
4. Click "Start Authentication Flow"
5. Complete the Microsoft authentication process
6. The system will automatically exchange the authorization code for a refresh token
7. Copy the generated environment variables for your worker nodes

The auth wizard handles all the token exchange steps and provides you with the exact configuration needed for your environment.

## Types of Microsoft Accounts

There are two main types of Microsoft accounts that can be used with OneDrive integration:

1. **Personal Microsoft Accounts** - These include accounts with @outlook.com, @hotmail.com, @live.com domains, or personal Microsoft accounts linked to other email addresses (like Gmail)
2. **Work/School Microsoft Accounts** - These are accounts managed by an organization through Microsoft 365 or Azure Active Directory

The setup process differs slightly based on which account type you're using.

## Common Setup Steps (All Account Types)

### 1. Register an application in Azure Active Directory

1. Go to the [Azure Portal](https://portal.azure.com/)
2. Navigate to "Azure Active Directory" > "App registrations"
3. Click "New registration"
4. Enter a name for your application (e.g., "DocuNova")
5. For "Supported account types", select the appropriate option:
   - For personal accounts: "Accounts in any organizational directory and personal Microsoft accounts"
   - For corporate accounts only: "Accounts in this organizational directory only"
6. For Redirect URI, select "Web" and enter your callback URL:
   - For auth wizard: `https://your-domain.com/onedrive-callback`
   - For manual setup: any URL you can access (e.g., `http://localhost:8000/auth/callback`)
7. Click "Register"

### 2. Get Application (client) ID

1. After registration, note the "Application (client) ID" from the overview page
2. Set this value as `ONEDRIVE_CLIENT_ID`

### 3. Create a client secret

1. In your application page, go to "Certificates & secrets"
2. Under "Client secrets," click "New client secret"
3. Add a description and select an expiration period
4. Click "Add" and immediately copy the secret value (it will only be shown once)
5. Set this value as `ONEDRIVE_CLIENT_SECRET`

### 4. Configure API permissions

1. In your application page, go to "API permissions"
2. Click "Add a permission"
3. Select "Microsoft Graph" > "Delegated permissions"
4. Search for and add the following permission:
   - `Files.ReadWrite` (Allows the app to read and write files that the user has access to)
   - `offline_access` (Required for refresh tokens)
5. If using application permissions (for service accounts), add:
   - `Files.ReadWrite.All` (Required for app-only access)
6. Click "Add permissions"
7. For organizational accounts, you may need an admin to "Grant admin consent"

> **Important Scope Change**: The system now uses the `.default` scope during authentication, which requests all permissions that have been granted to the application. This ensures that the app has all required permissions at once, rather than requesting each scope individually.

## For Personal Microsoft Accounts

If you're using a personal Microsoft account (@outlook.com, @hotmail.com, or personal accounts linked to other emails):

### 1. Set Tenant ID to "common"

- Set `ONEDRIVE_TENANT_ID=common` in your configuration

### 2. Generate a Refresh Token

#### Using the Auth Wizard (Recommended)
1. Navigate to the OneDrive Setup page at `/onedrive-setup`
2. Enter your Client ID and leave Tenant ID as "common"
3. Click "Start Authentication Flow" and follow the prompts
4. The wizard will handle token exchange automatically

#### Manual Method
1. Use the following URL (replace CLIENT_ID and REDIRECT_URI with your values):
   ```
   https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=YOUR_REDIRECT_URI&response_mode=query&scope=https://graph.microsoft.com/.default offline_access&prompt=consent
   ```
2. Open this URL in your browser
3. Sign in with your personal Microsoft account
4. After authentication, you'll be redirected to your redirect URI with a code parameter in the URL
5. Copy the code value from the URL (everything after "code=")

### 3. Exchange Code for Refresh Token (Manual Method Only)

1. Use the following command to exchange the code for tokens:
   ```bash
   curl -X POST https://login.microsoftonline.com/common/oauth2/v2.0/token \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "client_id=YOUR_CLIENT_ID&scope=https://graph.microsoft.com/.default offline_access&code=YOUR_AUTH_CODE&redirect_uri=YOUR_REDIRECT_URI&grant_type=authorization_code&client_secret=YOUR_CLIENT_SECRET"
   ```
2. From the response JSON, copy the `refresh_token` value
3. Set this as `ONEDRIVE_REFRESH_TOKEN` in your configuration

## For Corporate Microsoft Accounts

If you're using a work/school account provided by your organization:

### 1. Get your Tenant ID

1. In the Azure Portal, find your "Tenant ID" (also called "Directory ID")
2. It will be in the Azure Active Directory overview or properties section
3. Set this value as `ONEDRIVE_TENANT_ID` in your configuration

### 2. Configuration based on use case

**Option A: Access your own OneDrive (Interactive Login)**
   
This option requires a refresh token:
1. Use the auth wizard with your tenant ID, or
2. Follow the same manual steps as for personal accounts, but use your work email to sign in
3. Make sure to set `ONEDRIVE_TENANT_ID` to your organization's tenant ID instead of "common"
4. Set the refresh token you receive as `ONEDRIVE_REFRESH_TOKEN`

**Option B: Access OneDrive as a system service (App-only access)**
   
This option is for service accounts or automated systems with no user interaction:
1. In API permissions, add "Application permissions" instead of "Delegated permissions"
2. Add `Files.ReadWrite.All` permission under "Application permissions"
3. Click "Grant admin consent" (requires admin privileges)
4. In this case, `ONEDRIVE_REFRESH_TOKEN` is not needed as the app will use client credentials flow
5. Note: This approach can only access specific shared folders or sites, not personal OneDrives

## Troubleshooting OAuth Login Issues

If you encounter errors during authentication:

1. **Check account permissions**: 
   - Ensure your Microsoft account has the necessary permissions to grant access
   - For corporate accounts, check if your admin has restricted third-party app access

2. **Permission errors**: 
   - Verify the app registration has the correct API permissions
   - For corporate accounts, ensure an admin has consented to the permissions

3. **Refresh token expired**: 
   - If uploads stop working, you can generate a new refresh token using the auth wizard
   - Click on "Refresh Token" in the OneDrive setup page

4. **Scope issues**:
   - If you see permission errors, make sure your app has the correct permissions added
   - The `.default` scope is now used, which includes all permissions granted to the app
   - Check that both `Files.ReadWrite` and `offline_access` permissions are added to your app

## Configuration Examples

**Personal Microsoft Account:**
```dotenv
ONEDRIVE_CLIENT_ID=12345678-1234-1234-1234-123456789012
ONEDRIVE_CLIENT_SECRET=your_client_secret
ONEDRIVE_TENANT_ID=common
ONEDRIVE_REFRESH_TOKEN=your_refresh_token
ONEDRIVE_FOLDER_PATH=Documents/Uploads
```

**Corporate Account with Interactive Login:**
```dotenv
ONEDRIVE_CLIENT_ID=12345678-1234-1234-1234-123456789012
ONEDRIVE_CLIENT_SECRET=your_client_secret
ONEDRIVE_TENANT_ID=87654321-4321-4321-4321-210987654321
ONEDRIVE_REFRESH_TOKEN=your_refresh_token
ONEDRIVE_FOLDER_PATH=Documents/Uploads
```

**Corporate Account with App-Only Access:**
```dotenv
ONEDRIVE_CLIENT_ID=12345678-1234-1234-1234-123456789012
ONEDRIVE_CLIENT_SECRET=your_client_secret
ONEDRIVE_TENANT_ID=87654321-4321-4321-4321-210987654321
# No refresh token needed for app-only access
ONEDRIVE_FOLDER_PATH=Documents/Uploads
```
