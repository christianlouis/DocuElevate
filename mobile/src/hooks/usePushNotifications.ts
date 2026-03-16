/**
 * usePushNotifications – register the device for push notifications.
 *
 * Requests the user's permission for notifications, obtains an Expo push
 * token, and registers it with the DocuElevate backend via
 * POST /api/mobile/register-device.
 *
 * This hook should be called once from the root component after the user has
 * successfully authenticated.
 */

import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { useCallback, useEffect, useRef } from "react";
import { Platform } from "react-native";
import api from "../services/api";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export function usePushNotifications(isAuthenticated: boolean) {
  const notificationListener = useRef<Notifications.Subscription | null>(null);
  const responseListener = useRef<Notifications.Subscription | null>(null);

  const registerForPushNotifications = useCallback(async () => {
    if (!Device.isDevice) {
      // Push tokens are not available in simulators.
      return;
    }

    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("default", {
        name: "DocuElevate",
        importance: Notifications.AndroidImportance.MAX,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: "#1e40af",
      });
    }

    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;

    if (existingStatus !== "granted") {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }

    if (finalStatus !== "granted") {
      // User declined – no push notifications
      return;
    }

    let projectId: string | undefined;
    try {
      projectId =
        Constants.expoConfig?.extra?.eas?.projectId ??
        Constants.easConfig?.projectId;
    } catch {
      // ignore
    }

    const tokenData = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined
    );

    const pushToken = tokenData.data;
    const platform = Platform.OS as "ios" | "android" | "web";

    let deviceName = "Mobile App";
    try {
      deviceName = Device.modelName ?? Device.deviceName ?? "Mobile App";
    } catch {
      // ignore
    }

    try {
      await api.registerDevice({ push_token: pushToken, device_name: deviceName, platform });
    } catch {
      // Registration failure is non-fatal – the app still works without push.
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;

    registerForPushNotifications();

    // Listen for incoming notifications while app is foregrounded
    notificationListener.current = Notifications.addNotificationReceivedListener((notification) => {
      console.log("Notification received:", notification.request.content.title);
    });

    // Listen for user taps on notifications
    responseListener.current = Notifications.addNotificationResponseReceivedListener((response) => {
      const data = response.notification.request.content.data as Record<string, unknown>;
      // Navigate to file detail if file_id is present
      if (data?.file_id) {
        console.log("User tapped notification for file:", data.file_id);
        // Navigation would be wired up by the caller via a callback prop
      }
    });

    return () => {
      notificationListener.current?.remove();
      responseListener.current?.remove();
    };
  }, [isAuthenticated, registerForPushNotifications]);
}
