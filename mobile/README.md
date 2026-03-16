# DocuElevate Mobile App

Native mobile application for DocuElevate, built with **React Native** and **Expo** for iOS, Android, and Web.

## Features

- 🔐 **SSO Login** – authenticate via your DocuElevate server's OAuth2/SSO provider; an API token is auto-generated and stored securely in the device keychain
- 📷 **Camera Capture** – scan documents directly with the device camera
- 📄 **File Picker** – upload PDFs, images, and Office documents from the device's Files app
- 🔗 **Share Extension** – send files from any app directly to DocuElevate via the iOS/Android share sheet
- 🔔 **Push Notifications** – receive real-time push notifications when documents finish processing (via Expo push notifications)
- 📂 **Document List** – browse and search your processed documents
- 👤 **Profile** – view account details and sign out
- 🌐 **Web** – run directly in the browser via Expo web (Metro bundler)

## Requirements

- Node.js 20.19.4+ (use [nvm](https://github.com/nvm-sh/nvm): `nvm use` in this directory)
- Expo CLI (`npm install -g @expo/cli`)
- Expo Go app on device (for development) **or** Expo Application Services (EAS) for production builds
- An Expo account: <https://expo.dev/>

## Setup

```bash
# 1. Install dependencies
cd mobile
npm install

# 2. Start the development server (choose a platform)
npx expo start          # interactive menu (iOS / Android / Web)
npx expo start --ios    # open directly in iOS Simulator
npx expo start --android # open in Android Emulator
npx expo start --web    # open in the browser
```

Scan the QR code with **Expo Go** on your iOS or Android device, or press `w` in the interactive menu to open the web build.

## Building

DocuElevate uses **EAS Build** for production binaries.

```bash
# Install EAS CLI
npm install -g eas-cli

# Log in to Expo
eas login

# Build for iOS
eas build --platform ios

# Build for Android
eas build --platform android

# Build for both
eas build --platform all
```

> **Note:** The EAS project ID is already configured in `app.json` (`extra.eas.projectId`). You only need to run `eas init` if you are setting up a fork or a brand-new EAS project — in that case, replace the `extra.eas.projectId` value in `app.json` with the ID printed by `eas init`.

### iOS-specific

- An Apple Developer account is required for TestFlight and App Store distribution
- Update `eas.json` → `submit.production.ios` with:
  - `appleId`: your Apple ID email address
  - `ascAppId`: App Store Connect → App Information → Apple ID
  - `appleTeamId`: Apple Developer portal → Membership → Team ID
- Camera, photo library, and push notification usage descriptions are configured in `app.json`

### Android-specific

- **Android push notifications** require a `google-services.json` file from Firebase Console. This file is intentionally excluded from the repository (`.gitignore`). To enable FCM push notifications in your Android builds:
  1. Create a Firebase project at <https://console.firebase.google.com/>
  2. Add an Android app with the package name `org.docuelevate.mobile`
  3. Download `google-services.json` and place it in the `mobile/` directory
  4. Add `"googleServicesFile": "./google-services.json"` back to the `android` section of `app.json` before building
- The app runs and bundles correctly without `google-services.json`; only Android push notifications will be unavailable
- For Play Store submission: create a service account in Google Play Console, download the JSON key as `google-play-service-account.json`, and update `eas.json`

## CI/CD

An EAS Cloud Workflow (`mobile/.eas/workflows/create-builds.yml`) runs automatically when changes inside `mobile/` are pushed to `main`:

1. **Path filtering** — only commits that modify files under `mobile/` trigger a build; backend-only changes are skipped.
2. **Parallel builds** — iOS and Android production builds run at the same time on EAS Build.
3. **Auto-submit to Apple** — after the iOS build succeeds, the workflow submits the binary to App Store Connect (TestFlight) using the credentials in `eas.json` → `submit.production.ios`.

> An [App Store Connect API Key](https://docs.expo.dev/app-signing/app-credentials/#app-store-connect-api-key) must be configured in EAS (`eas credentials`) for non-interactive submission.

## Configuration

No code changes are needed to point the app at a different server.  The server URL is entered by the user on the login screen and stored in the device's secure store.

## Authentication Flow

1. User enters the DocuElevate server URL on the login screen
2. The app opens the server's `/login?mobile=1&redirect_uri=docuelevate://callback` URL in the system browser
3. The user authenticates (SSO / local login)
4. The server redirects back to `docuelevate://callback`
5. The app exchanges the browser session for a permanent API token via `POST /api/mobile/generate-token`
6. The token is stored in the device's secure keychain (`expo-secure-store`)

## Push Notifications

The app uses **Expo Push Notifications** which route through Expo's servers to APNs (iOS) and FCM (Android) – no server-side APNs/FCM credentials are needed.

The Expo push token is sent to the backend after login via `POST /api/mobile/register-device` and the server uses it to deliver notifications when documents are processed.

## Project Structure

```
mobile/
├── app/                           # expo-router file-based routes
│   ├── _layout.tsx                # Root layout (AuthProvider + auth guard)
│   ├── (auth)/                    # Unauthenticated route group
│   │   ├── _layout.tsx            # Auth stack (no header)
│   │   ├── index.tsx              # Welcome screen
│   │   └── login.tsx              # Login screen
│   └── (tabs)/                    # Authenticated route group
│       ├── _layout.tsx            # Tab navigator (Upload / Files / Profile)
│       ├── index.tsx              # Upload tab
│       ├── files.tsx              # Files tab
│       └── profile.tsx            # Profile tab
├── App.tsx                        # Legacy file (not the entry point; see app/)
├── app.json                       # Expo configuration
├── eas.json                       # EAS Build configuration
├── package.json
├── tsconfig.json
└── src/
    ├── context/
    │   └── AuthContext.tsx        # Authentication state management
    ├── hooks/
    │   └── usePushNotifications.ts  # Push notification registration
    ├── screens/
    │   ├── WelcomeScreen.tsx      # Branded intro / onboarding
    │   ├── LoginScreen.tsx        # SSO login
    │   ├── UploadScreen.tsx       # Camera capture + file picker
    │   ├── FilesScreen.tsx        # Document list
    │   └── ProfileScreen.tsx      # User profile + sign out
    └── services/
        └── api.ts                 # DocuElevate API client
```

## Share Extension (iOS)

The app registers the `docuelevate://` URL scheme and the `com.docuelevate.app` bundle identifier.  To enable the share sheet:

1. Ensure the app is installed on the device
2. Open any file in Files, Mail, Safari, etc.
3. Tap the share icon → find **DocuElevate** in the share sheet
4. The file is uploaded immediately

Android uses a similar intent filter configured in `app.json`.

## Backend API

The mobile app uses the following backend endpoints:

| Method   | Endpoint                            | Description                           |
|----------|-------------------------------------|---------------------------------------|
| `POST`   | `/api/mobile/generate-token`        | Exchange SSO session for API token    |
| `POST`   | `/api/mobile/register-device`       | Register Expo push token              |
| `GET`    | `/api/mobile/devices`               | List registered devices               |
| `DELETE` | `/api/mobile/devices/{id}`          | Deactivate device registration        |
| `GET`    | `/api/mobile/whoami`                | Get current user profile              |
| `POST`   | `/api/ui-upload`                    | Upload file for processing            |
| `GET`    | `/api/files`                        | List processed documents              |

Authentication uses `Authorization: Bearer <api_token>` on all requests.

## Troubleshooting

### `Session expired Local session` when running `eas build`

EAS CLI stores an Apple ID session locally to manage provisioning profiles and code-signing certificates. This session expires after several weeks.

**Quick fix (local):** Re-authenticate by running:

```bash
eas credentials
```

Select iOS → re-enter your Apple ID credentials when prompted.

**Recommended (CI / automation):** Switch to an [App Store Connect API Key](https://docs.expo.dev/app-signing/app-credentials/#app-store-connect-api-key) which does not expire automatically and works non-interactively:

1. Go to [appstoreconnect.apple.com → Users → Integrations → Keys](https://appstoreconnect.apple.com/access/integrations/api) and create a key with *Developer* or *App Manager* role.
2. Download the `.p8` file; note the **Key ID** and **Issuer ID**.
3. Run `eas credentials` → iOS → *Add an App Store Connect API key* and upload the `.p8` file.

Once an API key is stored in EAS, all future builds (local and CI) will use it automatically without requiring an Apple ID session.

### `[DEP0169] DeprecationWarning: url.parse()` during build

```text
(node:XXXXX) [DEP0169] DeprecationWarning: `url.parse()` behavior is not standardized…
```

This is emitted by EAS CLI itself when it runs on **Node.js 22 or later**, which deprecates `url.parse()`. It is a warning only and does not cause build failures on its own. The `eas.json` build profiles already suppress it via `"NODE_NO_WARNINGS": "1"` in their `env` sections.

To suppress the warning locally, either:

```bash
# Option A: Run with the warning suppressed
NODE_NO_WARNINGS=1 eas build --platform ios

# Option B: Switch to the pinned Node version (no warning on Node 20)
nvm use   # reads .nvmrc → Node 20.19.4
eas build --platform ios
```
