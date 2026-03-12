/**
 * Authentication context for the DocuElevate mobile app.
 *
 * Manages the lifecycle of the stored API token and user profile.  The SSO
 * login flow uses expo-auth-session to open the server's OAuth page in the
 * system browser; on return the redirect URL carries a one-time code that is
 * exchanged for a session cookie, which is then traded for a permanent API
 * token via POST /api/mobile/generate-token.
 */

import * as SecureStore from "expo-secure-store";
import * as WebBrowser from "expo-web-browser";
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
          setUser(profile);
          setIsAuthenticated(true);
        }
      } catch {
        // Token expired or server unavailable – clear stored credentials
        await SecureStore.deleteItemAsync(SECURE_STORE_API_TOKEN_KEY);
        await SecureStore.deleteItemAsync(SECURE_STORE_OWNER_ID_KEY);
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
    setIsAuthenticated(true);
  }, []);

  const signIn = useCallback(
    async (serverUrl: string) => {
      const cleanUrl = serverUrl.replace(/\/$/, "");
      await api.init(cleanUrl);
      setBaseUrl(cleanUrl);

      // Open the web login page in the system browser.  The user authenticates
      // via SSO or local credentials, then the app deep-link (docuelevate://callback)
      // is triggered.  The WebBrowser.openAuthSessionAsync handles the redirect
      // back to the app.
      const result = await WebBrowser.openAuthSessionAsync(
        `${cleanUrl}/login?mobile=1&redirect_uri=docuelevate://callback`,
        "docuelevate://callback"
      );

      if (result.type !== "success") {
        throw new Error("Authentication was cancelled or failed");
      }

      // Parse the token from the redirect URL if the server appended it,
      // otherwise hit the generate-token endpoint (session cookie is carried
      // by the WebBrowser).
      const url = new URL(result.url);
      const inlineToken = url.searchParams.get("token");

      if (inlineToken) {
        await setToken(inlineToken);
      } else {
        // The server set a session cookie during the browser session; exchange
        // it for a persistent API token.
        const deviceInfo = await _getDeviceName();
        const tokenResp = await api.generateMobileToken(deviceInfo);
        await setToken(tokenResp.token);
      }
    },
    [setToken]
  );

  const signOut = useCallback(async () => {
    await SecureStore.deleteItemAsync(SECURE_STORE_API_TOKEN_KEY);
    await SecureStore.deleteItemAsync(SECURE_STORE_OWNER_ID_KEY);
    setUser(null);
    setIsAuthenticated(false);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        isLoading,
        isAuthenticated,
        user,
        baseUrl,
        signIn,
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
