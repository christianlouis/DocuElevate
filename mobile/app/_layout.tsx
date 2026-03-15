/**
 * Root layout for the DocuElevate mobile app.
 *
 * Wraps the entire app in AuthProvider and SafeAreaProvider, then uses the
 * AuthGuard component to redirect between the unauthenticated (auth) route
 * group and the authenticated (tabs) route group based on session state.
 */

import { Stack, useRouter, useSegments } from "expo-router";
import React, { useEffect } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AuthProvider, useAuth } from "../src/context/AuthContext";

// ---------------------------------------------------------------------------
// Auth guard – redirects to the correct route group after auth state resolves
// ---------------------------------------------------------------------------

function AuthGuard() {
  const { isLoading, isAuthenticated } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;

    const inAuthGroup = segments[0] === "(auth)";

    if (!isAuthenticated && !inAuthGroup) {
      // Unauthenticated visitor outside the auth group → send to welcome
      router.replace("/(auth)/");
    } else if (isAuthenticated && inAuthGroup) {
      // Authenticated user on auth screens → send to main app
      router.replace("/(tabs)/");
    }
  }, [isAuthenticated, isLoading, segments, router]);

  if (isLoading) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator size="large" color="#1e40af" />
        <Text style={styles.loadingText}>Loading…</Text>
      </View>
    );
  }

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="(auth)" />
      <Stack.Screen name="(tabs)" />
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Root layout export
// ---------------------------------------------------------------------------

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <AuthGuard />
      </AuthProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#f9fafb",
    gap: 12,
  },
  loadingText: {
    color: "#6b7280",
    fontSize: 15,
  },
});
