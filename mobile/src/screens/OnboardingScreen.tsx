import { useRouter } from "expo-router";
import React, { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { useAuth } from "../context/AuthContext";
import { t } from "../i18n";
import api from "../services/api";

export default function OnboardingScreen() {
  const router = useRouter(); const { user } = useAuth();
  const [name, setName] = useState(user?.display_name || ""); const [email, setEmail] = useState(user?.email || ""); const [saving, setSaving] = useState(false); const [error, setError] = useState("");
  async function finish() { setSaving(true); setError(""); try { await api.saveOnboardingProfile({ display_name: name || undefined, contact_email: email || undefined, space_mode: "personal" }); await api.completeOnboarding(); router.replace("/(tabs)/"); } catch (e) { setError(e instanceof Error ? e.message : t("onboarding.failed")); } finally { setSaving(false); } }
  return <View style={styles.container}><Text style={styles.title}>{t("onboarding.title")}</Text><Text style={styles.text}>{t("onboarding.intro")}</Text><TextInput style={styles.input} value={name} onChangeText={setName} placeholder={t("onboarding.name")} /><TextInput style={styles.input} value={email} onChangeText={setEmail} placeholder={t("onboarding.email")} keyboardType="email-address" autoCapitalize="none"/><Text style={styles.note}>{t("onboarding.cloud_optional")}</Text>{error ? <Text style={styles.error}>{error}</Text> : null}<Pressable style={styles.button} disabled={saving} onPress={finish}>{saving ? <ActivityIndicator color="#fff"/> : <Text style={styles.buttonText}>{t("onboarding.finish")}</Text>}</Pressable></View>;
}
const styles=StyleSheet.create({container:{flex:1,padding:24,justifyContent:"center",gap:14},title:{fontSize:26,fontWeight:"700"},text:{fontSize:16,lineHeight:23},input:{borderWidth:1,borderColor:"#d1d5db",borderRadius:8,padding:12,minHeight:48},note:{fontSize:13,color:"#6b7280"},button:{backgroundColor:"#1e40af",padding:14,borderRadius:8,alignItems:"center",minHeight:48},buttonText:{color:"#fff",fontWeight:"700"},error:{color:"#b91c1c"}});
