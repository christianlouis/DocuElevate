/**
 * ShareContext – propagates files received from the iOS Share Sheet or the
 * Android Share Intent to the UploadScreen so they can be uploaded
 * automatically.
 *
 * The root layout listens for incoming file:// / content:// URLs via
 * expo-linking and calls addPendingFile().  UploadScreen consumes the context,
 * uploads each pending file, then calls clearPendingFiles().
 */

import React, { createContext, useCallback, useContext, useState } from "react";

export interface SharedFile {
  uri: string;
  filename: string;
  mimeType?: string;
}

interface ShareContextValue {
  pendingFiles: SharedFile[];
  addPendingFile: (file: SharedFile) => void;
  clearPendingFiles: () => void;
}

const ShareContext = createContext<ShareContextValue>({
  pendingFiles: [],
  addPendingFile: () => {},
  clearPendingFiles: () => {},
});

/**
 * Aggressively normalise a file URI so that the same physical file is
 * recognised regardless of how the URI was constructed.
 *
 * - Decode percent-encoding (`%20` → ` `)
 * - Collapse consecutive slashes after the scheme (`file:////` → `file:///`)
 * - Strip trailing slashes
 */
function normalizeFileUri(uri: string): string {
  let norm: string;
  try {
    norm = decodeURIComponent(uri);
  } catch {
    norm = uri;
  }
  // Collapse multiple slashes after the scheme (e.g. file://// → file:///)
  norm = norm.replace(/^(file:\/\/)\/{2,}/, "$1/");
  // Strip trailing slash
  norm = norm.replace(/\/+$/, "");
  return norm;
}

export function ShareProvider({ children }: { children: React.ReactNode }) {
  const [pendingFiles, setPendingFiles] = useState<SharedFile[]>([]);

  const addPendingFile = useCallback((file: SharedFile) => {
    setPendingFiles((prev) => {
      // Deduplicate by normalised URI so the same file is not uploaded twice
      // when both the Linking handler (_layout.tsx) and +not-found.tsx fire.
      const norm = normalizeFileUri(file.uri);
      if (prev.some((f) => normalizeFileUri(f.uri) === norm)) return prev;
      return [...prev, file];
    });
  }, []);

  const clearPendingFiles = useCallback(() => {
    setPendingFiles([]);
  }, []);

  return (
    <ShareContext.Provider value={{ pendingFiles, addPendingFile, clearPendingFiles }}>
      {children}
    </ShareContext.Provider>
  );
}

export function useShare(): ShareContextValue {
  return useContext(ShareContext);
}
