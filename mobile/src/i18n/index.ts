/**
 * Lightweight i18n module for the DocuElevate mobile app.
 *
 * Uses the device locale (via expo-localization) to select the best matching
 * translation file.  Falls back to English for missing keys or unsupported
 * locales.
 *
 * Supported languages: English, German, Spanish, French, Italian.
 *
 * ## React integration
 *
 * Wrap the app root in `<LocaleProvider>` and call `useLocale()` in any
 * component that renders translated strings.  `useLocale()` returns the
 * active language code and a `setLang` setter that:
 *   1. Updates the in-memory `currentLanguage` variable (so `t()` picks it up)
 *   2. Triggers a React re-render of every consumer
 *   3. Persists the choice to AsyncStorage (survives app restarts)
 *
 * Language priority on startup:
 *   server preference (from /api/mobile/whoami) > AsyncStorage > device locale > "en"
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import { getLocales } from "expo-localization";
import React from "react";

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

const LANG_STORAGE_KEY = "@docuelevate:language";

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
// Plain-function public API (framework-agnostic)
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

/**
 * Update the active language in memory.
 * Prefer `useLocale().setLang` inside React components – it also persists
 * the choice and triggers re-renders.
 */
export function setLanguage(lang: string): void {
  if (translations[lang]) {
    currentLanguage = lang;
  }
}

/** Return true if the given language code is supported by the mobile app. */
export function isLanguageSupported(lang: string): boolean {
  return Object.prototype.hasOwnProperty.call(translations, lang);
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

// ---------------------------------------------------------------------------
// React integration – context + provider + hook
// ---------------------------------------------------------------------------

interface LocaleContextValue {
  /** The active language code, e.g. "en" or "de". */
  lang: string;
  /**
   * Switch to a new language.  Persists the choice to AsyncStorage and
   * triggers a re-render of every `useLocale()` consumer.
   */
  setLang: (code: string) => Promise<void>;
}

const LocaleContext = React.createContext<LocaleContextValue>({
  lang: currentLanguage,
  // Default setter used outside of a provider – updates in-memory only.
  setLang: async (code: string) => {
    setLanguage(code);
  },
});

/**
 * Wrap the app root in `LocaleProvider` to enable reactive language switching.
 *
 * On mount it reads the persisted language from AsyncStorage so the user's
 * choice survives app restarts.  The server-preferred language is applied
 * externally (see `AuthGuard` in `app/_layout.tsx`) after the profile is
 * fetched from `/api/mobile/whoami`.
 */
export function LocaleProvider({ children }: { children: React.ReactNode }): React.ReactElement {
  const [lang, setLangState] = React.useState(currentLanguage);

  // Restore the persisted language preference once on app start.
  React.useEffect(() => {
    AsyncStorage.getItem(LANG_STORAGE_KEY)
      .then((saved) => {
        if (saved && isLanguageSupported(saved)) {
          setLanguage(saved);
          setLangState(saved);
        }
      })
      .catch(() => {
        // Ignore read errors – fall back to device-detected language.
      });
  }, []);

  const setLang = React.useCallback(async (code: string): Promise<void> => {
    if (!isLanguageSupported(code)) return;
    setLanguage(code);
    setLangState(code);
    try {
      await AsyncStorage.setItem(LANG_STORAGE_KEY, code);
    } catch {
      // Ignore write errors – the in-memory change is still applied.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // setLangState is a React state setter – its identity is guaranteed stable

  const value = React.useMemo(() => ({ lang, setLang }), [lang, setLang]);

  return React.createElement(LocaleContext.Provider, { value }, children);
}

/**
 * Hook that subscribes to language changes.
 *
 * Any component calling `useLocale()` re-renders automatically when the
 * language changes.  Call `t()` freely inside the component body – the
 * re-render will pick up the new translations.
 *
 * ```tsx
 * function MyScreen() {
 *   const { lang, setLang } = useLocale(); // subscribes to changes
 *   return <Text>{t("common.loading")}</Text>;
 * }
 * ```
 */
export function useLocale(): LocaleContextValue {
  return React.useContext(LocaleContext);
}
