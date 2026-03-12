/**
 * App.tsx – root component for the DocuElevate mobile app.
 *
 * Wraps the entire app in the AuthProvider and renders either the login
 * screen (unauthenticated) or the main tab navigator (authenticated).
 * Push notification registration is handled by the usePushNotifications hook.
 */

import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import React from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AuthProvider, useAuth } from "./src/context/AuthContext";
import { usePushNotifications } from "./src/hooks/usePushNotifications";
import FilesScreen from "./src/screens/FilesScreen";
import LoginScreen from "./src/screens/LoginScreen";
import ProfileScreen from "./src/screens/ProfileScreen";
import UploadScreen from "./src/screens/UploadScreen";

const Tab = createBottomTabNavigator();

function TabNavigator() {
  const { isAuthenticated } = useAuth();
  usePushNotifications(isAuthenticated);

  return (
    <Tab.Navigator
      screenOptions={{
        tabBarActiveTintColor: "#1e40af",
        tabBarInactiveTintColor: "#9ca3af",
        tabBarStyle: {
          borderTopColor: "#e5e7eb",
          backgroundColor: "#ffffff",
        },
        headerStyle: {
          backgroundColor: "#1e40af",
        },
        headerTintColor: "#ffffff",
        headerTitleStyle: {
          fontWeight: "700",
        },
      }}
    >
      <Tab.Screen
        name="Upload"
        component={UploadScreen}
        options={{
          title: "Upload",
          tabBarLabel: "Upload",
          tabBarIcon: ({ color }) => (
            <Text style={{ fontSize: 20, color }}>⬆️</Text>
          ),
          headerTitle: "DocuElevate",
        }}
      />
      <Tab.Screen
        name="Files"
        component={FilesScreen}
        options={{
          title: "Files",
          tabBarLabel: "Files",
          tabBarIcon: ({ color }) => (
            <Text style={{ fontSize: 20, color }}>📄</Text>
          ),
          headerTitle: "My Documents",
        }}
      />
      <Tab.Screen
        name="Profile"
        component={ProfileScreen}
        options={{
          title: "Profile",
          tabBarLabel: "Profile",
          tabBarIcon: ({ color }) => (
            <Text style={{ fontSize: 20, color }}>👤</Text>
          ),
          headerTitle: "Profile",
        }}
      />
    </Tab.Navigator>
  );
}

function AppContent() {
  const { isLoading, isAuthenticated } = useAuth();

  if (isLoading) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator size="large" color="#1e40af" />
        <Text style={styles.loadingText}>Loading…</Text>
      </View>
    );
  }

  return (
    <NavigationContainer>
      {isAuthenticated ? <TabNavigator /> : <LoginScreen />}
    </NavigationContainer>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <AppContent />
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
