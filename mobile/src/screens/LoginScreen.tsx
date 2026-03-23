/**
 * LoginScreen – server URL entry, SSO sign-in, and QR code login.
 *
 * Renders a server URL input, a "Sign in with SSO" button that opens the
 * DocuElevate web login page in the system browser, and a "Scan QR Code"
 * button that opens the device camera to scan a QR code generated from the
 * web interface.  On success the AuthContext stores the API token and
 * navigates to the main app.
 */

import * as Linking from "expo-linking";
import { useRouter } from "expo-router";
import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useAuth } from "../context/AuthContext";
import { useLocale, t } from "../i18n";

export default function LoginScreen() {
  const { signIn, signInWithQR } = useAuth();
  const router = useRouter();
  const [serverUrl, setServerUrl] = useState("https://app.docuelevate.org");
  const [loading, setLoading] = useState(false);
  const [qrLoading, setQrLoading] = useState(false);
  // Subscribe to language changes so translated strings re-render.
  useLocale();

  // Handle incoming deep links for QR login (docuelevate://qr-login?token=...&server=...)
  const handleDeepLink = useCallback(
    async (event: { url: string }) => {
      try {
        const url = new URL(event.url);
        if (url.hostname === "qr-login" || url.pathname === "/qr-login") {
          const token = url.searchParams.get("token");
          const server = url.searchParams.get("server");
          if (token && server) {
            setQrLoading(true);
            await signInWithQR(server, token);
          }
        }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : t("login.qr_login_failed");
        Alert.alert(t("login.qr_login_failed"), message);
      } finally {
        setQrLoading(false);
      }
    },
    [signInWithQR]
  );

  useEffect(() => {
    // Listen for incoming deep links
    const subscription = Linking.addEventListener("url", handleDeepLink);

    // Check if the app was opened via a deep link
    Linking.getInitialURL().then((url) => {
      if (url) handleDeepLink({ url });
    });

    return () => subscription.remove();
  }, [handleDeepLink]);

  async function handleSignIn() {
    const url = serverUrl.trim();
    if (!url) {
      Alert.alert(t("login.server_url_required"), t("login.server_url_required_msg"));
      return;
    }
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      Alert.alert(t("login.invalid_url"), t("login.invalid_url_msg"));
      return;
    }

    setLoading(true);
    try {
      await signIn(url);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t("login.sign_in_failed");
      Alert.alert(t("login.sign_in_failed"), message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.card}>
        <View style={styles.logoContainer}>
          <Image
            source={require("../../assets/logo.png")}
            style={styles.logoImage}
            resizeMode="contain"
            accessibilityLabel="DocuElevate logo"
          />
          <Text style={styles.logoText}>DocuElevate</Text>
        </View>
        <Text style={styles.tagline}>{t("welcome.tagline")}</Text>

        <Text style={styles.label}>{t("login.server_url")}</Text>
        <TextInput
          style={styles.input}
          placeholder={t("login.server_url_placeholder")}
          placeholderTextColor="#9ca3af"
          value={serverUrl}
          onChangeText={setServerUrl}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          returnKeyType="go"
          onSubmitEditing={handleSignIn}
          accessibilityLabel={t("login.server_url")}
        />

        <Pressable
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={handleSignIn}
          disabled={loading || qrLoading}
          accessibilityRole="button"
          accessibilityLabel={t("login.sign_in_sso")}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>{t("login.sign_in_sso")}</Text>
          )}
        </Pressable>

        <View style={styles.dividerRow}>
          <View style={styles.dividerLine} />
          <Text style={styles.dividerText}>{t("login.or")}</Text>
          <View style={styles.dividerLine} />
        </View>

        <Pressable
          style={[styles.qrButton, qrLoading && styles.buttonDisabled]}
          onPress={() => {
            router.push("/(auth)/qr-scanner");
          }}
          disabled={loading || qrLoading}
          accessibilityRole="button"
          accessibilityLabel={t("login.scan_qr")}
        >
          {qrLoading ? (
            <ActivityIndicator color="#1e40af" />
          ) : (
            <Text style={styles.qrButtonText}>{t("login.scan_qr")}</Text>
          )}
        </Pressable>

        <Text style={styles.hint}>{t("login.hint")}</Text>

        <Pressable
          onPress={() => router.back()}
          accessibilityRole="button"
          accessibilityLabel={t("login.back")}
          style={styles.backLink}
        >
          <Text style={styles.backLinkText}>{t("login.back")}</Text>
        </Pressable>

        {/* Legal links – accessible pre-login for GDPR / Apple compliance */}
        <View style={styles.legalLinks}>
          <Pressable
            onPress={() => {
              const base = serverUrl.trim() || "https://app.docuelevate.org";
              Linking.openURL(`${base.replace(/\/$/, "")}/privacy`);
            }}
            accessibilityRole="link"
            accessibilityLabel={t("legal.privacy_policy")}
            style={styles.legalLinkButton}
          >
            <Text style={styles.legalLinkText}>{t("legal.privacy_policy")}</Text>
          </Pressable>
          <Text style={styles.legalSeparator}>·</Text>
          <Pressable
            onPress={() => {
              const base = serverUrl.trim() || "https://app.docuelevate.org";
              Linking.openURL(`${base.replace(/\/$/, "")}/terms`);
            }}
            accessibilityRole="link"
            accessibilityLabel={t("legal.terms")}
            style={styles.legalLinkButton}
          >
            <Text style={styles.legalLinkText}>{t("legal.terms")}</Text>
          </Pressable>
          <Text style={styles.legalSeparator}>·</Text>
          <Pressable
            onPress={() => {
              const base = serverUrl.trim() || "https://app.docuelevate.org";
              Linking.openURL(`${base.replace(/\/$/, "")}/imprint`);
            }}
            accessibilityRole="link"
            accessibilityLabel={t("legal.imprint")}
            style={styles.legalLinkButton}
          >
            <Text style={styles.legalLinkText}>{t("legal.imprint")}</Text>
          </Pressable>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#f3f4f6",
    justifyContent: "center",
    padding: 24,
  },
  card: {
    backgroundColor: "#ffffff",
    borderRadius: 16,
    padding: 28,
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowOffset: { width: 0, height: 4 },
    shadowRadius: 12,
    elevation: 4,
  },
  logoContainer: {
    alignItems: "center",
    marginBottom: 4,
  },
  logoImage: {
    width: 80,
    height: 80,
    marginBottom: 10,
  },
  logoText: {
    fontSize: 28,
    fontWeight: "700",
    color: "#1e40af",
    textAlign: "center",
  },
  tagline: {
    fontSize: 14,
    color: "#6b7280",
    textAlign: "center",
    marginBottom: 32,
  },
  label: {
    fontSize: 14,
    fontWeight: "600",
    color: "#374151",
    marginBottom: 6,
  },
  input: {
    borderWidth: 1,
    borderColor: "#d1d5db",
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 15,
    color: "#111827",
    marginBottom: 20,
    backgroundColor: "#f9fafb",
  },
  button: {
    backgroundColor: "#1e40af",
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 48,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: "#ffffff",
    fontSize: 16,
    fontWeight: "600",
  },
  dividerRow: {
    flexDirection: "row",
    alignItems: "center",
    marginVertical: 16,
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: "#e5e7eb",
  },
  dividerText: {
    marginHorizontal: 12,
    fontSize: 12,
    color: "#9ca3af",
  },
  qrButton: {
    borderWidth: 1,
    borderColor: "#1e40af",
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 48,
    backgroundColor: "#eff6ff",
  },
  qrButtonText: {
    color: "#1e40af",
    fontSize: 15,
    fontWeight: "600",
  },
  hint: {
    marginTop: 16,
    fontSize: 12,
    color: "#9ca3af",
    textAlign: "center",
  },
  backLink: {
    marginTop: 20,
    alignItems: "center",
    minHeight: 44,
    justifyContent: "center",
  },
  backLinkText: {
    fontSize: 13,
    color: "#6b7280",
  },
  legalLinks: {
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    marginTop: 16,
    flexWrap: "wrap",
  },
  legalLinkButton: {
    minHeight: 44,
    justifyContent: "center",
    paddingHorizontal: 4,
  },
  legalLinkText: {
    fontSize: 12,
    color: "#9ca3af",
    textDecorationLine: "underline",
  },
  legalSeparator: {
    fontSize: 12,
    color: "#d1d5db",
    marginHorizontal: 4,
  },
});
