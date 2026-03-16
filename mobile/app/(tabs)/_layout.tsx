/**
 * Tab navigator layout for authenticated users.
 *
 * Registers three tabs: Upload (default), Files, and Profile.
 * Push notifications are initialised here so they activate as soon as the
 * user enters the authenticated area.
 */

import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { usePushNotifications } from "../../src/hooks/usePushNotifications";
import { useAuth } from "../../src/context/AuthContext";

export default function TabLayout() {
  const { isAuthenticated } = useAuth();
  usePushNotifications(isAuthenticated);

  return (
    <Tabs
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
      <Tabs.Screen
        name="index"
        options={{
          title: "Upload",
          tabBarLabel: "Upload",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="cloud-upload-outline" size={size} color={color} />
          ),
          headerTitle: "DocuElevate",
        }}
      />
      <Tabs.Screen
        name="files"
        options={{
          title: "Files",
          tabBarLabel: "Files",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="document-text-outline" size={size} color={color} />
          ),
          headerTitle: "My Documents",
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: "Profile",
          tabBarLabel: "Profile",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="person-circle-outline" size={size} color={color} />
          ),
          headerTitle: "Profile",
        }}
      />
    </Tabs>
  );
}
