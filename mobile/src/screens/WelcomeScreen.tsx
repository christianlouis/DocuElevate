/**
 * WelcomeScreen – first screen shown to unauthenticated users on first launch.
 *
 * Presents the DocuElevate brand, a short description of what the app does,
 * and a "Get Started" button that navigates to the LoginScreen.
 */

import { useRouter } from "expo-router";
import * as Linking from "expo-linking";
import React from "react";
import {
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

const FEATURES: { icon: string; title: string; description: string }[] = [
  {
    icon: "🔍",
    title: "OCR & Text Extraction",
    description: "Convert scanned PDFs and images into fully searchable text automatically.",
  },
  {
    icon: "🤖",
    title: "AI Metadata Extraction",
    description: "AI classifies documents and pulls out key fields like dates, amounts, and subjects.",
  },
  {
    icon: "☁️",
    title: "Multi-Cloud Storage",
    description: "Route processed files to Dropbox, Google Drive, OneDrive, S3, Nextcloud, and more.",
  },
];

export default function WelcomeScreen() {
  const router = useRouter();
  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        {/* Hero */}
        <View style={styles.hero}>
          <View style={styles.logoContainer}>
            <Image
              source={require("../../assets/logo.png")}
              style={styles.logoImage}
              resizeMode="contain"
              accessibilityLabel="DocuElevate logo"
            />
          </View>
          <Text style={styles.appName}>DocuElevate</Text>
          <Text style={styles.tagline}>Intelligent Document Processing</Text>
          <Text style={styles.heroDescription}>
            Ingest documents, run OCR, extract metadata with AI, and route files
            to your cloud storage — all in one seamless pipeline.
          </Text>
        </View>

        {/* Feature highlights */}
        <View style={styles.features}>
          {FEATURES.map((feature) => (
            <View key={feature.title} style={styles.featureRow}>
              <Text style={styles.featureIcon} aria-hidden={true}>{feature.icon}</Text>
              <View style={styles.featureText}>
                <Text style={styles.featureTitle}>{feature.title}</Text>
                <Text style={styles.featureDescription}>{feature.description}</Text>
              </View>
            </View>
          ))}
        </View>

        {/* CTA */}
        <Pressable
          style={({ pressed }) => [styles.button, pressed && styles.buttonPressed]}
          onPress={() => router.push("/(auth)/login")}
          accessibilityRole="button"
          accessibilityLabel="Get started — connect to your DocuElevate server"
        >
          <Text style={styles.buttonText}>Get Started</Text>
        </Pressable>

        <Text style={styles.hint}>
          Connect to your self-hosted or cloud DocuElevate server.
        </Text>

        {/* Legal links – accessible pre-login for GDPR / Apple compliance */}
        <View style={styles.legalLinks}>
          <Pressable
            onPress={() => Linking.openURL("https://app.docuelevate.org/privacy")}
            accessibilityRole="link"
            accessibilityLabel="Privacy Policy"
            style={styles.legalLinkButton}
          >
            <Text style={styles.legalLinkText}>Privacy Policy</Text>
          </Pressable>
          <Text style={styles.legalSeparator}>·</Text>
          <Pressable
            onPress={() => Linking.openURL("https://app.docuelevate.org/terms")}
            accessibilityRole="link"
            accessibilityLabel="Terms of Service"
            style={styles.legalLinkButton}
          >
            <Text style={styles.legalLinkText}>Terms</Text>
          </Pressable>
          <Text style={styles.legalSeparator}>·</Text>
          <Pressable
            onPress={() => Linking.openURL("https://app.docuelevate.org/imprint")}
            accessibilityRole="link"
            accessibilityLabel="Imprint"
            style={styles.legalLinkButton}
          >
            <Text style={styles.legalLinkText}>Imprint</Text>
          </Pressable>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: "#1e40af",
  },
  scroll: {
    flexGrow: 1,
    paddingHorizontal: 28,
    paddingTop: 48,
    paddingBottom: 40,
  },
  hero: {
    alignItems: "center",
    marginBottom: 40,
  },
  logoContainer: {
    width: 96,
    height: 96,
    borderRadius: 24,
    backgroundColor: "rgba(255,255,255,0.15)",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 16,
  },
  logoImage: {
    width: 72,
    height: 72,
  },
  appName: {
    fontSize: 36,
    fontWeight: "800",
    color: "#ffffff",
    textAlign: "center",
    marginBottom: 6,
    letterSpacing: 0.5,
  },
  tagline: {
    fontSize: 14,
    fontWeight: "600",
    color: "rgba(255,255,255,0.75)",
    textTransform: "uppercase",
    letterSpacing: 1.5,
    textAlign: "center",
    marginBottom: 16,
  },
  heroDescription: {
    fontSize: 16,
    color: "rgba(255,255,255,0.85)",
    textAlign: "center",
    lineHeight: 24,
    maxWidth: 320,
  },
  features: {
    backgroundColor: "rgba(255,255,255,0.1)",
    borderRadius: 16,
    paddingVertical: 8,
    paddingHorizontal: 16,
    marginBottom: 36,
  },
  featureRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "rgba(255,255,255,0.2)",
  },
  featureIcon: {
    fontSize: 24,
    marginRight: 14,
    marginTop: 1,
  },
  featureText: {
    flex: 1,
  },
  featureTitle: {
    fontSize: 15,
    fontWeight: "600",
    color: "#ffffff",
    marginBottom: 2,
  },
  featureDescription: {
    fontSize: 13,
    color: "rgba(255,255,255,0.75)",
    lineHeight: 18,
  },
  button: {
    backgroundColor: "#ffffff",
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 52,
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowOffset: { width: 0, height: 4 },
    shadowRadius: 8,
    elevation: 4,
    marginBottom: 16,
  },
  buttonPressed: {
    opacity: 0.9,
    transform: [{ scale: 0.98 }],
  },
  buttonText: {
    color: "#1e40af",
    fontSize: 17,
    fontWeight: "700",
    letterSpacing: 0.3,
  },
  hint: {
    fontSize: 12,
    color: "rgba(255,255,255,0.55)",
    textAlign: "center",
  },
  legalLinks: {
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    marginTop: 20,
    flexWrap: "wrap",
  },
  legalLinkButton: {
    minHeight: 44,
    justifyContent: "center",
    paddingHorizontal: 4,
  },
  legalLinkText: {
    fontSize: 12,
    color: "rgba(255,255,255,0.65)",
    textDecorationLine: "underline",
  },
  legalSeparator: {
    fontSize: 12,
    color: "rgba(255,255,255,0.45)",
    marginHorizontal: 4,
  },
});
