/**
 * UploadScreen – document upload via camera or file picker.
 *
 * Users can:
 * 1. Take a photo of a document with the device camera.
 * 2. Pick an existing file (PDF, image, Office document) from the Files app.
 * 3. Receive files shared from other apps via the iOS Share Sheet / Android
 *    Share Intent (handled by the expo-sharing + deep-link integration).
 */

import * as DocumentPicker from "expo-document-picker";
import * as ImagePicker from "expo-image-picker";
import React, { useState } from "react";
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
import api from "../services/api";

interface UploadItem {
  id: string;
  filename: string;
  status: "pending" | "uploading" | "done" | "error";
  error?: string;
  taskId?: string;
}

export default function UploadScreen() {
  const { isAuthenticated } = useAuth();
  const [uploads, setUploads] = useState<UploadItem[]>([]);

  function updateItem(id: string, patch: Partial<UploadItem>) {
    setUploads((prev) =>
      prev.map((item) => (item.id === id ? { ...item, ...patch } : item))
    );
  }

  async function uploadFile(uri: string, filename: string, mimeType?: string) {
    const id = `${Date.now()}-${filename}`;
    setUploads((prev) => [
      { id, filename, status: "uploading" },
      ...prev,
    ]);

    try {
      const resp = await api.uploadFile(uri, filename, mimeType);
      updateItem(id, { status: "done", taskId: resp.task_id });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      updateItem(id, { status: "error", error: msg });
    }
  }

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
          style={[styles.actionButton, styles.fileButton]}
          onPress={handleFilePicker}
          accessibilityRole="button"
          accessibilityLabel="Pick file from device"
        >
          <Text style={styles.actionIcon}>📄</Text>
          <Text style={styles.actionLabel}>File Picker</Text>
        </Pressable>
      </View>

      {/* Upload list */}
      <ScrollView style={styles.list} contentContainerStyle={styles.listContent}>
        {uploads.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyEmoji}>☁️</Text>
            <Text style={styles.emptyText}>
              Tap Camera or File Picker to upload a document.
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
  const icons: Record<UploadItem["status"], string> = {
    pending: "⏳",
    uploading: "⬆️",
    done: "✅",
    error: "❌",
  };

  return (
    <View style={rowStyles.row}>
      <Text style={rowStyles.icon}>{icons[item.status]}</Text>
      <View style={rowStyles.info}>
        <Text style={rowStyles.filename} numberOfLines={1}>
          {item.filename}
        </Text>
        {item.status === "uploading" && (
          <ActivityIndicator size="small" color="#1e40af" />
        )}
        {item.status === "done" && (
          <Text style={rowStyles.statusDone}>Queued for processing</Text>
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
  statusError: { fontSize: 12, color: "#dc2626" },
});
