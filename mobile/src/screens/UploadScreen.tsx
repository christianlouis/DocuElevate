/**
 * UploadScreen – document upload via camera, photo library, or file picker.
 *
 * Users can:
 * 1. Take a photo of a document with the device camera.
 * 2. Select an existing photo from the device's photo library.
 * 3. Pick an existing file (PDF, image, Office document) from the Files app.
 * 4. Receive files shared from other apps via the iOS Share Sheet / Android
 *    Share Intent (handled via ShareContext populated by the root layout).
 *
 * After a successful upload the screen polls the backend every 5 seconds to
 * track the real-time processing status of each uploaded file.
 */

import * as DocumentPicker from "expo-document-picker";
import * as ImagePicker from "expo-image-picker";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useAuth } from "../context/AuthContext";
import { useShare } from "../context/ShareContext";
import api from "../services/api";

/** Statuses that indicate processing has finished (no further polling needed). */
const TERMINAL_STATUSES = new Set(["completed", "failed", "duplicate"]);

interface UploadItem {
  id: string;
  filename: string;
  status: "pending" | "uploading" | "done" | "error";
  error?: string;
  taskId?: string;
  /** Sanitised filename returned by the server – used to search for the record. */
  originalFilename?: string;
  /** Database ID of the FileRecord once it has been created by the worker. */
  fileId?: number;
  /** Actual server-side processing status (e.g. "pending", "processing", "completed"). */
  serverStatus?: string;
}

export default function UploadScreen() {
  const { isAuthenticated } = useAuth();
  const { pendingFiles, clearPendingFiles } = useShare();
  const [uploads, setUploads] = useState<UploadItem[]>([]);

  // Keep a ref in sync so the polling interval can read current state without
  // capturing a stale closure.
  const uploadsRef = useRef<UploadItem[]>([]);
  useEffect(() => {
    uploadsRef.current = uploads;
  }, [uploads]);

  // ---------------------------------------------------------------------------
  // Core helpers (declared before the effects that depend on them)
  // ---------------------------------------------------------------------------

  const uploadFile = useCallback(async (uri: string, filename: string, mimeType?: string) => {
    const id = `${Date.now()}-${filename}`;
    setUploads((prev) => [{ id, filename, status: "uploading" }, ...prev]);

    try {
      const resp = await api.uploadFile(uri, filename, mimeType);
      setUploads((prev) =>
        prev.map((item) =>
          item.id === id
            ? { ...item, status: "done", taskId: resp.task_id, originalFilename: resp.original_filename }
            : item
        )
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      setUploads((prev) =>
        prev.map((item) => (item.id === id ? { ...item, status: "error", error: msg } : item))
      );
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Polling – check server-side processing status every 5 seconds
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const poll = async () => {
      const current = uploadsRef.current;
      for (const item of current) {
        // Only poll items that were successfully uploaded and haven't reached a
        // terminal status yet.
        if (item.status !== "done") continue;
        if (item.serverStatus && TERMINAL_STATUSES.has(item.serverStatus)) continue;

        try {
          if (item.fileId !== undefined) {
            // We already know the file ID – just refresh its status.
            const ps = await api.getFileStatus(item.fileId);
            setUploads((prev) =>
              prev.map((u) => (u.id === item.id ? { ...u, serverStatus: ps.status } : u))
            );
          } else if (item.originalFilename) {
            // Search for the file by name; it may not exist yet if the worker
            // hasn't started.
            const files = await api.listFiles(1, 5, item.originalFilename);
            const found = files.find((f) => f.original_filename === item.originalFilename);
            if (found) {
              setUploads((prev) =>
                prev.map((u) =>
                  u.id === item.id
                    ? { ...u, fileId: found.id, serverStatus: found.processing_status.status }
                    : u
                )
              );
            }
          }
        } catch (err) {
          // Network errors are transient – silently retry on the next tick.
          console.debug("[StatusPoll] failed:", err);
        }
      }
    };

    const interval = setInterval(poll, 5000);
    return () => clearInterval(interval);
  }, []); // Intentionally empty – poll() reads state via uploadsRef

  // ---------------------------------------------------------------------------
  // Handle files received from the iOS Share Sheet / Android Share Intent
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (pendingFiles.length === 0 || !isAuthenticated) return;
    const files = [...pendingFiles];
    clearPendingFiles();
    files.forEach((file) => {
      void uploadFile(file.uri, file.filename, file.mimeType);
    });
  }, [pendingFiles, isAuthenticated, clearPendingFiles, uploadFile]);

  async function handleCamera() {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== "granted") {
      Alert.alert(
        "Camera access required",
        "Please grant camera access in Settings to capture documents."
      );
      return;
    }

    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ["images"],
      quality: 0.9,
      allowsEditing: false,
    });

    if (!result.canceled && result.assets.length > 0) {
      const asset = result.assets[0];
      const filename = `scan_${Date.now()}.jpg`;
      await uploadFile(asset.uri, filename, "image/jpeg");
    }
  }

  async function handlePhotoLibrary() {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== "granted") {
      Alert.alert(
        "Photo library access required",
        "Please grant photo library access in Settings to select images."
      );
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.9,
      allowsEditing: false,
    });

    if (!result.canceled && result.assets.length > 0) {
      const asset = result.assets[0];
      const filename = asset.fileName ?? `photo_${Date.now()}.jpg`;
      await uploadFile(asset.uri, filename, asset.mimeType ?? "image/jpeg");
    }
  }

  async function handleFilePicker() {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: "*/*",
        multiple: true,
        copyToCacheDirectory: true,
      });

      if (!result.canceled) {
        for (const asset of result.assets) {
          await uploadFile(asset.uri, asset.name, asset.mimeType ?? undefined);
        }
      }
    } catch (err: unknown) {
      Alert.alert("File picker error", err instanceof Error ? err.message : "Could not open file picker");
    }
  }

  if (!isAuthenticated) {
    return (
      <View style={styles.center}>
        <Text style={styles.emptyText}>Please sign in to upload documents.</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Action buttons */}
      <View style={styles.actions}>
        <Pressable
          style={[styles.actionButton, styles.cameraButton]}
          onPress={handleCamera}
          accessibilityRole="button"
          accessibilityLabel="Capture document with camera"
        >
          <Text style={styles.actionIcon}>📷</Text>
          <Text style={styles.actionLabel}>Camera</Text>
        </Pressable>

        <Pressable
          style={[styles.actionButton, styles.photoLibraryButton]}
          onPress={handlePhotoLibrary}
          accessibilityRole="button"
          accessibilityLabel="Select photo from library"
        >
          <Text style={styles.actionIcon}>🖼️</Text>
          <Text style={styles.actionLabel}>Photos</Text>
        </Pressable>

        <Pressable
          style={[styles.actionButton, styles.fileButton]}
          onPress={handleFilePicker}
          accessibilityRole="button"
          accessibilityLabel="Pick file from device"
        >
          <Text style={styles.actionIcon}>📄</Text>
          <Text style={styles.actionLabel}>Files</Text>
        </Pressable>
      </View>

      {/* Upload list */}
      <ScrollView style={styles.list} contentContainerStyle={styles.listContent}>
        {uploads.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyEmoji}>☁️</Text>
            <Text style={styles.emptyText}>
              Tap Camera, Photos, or Files to upload a document.
            </Text>
            <Text style={styles.emptyHint}>
              You can also share files from other apps directly to DocuElevate.
            </Text>
          </View>
        ) : (
          uploads.map((item) => (
            <UploadRow key={item.id} item={item} />
          ))
        )}
      </ScrollView>
    </View>
  );
}

function UploadRow({ item }: { item: UploadItem }) {
  const uploadIcons: Record<UploadItem["status"], string> = {
    pending: "⏳",
    uploading: "⬆️",
    done: "✅",
    error: "❌",
  };

  /** Human-readable label for the server-side processing status. */
  function serverStatusLabel(s: string): string {
    const labels: Record<string, string> = {
      pending: "Queued for processing…",
      processing: "Processing…",
      completed: "Processed ✓",
      failed: "Processing failed",
      duplicate: "Duplicate – already processed",
    };
    return labels[s] ?? s;
  }

  return (
    <View style={rowStyles.row}>
      <Text style={rowStyles.icon}>{uploadIcons[item.status]}</Text>
      <View style={rowStyles.info}>
        <Text style={rowStyles.filename} numberOfLines={1}>
          {item.filename}
        </Text>
        {item.status === "uploading" && (
          <ActivityIndicator size="small" color="#1e40af" />
        )}
        {item.status === "done" && !item.serverStatus && (
          <Text style={rowStyles.statusQueued}>Queued for processing…</Text>
        )}
        {item.status === "done" && item.serverStatus && (
          <Text
            style={
              item.serverStatus === "completed"
                ? rowStyles.statusDone
                : item.serverStatus === "failed"
                ? rowStyles.statusError
                : rowStyles.statusQueued
            }
          >
            {serverStatusLabel(item.serverStatus)}
          </Text>
        )}
        {item.status === "error" && (
          <Text style={rowStyles.statusError}>{item.error}</Text>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f9fafb" },
  actions: {
    flexDirection: "row",
    padding: 16,
    gap: 12,
  },
  actionButton: {
    flex: 1,
    borderRadius: 12,
    paddingVertical: 20,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 80,
  },
  cameraButton: { backgroundColor: "#1e40af" },
  photoLibraryButton: { backgroundColor: "#7c3aed" },
  fileButton: { backgroundColor: "#059669" },
  actionIcon: { fontSize: 28, marginBottom: 6 },
  actionLabel: {
    color: "#fff",
    fontSize: 14,
    fontWeight: "600",
  },
  list: { flex: 1 },
  listContent: { padding: 16 },
  emptyState: {
    alignItems: "center",
    paddingTop: 60,
  },
  emptyEmoji: { fontSize: 48, marginBottom: 12 },
  emptyText: {
    fontSize: 16,
    color: "#374151",
    textAlign: "center",
    marginBottom: 8,
  },
  emptyHint: {
    fontSize: 13,
    color: "#6b7280",
    textAlign: "center",
    paddingHorizontal: 32,
  },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
});

const rowStyles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fff",
    borderRadius: 10,
    padding: 14,
    marginBottom: 10,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 4,
    elevation: 2,
  },
  icon: { fontSize: 22, marginRight: 12 },
  info: { flex: 1 },
  filename: {
    fontSize: 14,
    fontWeight: "600",
    color: "#111827",
    marginBottom: 4,
  },
  statusDone: { fontSize: 12, color: "#059669" },
  statusQueued: { fontSize: 12, color: "#6b7280" },
  statusError: { fontSize: 12, color: "#dc2626" },
});
