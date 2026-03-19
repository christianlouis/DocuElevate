# Mobile App

DocuElevate includes a native mobile application for iOS and Android built with **React Native** and **Expo**.  The app allows users to capture documents with the device camera, pick files from the device storage, and receive push notifications when documents finish processing.

## Features

| Feature | iOS | Android |
|---------|-----|---------|
| SSO login (OAuth2) | ✅ | ✅ |
| Local / basic auth login | ✅ | ✅ |
| QR code login (scan from web) | ✅ | ✅ |
| Auto-generated API token | ✅ | ✅ |
| Camera capture → upload | ✅ | ✅ |
| File picker upload | ✅ | ✅ |
| Share Sheet / Share Intent | ✅ | ✅ |
| Push notifications | ✅ | ✅ |
| Document list | ✅ | ✅ |
| Dark mode | ✅ | ✅ |

## Getting Started (Development)

### Prerequisites

- Node.js 20.19.4 or later (use [nvm](https://github.com/nvm-sh/nvm): `nvm install` inside `mobile/` reads `.nvmrc` automatically)
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

## Automated CI/CD

An **EAS Cloud Workflow** (`mobile/.eas/workflows/create-builds.yml`) automates production builds and iOS submission:

- **Path filtering:** The workflow only triggers on pushes to `main` that include changes inside the `mobile/` directory.  Backend-only or documentation-only changes do not trigger a mobile build.
- **Build:** Both iOS and Android production builds run in parallel on EAS Build.
- **Auto-submit (iOS):** After a successful iOS build, the workflow automatically submits the binary to **App Store Connect** using the credentials configured in `eas.json` (`submit.production.ios`).  The build then appears in **TestFlight** for internal testing and can be promoted to the App Store from App Store Connect.

> **Prerequisite:** An App Store Connect API Key must be configured in EAS for non-interactive submission.  See [Troubleshooting → "Session expired"](#session-expired-local-session-during-ios-build) below for setup instructions.

### Version Management

Build numbers (iOS `buildNumber` / Android `versionCode`) are managed **remotely** by EAS.  The `eas.json` configuration uses:

```json
{
  "cli": { "appVersionSource": "remote" },
  "build": { "production": { "autoIncrement": true } }
}
```

- **`appVersionSource: "remote"`** — EAS stores the current build number on its servers instead of reading it from `app.json`.  This ensures every CI build gets a unique, ever-increasing number without needing to commit version bumps back to the repository.
- **`autoIncrement: true`** — EAS automatically increments the build number before each production build.

The `ios.buildNumber` and `android.versionCode` values in `app.json` serve as the **initial seed** when the remote version is first created; after that they are informational only.  Do not rely on them for the actual version submitted to the stores.

> **Tip:** To check or manually set the remote version, use `eas build:version:get` and `eas build:version:set`.

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

> **Security note:** The `redirect_uri` is validated server-side; only URIs with the `docuelevate://` custom scheme (production) or the `exp://` scheme (Expo Go development) are accepted, preventing open-redirect attacks.

### Testing in Expo Go

When developing with **Expo Go** the app does not have the `docuelevate://` custom URL scheme registered.  The auth flow adapts automatically:

1. `Linking.createURL('callback')` returns an `exp://` URI pointing at the local dev server (e.g. `exp://192.168.1.5:8081/--/callback`).
2. This URI is sent to the server as `redirect_uri`; the server accepts it alongside the production `docuelevate://` scheme.
3. After successful authentication the server redirects back to the `exp://` URI.
4. `WebBrowser.openAuthSessionAsync` intercepts the deep link and the Expo Go app receives the token.

No extra configuration is needed — just run `npx expo start` and scan the QR code with the **Expo Go** app.

### QR Code Login Flow

As an alternative to SSO, users can log in by scanning a QR code displayed in the web UI:

1. The authenticated web user navigates to **Profile → Security & Sessions → Log in on mobile via QR code**.
2. A QR code is displayed containing a deep link: `docuelevate://qr-login?token=<challenge_token>&server=<server_url>`.
3. In the mobile app, the user taps **Scan QR Code to Login**, which opens the device camera.
4. The app scans the QR code, extracts both the server URL and the challenge token, and calls `POST /api/qr-auth/claim`.
5. An API token is issued and stored securely — no need to enter the server URL manually.

> **Note:** The QR code already contains the server URL, so users do not need to type it in when using QR login.

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

### Photo Library

1. Open the **Upload** tab.
2. Tap **Photos**.
3. Select an existing photo from the device's photo library.
4. The image is uploaded and queued for processing.

### File Picker

1. Open the **Upload** tab.
2. Tap **Files**.
3. Browse to and select one or more files (PDF, DOCX, images, etc.).
4. Files are uploaded and queued for processing.

### Share Sheet (iOS) / Share Intent (Android)

The app registers itself as a share target so any file can be sent directly to DocuElevate from another app:

1. Open a file in Files, Mail, Safari, or any other app.
2. Tap the **Share** button (iOS) or **Share** (Android).
3. Find and tap **DocuElevate** in the share sheet.
4. The file is immediately uploaded and queued for processing.

> **Note:** The app must be installed on the device for it to appear in the share sheet.

#### iOS implementation

`app.json` declares `CFBundleDocumentTypes` (with `LSHandlerRank: Alternate`) inside the iOS `infoPlist`.  This tells iOS that DocuElevate can open common document types, making it visible in the share sheet without overriding system defaults.  When the user selects DocuElevate, iOS opens the app with a URL via `application:openURL:options:`.

The URL may arrive as a standard `file://` path **or** under the app's custom `docuelevate://` scheme (e.g. `docuelevate://private/var/mobile/Library/…/file.pdf`).  The root layout detects the custom-scheme form and rewrites it to a `file://` URL before forwarding it to the Upload screen through `ShareContext`.

##### Handling "unmatched route" errors from "Open In…"

iOS sometimes delivers the file path under the `docuelevate://` scheme, e.g.:

```
docuelevate://private/var/mobile/Library/Mobile Documents/…/Invoice.pdf
```

expo-router strips the scheme and tries to match `/private/var/mobile/…` as an in-app route.  Because no such route exists, it previously threw an **"unmatched route docuelevate://"** error and the upload never completed.

The fix is a catch-all `+not-found.tsx` route (see `mobile/app/+not-found.tsx`).  When expo-router cannot match the path, it renders this screen instead.  The screen detects that the path is a filesystem path rather than a real in-app route, adds the file directly to `ShareContext`, and redirects to the Upload tab.  `UploadScreen` picks up the pending file and begins uploading automatically.  The `Linking` listener in the root layout may also fire for the same URL; `ShareContext.addPendingFile` deduplicates by URI so the file is only uploaded once.

##### File accessibility and local caching

Shared files may reference paths outside the app's sandbox or use security-scoped URLs that React Native's `fetch` cannot read directly.  To guarantee reliable uploads:

- **`LSSupportsOpeningDocumentsInPlace`** is set to `false` in `app.json`, which tells iOS to copy shared files into the app's `Documents/Inbox` directory before handing them to the app.
- **`UploadScreen`** uses `expo-file-system` (`FileSystem.copyAsync`) to copy any `file://` URI that is outside the app's cache/documents directory to a local cache path before uploading.  This ensures the file is readable regardless of its origin.
- **MIME type inference**: Both `+not-found.tsx` and the `Linking` handler in `_layout.tsx` infer the MIME type from the file extension (e.g. `.pdf` → `application/pdf`) so the server receives a correct `Content-Type` instead of `application/octet-stream`.

##### iOS Action / Share Extension (future enhancement)

Apps like DeepL ("Translate in DeepL") and Microsoft Word ("Convert to Word") appear as **Action Extensions** in the iOS share sheet — a system-level feature that requires a separate Xcode target built with Swift or Objective-C.  A proper Action Extension runs in its own process and must share authentication credentials with the main app via an iOS **App Group** (shared keychain / shared container).

This level of iOS-native integration is a planned future enhancement.  Until it is available, the recommended workflow is the current one: tap **Share → DocuElevate** (the app appears in the "Open With" row of the share sheet via `CFBundleDocumentTypes`).

#### Android implementation

`app.json` declares `ACTION_SEND` and `ACTION_SEND_MULTIPLE` intent filters for `mimeType: "*/*"` in the `android.intentFilters` section.  Incoming content URIs are received the same way as on iOS.

#### Upload status polling

After a file is uploaded the app polls `/api/files?search=<filename>` every 5 seconds to find the corresponding `FileRecord`, then polls `/api/files/{id}` to track the processing status in real time.  Polling stops automatically once the status reaches a terminal state (`completed`, `failed`, or `duplicate`).

#### Retrying failed uploads

If a file upload fails (e.g. due to network issues or a server error), the failed item stays visible in the upload list with an error message and a **"Tap to retry"** hint.  Users can retry the upload in two ways:

- **Tap** the failed item to immediately retry the upload.
- **Long-press** the failed item to see a confirmation dialog with a **Retry** option.

The retry re-uses the original file URI so no re-selection is needed.

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
├── App.tsx                      # Root component (legacy, not used at runtime)
├── app/                         # Expo Router file-based routes
│   ├── _layout.tsx              # Root layout (AuthGuard + providers)
│   ├── index.tsx                # Root redirect → /(auth)/
│   ├── (auth)/                  # Unauthenticated route group
│   │   ├── _layout.tsx          # Stack navigator (headerless)
│   │   ├── index.tsx            # Welcome screen
│   │   ├── login.tsx            # Login screen
│   │   └── qr-scanner.tsx       # QR code scanner screen
│   └── (tabs)/                  # Authenticated route group
│       ├── _layout.tsx          # Tab navigator
│       ├── index.tsx            # Upload screen (default tab)
│       ├── files.tsx            # Files screen
│       └── profile.tsx          # Profile screen
├── app.json                     # Expo/EAS configuration
├── eas.json                     # EAS Build profiles
├── package.json
├── tsconfig.json
└── src/
    ├── context/
    │   ├── AuthContext.tsx      # Auth state + SSO login flow
    │   └── ShareContext.tsx     # Shared-file queue (iOS Share Sheet / Android Intent)
    ├── hooks/
    │   └── usePushNotifications.ts  # Push token registration
    ├── screens/
    │   ├── LoginScreen.tsx      # Server URL + SSO button + QR code scanner
    │   ├── QRScannerScreen.tsx  # Camera-based QR code scanner for login
    │   ├── UploadScreen.tsx     # Camera capture + photo library + file picker
    │   ├── FilesScreen.tsx      # Processed document list
    │   └── ProfileScreen.tsx    # User profile + sign out
    └── services/
        └── api.ts               # DocuElevate REST API client
```

## Troubleshooting

### App shows "Hello World" / default Expo page after update

If the iOS or Android app shows a generic "Hello World – This is the first page of your app" screen instead of the DocuElevate UI, it means a stale default `index.tsx` file (generated by Expo CLI scaffolding) is being picked up in the `mobile/app/` directory.

**To fix:**

1. Delete any leftover default `mobile/app/index.tsx` that is **not** the repository version (the repo version contains a `<Redirect>` to `/(auth)/`).
2. Clear the Metro bundler cache and rebuild:
   ```bash
   cd mobile
   npx expo start --clear
   ```
3. For production builds, run a clean EAS build:
   ```bash
   eas build --platform ios --clear-cache
   ```

The repository includes a root `app/index.tsx` that immediately redirects to the authentication flow, so this issue should not recur once the correct file is present.

### "Session expired Local session" during iOS build

EAS stores an Apple ID session locally (in `~/.expo/`) to manage code-signing certificates and provisioning profiles.  This session expires after a few weeks.

**To fix:**

1. **Refresh the session** by running `eas credentials` and re-authenticating with your Apple ID.
2. **Recommended for automation:** Replace the Apple ID session with an [App Store Connect API Key](https://docs.expo.dev/app-signing/app-credentials/#app-store-connect-api-key).  API keys do not expire and work fully non-interactively:
   - Create a key at [appstoreconnect.apple.com → Users → Integrations → Keys](https://appstoreconnect.apple.com/access/integrations/api)
   - Download the `.p8` file and note the **Key ID** and **Issuer ID**
   - Run `eas credentials` → iOS → *Add an App Store Connect API key*
   - Upload the `.p8` file when prompted

Once an API key is configured in EAS, automated builds (including CI and EAS Cloud Workflows) will no longer prompt for a password.

### Node.js deprecation warning `[DEP0169]` during EAS build

```
(node:XXXXX) [DEP0169] DeprecationWarning: `url.parse()` behavior is not standardized…
```

This warning is emitted by **EAS CLI** (an external tool) when it runs on **Node.js 22 or later**, which deprecates `url.parse()`.  It does not indicate a problem in the DocuElevate mobile app itself and will not cause a build failure on its own.

The `eas.json` build profiles already include `"NODE_NO_WARNINGS": "1"` in their `env` sections to suppress this warning during EAS Cloud builds.  For local builds with a system Node.js ≥ 22, suppress it by running:

```bash
NODE_NO_WARNINGS=1 eas build --platform ios
```

or by activating the project's pinned Node.js version first:

```bash
cd mobile
nvm use   # reads .nvmrc → Node 20.19.4 (no deprecation warning)
eas build --platform ios
```

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
- [Apple App Store Compliance Audit](./AppleAppStoreCompliance.md)
