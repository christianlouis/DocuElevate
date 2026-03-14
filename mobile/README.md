# DocuElevate Mobile App

Native mobile application for DocuElevate, built with **React Native** and **Expo** for both iOS (primary) and Android.

## Features

- 🔐 **SSO Login** – authenticate via your DocuElevate server's OAuth2/SSO provider; an API token is auto-generated and stored securely in the device keychain
- 📷 **Camera Capture** – scan documents directly with the device camera
- 📄 **File Picker** – upload PDFs, images, and Office documents from the device's Files app
- 🔗 **Share Extension** – send files from any app directly to DocuElevate via the iOS/Android share sheet
- 🔔 **Push Notifications** – receive real-time push notifications when documents finish processing (via Expo push notifications)
- 📂 **Document List** – browse and search your processed documents
- 👤 **Profile** – view account details and sign out

## Requirements

- Node.js 18+
- Expo CLI (`npm install -g @expo/cli`)
- Expo Go app on device (for development) **or** Expo Application Services (EAS) for production builds
- An Expo account: <https://expo.dev/>

## Setup

```bash
# 1. Install dependencies
cd mobile
npm install

# 2. Start the development server
npx expo start
```

Scan the QR code with **Expo Go** on your iOS or Android device.

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

- Add a `google-services.json` file (from Firebase Console) to the `mobile/` directory for push notification support
- For Play Store submission: create a service account in Google Play Console, download the JSON key as `google-play-service-account.json`, and update `eas.json`

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
├── App.tsx                    # Root component
├── app.json                   # Expo configuration
├── eas.json                   # EAS Build configuration
├── package.json
├── tsconfig.json
└── src/
    ├── context/
    │   └── AuthContext.tsx    # Authentication state management
    ├── hooks/
    │   └── usePushNotifications.ts  # Push notification registration
    ├── screens/
    │   ├── LoginScreen.tsx    # SSO login
    │   ├── UploadScreen.tsx   # Camera capture + file picker
    │   ├── FilesScreen.tsx    # Document list
    │   └── ProfileScreen.tsx  # User profile + sign out
    └── services/
        └── api.ts             # DocuElevate API client
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
