/**
 * DocuElevate API client for the mobile app.
 *
 * All requests authenticate via a Bearer token stored in the device's secure
 * keychain (via expo-secure-store).  The token is obtained once through the
 * SSO flow and cached until the user explicitly logs out.
 */

import * as SecureStore from "expo-secure-store";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const SECURE_STORE_API_TOKEN_KEY = "de_api_token";
export const SECURE_STORE_BASE_URL_KEY = "de_base_url";
export const SECURE_STORE_OWNER_ID_KEY = "de_owner_id";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface WhoAmIResponse {
  owner_id: string;
  display_name: string | null;
  email: string | null;
  avatar_url: string | null;
  is_admin: boolean;
}

export interface GenerateTokenResponse {
  token: string;
  token_id: number;
  name: string;
  created_at: string;
}

export interface QRClaimResponse {
  token: string;
  token_id: number;
  name: string;
  owner_id: string;
  created_at: string;
}

export interface DeviceRegistration {
  push_token: string;
  device_name?: string;
  platform: "ios" | "android" | "web";
}

export interface ProcessingStatus {
  status: string;
  last_step: string | null;
  has_errors: boolean;
  total_steps: number;
}

export interface FileRecord {
  id: number;
  original_filename: string;
  file_size: number | null;
  mime_type: string | null;
  created_at: string;
  processing_status: ProcessingStatus;
}

export interface UploadResponse {
  task_id?: string;
  status: string;
  original_filename: string;
  stored_filename: string;
  duplicate_of?: {
    duplicate_type: string;
    original_file_id: number;
    original_filename: string;
    message: string;
  };
}

export interface ProcessingLog {
  id: number;
  task_id: string;
  step_name: string;
  status: string;
  message: string;
  timestamp: string;
}

export interface FileDetail {
  file: {
    id: number;
    filehash: string;
    original_filename: string;
    local_filename: string;
    file_size: number;
    mime_type: string;
    created_at: string;
  };
  processing_status: ProcessingStatus;
  logs: ProcessingLog[];
  files_on_disk: {
    original: boolean;
  };
}

// ---------------------------------------------------------------------------
// Base API client
// ---------------------------------------------------------------------------

class DocuElevateAPI {
  private baseUrl: string = "";

  async init(baseUrl: string): Promise<void> {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    await SecureStore.setItemAsync(SECURE_STORE_BASE_URL_KEY, this.baseUrl);
  }

  async loadFromStorage(): Promise<boolean> {
    try {
      const url = await SecureStore.getItemAsync(SECURE_STORE_BASE_URL_KEY);
      if (url) {
        this.baseUrl = url;
        return true;
      }
    } catch {
      // ignore
    }
    return false;
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }

  private async getToken(): Promise<string | null> {
    try {
      return await SecureStore.getItemAsync(SECURE_STORE_API_TOKEN_KEY);
    } catch {
      return null;
    }
  }

  private async request<T>(
    method: string,
    path: string,
    options?: { body?: unknown; formData?: FormData }
  ): Promise<T> {
    const token = await this.getToken();
    const headers: Record<string, string> = {};

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    let body: string | FormData | undefined;
    if (options?.formData) {
      body = options.formData;
      // Let fetch set multipart content-type with boundary automatically
    } else if (options?.body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(options.body);
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers,
      body,
    });

    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const err = await response.json();
        detail = err.detail || JSON.stringify(err);
      } catch {
        // ignore
      }
      throw new Error(detail);
    }

    if (response.status === 204) {
      return undefined as unknown as T;
    }

    return response.json();
  }

  // -------------------------------------------------------------------------
  // Auth
  // -------------------------------------------------------------------------

  /** Exchange the current session (cookie) for a long-lived API token. */
  async generateMobileToken(deviceName: string): Promise<GenerateTokenResponse> {
    return this.request<GenerateTokenResponse>("POST", "/api/mobile/generate-token", {
      body: { device_name: deviceName },
    });
  }

  /** Claim a QR login challenge and receive an API token. */
  async claimQRChallenge(challengeToken: string, deviceName: string): Promise<QRClaimResponse> {
    return this.request<QRClaimResponse>("POST", "/api/qr-auth/claim", {
      body: { challenge_token: challengeToken, device_name: deviceName },
    });
  }

  /** Return profile information for the authenticated user. */
  async whoAmI(): Promise<WhoAmIResponse> {
    return this.request<WhoAmIResponse>("GET", "/api/mobile/whoami");
  }

  // -------------------------------------------------------------------------
  // Push notifications
  // -------------------------------------------------------------------------

  /** Register a push notification device token. */
  async registerDevice(data: DeviceRegistration): Promise<void> {
    await this.request("POST", "/api/mobile/register-device", { body: data });
  }

  /** Deactivate a device registration. */
  async deactivateDevice(deviceId: number): Promise<void> {
    await this.request("DELETE", `/api/mobile/devices/${deviceId}`);
  }

  // -------------------------------------------------------------------------
  // Files
  // -------------------------------------------------------------------------

  /** Upload a file for processing. */
  async uploadFile(uri: string, filename: string, mimeType?: string): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append("file", {
      uri,
      name: filename,
      type: mimeType || "application/octet-stream",
    } as unknown as Blob);

    return this.request<UploadResponse>("POST", "/api/ui-upload", { formData });
  }

  /** List recently processed files, optionally filtered by filename search. */
  async listFiles(page = 1, pageSize = 20, search?: string): Promise<FileRecord[]> {
    let url = `/api/files?page=${page}&per_page=${pageSize}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    const data = await this.request<{ files: FileRecord[]; pagination: unknown }>("GET", url);
    return data.files;
  }

  /** Get the processing status for a single file by its ID. */
  async getFileStatus(fileId: number): Promise<ProcessingStatus> {
    const data = await this.request<{ processing_status: ProcessingStatus }>(
      "GET",
      `/api/files/${fileId}`
    );
    return data.processing_status;
  }

  /** Get full file details including processing logs. */
  async getFileDetail(fileId: number): Promise<FileDetail> {
    return this.request<FileDetail>("GET", `/api/files/${fileId}`);
  }
}

export const api = new DocuElevateAPI();
export default api;
