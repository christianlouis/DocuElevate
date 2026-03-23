# Setting up SharePoint Integration

This guide explains how to set up the Microsoft SharePoint Online integration for DocuElevate.

## Required Configuration Parameters

| **Variable**                    | **Description**                                       |
|---------------------------------|-------------------------------------------------------|
| `SHAREPOINT_CLIENT_ID`          | Azure AD application client ID                        |
| `SHAREPOINT_CLIENT_SECRET`      | Azure AD application client secret                    |
| `SHAREPOINT_TENANT_ID`          | Azure AD tenant ID (use "common" for multi-tenant apps) |
| `SHAREPOINT_REFRESH_TOKEN`      | OAuth 2.0 refresh token                               |
| `SHAREPOINT_SITE_URL`           | SharePoint site URL (e.g. `https://tenant.sharepoint.com/sites/sitename`) |
| `SHAREPOINT_DOCUMENT_LIBRARY`   | Document library name (default: `Documents`)          |
| `SHAREPOINT_FOLDER_PATH`        | Subfolder path inside the document library            |

For a complete list of configuration options, see the [Configuration Guide](ConfigurationGuide.md).

## Overview

SharePoint Online integration uses the same Microsoft Graph API as OneDrive. The key difference is that SharePoint targets a **site-specific document library** rather than a personal OneDrive. Documents are uploaded via chunked upload sessions for reliability with large files.

> **Tip:** If you already have an Azure AD app registration for OneDrive, you can reuse it for SharePoint — just add the `Sites.ReadWrite.All` permission.

## Setup Steps

### 1. Register an application in Azure Active Directory

If you don't already have an app registration (e.g. from OneDrive setup):

1. Go to the [Azure Portal](https://portal.azure.com/)
2. Navigate to **Azure Active Directory** > **App registrations**
3. Click **New registration**
4. Enter a name for your application (e.g., "DocuElevate")
5. For **Supported account types**, select:
   - **Single tenant**: "Accounts in this organizational directory only"
   - **Multi-tenant**: "Accounts in any organizational directory"
6. For **Redirect URI**, select "Web" and enter your callback URL (e.g., `https://your-domain.com/onedrive-callback`)
7. Click **Register**

### 2. Get Application (client) ID

1. After registration, note the **Application (client) ID** from the overview page
2. Set this value as `SHAREPOINT_CLIENT_ID`

### 3. Create a client secret

1. In your application page, go to **Certificates & secrets**
2. Under **Client secrets**, click **New client secret**
3. Add a description and select an expiration period
4. Click **Add** and immediately copy the secret value (it will only be shown once)
5. Set this value as `SHAREPOINT_CLIENT_SECRET`

### 4. Configure API permissions

1. In your application page, go to **API permissions**
2. Click **Add a permission**
3. Select **Microsoft Graph**
4. For **delegated permissions** (user-context access), add:
   - `Sites.ReadWrite.All` — Read and write items in all site collections
   - `offline_access` — Required for refresh tokens
5. For **application permissions** (app-only access without a user), add:
   - `Sites.ReadWrite.All` — Read and write items in all site collections
6. Click **Add permissions**
7. Click **Grant admin consent** (requires admin privileges)

> **Important:** SharePoint access requires `Sites.ReadWrite.All` rather than the `Files.ReadWrite` permission used by OneDrive.

### 5. Get your Tenant ID

1. In the Azure Portal, find your **Tenant ID** (also called "Directory ID")
2. It is on the **Azure Active Directory** overview page
3. Set this value as `SHAREPOINT_TENANT_ID`

### 6. Generate a Refresh Token

#### Using the OneDrive Auth Wizard

The SharePoint integration reuses the same MSAL token flow as OneDrive:

1. Navigate to `/onedrive-setup`
2. Enter your SharePoint Client ID and Tenant ID
3. Click **Start Authentication Flow** and follow the prompts
4. Copy the generated refresh token and set it as `SHAREPOINT_REFRESH_TOKEN`

#### Manual Method

1. Open the following URL in your browser (replace placeholders):
   ```
   https://login.microsoftonline.com/YOUR_TENANT_ID/oauth2/v2.0/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=YOUR_REDIRECT_URI&response_mode=query&scope=https://graph.microsoft.com/.default offline_access&prompt=consent
   ```
2. Sign in with your Microsoft work account
3. After authentication, copy the `code` parameter from the redirect URL
4. Exchange the code for tokens:
   ```bash
   curl -X POST https://login.microsoftonline.com/YOUR_TENANT_ID/oauth2/v2.0/token \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "client_id=YOUR_CLIENT_ID&scope=https://graph.microsoft.com/.default offline_access&code=YOUR_AUTH_CODE&redirect_uri=YOUR_REDIRECT_URI&grant_type=authorization_code&client_secret=YOUR_CLIENT_SECRET"
   ```
5. From the response JSON, copy the `refresh_token` value
6. Set this as `SHAREPOINT_REFRESH_TOKEN`

### 7. Find your SharePoint Site URL

Your SharePoint site URL follows the pattern:
```
https://YOUR-TENANT.sharepoint.com/sites/SITE-NAME
```

For example:
- `https://contoso.sharepoint.com/sites/documents`
- `https://contoso.sharepoint.com/sites/engineering-team`

Set this as `SHAREPOINT_SITE_URL`.

### 8. Choose your Document Library

Each SharePoint site has one or more document libraries. The default library is usually called `Documents` (or `Shared Documents`). You can find your library names by navigating to your SharePoint site in a browser and looking at the left sidebar.

Set the library name as `SHAREPOINT_DOCUMENT_LIBRARY` (default: `Documents`).

### 9. Set the Upload Folder (Optional)

If you want documents to be uploaded into a subfolder inside the library, set `SHAREPOINT_FOLDER_PATH`. For example, `Uploads` or `DocuElevate/Processed`.

## App-Only Access (No User Token)

For fully automated scenarios without user interaction:

1. Add **Application permissions** (not Delegated) for `Sites.ReadWrite.All`
2. Grant admin consent
3. Set `SHAREPOINT_TENANT_ID` to your organization's tenant ID
4. Leave `SHAREPOINT_REFRESH_TOKEN` empty — the app will use the client credentials flow

> **Note:** Client credentials flow requires a specific tenant ID (not "common").

## Configuration Examples

**With Refresh Token (Delegated Permissions):**
```dotenv
SHAREPOINT_CLIENT_ID=12345678-1234-1234-1234-123456789012
SHAREPOINT_CLIENT_SECRET=your_client_secret
SHAREPOINT_TENANT_ID=87654321-4321-4321-4321-210987654321
SHAREPOINT_REFRESH_TOKEN=your_refresh_token
SHAREPOINT_SITE_URL=https://contoso.sharepoint.com/sites/documents
SHAREPOINT_DOCUMENT_LIBRARY=Documents
SHAREPOINT_FOLDER_PATH=Uploads
```

**App-Only Access (Application Permissions):**
```dotenv
SHAREPOINT_CLIENT_ID=12345678-1234-1234-1234-123456789012
SHAREPOINT_CLIENT_SECRET=your_client_secret
SHAREPOINT_TENANT_ID=87654321-4321-4321-4321-210987654321
# No refresh token needed for app-only access
SHAREPOINT_SITE_URL=https://contoso.sharepoint.com/sites/documents
SHAREPOINT_DOCUMENT_LIBRARY=Shared Documents
SHAREPOINT_FOLDER_PATH=DocuElevate/Processed
```

## Troubleshooting

### "Failed to resolve SharePoint site"

- Verify `SHAREPOINT_SITE_URL` is correct and accessible
- Ensure your app has `Sites.ReadWrite.All` permission with admin consent
- Check that the site exists and your account has access to it

### "Document library not found"

- Verify the library name in `SHAREPOINT_DOCUMENT_LIBRARY` matches exactly (case-insensitive)
- Navigate to your SharePoint site in a browser to confirm the library name
- Common names: `Documents`, `Shared Documents`

### Token errors

- If using a refresh token, try re-authorizing via the OAuth flow
- Ensure `offline_access` scope is included in your permissions
- For app-only access, verify the tenant ID is not set to "common"

### Permission errors

- Ensure an admin has granted consent for `Sites.ReadWrite.All`
- Verify the app registration has the correct permissions
- Check that the site's sharing settings allow API access
