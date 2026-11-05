export type MobilePreflightDecision = "supported" | "unsupported" | "invalid";

export class MobileServerUnsupportedError extends Error {
  constructor() {
    super("This server does not support mobile sign-in. Update the DocuElevate server and try again.");
    this.name = "MobileServerUnsupportedError";
  }
}

export class MobileServerPreflightError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MobileServerPreflightError";
  }
}

export function classifyMobilePreflight(status: number, contentType: string): MobilePreflightDecision {
  if (status === 404) return "unsupported";
  const isJson = contentType.toLowerCase().includes("application/json");
  if ((status === 401 || status === 403 || (status >= 200 && status < 300)) && isJson) {
    return "supported";
  }
  return "invalid";
}

/** Probe API compatibility without forwarding credentials from a previous login. */
export async function checkMobileSupport(
  baseUrl: string,
  fetchImpl: typeof fetch = fetch,
  timeoutMs = 10_000
): Promise<void> {
  const cleanUrl = baseUrl.replace(/\/$/, "");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(`${cleanUrl}/api/mobile/whoami`, {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "omit",
      signal: controller.signal,
    });
    const decision = classifyMobilePreflight(response.status, response.headers.get("content-type") || "");
    if (decision === "unsupported") throw new MobileServerUnsupportedError();
    if (decision === "supported" && response.status >= 200 && response.status < 300) {
      let profile: unknown;
      try {
        profile = await response.json();
      } catch {
        throw new MobileServerPreflightError("Mobile sign-in returned an invalid or incomplete server response.");
      }
      if (!profile || typeof profile !== "object" || typeof (profile as { owner_id?: unknown }).owner_id !== "string") {
        throw new MobileServerPreflightError("Mobile sign-in returned an invalid server response.");
      }
    }
    if (decision === "supported") return;
    throw new MobileServerPreflightError(
      `Mobile sign-in received an unexpected server response (HTTP ${response.status}).`
    );
  } catch (error) {
    if (error instanceof MobileServerUnsupportedError || error instanceof MobileServerPreflightError) {
      throw error;
    }
    throw new MobileServerPreflightError(
      "Could not reach this DocuElevate server. Check the URL and your network connection."
    );
  } finally {
    // Keep the timeout active while reading the response body, too.
    clearTimeout(timeout);
  }
}

export function callbackToken(callbackUrl: string, redirectUri: string): string {
  let callback: URL;
  let expected: URL;
  try {
    callback = new URL(callbackUrl);
    expected = new URL(redirectUri);
  } catch {
    throw new Error("Authentication returned an invalid callback URL. Please try again.");
  }
  const matchesTarget =
    callback.protocol === expected.protocol &&
    callback.hostname === expected.hostname &&
    callback.port === expected.port &&
    callback.pathname === expected.pathname;
  if (!matchesTarget) throw new Error("Authentication returned an unexpected callback URL. Please try again.");
  const token = callback.searchParams.get("token");
  if (!token) throw new Error("The server completed sign-in without returning a mobile token. Update the server and try again.");
  return token;
}
