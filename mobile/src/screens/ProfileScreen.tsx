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
import { useLocale, getSupportedLanguages, t } from "../i18n";
import api from "../services/api";

const DEFAULT_SERVER_URL = "https://app.docuelevate.org";

export default function ProfileScreen() {
  const { user, signOut, baseUrl } = useAuth();
  const { lang, setLang } = useLocale();

  const effectiveBaseUrl = baseUrl || DEFAULT_SERVER_URL;
  const appVersion = Constants.expoConfig?.version ?? "1.0.0";
  const languages = getSupportedLanguages();

  async function handleLanguageSelect(code: string) {
    await setLang(code);
    // Fire-and-forget: sync the choice to the server so it persists across
    // platforms (desktop web will reflect this preference too).
    api.setServerLanguage(code).catch(() => {
      // Network errors are non-critical – the local change is already applied.
    });
  }

  function handleSignOut() {
    Alert.alert(t("profile.sign_out_title"), t("profile.sign_out_msg"), [
      { text: t("common.cancel"), style: "cancel" },
      {
        text: t("profile.sign_out"),
        style: "destructive",
        onPress: signOut,
      },
    ]);
  }

  function handleDeleteAccount() {
    Alert.alert(
      t("profile.delete_account_title"),
      t("profile.delete_account_msg"),
      [
        { text: t("common.cancel"), style: "cancel" },
        {
          text: t("profile.delete_account"),
          style: "destructive",
          onPress: () => {
            Linking.openURL(`${effectiveBaseUrl}/account/delete`).catch(() => {
              Alert.alert(t("common.error"), t("profile.could_not_open", { page: t("profile.delete_account") }));
            });
          },
        },
      ]
    );
  }

  function openPrivacyPolicy() {
    Linking.openURL(`${effectiveBaseUrl}/privacy`).catch(() => {
      Alert.alert(t("common.error"), t("profile.could_not_open", { page: t("profile.privacy_policy") }));
    });
  }

  function openTermsOfService() {
    Linking.openURL(`${effectiveBaseUrl}/terms`).catch(() => {
      Alert.alert(t("common.error"), t("profile.could_not_open", { page: t("profile.terms_of_service") }));
    });
  }

  function openImprint() {
    Linking.openURL(`${effectiveBaseUrl}/imprint`).catch(() => {
      Alert.alert(t("common.error"), t("profile.could_not_open", { page: t("profile.imprint") }));
    });
  }

  if (!user) {
    return (
      <View style={styles.center}>
        <Text style={styles.emptyText}>{t("profile.not_signed_in")}</Text>
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
        {user.is_admin && <Text style={styles.adminBadge}>{t("profile.admin")}</Text>}
      </View>

      {/* Server info */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>{t("profile.connection")}</Text>
        <View style={styles.row}>
          <Text style={styles.rowLabel}>{t("profile.server")}</Text>
          <Text style={styles.rowValue} numberOfLines={1}>
            {effectiveBaseUrl}
          </Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.rowLabel}>{t("profile.user_id")}</Text>
          <Text style={styles.rowValue} numberOfLines={1}>
            {user.owner_id}
          </Text>
        </View>
      </View>

      {/* Settings */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>{t("profile.settings")}</Text>
        <Text style={styles.settingLabel}>{t("profile.language")}</Text>
        <View style={styles.languageGrid}>
          {languages.map((l) => (
            <Pressable
              key={l.code}
              style={[
                styles.languageChip,
                lang === l.code && styles.languageChipActive,
              ]}
              onPress={() => handleLanguageSelect(l.code)}
              accessibilityRole="button"
              accessibilityLabel={`Set language to ${l.label}`}
              accessibilityState={{ selected: lang === l.code }}
            >
              <Text
                style={[
                  styles.languageChipText,
                  lang === l.code && styles.languageChipTextActive,
                ]}
              >
                {l.label}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>

      {/* Legal & Privacy */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>{t("profile.legal")}</Text>
        <Pressable
          style={styles.linkRow}
          onPress={openPrivacyPolicy}
          accessibilityRole="link"
          accessibilityLabel={t("profile.privacy_policy")}
        >
          <Text style={styles.linkText}>{t("profile.privacy_policy")}</Text>
          <Text style={styles.linkChevron}>›</Text>
        </Pressable>
        <Pressable
          style={styles.linkRow}
          onPress={openTermsOfService}
          accessibilityRole="link"
          accessibilityLabel={t("profile.terms_of_service")}
        >
          <Text style={styles.linkText}>{t("profile.terms_of_service")}</Text>
          <Text style={styles.linkChevron}>›</Text>
        </Pressable>
        <Pressable
          style={[styles.linkRow, styles.linkRowLast]}
          onPress={openImprint}
          accessibilityRole="link"
          accessibilityLabel={t("profile.imprint")}
        >
          <Text style={styles.linkText}>{t("profile.imprint")}</Text>
          <Text style={styles.linkChevron}>›</Text>
        </Pressable>
      </View>

      {/* Sign out */}
      <View style={styles.section}>
        <Pressable
          style={styles.signOutButton}
          onPress={handleSignOut}
          accessibilityRole="button"
          accessibilityLabel={t("profile.sign_out")}
        >
          <Text style={styles.signOutText}>{t("profile.sign_out")}</Text>
        </Pressable>
      </View>

      {/* Account deletion – Apple Guideline 5.1.1(v) */}
      <View style={styles.section}>
        <Pressable
          style={styles.deleteAccountButton}
          onPress={handleDeleteAccount}
          accessibilityRole="button"
          accessibilityLabel={t("profile.delete_account")}
        >
          <Text style={styles.deleteAccountText}>{t("profile.delete_account")}</Text>
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
  linkRowLast: {
    borderBottomWidth: 0,
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
  settingLabel: {
    fontSize: 14,
    color: "#374151",
    fontWeight: "500",
    marginBottom: 10,
  },
  languageGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  languageChip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: "#f3f4f6",
    borderWidth: 1,
    borderColor: "#e5e7eb",
    minHeight: 36,
    justifyContent: "center",
  },
  languageChipActive: {
    backgroundColor: "#dbeafe",
    borderColor: "#1e40af",
  },
  languageChipText: {
    fontSize: 13,
    color: "#6b7280",
    fontWeight: "500",
  },
  languageChipTextActive: {
    color: "#1e40af",
    fontWeight: "700",
  },
});
