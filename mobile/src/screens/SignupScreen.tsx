import * as Linking from "expo-linking";
import { useRouter } from "expo-router";
import React, { useState } from "react";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useLocale, t } from "../i18n";
import api from "../services/api";

export default function SignupScreen() {
  useLocale(); const router = useRouter();
  const [serverUrl, setServerUrl] = useState("https://app.docuelevate.org");
  const [email, setEmail] = useState(""); const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState(""); const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState(""); const [accepted, setAccepted] = useState(false);
  const [pending, setPending] = useState(false); const [loading, setLoading] = useState(false); const [error, setError] = useState("");
  const submit = async () => {
    if (!accepted || password !== confirm || password.length < 8) { setError(t("signup.invalid")); return; }
    try { const url = new URL(serverUrl.trim()); if (url.protocol !== "https:") throw new Error("HTTPS required"); await api.init(url.origin); setLoading(true); const result = await api.signup({email, username, display_name: displayName || undefined, password, password_confirm: confirm, terms_accepted: true, privacy_accepted: true}); setPending(result.email_verification_required); }
    catch (e) { setError(e instanceof Error ? e.message : t("signup.failed")); } finally { setLoading(false); }
  };
  if (pending) return <View style={styles.center}><Text style={styles.title}>{t("signup.verify_title")}</Text><Text style={styles.text}>{t("signup.verify_msg", { email })}</Text><Pressable style={styles.button} onPress={async () => { try { await api.resendVerification(email); Alert.alert(t("signup.resend_done")); } catch (e) { Alert.alert(t("signup.failed")); } }}><Text style={styles.buttonText}>{t("signup.resend")}</Text></Pressable><Pressable onPress={() => router.replace("/(auth)/login")}><Text style={styles.link}>{t("signup.back_login")}</Text></Pressable></View>;
  return <ScrollView contentContainerStyle={styles.container}><Text style={styles.title}>{t("signup.title")}</Text><TextInput style={styles.input} value={serverUrl} onChangeText={setServerUrl} placeholder="https://…" autoCapitalize="none"/><TextInput style={styles.input} value={email} onChangeText={setEmail} placeholder={t("signup.email")} keyboardType="email-address" autoCapitalize="none"/><TextInput style={styles.input} value={username} onChangeText={setUsername} placeholder={t("signup.username")} autoCapitalize="none"/><TextInput style={styles.input} value={displayName} onChangeText={setDisplayName} placeholder={t("signup.display_name")}/><TextInput style={styles.input} value={password} onChangeText={setPassword} placeholder={t("signup.password")} secureTextEntry/><TextInput style={styles.input} value={confirm} onChangeText={setConfirm} placeholder={t("signup.confirm")} secureTextEntry/><Pressable onPress={() => setAccepted(!accepted)} style={styles.consent}><Text>{accepted ? "☑" : "□"} {t("signup.consent")}</Text></Pressable>{error ? <Text style={styles.error}>{error}</Text> : null}<Pressable style={[styles.button, loading && {opacity:.5}]} disabled={loading} onPress={submit}>{loading ? <ActivityIndicator color="#fff"/> : <Text style={styles.buttonText}>{t("signup.submit")}</Text>}</Pressable><Pressable onPress={() => Linking.openURL(`${serverUrl}/privacy`)}><Text style={styles.link}>{t("legal.privacy_policy")}</Text></Pressable><Pressable onPress={() => router.back()}><Text style={styles.link}>{t("signup.back_login")}</Text></Pressable></ScrollView>;
}
const styles=StyleSheet.create({container:{padding:24,gap:12},center:{flex:1,padding:24,justifyContent:"center",gap:16},title:{fontSize:26,fontWeight:"700",marginBottom:12},text:{fontSize:16,lineHeight:23},input:{borderWidth:1,borderColor:"#d1d5db",borderRadius:8,padding:12,minHeight:48},consent:{paddingVertical:8},button:{backgroundColor:"#1e40af",padding:14,borderRadius:8,alignItems:"center",minHeight:48},buttonText:{color:"#fff",fontWeight:"700"},link:{color:"#1e40af",textAlign:"center",padding:10},error:{color:"#b91c1c"}});
