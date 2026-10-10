/** Redirect unmatched routes without interpreting URL text as a file path. */

import { usePathname, useRouter } from "expo-router";
import React, { useEffect } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";

export default function NotFoundScreen() {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    router.replace("/");
  }, [pathname, router]);

  return (
    <View style={styles.container}>
      <ActivityIndicator size="large" color="#1e40af" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#f9fafb",
  },
});
