/**
 * QRScannerScreen – camera-based QR code scanner for mobile login.
 *
 * Opens the device camera and scans for QR codes containing a
 * `docuelevate://qr-login?token=...&server=...` payload.  On successful
 * scan the token is claimed via the API and the user is signed in.
 */

import { CameraView, useCameraPermissions } from "expo-camera";
import { useRouter } from "expo-router";
import React, { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useAuth } from "../context/AuthContext";

export default function QRScannerScreen() {
  const { signInWithQR } = useAuth();
  const router = useRouter();
  const [permission, requestPermission] = useCameraPermissions();
  const [scanned, setScanned] = useState(false);
  const [processing, setProcessing] = useState(false);
  const processingRef = useRef(false);

  const handleBarCodeScanned = useCallback(
    async (result: { data: string }) => {
      // Prevent duplicate scans while processing
      if (processingRef.current) return;

      const { data } = result;

      // Only accept docuelevate:// QR codes
      if (!data.startsWith("docuelevate://qr-login")) return;

      processingRef.current = true;
      setScanned(true);
      setProcessing(true);

      try {
        const url = new URL(data);
        const token = url.searchParams.get("token");
        const server = url.searchParams.get("server");

        if (!token || !server) {
          Alert.alert("Invalid QR Code", "This QR code does not contain valid login information.");
          setScanned(false);
          processingRef.current = false;
          setProcessing(false);
          return;
        }

        await signInWithQR(server, token);
        // signInWithQR updates AuthContext → AuthGuard redirects to main app
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "QR login failed";
        Alert.alert("QR Login Failed", message);
        setScanned(false);
        processingRef.current = false;
        setProcessing(false);
      }
    },
    [signInWithQR]
  );

  // Permissions not yet determined
  if (!permission) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#1e40af" />
      </View>
    );
  }

  // Permission denied
  if (!permission.granted) {
    return (
      <View style={styles.centered}>
        <Text style={styles.permissionText}>
          Camera access is required to scan QR codes.
        </Text>
        <Pressable
          style={styles.permissionButton}
          onPress={requestPermission}
          accessibilityRole="button"
          accessibilityLabel="Grant camera access"
        >
          <Text style={styles.permissionButtonText}>Grant Camera Access</Text>
        </Pressable>
        <Pressable
          onPress={() => router.back()}
          style={styles.backLink}
          accessibilityRole="button"
          accessibilityLabel="Go back"
        >
          <Text style={styles.backLinkText}>← Back</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView
        style={styles.camera}
        facing="back"
        barcodeScannerSettings={{
          barcodeTypes: ["qr"],
        }}
        onBarcodeScanned={scanned ? undefined : handleBarCodeScanned}
      />

      {/* Overlay with scan area indicator */}
      <View style={styles.overlay}>
        <View style={styles.overlayTop} />
        <View style={styles.overlayMiddle}>
          <View style={styles.overlaySide} />
          <View style={styles.scanArea}>
            <View style={[styles.corner, styles.cornerTopLeft]} />
            <View style={[styles.corner, styles.cornerTopRight]} />
            <View style={[styles.corner, styles.cornerBottomLeft]} />
            <View style={[styles.corner, styles.cornerBottomRight]} />
          </View>
          <View style={styles.overlaySide} />
        </View>
        <View style={styles.overlayBottom}>
          {processing ? (
            <View style={styles.statusContainer}>
              <ActivityIndicator color="#fff" />
              <Text style={styles.statusText}>Signing in…</Text>
            </View>
          ) : (
            <Text style={styles.instructionText}>
              Point your camera at the QR code{"\n"}shown on the DocuElevate web app
            </Text>
          )}

          <Pressable
            onPress={() => router.back()}
            style={styles.cancelButton}
            accessibilityRole="button"
            accessibilityLabel="Cancel QR scan"
          >
            <Text style={styles.cancelButtonText}>Cancel</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const SCAN_AREA_SIZE = 250;
const CORNER_SIZE = 24;
const CORNER_WIDTH = 3;

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#000",
  },
  camera: {
    flex: 1,
  },
  centered: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: "#f3f4f6",
    padding: 24,
  },
  permissionText: {
    fontSize: 16,
    color: "#374151",
    textAlign: "center",
    marginBottom: 20,
  },
  permissionButton: {
    backgroundColor: "#1e40af",
    borderRadius: 8,
    paddingVertical: 14,
    paddingHorizontal: 24,
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
  },
  permissionButtonText: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "600",
  },
  backLink: {
    marginTop: 20,
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  backLinkText: {
    fontSize: 14,
    color: "#6b7280",
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
  },
  overlayTop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.5)",
  },
  overlayMiddle: {
    flexDirection: "row",
    height: SCAN_AREA_SIZE,
  },
  overlaySide: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.5)",
  },
  scanArea: {
    width: SCAN_AREA_SIZE,
    height: SCAN_AREA_SIZE,
  },
  corner: {
    position: "absolute",
    width: CORNER_SIZE,
    height: CORNER_SIZE,
  },
  cornerTopLeft: {
    top: 0,
    left: 0,
    borderTopWidth: CORNER_WIDTH,
    borderLeftWidth: CORNER_WIDTH,
    borderColor: "#fff",
  },
  cornerTopRight: {
    top: 0,
    right: 0,
    borderTopWidth: CORNER_WIDTH,
    borderRightWidth: CORNER_WIDTH,
    borderColor: "#fff",
  },
  cornerBottomLeft: {
    bottom: 0,
    left: 0,
    borderBottomWidth: CORNER_WIDTH,
    borderLeftWidth: CORNER_WIDTH,
    borderColor: "#fff",
  },
  cornerBottomRight: {
    bottom: 0,
    right: 0,
    borderBottomWidth: CORNER_WIDTH,
    borderRightWidth: CORNER_WIDTH,
    borderColor: "#fff",
  },
  overlayBottom: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.5)",
    alignItems: "center",
    paddingTop: 32,
  },
  statusContainer: {
    flexDirection: "row",
    alignItems: "center",
  },
  statusText: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "600",
    marginLeft: 10,
  },
  instructionText: {
    color: "#fff",
    fontSize: 15,
    textAlign: "center",
    lineHeight: 22,
  },
  cancelButton: {
    marginTop: 24,
    paddingVertical: 12,
    paddingHorizontal: 32,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.5)",
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  cancelButtonText: {
    color: "#fff",
    fontSize: 15,
    fontWeight: "500",
  },
});
