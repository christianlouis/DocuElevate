/**
 * Root layout for the DocuElevate mobile app.
 *
 * Wraps the entire app in AuthProvider and SafeAreaProvider, then uses the
 * AuthGuard component to redirect between the unauthenticated (auth) route
 * group and the authenticated (tabs) route group based on session state.
 *
 * ShareProvider + Linking listener: when iOS opens the app via the share
 * sheet (CFBundleDocumentTypes) or Android via a SEND intent, the incoming
 * file:// / content:// URL is captured and forwarded to UploadScreen via
 * ShareContext.
 */

import * as Linking from "expo-linking";
import { Stack, useRouter, useSegments } from "expo-router";
import React, { useEffect } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AuthProvider, useAuth } from "../src/context/AuthContext";
import { ShareProvider, useShare } from "../src/context/ShareContext";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** The custom URL scheme registered in app.json. */
const APP_SCHEME_PREFIX = "docuelevate://";

/** Extract a display filename from a file:// or content:// URI. */
function filenameFromUri(uri: string): string {
  try {
    const decoded = decodeURIComponent(uri);
    // Take the last path segment and strip any query string
    const last = decoded.split("/").pop() ?? "shared_file";
    return last.split("?")[0] || "shared_file";
  } catch {
    return "shared_file";
  }
}

/**
 * Build a Linking URL handler that forwards incoming file:// / content://
 * URLs to ShareContext.  Extracted as a module-level factory so the handler
 * itself is created once and can be easily unit-tested without a React context.
 *
 * On iOS the Share Sheet / "Open In" action may deliver the file path under
 * the app's custom URL scheme (`docuelevate://…/file.pdf`) instead of a plain
 * `file://` URL.  When that happens we rewrite the URL to `file:///…` so the
 * upload logic can read the file normally.
 */
function makeUrlHandler(addPendingFile: (f: { uri: string; filename: string }) => void) {
  return ({ url }: { url: string }) => {
    let fileUri = url;

    // iOS may pass a filesystem path under the app's custom scheme.
    // Rewrite it to a file:// URL unless it looks like an in-app deep-link
    // (expo-router groups always start with "(").
    if (url.startsWith(APP_SCHEME_PREFIX)) {
      const path = url.slice(APP_SCHEME_PREFIX.length);
      if (path.length > 0 && !path.startsWith("(")) {
        fileUri = "file:///" + path.replace(/^\/+/, "");
      }
    }

    if (!fileUri.startsWith("file://") && !fileUri.startsWith("content://")) return;
    addPendingFile({ uri: fileUri, filename: filenameFromUri(fileUri) });
  };
}

// ---------------------------------------------------------------------------
// Auth guard – redirects to the correct route group after auth state resolves
// ---------------------------------------------------------------------------

function AuthGuard() {
  const { isLoading, isAuthenticated } = useAuth();
  const { addPendingFile } = useShare();
  const segments = useSegments();
  const router = useRouter();

  // Listen for files shared from other apps (iOS Share Sheet / Android Intent).
  // Both cold-start (app was not running) and warm-start (app in background)
  // cases are handled.
  useEffect(() => {
    const handleIncomingUrl = makeUrlHandler(addPendingFile);

    // Cold start – app launched directly by a share action
    Linking.getInitialURL().then((url) => {
      if (url) handleIncomingUrl({ url });
    });

    // Warm start – app was already running when the share action occurred
    const subscription = Linking.addEventListener("url", handleIncomingUrl);
    return () => subscription.remove();
  }, [addPendingFile]);

  useEffect(() => {
    if (isLoading) return;

    const inAuthGroup = segments[0] === "(auth)";

    if (!isAuthenticated && !inAuthGroup) {
      // Unauthenticated visitor outside the auth group → send to welcome
      router.replace("/(auth)/");
    } else if (isAuthenticated && inAuthGroup) {
      // Authenticated user on auth screens → send to main app
      router.replace("/(tabs)/");
    }
  }, [isAuthenticated, isLoading, segments, router]);

  if (isLoading) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator size="large" color="#1e40af" />
        <Text style={styles.loadingText}>Loading…</Text>
      </View>
    );
  }

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="(auth)" />
      <Stack.Screen name="(tabs)" />
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Root layout export
// ---------------------------------------------------------------------------

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <ShareProvider>
        <AuthProvider>
          <AuthGuard />
        </AuthProvider>
      </ShareProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#f9fafb",
    gap: 12,
  },
  loadingText: {
    color: "#6b7280",
    fontSize: 15,
  },
});
