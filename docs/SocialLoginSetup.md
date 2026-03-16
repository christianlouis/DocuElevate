# Social Login Setup Guide

This guide explains how to configure social login providers (Google, Microsoft, Apple, Dropbox) for DocuElevate. Social login lets your users sign in with their existing accounts, reducing friction and eliminating the need for separate passwords.

## Overview

DocuElevate supports four social login providers:

| Provider | Protocol | Best For |
|----------|----------|----------|
| **Google** | OAuth2 / OpenID Connect | Consumers and Google Workspace organizations |
| **Microsoft** | OAuth2 / OpenID Connect | Microsoft 365 / Azure AD organizations and personal Microsoft accounts |
| **Apple** | OAuth2 / OpenID Connect | iOS/macOS users, privacy-focused users |
| **Dropbox** | OAuth2 | Teams already using Dropbox as a storage destination |

Each provider is **independently enabled** — you can use one, several, or all of them at the same time. Social login works alongside any other DocuElevate authentication method (simple auth, OIDC/Authentik, local signup).

## Prerequisites

Before configuring any social login provider, ensure:

1. **Authentication is enabled**: `AUTH_ENABLED=true` in your `.env` file
2. **Session secret is set**: `SESSION_SECRET` must be a random string of at least 32 characters
3. **HTTPS is configured**: All social login providers require HTTPS redirect URIs in production. Use a reverse proxy (Traefik, Nginx, Caddy) with a valid TLS certificate
4. **External hostname is set**: `EXTERNAL_HOSTNAME` must match your public domain (e.g., `docuelevate.example.com`)

> **Note:** Social login users are regular (non-admin) users by default. To grant admin access, use the Admin Panel (**Settings → User Management**) after the user's first login, or configure admin groups via Authentik/OIDC.

## Callback URLs

Each social login provider uses a callback URL to redirect users back to DocuElevate after authentication. The callback URL pattern is:

```
https://<EXTERNAL_HOSTNAME>/social-callback/<provider>
```

For example, if your DocuElevate instance is at `https://docuelevate.example.com`:

| Provider | Callback URL |
|----------|-------------|
| Google | `https://docuelevate.example.com/social-callback/google` |
| Microsoft | `https://docuelevate.example.com/social-callback/microsoft` |
| Apple | `https://docuelevate.example.com/social-callback/apple` |
| Dropbox | `https://docuelevate.example.com/social-callback/dropbox` |

---

## Google Sign-In

### 1. Create OAuth Credentials in Google Cloud Console

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Navigate to **APIs & Services → Credentials**
4. Click **Create Credentials → OAuth client ID**
5. If prompted, configure the **OAuth consent screen** first:
   - **User Type**: External (or Internal for Google Workspace)
   - **App name**: DocuElevate
   - **User support email**: Your email
   - **Authorized domains**: Your domain (e.g., `example.com`)
   - **Scopes**: Add `email`, `profile`, and `openid`
6. Back on the Credentials page, create an **OAuth 2.0 Client ID**:
   - **Application type**: Web application
   - **Name**: DocuElevate
   - **Authorized redirect URIs**: `https://docuelevate.example.com/social-callback/google`
7. Note the **Client ID** and **Client Secret**

### 2. Configure DocuElevate

Add to your `.env` file:

```bash
SOCIAL_AUTH_GOOGLE_ENABLED=true
SOCIAL_AUTH_GOOGLE_CLIENT_ID=123456789-abcdefg.apps.googleusercontent.com
SOCIAL_AUTH_GOOGLE_CLIENT_SECRET=GOCSPX-your-secret-here
```

### 3. Restart DocuElevate

```bash
docker compose restart api worker
```

### Google-Specific Notes

- **Google Workspace**: If you want to restrict sign-in to users in your Google Workspace organization, set the OAuth consent screen to "Internal"
- **Verification**: Google may require app verification if you're using External user type and requesting sensitive scopes. For small teams (<100 users), you can add test users instead
- **Unified Auth**: If you also use Google Drive as a storage destination, users who sign in with Google will already be authenticated with a Google identity — simplifying the Google Drive integration experience

---

## Microsoft Sign-In (Azure AD / Microsoft Entra ID)

### 1. Register an Application in Azure

1. Go to the [Azure Portal](https://portal.azure.com/)
2. Navigate to **Microsoft Entra ID → App registrations**
3. Click **New registration**
4. Fill in:
   - **Name**: DocuElevate
   - **Supported account types**: Choose based on your needs:
     - *Accounts in this organizational directory only* — single-tenant (your org only)
     - *Accounts in any organizational directory* — multi-tenant
     - *Accounts in any organizational directory and personal Microsoft accounts* — broadest reach
   - **Redirect URI**: Select **Web** and enter `https://docuelevate.example.com/social-callback/microsoft`
5. Click **Register**
6. Note the **Application (client) ID**
7. Navigate to **Certificates & secrets → New client secret**
8. Add a description and expiration, then click **Add**
9. Note the **Value** (this is your client secret — it's only shown once!)

### 2. Configure API Permissions

1. In your app registration, go to **API permissions**
2. Ensure these permissions are present (they're usually added by default):
   - `openid`
   - `profile`
   - `email`
3. Click **Grant admin consent** if you're a tenant admin

### 3. Configure DocuElevate

Add to your `.env` file:

```bash
SOCIAL_AUTH_MICROSOFT_ENABLED=true
SOCIAL_AUTH_MICROSOFT_CLIENT_ID=12345678-abcd-efgh-ijkl-123456789012
SOCIAL_AUTH_MICROSOFT_CLIENT_SECRET=your~client~secret~value
SOCIAL_AUTH_MICROSOFT_TENANT=common
```

**Tenant options:**

| Value | Who Can Sign In |
|-------|----------------|
| `common` | Any Microsoft account (personal + any Azure AD organization) |
| `organizations` | Any Azure AD organization (work/school accounts only) |
| `consumers` | Personal Microsoft accounts only (outlook.com, hotmail.com, etc.) |
| `<tenant-id>` | Only users in a specific Azure AD tenant (use the GUID from Azure Portal) |

### 4. Restart DocuElevate

```bash
docker compose restart api worker
```

### Microsoft-Specific Notes

- **Client secret expiration**: Azure AD client secrets expire (max 2 years). Set a calendar reminder to rotate them before they expire
- **Conditional Access**: If your organization uses Azure AD Conditional Access policies, social login will respect them
- **Unified Auth**: If you also use OneDrive as a storage destination, users who sign in with Microsoft will already have a Microsoft identity — potentially simplifying OneDrive integration

---

## Apple Sign-In

Apple Sign-In requires an Apple Developer account ($99/year) and more setup than other providers.

### 1. Configure in Apple Developer Portal

1. Go to the [Apple Developer Portal](https://developer.apple.com/account/)
2. Navigate to **Certificates, Identifiers & Profiles → Identifiers**
3. Click **+** and select **App IDs** → Register an App ID:
   - **Description**: DocuElevate
   - **Bundle ID**: e.g., `com.example.docuelevate`
   - Enable **Sign In with Apple** capability
4. Click **+** again and select **Services IDs**:
   - **Description**: DocuElevate Web
   - **Identifier**: e.g., `com.example.docuelevate.web` (this is your Client ID)
   - Enable **Sign In with Apple**
   - Click **Configure** next to Sign In with Apple:
     - **Primary App ID**: Select the App ID created above
     - **Domains**: `docuelevate.example.com`
     - **Return URLs**: `https://docuelevate.example.com/social-callback/apple`
5. Click **Save** and **Continue** → **Register**
6. Navigate to **Keys** → Click **+** to create a new key:
   - **Key Name**: DocuElevate Sign-In
   - Enable **Sign In with Apple**
   - Click **Configure** and select the App ID created above
   - Click **Continue** → **Register**
   - **Download the private key file** (`.p8`) — you can only download it once!
   - Note the **Key ID**
7. Note your **Team ID** (shown in the top-right corner of the Developer Portal)

### 2. Configure DocuElevate

Add to your `.env` file:

```bash
SOCIAL_AUTH_APPLE_ENABLED=true
SOCIAL_AUTH_APPLE_CLIENT_ID=com.example.docuelevate.web
SOCIAL_AUTH_APPLE_TEAM_ID=ABCDE12345
SOCIAL_AUTH_APPLE_KEY_ID=FGHIJ67890
SOCIAL_AUTH_APPLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----
MIGTAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBHkwdwIBAQQg...
...your key content here...
-----END PRIVATE KEY-----"
```

> **Tip:** You can also store the private key as a single line with `\n` for line breaks:
> ```bash
> SOCIAL_AUTH_APPLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nMIGTAgEAMBMG...\n-----END PRIVATE KEY-----"
> ```

### 3. Restart DocuElevate

```bash
docker compose restart api worker
```

### Apple-Specific Notes

- **Email relay**: Apple offers a "Hide My Email" feature that provides a relay email address (e.g., `abc123@privaterelay.appleid.com`). DocuElevate accepts these addresses
- **First login only**: Apple sends the user's name only on the very first authorization. If the user revokes and re-authorizes, their name may not be sent again
- **Developer account required**: You need an Apple Developer account ($99/year) to use Sign In with Apple
- **Key rotation**: Apple private keys don't expire, but if you suspect compromise, revoke the key in the Developer Portal and create a new one

---

## Dropbox Sign-In

### 1. Create a Dropbox App

1. Go to the [Dropbox App Console](https://www.dropbox.com/developers/apps)
2. Click **Create app**
3. Choose:
   - **API**: Scoped access
   - **Access type**: Full Dropbox (or App folder, depending on your needs)
   - **Name**: DocuElevate Auth (or reuse your existing Dropbox storage app)
4. In the app settings, go to the **OAuth 2** section:
   - Add **Redirect URI**: `https://docuelevate.example.com/social-callback/dropbox`
5. Note the **App key** (this is your Client ID) and **App secret** (this is your Client Secret)

> **Tip:** If you already have a Dropbox app configured for DocuElevate's storage integration, you can reuse the same app — just add the social login redirect URI. Alternatively, create a separate app for authentication to keep concerns separated.

### 2. Configure DocuElevate

Add to your `.env` file:

```bash
SOCIAL_AUTH_DROPBOX_ENABLED=true
SOCIAL_AUTH_DROPBOX_CLIENT_ID=your_dropbox_app_key
SOCIAL_AUTH_DROPBOX_CLIENT_SECRET=your_dropbox_app_secret
```

### 3. Restart DocuElevate

```bash
docker compose restart api worker
```

### Dropbox-Specific Notes

- **Unified Auth**: If you also use Dropbox as a storage destination, authenticating via Dropbox establishes the user's Dropbox identity — making it easier to manage Dropbox storage integration
- **App review**: Dropbox may require app review for production apps with more than 50 users. See [Dropbox App Review](https://www.dropbox.com/developers/reference/developer-guide#app-review)
- **Personal vs. Business**: The same app works for both personal Dropbox and Dropbox Business accounts

---

## Unified Authentication and Storage

One of the key advantages of social login in DocuElevate is the potential for **unified authentication** — using the same identity for both signing in and accessing cloud storage destinations:

| Social Login Provider | Related Storage Destination | Benefit |
|---|---|---|
| Google | Google Drive | User already has a Google identity for Drive integration |
| Microsoft | OneDrive | User already has a Microsoft identity for OneDrive integration |
| Dropbox | Dropbox | User already has a Dropbox identity for Dropbox integration |
| Apple | *(none)* | Provides a familiar, privacy-respecting login option |

When a user signs in with a social provider that matches a configured storage destination, the administrator can leverage the same OAuth credentials or simplify the integration setup. Note that the storage integration credentials are configured separately in the admin settings — social login establishes the user's identity, not their storage permissions.

## Combining Multiple Auth Methods

DocuElevate supports running multiple authentication methods simultaneously:

```
┌──────────────────────────────────────────────────┐
│                  Login Page                        │
├──────────────────────────────────────────────────┤
│  Username / Password form (always shown)          │
│                                                    │
│  ─── Or continue with ───                         │
│                                                    │
│  [Authentik SSO]        (if OIDC configured)      │
│  [Sign in with Google]  (if Google enabled)       │
│  [Sign in with Microsoft] (if Microsoft enabled)  │
│  [Sign in with Apple]   (if Apple enabled)        │
│  [Sign in with Dropbox] (if Dropbox enabled)      │
│                                                    │
│  [Create account]       (if local signup enabled) │
└──────────────────────────────────────────────────┘
```

All methods create or update the same `UserProfile` record, so a user is consistently identified regardless of how they sign in.

## Admin Management

Social login users appear in the **Admin → User Management** panel like any other user. Admins can:

- View which provider a user authenticated with
- Block or unblock social login users
- Set upload limits and subscription tiers
- Grant admin privileges (social login users are never automatically admin)

## Security Considerations

1. **HTTPS is required**: All social login providers require HTTPS callback URLs in production
2. **Credentials are sensitive**: Store client secrets securely — use environment variables, never commit them to source control
3. **Least privilege**: Only request the scopes you need (DocuElevate requests `openid`, `profile`, and `email`)
4. **Rotate secrets**: Set calendar reminders to rotate OAuth client secrets before they expire (especially Microsoft, which has a max 2-year expiration)
5. **Monitor logins**: Check the DocuElevate audit log for unusual login patterns
6. **Social login users are not admins**: Admin access must be explicitly granted by an existing admin

## Troubleshooting

### Common Issues

1. **"Unknown social provider" error**
   - The provider is not enabled or credentials are missing
   - Check that `SOCIAL_AUTH_<PROVIDER>_ENABLED=true` is set
   - Verify client ID and secret are configured

2. **"Could not retrieve email from provider" error**
   - The provider didn't return an email address
   - For Google: Ensure `email` scope is included (it is by default)
   - For Apple: User may have chosen "Hide My Email" — this is expected and should still work
   - For Dropbox: Ensure the app has permission to read the user's email

3. **Redirect URI mismatch**
   - The callback URL registered with the provider must exactly match what DocuElevate generates
   - Check your `EXTERNAL_HOSTNAME` setting
   - Ensure you're using HTTPS in production
   - The callback URL format is: `https://<EXTERNAL_HOSTNAME>/social-callback/<provider>`

4. **"Social login failed" error**
   - Check DocuElevate logs (`docker compose logs api`) for detailed error messages
   - Verify the provider's OAuth app is not suspended or in development mode
   - For Google: Check if the OAuth consent screen needs verification
   - For Microsoft: Ensure admin consent was granted for the required permissions

5. **User can't log in after changing provider settings**
   - After changing social login configuration, restart DocuElevate: `docker compose restart api worker`
   - Social login settings require a restart to take effect (`restart_required: true`)

### Debug Checklist

- [ ] `AUTH_ENABLED=true` is set
- [ ] `SESSION_SECRET` is at least 32 characters
- [ ] `EXTERNAL_HOSTNAME` matches your public domain
- [ ] Provider-specific `_ENABLED=true` is set
- [ ] Client ID and secret are correctly configured (no extra spaces)
- [ ] Callback URL is registered with the provider
- [ ] HTTPS is working on your domain
- [ ] DocuElevate has been restarted after configuration changes

## Environment Variable Reference

| Variable | Required | Description |
|---|---|---|
| `SOCIAL_AUTH_GOOGLE_ENABLED` | No | Enable Google Sign-In (`true`/`false`). Default: `false` |
| `SOCIAL_AUTH_GOOGLE_CLIENT_ID` | When Google enabled | Google OAuth2 client ID |
| `SOCIAL_AUTH_GOOGLE_CLIENT_SECRET` | When Google enabled | Google OAuth2 client secret |
| `SOCIAL_AUTH_MICROSOFT_ENABLED` | No | Enable Microsoft Sign-In (`true`/`false`). Default: `false` |
| `SOCIAL_AUTH_MICROSOFT_CLIENT_ID` | When Microsoft enabled | Azure AD application (client) ID |
| `SOCIAL_AUTH_MICROSOFT_CLIENT_SECRET` | When Microsoft enabled | Azure AD client secret |
| `SOCIAL_AUTH_MICROSOFT_TENANT` | No | Azure AD tenant. Default: `common` |
| `SOCIAL_AUTH_APPLE_ENABLED` | No | Enable Apple Sign-In (`true`/`false`). Default: `false` |
| `SOCIAL_AUTH_APPLE_CLIENT_ID` | When Apple enabled | Apple Services ID |
| `SOCIAL_AUTH_APPLE_TEAM_ID` | When Apple enabled | Apple Developer Team ID |
| `SOCIAL_AUTH_APPLE_KEY_ID` | When Apple enabled | Apple Sign-In key ID |
| `SOCIAL_AUTH_APPLE_PRIVATE_KEY` | When Apple enabled | Apple Sign-In private key (PEM) |
| `SOCIAL_AUTH_DROPBOX_ENABLED` | No | Enable Dropbox Sign-In (`true`/`false`). Default: `false` |
| `SOCIAL_AUTH_DROPBOX_CLIENT_ID` | When Dropbox enabled | Dropbox App Key |
| `SOCIAL_AUTH_DROPBOX_CLIENT_SECRET` | When Dropbox enabled | Dropbox App Secret |
