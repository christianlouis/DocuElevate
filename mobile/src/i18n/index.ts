/**
 * Lightweight i18n module for the DocuElevate mobile app.
 *
 * Uses the device locale (via expo-localization) to select the best matching
 * translation file.  Falls back to English for missing keys or unsupported
 * locales.
 *
 * Supported languages: English, German, Spanish, French, Italian.
 */

import { getLocales } from "expo-localization";

import de from "./de.json";
import en from "./en.json";
import es from "./es.json";
import fr from "./fr.json";
import it from "./it.json";

// ---------------------------------------------------------------------------
// Translation catalog
// ---------------------------------------------------------------------------

type TranslationMap = Record<string, Record<string, string>>;

const translations: Record<string, TranslationMap> = { en, de, es, fr, it };

// ---------------------------------------------------------------------------
// Locale detection
// ---------------------------------------------------------------------------

/** Resolve the best-matching language code from the device locale list. */
function detectLanguage(): string {
  try {
    const locales = getLocales();
    if (locales.length > 0) {
      // Try exact match first (e.g. "de"), then fall back to language prefix
      const code = locales[0].languageCode?.toLowerCase();
      if (code && translations[code]) return code;
    }
  } catch {
    // getLocales() can throw on some platforms – default to English
  }
  return "en";
}

let currentLanguage: string = detectLanguage();

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Translate a dot-separated key, e.g. `t("upload.camera")`.
 *
 * Supports simple placeholder interpolation:
 *   `t("upload.retry_msg", { filename: "doc.pdf" })`
 * replaces `{filename}` in the translated string.
 *
 * Falls back to the English value, then to the raw key if no translation
 * exists.
 */
export function t(key: string, params?: Record<string, string>): string {
  const [section, ...rest] = key.split(".");
  const subKey = rest.join(".");

  let value =
    translations[currentLanguage]?.[section]?.[subKey] ??
    translations.en?.[section]?.[subKey] ??
    key;

  if (params) {
    for (const [k, v] of Object.entries(params)) {
      value = value.replaceAll(`{${k}}`, v);
    }
  }

  return value;
}

/** Return the current language code (e.g. "en", "de"). */
export function getLanguage(): string {
  return currentLanguage;
}

/** Override the language manually (e.g. from user settings). */
export function setLanguage(lang: string): void {
  if (translations[lang]) {
    currentLanguage = lang;
  }
}

/** Return the list of supported language codes. */
export function getSupportedLanguages(): { code: string; label: string }[] {
  return [
    { code: "en", label: "English" },
    { code: "de", label: "Deutsch" },
    { code: "es", label: "Español" },
    { code: "fr", label: "Français" },
    { code: "it", label: "Italiano" },
  ];
}
