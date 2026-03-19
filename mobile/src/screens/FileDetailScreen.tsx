/**
 * FileDetailScreen – shows detailed status and processing logs for a single file.
 *
 * Replicates the web /files/:id and /files/:id/detail views in a
 * mobile-friendly layout.  Displays file metadata, processing status with
 * a progress indicator, and a chronological list of processing log entries.
 */

import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import type { FileDetail } from "../services/api";
import api from "../services/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "–";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function statusColor(status: string): string {
  const colors: Record<string, string> = {
    completed: "#059669",
    processing: "#d97706",
    pending: "#6b7280",
    failed: "#dc2626",
    duplicate: "#6b7280",
  };
  return colors[status?.toLowerCase()] ?? "#6b7280";
}

function statusIcon(status: string): keyof typeof Ionicons.glyphMap {
  const icons: Record<string, keyof typeof Ionicons.glyphMap> = {
    completed: "checkmark-circle",
    processing: "sync-circle",
    pending: "time-outline",
    failed: "close-circle",
    duplicate: "copy-outline",
  };
  return icons[status?.toLowerCase()] ?? "document-outline";
}

function logStepIcon(status: string): { name: keyof typeof Ionicons.glyphMap; color: string } {
  const lower = status?.toLowerCase();
  if (lower === "completed" || lower === "success") return { name: "checkmark-circle", color: "#059669" };
  if (lower === "failed" || lower === "error") return { name: "close-circle", color: "#dc2626" };
  if (lower === "skipped") return { name: "remove-circle-outline", color: "#9ca3af" };
  if (lower === "processing" || lower === "running") return { name: "sync-circle", color: "#d97706" };
  return { name: "ellipse-outline", color: "#6b7280" };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function FileDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [detail, setDetail] = useState<FileDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fileId = parseInt(id ?? "0", 10);

  const fetchDetail = useCallback(async () => {
    if (!fileId) return;
    try {
      const data = await api.getFileDetail(fileId);
      setDetail(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load file details");
    }
  }, [fileId]);

  useEffect(() => {
    (async () => {
      setLoading(true);
      await fetchDetail();
      setLoading(false);
    })();
  }, [fetchDetail]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchDetail();
    setRefreshing(false);
  }, [fetchDetail]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#1e40af" />
      </View>
    );
  }

  if (error || !detail) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>{error ?? "File not found"}</Text>
        <Pressable style={styles.retryButton} onPress={handleRefresh}>
          <Text style={styles.retryText}>Retry</Text>
        </Pressable>
        <Pressable style={styles.backButton} onPress={() => router.back()}>
          <Text style={styles.backButtonText}>← Back</Text>
        </Pressable>
      </View>
    );
  }

  const file = detail.file;
  const status = detail.processing_status;

  return (
    <ScrollView
      style={styles.scroll}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />}
    >
      {/* Header with back button */}
      <Pressable
        style={styles.backRow}
        onPress={() => router.back()}
        accessibilityRole="button"
        accessibilityLabel="Go back"
      >
        <Ionicons name="arrow-back" size={20} color="#1e40af" />
        <Text style={styles.backLabel}>Back to Files</Text>
      </Pressable>

      {/* File info card */}
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <Ionicons
            name={statusIcon(status.status)}
            size={28}
            color={statusColor(status.status)}
            style={{ marginRight: 12 }}
          />
          <View style={{ flex: 1 }}>
            <Text style={styles.filename} numberOfLines={2}>
              {file.original_filename}
            </Text>
            <Text style={[styles.statusBadge, { color: statusColor(status.status) }]}>
              {status.status.charAt(0).toUpperCase() + status.status.slice(1)}
            </Text>
          </View>
        </View>

        <View style={styles.metaGrid}>
          <MetaRow label="File Size" value={formatBytes(file.file_size)} />
          <MetaRow label="MIME Type" value={file.mime_type ?? "–"} />
          <MetaRow label="Uploaded" value={formatDateTime(file.created_at)} />
          <MetaRow label="File Hash" value={file.filehash ? `${file.filehash.slice(0, 16)}…` : "–"} />
          <MetaRow label="Last Step" value={status.last_step ?? "–"} />
          <MetaRow label="Total Steps" value={String(status.total_steps)} />
        </View>
      </View>

      {/* Processing logs */}
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Processing Log</Text>
        {detail.logs.length === 0 ? (
          <Text style={styles.emptyLog}>No processing logs yet.</Text>
        ) : (
          detail.logs.map((log, idx) => {
            const icon = logStepIcon(log.status);
            const isLast = idx === detail.logs.length - 1;
            return (
              <View key={log.id} style={[styles.logEntry, !isLast && styles.logEntryBorder]}>
                <Ionicons name={icon.name} size={18} color={icon.color} style={styles.logIcon} />
                <View style={styles.logContent}>
                  <Text style={styles.logStep}>{log.step_name}</Text>
                  <Text style={styles.logMessage} numberOfLines={3}>
                    {log.message}
                  </Text>
                  <Text style={styles.logTimestamp}>{formatDateTime(log.timestamp)}</Text>
                </View>
              </View>
            );
          })
        )}
      </View>
    </ScrollView>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metaRow}>
      <Text style={styles.metaLabel}>{label}</Text>
      <Text style={styles.metaValue} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: "#f9fafb" },
  content: { padding: 16, paddingBottom: 40 },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#f9fafb",
    padding: 24,
  },
  errorText: { color: "#dc2626", fontSize: 15, textAlign: "center", marginBottom: 16 },
  retryButton: {
    backgroundColor: "#1e40af",
    borderRadius: 8,
    paddingHorizontal: 24,
    paddingVertical: 10,
    marginBottom: 12,
  },
  retryText: { color: "#fff", fontWeight: "600" },
  backButton: { paddingVertical: 10 },
  backButtonText: { color: "#6b7280", fontSize: 14 },
  backRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 16,
    minHeight: 44,
  },
  backLabel: {
    fontSize: 15,
    color: "#1e40af",
    fontWeight: "600",
    marginLeft: 6,
  },
  card: {
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 6,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginBottom: 16,
  },
  filename: {
    fontSize: 17,
    fontWeight: "700",
    color: "#111827",
    marginBottom: 4,
  },
  statusBadge: {
    fontSize: 13,
    fontWeight: "600",
    textTransform: "capitalize",
  },
  metaGrid: {},
  metaRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: "#f3f4f6",
  },
  metaLabel: { fontSize: 13, color: "#6b7280", fontWeight: "500" },
  metaValue: { fontSize: 13, color: "#374151", maxWidth: "55%", textAlign: "right" },
  sectionTitle: {
    fontSize: 15,
    fontWeight: "700",
    color: "#374151",
    marginBottom: 12,
  },
  emptyLog: { fontSize: 13, color: "#9ca3af", fontStyle: "italic" },
  logEntry: {
    flexDirection: "row",
    alignItems: "flex-start",
    paddingVertical: 10,
  },
  logEntryBorder: {
    borderBottomWidth: 1,
    borderBottomColor: "#f3f4f6",
  },
  logIcon: { marginRight: 10, marginTop: 1 },
  logContent: { flex: 1 },
  logStep: { fontSize: 13, fontWeight: "600", color: "#374151", marginBottom: 2 },
  logMessage: { fontSize: 12, color: "#6b7280", lineHeight: 17, marginBottom: 2 },
  logTimestamp: { fontSize: 11, color: "#9ca3af" },
});
