import * as Linking from "expo-linking";
import { useRouter } from "expo-router";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput } from "react-native";
import { useAuth } from "../context/AuthContext";
import { t, useLocale } from "../i18n";
import api, { AuthCapabilities } from "../services/api";

export default function OnboardingScreen() {
  useLocale();
  const router = useRouter();
  const { user } = useAuth();
  const [name, setName] = useState(user?.display_name || "");
  const [email, setEmail] = useState(user?.email || "");
  const [spaceMode, setSpaceMode] = useState<"personal" | "shared">("personal");
  const [spaceName, setSpaceName] = useState("");
  const [currentPlan, setCurrentPlan] = useState("free");
  const [destination, setDestination] = useState<string | null>(null);
  const [localOnly, setLocalOnly] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [capabilities, setCapabilities] = useState<AuthCapabilities | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([api.authCapabilities(), api.onboardingStatus()]).then(([value, status]) => {
      if (active) { setCapabilities(value); setCurrentPlan(status.profile?.subscription_tier || "free"); setDestination(status.profile?.preferred_destination || null); }
    })
      .catch(() => { if (active) setError(t("signup.capabilities_failed")); });
    return () => { active = false; };
  }, []);

  async function finish() {
    if (!capabilities || !accepted || (spaceMode === "shared" && !spaceName.trim())) return;
    setSaving(true); setError("");
    try {
      await api.saveOnboardingProfile({ display_name: name || undefined, contact_email: email || undefined, space_mode: spaceMode, tribe_name: spaceMode === "shared" ? spaceName.trim() : undefined });
      if (currentPlan === "free") await api.saveOnboardingPlan();
      if (localOnly) await api.saveOnboardingStorage();
      await api.completeOnboarding({ accept_terms: true, accept_privacy: true, terms_version: capabilities.terms_version, privacy_version: capabilities.privacy_version });
      router.replace("/(tabs)/");
    } catch (e) { setError(e instanceof Error ? e.message : t("onboarding.failed")); }
    finally { setSaving(false); }
  }

  return <ScrollView contentContainerStyle={styles.container}>
    <Text style={styles.title}>{t("onboarding.title")}</Text>
    <Text style={styles.text}>{t("onboarding.intro")}</Text>
    <TextInput style={styles.input} value={name} onChangeText={setName} placeholder={t("onboarding.name")} />
    <TextInput style={styles.input} value={email} onChangeText={setEmail} placeholder={t("onboarding.email")} keyboardType="email-address" autoCapitalize="none" />
    <Text style={styles.text}>{t("onboarding.space")}</Text>
    {(["personal", "shared"] as const).map((mode) => <Pressable key={mode} accessibilityRole="radio" accessibilityState={{ checked: spaceMode === mode }} onPress={() => setSpaceMode(mode)}><Text>{spaceMode === mode ? "◉" : "○"} {t(`onboarding.${mode}`)}</Text></Pressable>)}
    {spaceMode === "shared" && <TextInput style={styles.input} value={spaceName} onChangeText={setSpaceName} placeholder={t("onboarding.space_name")} />}
    <Text style={styles.note}>{t("onboarding.current_plan", { plan: currentPlan })}</Text>
    <Text style={styles.note}>{destination && !localOnly ? t("onboarding.current_destination", { destination }) : t("onboarding.cloud_optional")}</Text>
    {destination && <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: localOnly }} onPress={() => setLocalOnly(!localOnly)}><Text>{localOnly ? "☑" : "□"} {t("onboarding.local_only")}</Text></Pressable>}
    <Pressable onPress={() => Linking.openURL(new URL("/integrations", api.getBaseUrl()).toString())}><Text style={styles.link}>{t("onboarding.configure_cloud")}</Text></Pressable>
    <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: accepted }} onPress={() => setAccepted(!accepted)}><Text>{accepted ? "☑" : "□"} {t("signup.consent")}</Text></Pressable>
    {capabilities && <><Pressable onPress={() => Linking.openURL(new URL(capabilities.terms_url, api.getBaseUrl()).toString())}><Text style={styles.link}>{t("legal.terms")}</Text></Pressable><Pressable onPress={() => Linking.openURL(new URL(capabilities.privacy_url, api.getBaseUrl()).toString())}><Text style={styles.link}>{t("legal.privacy_policy")}</Text></Pressable></>}
    {error ? <Text style={styles.error}>{error}</Text> : null}
    <Pressable style={[styles.button, (!capabilities || !accepted || saving) && { opacity: .5 }]} disabled={!capabilities || !accepted || saving || (spaceMode === "shared" && !spaceName.trim())} onPress={finish}>{saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>{t("onboarding.finish")}</Text>}</Pressable>
  </ScrollView>;
}
const styles = StyleSheet.create({ container: { flexGrow: 1, padding: 24, justifyContent: "center", gap: 14 }, title: { fontSize: 26, fontWeight: "700" }, text: { fontSize: 16, lineHeight: 23 }, input: { borderWidth: 1, borderColor: "#d1d5db", borderRadius: 8, padding: 12, minHeight: 48 }, note: { fontSize: 13, color: "#6b7280" }, link: { color: "#1e40af" }, button: { backgroundColor: "#1e40af", padding: 14, borderRadius: 8, alignItems: "center", minHeight: 48 }, buttonText: { color: "#fff", fontWeight: "700" }, error: { color: "#b91c1c" } });
