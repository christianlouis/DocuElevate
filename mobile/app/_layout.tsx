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
 *
 * The companion `+not-found.tsx` handles the case where expo-router receives
 * a `docuelevate://` URL with a filesystem path (from iOS "Open In…") and
 * cannot match it to a route.  It adds the file directly to ShareContext and
 * redirects to the Upload tab so the file is uploaded transparently.
 */

import * as Linking from "expo-linking";
import { Stack, useRouter, useSegments } from "expo-router";
import React, { useEffect } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AuthProvider, useAuth } from "../src/context/AuthContext";
import { ShareProvider, useShare } from "../src/context/ShareContext";
import { LocaleProvider, useLocale, isLanguageSupported, t } from "../src/i18n";
import { mimeTypeFromFilename } from "../src/utils/mimeTypes";
import api from "../src/services/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** The custom URL scheme registered in app.json. */
const APP_SCHEME_PREFIX = "docuelevate://";

/**
 * Known deep-link path prefixes that should NOT be treated as shared files.
 * These are in-app deep-link routes handled by their respective screens
 * (e.g. QR login, OAuth callback).
 */

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
 * On iOS the Share Sheet / "Open In…" action may deliver the file path under
 * the app's custom URL scheme (`docuelevate://…/file.pdf`) instead of a plain
 * `file://` URL.  When that happens we rewrite the URL to `file:///…` so the
 * upload logic can read the file normally.
 *
 * Note: expo-router also receives the same URL and will attempt to match it as
 * an in-app route.  When no route matches it renders `+not-found.tsx`, which
 * adds the file to ShareContext directly and redirects to the Upload tab.
 * Both this handler and `+not-found.tsx` call `addPendingFile`;
 * `ShareContext` deduplicates by URI so the file is only uploaded once.
 */
function makeUrlHandler(addPendingFile: (f: { uri: string; filename: string; mimeType?: string }) => void) {
  return ({ url }: { url: string }) => {
    let fileUri = url;

    // iOS may pass a filesystem path under the app's custom scheme.
    // Custom-scheme URLs are never proof of an OS-granted local file.
    if (url.startsWith(APP_SCHEME_PREFIX)) {
      return;
    }

    if (!fileUri.startsWith("file://") && !fileUri.startsWith("content://")) return;
    const filename = filenameFromUri(fileUri);
    addPendingFile({ uri: fileUri, filename, mimeType: mimeTypeFromFilename(filename) });
  };
}

// ---------------------------------------------------------------------------
// Auth guard – redirects to the correct route group after auth state resolves
// ---------------------------------------------------------------------------

function AuthGuard() {
  const { isLoading, isAuthenticated, user, signOut } = useAuth();
  const { addPendingFile } = useShare();
  const { setLang } = useLocale();
  const segments = useSegments();
  const router = useRouter();
  const [onboarding, setOnboarding] = React.useState<"checking" | "complete" | "incomplete" | "error">("checking");
  const [retry, setRetry] = React.useState(0);
  const [checkedRoute, setCheckedRoute] = React.useState<boolean | null>(null);
  const [checkedOwner, setCheckedOwner] = React.useState<string | null>(null);
  const onOnboarding = segments[0] === "onboarding";

  // Apply the server-side language preference whenever the user profile is
  // loaded (on login or app resume).  This syncs the language set on the
  // desktop/web client to the mobile app.  If the server language is not
  // supported by the mobile app, we leave the current language unchanged.
  useEffect(() => {
    if (user?.preferred_language && isLanguageSupported(user.preferred_language)) {
      void setLang(user.preferred_language);
    }
  }, [user?.preferred_language, setLang]);

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
    if (isLoading || !isAuthenticated) {
      setOnboarding("checking");
      return;
    }
    let active = true;
    setOnboarding("checking");
    api.onboardingStatus().then((status) => {
      if (active) { setCheckedRoute(onOnboarding); setCheckedOwner(user?.owner_id || null); setOnboarding(status.completed ? "complete" : "incomplete"); }
    }).catch(() => { if (active) setOnboarding("error"); });
    return () => { active = false; };
  }, [isLoading, isAuthenticated, user?.owner_id, onOnboarding, retry]);

  useEffect(() => {
    if (isLoading) return;
    const inAuthGroup = segments[0] === "(auth)";
    if (!isAuthenticated) {
      if (!inAuthGroup) router.replace("/(auth)/");
    } else if ((checkedRoute !== onOnboarding || checkedOwner !== (user?.owner_id || null))) {
      return;
    } else if (onboarding === "incomplete") {
      if (!onOnboarding) router.replace("/onboarding");
    } else if (onboarding === "complete" && (inAuthGroup || onOnboarding)) {
      router.replace("/(tabs)/");
    }
  }, [isAuthenticated, isLoading, segments, onOnboarding, onboarding, checkedRoute, checkedOwner, user?.owner_id, router]);

  return (
    <View style={{ flex: 1 }}>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="(auth)" />
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="+not-found" />
      </Stack>
      {(isLoading || (isAuthenticated && (onboarding === "checking" || onboarding === "error" || checkedRoute !== onOnboarding || checkedOwner !== (user?.owner_id || null)))) && (
        <View style={[styles.loading, StyleSheet.absoluteFillObject]}>
          {onboarding === "error" && !isLoading ? <>
            <Text style={styles.loadingText}>{t("onboarding.status_failed")}</Text>
            <Pressable onPress={() => setRetry((value) => value + 1)}><Text style={styles.loadingText}>{t("common.retry")}</Text></Pressable>
            <Pressable onPress={() => void signOut()}><Text style={styles.loadingText}>{t("signup.back_login")}</Text></Pressable>
          </> : <><ActivityIndicator size="large" color="#1e40af" /><Text style={styles.loadingText}>Loading…</Text></>}
        </View>
      )}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Root layout export
// ---------------------------------------------------------------------------

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <LocaleProvider>
        <ShareProvider>
          <AuthProvider>
            <AuthGuard />
          </AuthProvider>
        </ShareProvider>
      </LocaleProvider>
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
