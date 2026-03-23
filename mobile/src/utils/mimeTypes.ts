/**
 * Shared MIME type utilities for the DocuElevate mobile app.
 *
 * Used by the Linking handler in _layout.tsx, the catch-all +not-found.tsx,
 * and any other code that needs to infer a MIME type from a file extension.
 */

/**
 * Common MIME type mappings for file extensions.
 * Used to infer the MIME type of files shared via the Share Sheet / "Open In…"
 * so the server receives a correct Content-Type instead of application/octet-stream.
 */
export const EXT_TO_MIME: Record<string, string> = {
  pdf: "application/pdf",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  gif: "image/gif",
  bmp: "image/bmp",
  tiff: "image/tiff",
  tif: "image/tiff",
  webp: "image/webp",
  heic: "image/heic",
  heif: "image/heif",
  txt: "text/plain",
  csv: "text/csv",
  doc: "application/msword",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  xls: "application/vnd.ms-excel",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ppt: "application/vnd.ms-powerpoint",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  rtf: "application/rtf",
  html: "text/html",
  xml: "application/xml",
  json: "application/json",
  zip: "application/zip",
};

/** Infer MIME type from a filename's extension, or undefined if unknown. */
export function mimeTypeFromFilename(filename: string): string | undefined {
  const ext = filename.split(".").pop()?.toLowerCase();
  return ext ? EXT_TO_MIME[ext] : undefined;
}
