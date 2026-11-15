import { Platform } from "react-native";
import { requireOptionalNativeModule } from "expo-modules-core";
import Constants from "expo-constants";

type AuthBridge = {
  syncCredentials(baseUrl: string, token: string, ownerId: string): Promise<void>;
  clearCredentials(): Promise<void>;
};

const native = Platform.OS === "ios"
  ? requireOptionalNativeModule<AuthBridge>("DocuElevateAuth")
  : undefined;

// Expo Go does not contain this local native module. Development clients and
// standalone iOS builds must contain it so sharing cannot silently use stale
// credentials from a prior session.
const requiresNativeBridge = Platform.OS === "ios" && Constants.appOwnership !== "expo";

export async function syncShareCredentials(baseUrl: string, token: string, ownerId: string): Promise<void> {
  if (requiresNativeBridge && !native) throw new Error("DocuElevate share authentication is unavailable in this iOS build.");
  if (native) await native.syncCredentials(baseUrl, token, ownerId);
}

export async function clearShareCredentials(): Promise<void> {
  if (requiresNativeBridge && !native) throw new Error("DocuElevate share authentication is unavailable in this iOS build.");
  if (native) await native.clearCredentials();
}
