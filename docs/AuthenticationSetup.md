# Setting up Authentication

This guide explains how to configure authentication for DocuElevate to secure your installation.

## Required Configuration Parameters

| **Variable**                | **Description**                                           |
|----------------------------|----------------------------------------------------------|
| `AUTH_ENABLED`             | Enable or disable authentication (`True`/`False`)        |
| `SESSION_SECRET`           | Secret key for session encryption (min 32 characters)    |
| `ADMIN_USERNAME`           | Username for basic authentication                        |
| `ADMIN_PASSWORD`           | Password for basic authentication                        |
| `ADMIN_GROUP_NAME`         | OIDC group name that grants admin access (default: `admin`) |
| `AUTHENTIK_CLIENT_ID`      | Client ID for OpenID Connect authentication              |
| `AUTHENTIK_CLIENT_SECRET`  | Client secret for OpenID Connect authentication          |
| `AUTHENTIK_CONFIG_URL`     | OpenID Connect discovery URL                             |
| `OAUTH_PROVIDER_NAME`      | Display name for the OAuth provider button               |

For a complete list of configuration options, see the [Configuration Guide](ConfigurationGuide.md).

## Authentication Methods

DocuElevate supports multiple authentication methods that can be used independently or together:

1. **Simple Authentication** - Basic username/password authentication managed by DocuElevate
2. **OpenID Connect** - Integration with identity providers like Authentik, Keycloak, or Auth0
3. **Social Login** - Sign in with Google, Microsoft, Apple, or Dropbox accounts (see [Social Login Setup Guide](SocialLoginSetup.md))

## Session Security

DocuElevate uses FastAPI's session management to maintain user sessions. The session data is stored in cookies that are encrypted and signed using your application's secret key. This prevents tampering with session data while ensuring users remain authenticated between requests.

The `SESSION_SECRET` is automatically used by the web framework to:

1. Encrypt and sign session cookies
2. Protect against cross-site request forgery (CSRF) attacks
3. Secure other session-related functionality

Always use a strong, randomly generated secret key of at least 32 characters for production environments.

### Generating a Secure Session Secret

You can generate a secure random string using Python:

```python
import secrets
print(secrets.token_hex(32))  # Outputs a 64-character hex string (32 bytes)
```

Or using OpenSSL:

```bash
openssl rand -hex 32
```

Make sure to keep this secret value confidential and don't reuse it across different applications.

## Setting up Simple Authentication

For smaller deployments or testing, simple authentication is easy to set up:

1. In your `.env` file, set:
   ```
   AUTH_ENABLED=True
   SESSION_SECRET=your-secure-random-string-at-least-32-chars
   ADMIN_USERNAME=your_admin_username
   ADMIN_PASSWORD=your_secure_password
   ADMIN_GROUP_NAME=admin
   ```

2. Restart DocuElevate to apply the changes

3. When you navigate to the application, you'll be prompted to log in with the credentials you set


## Setting up OpenID Connect with Authentik

For larger deployments or when you need more advanced authentication features, OpenID Connect (OIDC) is recommended:

### 1. Create an Application in Authentik

1. Log in to your Authentik admin interface
2. Navigate to "Applications" > "Applications"
3. Click "Create"
4. Fill in the following details:
   - **Name**: DocuElevate
   - **Slug**: docuelevate
   - **Provider**: Create a new OAuth2/OIDC Provider
   - **Launch URL**: The URL of your DocuElevate instance (e.g., https://docuelevate.example.com)

5. For the OAuth2/OIDC Provider settings:
   - **Client Type**: Confidential
   - **Redirect URIs**: https://docuelevate.example.com/auth (adjust for your domain)
   - **Signing Key**: Select an appropriate signing key
   - **Scopes**: Select "openid", "email", and "profile" at minimum

6. Save the provider and then the application

7. Note down the **Client ID** and **Client Secret** from the provider details

### 2. Configure DocuElevate

1. In your `.env` file, set:
   ```
   AUTH_ENABLED=True
   SESSION_SECRET=your-secure-random-string-at-least-32-chars
   AUTHENTIK_CLIENT_ID=your_client_id_from_authentik
   AUTHENTIK_CLIENT_SECRET=your_client_secret_from_authentik
   AUTHENTIK_CONFIG_URL=https://auth.example.com/application/o/docuelevate/.well-known/openid-configuration
   OAUTH_PROVIDER_NAME=Authentik SSO
   ```

2. Adjust the `AUTHENTIK_CONFIG_URL` to match your Authentik instance and application slug

3. Restart DocuElevate to apply the changes

### 3. Test the Authentication

1. Navigate to your DocuElevate instance
2. You should be redirected to the Authentik login page
3. After successful authentication, you'll be redirected back to DocuElevate

## Using Other OpenID Connect Providers

DocuElevate can work with any OpenID Connect-compliant provider, not just Authentik:

### Keycloak Setup

1. Create a client in Keycloak with:
   - **Client ID**: your preferred client ID
   - **Access Type**: confidential
   - **Valid Redirect URIs**: https://docuelevate.example.com/auth

2. Get the client secret from the "Credentials" tab

3. Configure DocuElevate with:
   ```
   AUTHENTIK_CLIENT_ID=your_keycloak_client_id
   AUTHENTIK_CLIENT_SECRET=your_keycloak_client_secret
   AUTHENTIK_CONFIG_URL=https://keycloak.example.com/auth/realms/your-realm/.well-known/openid-configuration
   OAUTH_PROVIDER_NAME=Keycloak SSO
   ```

### Auth0 Setup

1. Create a new application in Auth0
2. Get your client ID and secret
3. Set the callback URL to https://docuelevate.example.com/auth
4. Configure DocuElevate with:
   ```
   AUTHENTIK_CLIENT_ID=your_auth0_client_id
   AUTHENTIK_CLIENT_SECRET=your_auth0_client_secret
   AUTHENTIK_CONFIG_URL=https://your-tenant.auth0.com/.well-known/openid-configuration
   OAUTH_PROVIDER_NAME=Auth0
   ```

## Server-Side Session Management

DocuElevate supports server-side session tracking. Every login creates a `UserSession` record that can be listed and revoked individually or all at once ("log off everywhere").

### Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SESSION_LIFETIME_DAYS` | Number of days before a session expires | `30` |
| `SESSION_LIFETIME_CUSTOM_DAYS` | Override for `SESSION_LIFETIME_DAYS` when set | — |

### Managing Sessions

Users can manage their active sessions from the **Profile → Security** section:

- **View active sessions** — see browser, device, IP address, and last activity for each session.
- **Revoke a single session** — immediately invalidate one session.
- **Log off everywhere** — revoke all sessions (optionally keeping the current one) and all API tokens at once.

Expired sessions are automatically cleaned up by a periodic background task.

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/sessions` | List the current user's active sessions |
| `DELETE` | `/api/sessions/{id}` | Revoke a single session |
| `POST` | `/api/sessions/revoke-all` | Revoke all sessions for the current user |

## QR Code Login

QR code login allows users to authenticate a mobile device by scanning a QR code displayed in the web UI, without manually entering credentials on the phone.

### How It Works

1. The authenticated web user opens the **QR Login** page and a challenge QR code is displayed.
2. The user opens the DocuElevate mobile app and taps **Scan QR Code to Login**, which opens the device camera.
3. The mobile app scans the QR code. The QR code contains both the challenge token and the server URL (`docuelevate://qr-login?token=...&server=...`), so there is no need to enter the server URL manually.
4. An API token is issued for the mobile device and the web UI is notified via polling.

> **Note:** The countdown timer on the web page uses server-relative time (TTL in seconds) rather than absolute timestamps, so it works correctly even when the client's clock is not in sync with the server.

### Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `QR_LOGIN_CHALLENGE_TTL_SECONDS` | How long a QR challenge is valid (seconds) | `120` |

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/qr-auth/challenge` | Create a new QR login challenge (returns `ttl_seconds` for client countdown) |
| `GET` | `/api/qr-auth/challenge/{id}/status` | Poll the status of a challenge |
| `POST` | `/api/qr-auth/claim` | Claim a challenge from a mobile device |

## Security Considerations

1. **Always use HTTPS** in production to protect authentication tokens and passwords
2. Generate a strong, random `SESSION_SECRET` (at least 32 characters)
3. Use strong passwords for simple authentication
4. Consider using a password manager to generate and store your admin credentials
5. Restrict the scopes requested from your OIDC provider to only what's needed
6. Consider setting up user groups and permissions in your identity provider
7. If using simple authentication in production, consider implementing rate limiting for login attempts

## Troubleshooting Authentication Issues

If you encounter issues with authentication:

1. **Login failures with simple authentication**:
   - Verify that the username and password exactly match the values in your `.env` file
   - Check if there are leading or trailing spaces in your credentials
   - Ensure your `.env` file is properly loaded by the application

2. **Session issues**:
   - Check that your `SESSION_SECRET` is set correctly
   - Clear browser cookies and cache if experiencing persistent login issues

3. **OIDC issues**:
   - **Redirect URI mismatch**: Ensure the redirect URI in your provider configuration exactly matches your DocuElevate URL + "/auth"
   - **SSL-related errors**: Make sure your certificates are valid and trusted
   - **Provider connectivity**: Ensure DocuElevate can reach your identity provider

4. **Token validation errors**:
   - Check that the clocks are synchronized between DocuElevate and the identity provider
   - Verify that the signing keys are correctly configured

5. **Debug OpenID information**:
   - For most providers, you can visit the `/.well-known/openid-configuration` endpoint to verify their settings

For more general configuration issues, see the [Configuration Troubleshooting Guide](ConfigurationTroubleshooting.md).

## Social Login

DocuElevate supports social login with Google, Microsoft, Apple, and Dropbox. Social login allows users to authenticate using their existing accounts with these providers, without needing a separate DocuElevate password.

Social login can be used alongside any other authentication method (simple auth, OIDC, local signup). Each social provider is independently configured.

For detailed setup instructions, prerequisites, and provider-specific configuration, see the **[Social Login Setup Guide](SocialLoginSetup.md)**.
