/**
 * Normalise a file URI for deduplication.
 *
 * - Decode percent-encoding (`%20` → ` `)
 * - Collapse consecutive slashes after the scheme (`file:////` → `file:///`)
 * - Strip trailing slashes
 */
export function normalizeFileUri(uri: string): string {
  let norm: string;
  try {
    norm = decodeURIComponent(uri);
  } catch {
    norm = uri;
  }
  // Collapse multiple slashes after the scheme (e.g. file://// → file:///)
  norm = norm.replace(/^(file:\/\/)\/{2,}/, "$1/");
  // Strip trailing slash
  norm = norm.replace(/\/+$/, "");
  return norm;
}
