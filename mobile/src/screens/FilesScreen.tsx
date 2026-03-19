/**
 * FilesScreen – list of documents processed by DocuElevate with search.
 */

import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import type { FileRecord } from "../services/api";
import api from "../services/api";

function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return "–";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function statusIcon(status: string): { name: keyof typeof Ionicons.glyphMap; color: string } {
  const map: Record<string, { name: keyof typeof Ionicons.glyphMap; color: string }> = {
    completed: { name: "checkmark-circle", color: "#059669" },
    processing: { name: "sync-circle", color: "#d97706" },
    pending: { name: "time-outline", color: "#6b7280" },
    failed: { name: "close-circle", color: "#dc2626" },
    duplicate: { name: "copy-outline", color: "#6b7280" },
  };
  return map[status?.toLowerCase()] ?? { name: "document-outline", color: "#6b7280" };
}

export default function FilesScreen() {
  const router = useRouter();
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchFiles = useCallback(
    async (pageNum: number, replace: boolean, search?: string) => {
      try {
        const data = await api.listFiles(pageNum, 20, search || undefined);
        if (replace) {
          setFiles(data);
        } else {
          setFiles((prev) => [...prev, ...data]);
        }
        setHasMore(data.length === 20);
        setError(null);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to load files");
      }
    },
    []
  );

  useEffect(() => {
    (async () => {
      setLoading(true);
      await fetchFiles(1, true);
      setLoading(false);
    })();
  }, [fetchFiles]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    setPage(1);
    await fetchFiles(1, true, searchQuery);
    setRefreshing(false);
  }, [fetchFiles, searchQuery]);

  const handleLoadMore = useCallback(async () => {
    if (!hasMore || loading || refreshing) return;
    const next = page + 1;
    setPage(next);
    await fetchFiles(next, false, searchQuery);
  }, [fetchFiles, hasMore, loading, page, refreshing, searchQuery]);

  const handleSearch = useCallback(
    (text: string) => {
      setSearchQuery(text);
      // Debounce search requests
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
      searchTimeoutRef.current = setTimeout(async () => {
        setPage(1);
        setLoading(true);
        await fetchFiles(1, true, text);
        setLoading(false);
      }, 400);
    },
    [fetchFiles]
  );

  const handleClearSearch = useCallback(() => {
    setSearchQuery("");
    setPage(1);
    setLoading(true);
    fetchFiles(1, true).then(() => setLoading(false));
  }, [fetchFiles]);

  const handleFilePress = useCallback(
    (file: FileRecord) => {
      router.push({ pathname: "/(tabs)/file-detail", params: { id: String(file.id) } });
    },
    [router]
  );

  if (loading && files.length === 0) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#1e40af" />
      </View>
    );
  }

  if (error && files.length === 0) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>{error}</Text>
        <Pressable style={styles.retryButton} onPress={handleRefresh}>
          <Text style={styles.retryText}>Retry</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Search bar */}
      <View style={styles.searchContainer}>
        <Ionicons name="search-outline" size={18} color="#9ca3af" style={styles.searchIcon} />
        <TextInput
          style={styles.searchInput}
          placeholder="Search documents…"
          placeholderTextColor="#9ca3af"
          value={searchQuery}
          onChangeText={handleSearch}
          autoCapitalize="none"
          autoCorrect={false}
          returnKeyType="search"
          accessibilityLabel="Search documents"
        />
        {searchQuery.length > 0 && (
          <Pressable
            onPress={handleClearSearch}
            style={styles.clearButton}
            accessibilityRole="button"
            accessibilityLabel="Clear search"
          >
            <Ionicons name="close-circle" size={18} color="#9ca3af" />
          </Pressable>
        )}
      </View>

      <FlatList
        style={styles.list}
        data={files}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={styles.listContent}
        renderItem={({ item }) => <FileRow file={item} onPress={handleFilePress} />}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
        }
        onEndReached={handleLoadMore}
        onEndReachedThreshold={0.4}
        ListEmptyComponent={
          <View style={styles.emptyState}>
            <Ionicons name="folder-open-outline" size={48} color="#9ca3af" style={{ marginBottom: 12 }} />
            <Text style={styles.emptyText}>
              {searchQuery ? "No documents match your search." : "No documents yet."}
            </Text>
            <Text style={styles.emptyHint}>
              {searchQuery
                ? "Try a different search term."
                : "Upload a document from the Upload tab to get started."}
            </Text>
          </View>
        }
        ListFooterComponent={
          hasMore && files.length > 0 ? (
            <ActivityIndicator color="#1e40af" style={{ marginVertical: 16 }} />
          ) : null
        }
      />
    </View>
  );
}

function FileRow({ file, onPress }: { file: FileRecord; onPress: (file: FileRecord) => void }) {
  const status = file.processing_status?.status ?? "pending";
  const icon = statusIcon(status);
  return (
    <Pressable
      style={rowStyles.row}
      onPress={() => onPress(file)}
      accessibilityRole="button"
      accessibilityLabel={`View details for ${file.original_filename}`}
    >
      <Ionicons name={icon.name} size={22} color={icon.color} style={rowStyles.icon} />
      <View style={rowStyles.info}>
        <Text style={rowStyles.filename} numberOfLines={1}>
          {file.original_filename}
        </Text>
        <Text style={rowStyles.meta}>
          {formatDate(file.created_at)} · {formatBytes(file.file_size)}
        </Text>
      </View>
      <View style={rowStyles.right}>
        <Text style={rowStyles.status}>{status}</Text>
        <Ionicons name="chevron-forward" size={16} color="#d1d5db" />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f9fafb" },
  list: { flex: 1 },
  listContent: { padding: 16, paddingTop: 0 },
  searchContainer: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fff",
    marginHorizontal: 16,
    marginVertical: 12,
    borderRadius: 10,
    paddingHorizontal: 12,
    borderWidth: 1,
    borderColor: "#e5e7eb",
    minHeight: 44,
  },
  searchIcon: { marginRight: 8 },
  searchInput: {
    flex: 1,
    fontSize: 15,
    color: "#111827",
    paddingVertical: 10,
  },
  clearButton: {
    padding: 4,
    minWidth: 44,
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
  },
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
  },
  retryText: { color: "#fff", fontWeight: "600" },
  emptyState: { alignItems: "center", paddingTop: 60 },
  emptyText: { fontSize: 16, color: "#374151", marginBottom: 8 },
  emptyHint: {
    fontSize: 13,
    color: "#6b7280",
    textAlign: "center",
    paddingHorizontal: 32,
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
  icon: { marginRight: 12 },
  info: { flex: 1 },
  filename: {
    fontSize: 14,
    fontWeight: "600",
    color: "#111827",
    marginBottom: 4,
  },
  meta: { fontSize: 12, color: "#6b7280" },
  right: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  status: {
    fontSize: 11,
    color: "#6b7280",
    fontWeight: "500",
    textTransform: "capitalize",
  },
});
