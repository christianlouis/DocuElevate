# Mobile App

DocuElevate includes a native mobile application for iOS and Android built with **React Native** and **Expo**.  The app allows users to capture documents with the device camera, pick files from the device storage, and receive push notifications when documents finish processing.

## Features

| Feature | iOS | Android |
|---------|-----|---------|
| SSO login (OAuth2) | ✅ | ✅ |
| Local / basic auth login | ✅ | ✅ |
| Auto-generated API token | ✅ | ✅ |
| Camera capture → upload | ✅ | ✅ |
| File picker upload | ✅ | ✅ |
| Share Sheet / Share Intent | ✅ | ✅ |
| Push notifications | ✅ | ✅ |
| Document list | ✅ | ✅ |
| Dark mode | ✅ | ✅ |

## Getting Started (Development)

### Prerequisites

- Node.js 18 or later
- [Expo CLI](https://docs.expo.dev/get-started/installation/): `npm install -g @expo/cli`
- [Expo Go](https://expo.dev/client) app on your iOS or Android device (for development)
- A running DocuElevate server reachable from your device

### Run in development mode

```bash
cd mobile
npm install
npx expo start
```

Scan the QR code with **Expo Go** on your device.  On iOS you can also use the Camera app.

## Building for Production

DocuElevate uses **Expo Application Services (EAS)** to produce App Store / Play Store binaries.

```bash
# Install EAS CLI globally
npm install -g eas-cli

# Authenticate with Expo
eas login

# Build for iOS (requires Apple Developer account)
eas build --platform ios

# Build for Android
eas build --platform android
```

> **Note:** The mobile app uses `expo-build-properties` with `buildReactNativeFromSource: true` for iOS builds. This is required for Expo SDK 54 (React Native 0.81) compatibility — some native modules still use legacy bridge APIs (`RCTBridge`, `RCTViewManager`, etc.) that are no longer included in the default precompiled XCFrameworks. Building React Native from source makes these headers available, at the cost of slightly longer iOS build times.

See the [EAS Build documentation](https://docs.expo.dev/build/introduction/) for full setup instructions.

## Authentication

### SSO Login Flow

The mobile app uses the server's existing OAuth2/SSO setup:

1. User enters the DocuElevate server URL on the login screen.
2. The app opens `<server>/login?mobile=1&redirect_uri=docuelevate://callback` in the **system browser** (Safari / Chrome Custom Tabs).
3. The server stores `docuelevate://callback` in the browser session and presents the login page.
4. The user authenticates via SSO or local credentials.
5. After successful authentication the server mints a long-lived API token and redirects the browser to `docuelevate://callback?token=<token>`.
6. `WebBrowser.openAuthSessionAsync` intercepts the `docuelevate://` deep link and returns the URL to the app.
7. The app extracts the token from the URL and stores it securely in the device's keychain (`expo-secure-store`).

> **Security note:** The `redirect_uri` is validated server-side; only URIs with the `docuelevate://` custom scheme are accepted, preventing open-redirect attacks.

### Auto-generated Mobile Token

When the mobile app completes login it automatically creates a named API token (`"Mobile App – <device name>"`) via `POST /api/mobile/generate-token`.  This token:

- Works identically to tokens created manually in the web UI.
- Is shown in the **API Tokens** page (`/api-tokens`) and can be revoked there.
- Is stored in the device's secure keychain, never in plain storage.

## Push Notifications

Push notifications are delivered via the **Expo Push Notification** service, which routes through Apple Push Notification service (APNs) for iOS and Firebase Cloud Messaging (FCM) for Android.

**No server-side APNs/FCM credentials are required** – Expo's servers handle the provider integration.

### How it works

1. After login, the app requests notification permission from the operating system.
2. If granted, the app obtains an **Expo Push Token** (`ExponentPushToken[…]`).
3. The token is registered with the backend via `POST /api/mobile/register-device`.
4. When a document finishes processing, the server sends a push notification to all registered devices for that user.

### Managing registered devices

Users can see and remove their registered devices from the **Profile** tab in the app, or via the API:

```bash
# List registered devices
curl -H "Authorization: Bearer <token>" https://your-server/api/mobile/devices

# Remove a device
curl -X DELETE -H "Authorization: Bearer <token>" https://your-server/api/mobile/devices/<id>
```

## Uploading Documents

### Camera Capture

1. Open the **Upload** tab.
2. Tap **Camera**.
3. Point the camera at the document and take a photo.
4. The image is immediately uploaded and queued for processing.

### File Picker

1. Open the **Upload** tab.
2. Tap **File Picker**.
3. Browse to and select one or more files (PDF, DOCX, images, etc.).
4. Files are uploaded and queued for processing.

### Share Sheet (iOS) / Share Intent (Android)

The app registers itself as a share target so any file can be sent directly to DocuElevate from another app:

1. Open a file in Files, Mail, Safari, or any other app.
2. Tap the **Share** button (iOS) or **Share** (Android).
3. Find and tap **DocuElevate** in the share sheet.
4. The file is immediately uploaded.

> **Note:** The app must be installed on the device for it to appear in the share sheet.

## Mobile API Endpoints

The backend exposes a dedicated `/api/mobile/` namespace:

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/mobile/generate-token` | Session | Exchange SSO session for API token |
| `POST` | `/api/mobile/register-device` | Bearer | Register Expo push token |
| `GET` | `/api/mobile/devices` | Bearer | List registered devices |
| `DELETE` | `/api/mobile/devices/{id}` | Bearer | Deactivate a device |
| `GET` | `/api/mobile/whoami` | Bearer | Get current user profile |

All other API endpoints (file upload, file listing, etc.) work with Bearer token authentication.

### POST /api/mobile/generate-token

Exchanges an active web session (cookie) for a permanent API token suitable for use in the mobile app.

**Request:**
```json
{ "device_name": "John's iPhone" }
```

**Response (201):**
```json
{
  "token": "de_AbCdEfGhIjKl...",
  "token_id": 42,
  "name": "Mobile App – John's iPhone",
  "created_at": "2026-03-10T09:30:00Z"
}
```

> ⚠️ The `token` value is returned **once only**.  Store it in the device's secure keychain immediately.

### POST /api/mobile/register-device

Registers an Expo push token for the authenticated user.

**Request:**
```json
{
  "push_token": "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]",
  "device_name": "John's iPhone",
  "platform": "ios"
}
```

Supported platforms: `ios`, `android`, `web`.

Re-registering the same token is safe (idempotent).

### GET /api/mobile/whoami

Returns the current user's profile.

**Response (200):**
```json
{
  "owner_id": "john@example.com",
  "display_name": "John Doe",
  "email": "john@example.com",
  "avatar_url": "https://www.gravatar.com/avatar/...",
  "is_admin": false
}
```

## Configuration

No server-side configuration is required to enable the mobile app.  The Expo push notification routing does not need FCM or APNs credentials on the server.

If you wish to use **direct FCM/APNs** without Expo's relay, replace the `send_expo_push_notification` function in `app/utils/push_notification.py` with your own implementation.

## Project Structure (mobile/)

```
mobile/
├── App.tsx                      # Root component
├── app.json                     # Expo/EAS configuration
├── eas.json                     # EAS Build profiles
├── package.json
├── tsconfig.json
└── src/
    ├── context/
    │   └── AuthContext.tsx      # Auth state + SSO login flow
    ├── hooks/
    │   └── usePushNotifications.ts  # Push token registration
    ├── screens/
    │   ├── LoginScreen.tsx      # Server URL + SSO button
    │   ├── UploadScreen.tsx     # Camera capture + file picker
    │   ├── FilesScreen.tsx      # Processed document list
    │   └── ProfileScreen.tsx    # User profile + sign out
    └── services/
        └── api.ts               # DocuElevate REST API client
```

## Troubleshooting

### "Authentication was cancelled or failed"

- Ensure the server URL is correct (including `https://`).
- Verify the server is reachable from your device's network.
- Confirm that `AUTH_ENABLED=True` on the server.

### Push notifications not arriving

1. Check that the app has notification permission (Settings → DocuElevate → Notifications).
2. Verify the device is registered: `GET /api/mobile/devices`.
3. Ensure the server can reach `https://exp.host` (outbound HTTPS on port 443).
4. On Android, add `google-services.json` to the `mobile/` directory if you are building your own binary.

### "Connection refused" or timeout

- Verify that the DocuElevate server is running and accessible.
- Ensure the server's `EXTERNAL_HOSTNAME` or reverse proxy is configured correctly.
- Check that the server accepts CORS requests from `docuelevate://`.

## Related Documentation

- [API Documentation](./API.md)
- [Configuration Guide](./ConfigurationGuide.md)
- [Deployment Guide](./DeploymentGuide.md)
