/**
 * Layout for the unauthenticated route group: Welcome → Login.
 *
 * Uses a headerless native stack so the screens animate naturally.
 */

import { Stack } from "expo-router";
import React from "react";

export default function AuthLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="login" />
      <Stack.Screen name="qr-scanner" />
    </Stack>
  );
}
