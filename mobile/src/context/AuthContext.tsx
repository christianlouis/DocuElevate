/**
 * Authentication context for the DocuElevate mobile app.
 *
 * Manages the lifecycle of the stored API token and user profile.  The SSO
 * login flow uses expo-auth-session to open the server's OAuth page in the
 * system browser; on return the redirect URL carries a persistent API token
 * that is stored in the device keychain.
 */

import * as Linking from "expo-linking";
import * as SecureStore from "expo-secure-store";
import * as WebBrowser from "expo-web-browser";
import { Alert } from "react-native";
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import {
  SECURE_STORE_API_TOKEN_KEY,
  SECURE_STORE_BASE_URL_KEY,
  SECURE_STORE_OWNER_ID_KEY,
  api,
  type WhoAmIResponse,
} from "../services/api";
import { callbackToken } from "../services/mobileAuth";
import { clearShareCredentials, syncShareCredentials } from "@docuelevate/auth-bridge";

WebBrowser.maybeCompleteAuthSession();

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AuthState {
  isLoading: boolean;
  isAuthenticated: boolean;
  user: WhoAmIResponse | null;
  baseUrl: string;
  signIn: (serverUrl: string) => Promise<void>;
  signInWithQR: (serverUrl: string, challengeToken: string) => Promise<void>;
  signOut: () => Promise<void>;
  setToken: (token: string) => Promise<void>;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AuthContext = createContext<AuthState>({
  isLoading: true,
  isAuthenticated: false,
  user: null,
  baseUrl: "",
  signIn: async () => {},
  signInWithQR: async () => {},
  signOut: async () => {},
  setToken: async () => {},
});

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState<WhoAmIResponse | null>(null);
  const [baseUrl, setBaseUrl] = useState("");

  // On mount: restore persisted session
  useEffect(() => {
    (async () => {
      try {
        const storedUrl = await SecureStore.getItemAsync(SECURE_STORE_BASE_URL_KEY);
        const storedToken = await SecureStore.getItemAsync(SECURE_STORE_API_TOKEN_KEY);

        if (storedUrl && storedToken) {
          await api.init(storedUrl);
          setBaseUrl(storedUrl);
          // Verify token is still valid
          const profile = await api.whoAmI();
          await syncShareCredentials(storedUrl, storedToken, profile.owner_id);
          setUser(profile);
          setIsAuthenticated(true);
        } else {
          // A partial SecureStore record must not leave a share credential
          // usable after the app has no valid session to restore.
          await clearShareCredentials();
        }
      } catch {
        // Token expired or server unavailable – clear stored credentials
        await SecureStore.deleteItemAsync(SECURE_STORE_API_TOKEN_KEY);
        await SecureStore.deleteItemAsync(SECURE_STORE_OWNER_ID_KEY);
        await clearShareCredentials();
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const setToken = useCallback(async (token: string) => {
    await SecureStore.setItemAsync(SECURE_STORE_API_TOKEN_KEY, token);
    const profile = await api.whoAmI();
    setUser(profile);
    await SecureStore.setItemAsync(SECURE_STORE_OWNER_ID_KEY, profile.owner_id);
    await syncShareCredentials(api.getBaseUrl(), token, profile.owner_id);
    setIsAuthenticated(true);
  }, []);

  const signIn = useCallback(
    async (serverUrl: string) => {
      const cleanUrl = serverUrl.replace(/\/$/, "");

      // Clear the extension bridge before probing or switching servers. The
      // probe is unauthenticated, so it cannot reuse a prior session token.
      await clearShareCredentials();
      // Probe before changing the active server or opening a browser session.
      // The probe is deliberately unauthenticated so a token for a previous
      // server cannot be sent to this URL.
      await api.checkMobileSupport(cleanUrl);
      // Never leave a token for a previous server available to the extension
      // while the user is signing in to a different server.
      await api.init(cleanUrl);
      setBaseUrl(cleanUrl);

      // Compute the correct redirect URI for the current runtime:
      //   • Expo Go (development)  → exp://<host>:<port>/--/callback
      //   • Standalone / EAS build → docuelevate://callback
      // Both schemes are accepted by the server; using Linking.createURL
      // ensures the browser deep-link resolves correctly in every environment.
      const redirectUri = Linking.createURL("callback");

      // Open the web login page in the system browser.  The user authenticates
      // via SSO or local credentials, then the app deep-link is triggered.
      // The WebBrowser.openAuthSessionAsync handles the redirect back to the app.
      const result = await WebBrowser.openAuthSessionAsync(
        `${cleanUrl}/login?mobile=1&redirect_uri=${encodeURIComponent(redirectUri)}`,
        redirectUri
      );

      if (result.type !== "success") {
        throw new Error("Authentication was cancelled or failed");
      }

      // Parse the token from the redirect URL if the server appended it,
      // otherwise fail safely. Native browser session cookies are not a
      // reliable authentication channel after an iOS callback.
      await setToken(callbackToken(result.url, redirectUri));
    },
    [setToken]
  );

  const signInWithQR = useCallback(
    async (serverUrl: string, challengeToken: string) => {
      const cleanUrl = serverUrl.replace(/\/$/, "");
      // QR claims can switch owners and servers just like browser login.
      await clearShareCredentials();
      await api.init(cleanUrl);
      setBaseUrl(cleanUrl);

      const deviceInfo = await _getDeviceName();
      const resp = await api.claimQRChallenge(challengeToken, deviceInfo);
      await setToken(resp.token);
    },
    [setToken]
  );

  const signOut = useCallback(async () => {
    const results = await Promise.allSettled([
      SecureStore.deleteItemAsync(SECURE_STORE_API_TOKEN_KEY),
      SecureStore.deleteItemAsync(SECURE_STORE_OWNER_ID_KEY),
      clearShareCredentials(),
    ]);
    setUser(null);
    setIsAuthenticated(false);
    if (results.some((result) => result.status === "rejected")) {
      Alert.alert("Sign-out cleanup incomplete", "Local session data was removed where possible. Restart the app before sharing documents again.");
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        isLoading,
        isAuthenticated,
        user,
        baseUrl,
        signIn,
        signInWithQR,
        signOut,
        setToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function _getDeviceName(): Promise<string> {
  try {
    const Constants = await import("expo-constants");
    return (
      Constants.default.deviceName ||
      Constants.default.expoConfig?.name ||
      "Mobile App"
    );
  } catch {
    return "Mobile App";
  }
}
