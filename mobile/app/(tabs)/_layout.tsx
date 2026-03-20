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
import { useLocale, t } from "../../src/i18n";

export default function TabLayout() {
  const { isAuthenticated } = useAuth();
  usePushNotifications(isAuthenticated);
  // Subscribe to language changes so tab labels re-render when the language
  // is switched.  The `lang` variable is intentionally unused – its only
  // purpose is to make this component a consumer of LocaleContext.
  useLocale();

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
          title: t("tabs.upload"),
          tabBarLabel: t("tabs.upload"),
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="cloud-upload-outline" size={size} color={color} />
          ),
          headerTitle: "DocuElevate",
        }}
      />
      <Tabs.Screen
        name="files"
        options={{
          title: t("tabs.files"),
          tabBarLabel: t("tabs.files"),
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="document-text-outline" size={size} color={color} />
          ),
          headerTitle: t("files.title"),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: t("tabs.profile"),
          tabBarLabel: t("tabs.profile"),
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="person-circle-outline" size={size} color={color} />
          ),
          headerTitle: t("tabs.profile"),
        }}
      />
      {/* File detail screen – hidden from tab bar, accessed via navigation */}
      <Tabs.Screen
        name="file-detail"
        options={{
          href: null,
          title: t("file_detail.title"),
          headerTitle: t("file_detail.title"),
        }}
      />
    </Tabs>
  );
}
