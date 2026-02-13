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

DocuElevate supports two primary authentication methods:

1. **Simple Authentication** - Basic username/password authentication managed by DocuElevate
2. **OpenID Connect** - Integration with identity providers like Authentik, Keycloak, or Auth0

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
