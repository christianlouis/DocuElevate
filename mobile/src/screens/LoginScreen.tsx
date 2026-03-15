/**
 * LoginScreen – server URL entry and SSO sign-in.
 *
 * Renders a server URL input and a "Sign in with SSO" button that opens the
 * DocuElevate web login page in the system browser.  On success the
 * AuthContext stores the API token and navigates to the main app.
 */

import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useState } from "react";
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
import type { AuthStackParamList } from "./WelcomeScreen";

type LoginScreenProps = {
  navigation: NativeStackNavigationProp<AuthStackParamList, "Login">;
};

export default function LoginScreen({ navigation }: LoginScreenProps) {
  const { signIn } = useAuth();
  const [serverUrl, setServerUrl] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSignIn() {
    const url = serverUrl.trim();
    if (!url) {
      Alert.alert("Server URL required", "Please enter the URL of your DocuElevate server.");
      return;
    }
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      Alert.alert("Invalid URL", "The server URL must start with http:// or https://");
      return;
    }

    setLoading(true);
    try {
      await signIn(url);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Sign-in failed";
      Alert.alert("Sign-in failed", message);
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
            source={require("../../../assets/logo.png")}
            style={styles.logoImage}
            resizeMode="contain"
            accessibilityLabel="DocuElevate logo"
          />
          <Text style={styles.logoText}>DocuElevate</Text>
        </View>
        <Text style={styles.tagline}>Intelligent Document Processing</Text>

        <Text style={styles.label}>Server URL</Text>
        <TextInput
          style={styles.input}
          placeholder="https://your-docuelevate-server.com"
          placeholderTextColor="#9ca3af"
          value={serverUrl}
          onChangeText={setServerUrl}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          returnKeyType="go"
          onSubmitEditing={handleSignIn}
          accessibilityLabel="Server URL"
        />

        <Pressable
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={handleSignIn}
          disabled={loading}
          accessibilityRole="button"
          accessibilityLabel="Sign in with SSO"
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>Sign in with SSO</Text>
          )}
        </Pressable>

        <Text style={styles.hint}>
          You will be redirected to your organisation's sign-in page.
        </Text>

        <Pressable
          onPress={() => navigation.navigate("Welcome")}
          accessibilityRole="button"
          accessibilityLabel="Back to welcome screen"
          style={styles.backLink}
        >
          <Text style={styles.backLinkText}>← Back</Text>
        </Pressable>
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
});
