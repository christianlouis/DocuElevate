/**
 * Catch-all "not found" route for expo-router.
 *
 * This screen intercepts two different situations:
 *
 * 1. **iOS "Open In…" / share sheet** — iOS delivers files to the app via a
 *    `docuelevate://<path>` URL.  expo-router strips the custom scheme and
 *    tries to match the raw filesystem path (e.g.
 *    `/private/var/mobile/Library/…/file.pdf`) as an in-app route.  Because
 *    no such route exists, expo-router previously threw "unmatched route
 *    docuelevate://…" and the upload never happened.
 *
 *    This screen detects the filesystem-path pattern, adds the file directly
 *    to `ShareContext`, and redirects to the Upload tab.  `UploadScreen`
 *    picks up the pending file and begins uploading automatically.
 *
 *    The `Linking` listener in `_layout.tsx` may also fire for the same URL;
 *    `ShareContext.addPendingFile` deduplicates by URI so the file is only
 *    uploaded once.
 *
 * 2. **Any other unmatched in-app route** — redirect silently to the root so
 *    the user isn't left on a blank error page.
 */

import { usePathname, useRouter } from "expo-router";
import React, { useEffect } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { useShare } from "../src/context/ShareContext";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * First path-segment names that identify iOS/Android sandbox filesystem paths.
 * These can never be expo-router route-group names, so their presence is a
 * strong positive signal that the URL is a shared file rather than a route.
 *
 *   iOS:     /private/var/mobile/…   → "private"
 *            /var/mobile/…           → "var"  (symlink to /private/var/mobile)
 *            /tmp/…                  → "tmp"
 *   Android: /data/user/0/…          → "data"
 *            /storage/emulated/0/…   → "storage"
 */
const FS_PATH_ROOTS = ["private", "var", "tmp", "data", "storage"];

/**
 * Route-group / special-file prefixes that identify genuine in-app routes
 * rather than filesystem path segments.
 *
 * ⚠️  Keep this list in sync with the top-level entries in the `app/`
 *     directory.  Add an entry here if you add a new top-level route group
 *     that does **not** use the parentheses convention.
 */
const IN_APP_ROUTE_PREFIXES = [
  "(auth)",  // app/(auth)/
  "(tabs)",  // app/(tabs)/
  "_",       // expo-router special files (_layout, _sitemap, …)
  "+",       // expo-router special files (+not-found, …)
  "--",      // Expo Go development proxy prefix
];

/**
 * Return `true` when `pathname` looks like a filesystem path delivered by iOS
 * "Open In…" (e.g. `/private/var/mobile/Library/…/file.pdf`) rather than a
 * legitimate in-app route.
 *
 * Detection strategy:
 *   1. **Positive check** – if the first path segment matches a known device
 *      filesystem root (see `FS_PATH_ROOTS`), it is definitely a file path.
 *   2. **Fallback negative check** – if the path does not start with any known
 *      in-app route prefix (see `IN_APP_ROUTE_PREFIXES`), treat it as a file
 *      path.  This is a heuristic but safe because expo-router route groups
 *      always use parentheses (e.g. `(auth)`, `(tabs)`).
 */
function looksLikeFilePath(pathname: string): boolean {
  const stripped = pathname.replace(/^\/+/, "");
  if (stripped.length === 0) return false;

  // Positive signal: path starts with a known device filesystem root segment.
  const firstSegment = stripped.split("/")[0];
  if (FS_PATH_ROOTS.includes(firstSegment)) return true;

  // Fallback: paths that start with a known in-app route prefix are routes.
  return !IN_APP_ROUTE_PREFIXES.some((prefix) => stripped.startsWith(prefix));
}

/**
 * Extract a display filename from a filesystem path.
 * Handles URL-encoded characters and strips query strings.
 */
function filenameFromPath(pathname: string): string {
  try {
    const decoded = decodeURIComponent(pathname);
    const segments = decoded.split("/").filter(Boolean);
    const last = segments[segments.length - 1] ?? "shared_file";
    return last.split("?")[0] || "shared_file";
  } catch {
    return "shared_file";
  }
}

// ---------------------------------------------------------------------------
// Screen component
// ---------------------------------------------------------------------------

export default function NotFoundScreen() {
  const pathname = usePathname();
  const router = useRouter();
  const { addPendingFile } = useShare();

  useEffect(() => {
    if (looksLikeFilePath(pathname)) {
      // Filesystem path from iOS "Open In…" – add the file to ShareContext
      // and redirect to the Upload tab.  UploadScreen will pick up the
      // pending file and begin uploading automatically.
      //
      // The pathname from expo-router is the raw filesystem path
      // (e.g. "/private/var/mobile/Library/…/file.pdf").  Reconstruct a
      // file:// URI so the upload logic can read the file.
      const fileUri = `file://${pathname}`;
      const filename = filenameFromPath(pathname);
      addPendingFile({ uri: fileUri, filename });
      router.replace("/(tabs)/");
    } else {
      // Truly unknown in-app route – fall back to the root redirect.
      router.replace("/");
    }
  }, [pathname, router, addPendingFile]);

  // Show a brief spinner while the redirect is in flight.
  return (
    <View style={styles.container}>
      <ActivityIndicator size="large" color="#1e40af" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#f9fafb",
  },
});
