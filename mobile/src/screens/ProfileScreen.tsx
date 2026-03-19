/**
 * ProfileScreen – authenticated user profile and settings.
 */

import Constants from "expo-constants";
import * as Linking from "expo-linking";
import React from "react";
import {
  Alert,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useAuth } from "../context/AuthContext";

export default function ProfileScreen() {
  const { user, signOut, baseUrl } = useAuth();

  const appVersion = Constants.expoConfig?.version ?? "1.0.0";

  function handleSignOut() {
    Alert.alert("Sign out", "Are you sure you want to sign out?", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Sign out",
        style: "destructive",
        onPress: signOut,
      },
    ]);
  }

  function handleDeleteAccount() {
    if (!baseUrl) {
      Alert.alert("Not Connected", "Cannot reach server. Please sign in again.");
      return;
    }
    Alert.alert(
      "Delete Account",
      "This will permanently delete your account and all associated data. This action cannot be undone.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete Account",
          style: "destructive",
          onPress: () => {
            Linking.openURL(`${baseUrl}/account/delete`);
          },
        },
      ]
    );
  }

  function openPrivacyPolicy() {
    if (!baseUrl) {
      Alert.alert("Not Connected", "Cannot reach server. Please sign in again.");
      return;
    }
    Linking.openURL(`${baseUrl}/privacy`);
  }

  function openTermsOfService() {
    if (!baseUrl) {
      Alert.alert("Not Connected", "Cannot reach server. Please sign in again.");
      return;
    }
    Linking.openURL(`${baseUrl}/terms`);
  }

  if (!user) {
    return (
      <View style={styles.center}>
        <Text style={styles.emptyText}>Not signed in</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
      {/* Avatar + name */}
      <View style={styles.profileCard}>
        {user.avatar_url ? (
          <Image
            source={{ uri: user.avatar_url }}
            style={styles.avatar}
            accessibilityLabel={`Avatar for ${user.display_name ?? user.owner_id}`}
          />
        ) : (
          <View style={[styles.avatar, styles.avatarPlaceholder]}>
            <Text style={styles.avatarInitial}>
              {(user.display_name ?? user.owner_id).charAt(0).toUpperCase()}
            </Text>
          </View>
        )}
        <Text style={styles.displayName}>{user.display_name ?? user.owner_id}</Text>
        {user.email && <Text style={styles.email}>{user.email}</Text>}
        {user.is_admin && <Text style={styles.adminBadge}>Admin</Text>}
      </View>

      {/* Server info */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Connection</Text>
        <View style={styles.row}>
          <Text style={styles.rowLabel}>Server</Text>
          <Text style={styles.rowValue} numberOfLines={1}>
            {baseUrl || "–"}
          </Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.rowLabel}>User ID</Text>
          <Text style={styles.rowValue} numberOfLines={1}>
            {user.owner_id}
          </Text>
        </View>
      </View>

      {/* Legal & Privacy */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Legal</Text>
        <Pressable
          style={styles.linkRow}
          onPress={openPrivacyPolicy}
          accessibilityRole="link"
          accessibilityLabel="Privacy Policy"
        >
          <Text style={styles.linkText}>Privacy Policy</Text>
          <Text style={styles.linkChevron}>›</Text>
        </Pressable>
        <Pressable
          style={styles.linkRow}
          onPress={openTermsOfService}
          accessibilityRole="link"
          accessibilityLabel="Terms of Service"
        >
          <Text style={styles.linkText}>Terms of Service</Text>
          <Text style={styles.linkChevron}>›</Text>
        </Pressable>
      </View>

      {/* Sign out */}
      <View style={styles.section}>
        <Pressable
          style={styles.signOutButton}
          onPress={handleSignOut}
          accessibilityRole="button"
          accessibilityLabel="Sign out"
        >
          <Text style={styles.signOutText}>Sign out</Text>
        </Pressable>
      </View>

      {/* Account deletion – Apple Guideline 5.1.1(v) */}
      <View style={styles.section}>
        <Pressable
          style={styles.deleteAccountButton}
          onPress={handleDeleteAccount}
          accessibilityRole="button"
          accessibilityLabel="Delete account"
        >
          <Text style={styles.deleteAccountText}>Delete Account</Text>
        </Pressable>
      </View>

      {/* App version */}
      <Text style={styles.versionText}>DocuElevate v{appVersion}</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: "#f9fafb" },
  content: { padding: 20, paddingBottom: 40 },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#f9fafb",
  },
  emptyText: { color: "#6b7280", fontSize: 16 },
  profileCard: {
    alignItems: "center",
    backgroundColor: "#fff",
    borderRadius: 16,
    padding: 24,
    marginBottom: 20,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowOffset: { width: 0, height: 4 },
    shadowRadius: 12,
    elevation: 3,
  },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
    marginBottom: 14,
  },
  avatarPlaceholder: {
    backgroundColor: "#1e40af",
    alignItems: "center",
    justifyContent: "center",
  },
  avatarInitial: {
    color: "#fff",
    fontSize: 32,
    fontWeight: "700",
  },
  displayName: {
    fontSize: 20,
    fontWeight: "700",
    color: "#111827",
    marginBottom: 4,
  },
  email: { fontSize: 14, color: "#6b7280", marginBottom: 6 },
  adminBadge: {
    backgroundColor: "#dbeafe",
    color: "#1e40af",
    fontSize: 11,
    fontWeight: "700",
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: 12,
    overflow: "hidden",
  },
  section: {
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
  sectionTitle: {
    fontSize: 13,
    fontWeight: "700",
    color: "#6b7280",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginBottom: 12,
  },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: "#f3f4f6",
  },
  rowLabel: { fontSize: 14, color: "#374151" },
  rowValue: {
    fontSize: 14,
    color: "#6b7280",
    maxWidth: "60%",
    textAlign: "right",
  },
  linkRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#f3f4f6",
    minHeight: 44,
  },
  linkText: {
    fontSize: 15,
    color: "#1e40af",
  },
  linkChevron: {
    fontSize: 18,
    color: "#9ca3af",
    fontWeight: "600",
  },
  signOutButton: {
    backgroundColor: "#fee2e2",
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: "center",
    minHeight: 48,
  },
  signOutText: {
    color: "#dc2626",
    fontWeight: "700",
    fontSize: 15,
  },
  deleteAccountButton: {
    backgroundColor: "#ffffff",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "#dc2626",
    paddingVertical: 14,
    alignItems: "center",
    minHeight: 48,
  },
  deleteAccountText: {
    color: "#dc2626",
    fontWeight: "600",
    fontSize: 14,
  },
  versionText: {
    fontSize: 12,
    color: "#9ca3af",
    textAlign: "center",
    marginTop: 8,
  },
});
