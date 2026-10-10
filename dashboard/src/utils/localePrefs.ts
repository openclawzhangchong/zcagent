export type UiLocale = "zh" | "en";

export const UI_LOCALE_STORAGE_KEY = "octop:ui-locale";

/** Map browser language tags to a supported dashboard locale. */
export function detectBrowserLocale(): UiLocale {
  if (typeof navigator === "undefined") return "en";

  const candidates =
    navigator.languages?.length > 0
      ? navigator.languages
      : [navigator.language];

  for (const raw of candidates) {
    const lang = raw?.toLowerCase() ?? "";
    if (lang.startsWith("zh")) return "zh";
    if (lang.startsWith("en")) return "en";
  }

  const primary = navigator.language?.toLowerCase() ?? "";
  if (primary.startsWith("zh")) return "zh";
  if (primary.startsWith("en")) return "en";

  return "en";
}

export function normalizeUiLocale(raw: string | null | undefined): UiLocale {
  if (!raw) return "zh";
  return raw.toLowerCase().startsWith("zh") ? "zh" : "en";
}

export function readStoredUiLocale(): UiLocale | null {
  try {
    const raw = localStorage.getItem(UI_LOCALE_STORAGE_KEY);
    if (raw === "zh" || raw === "en") return raw;
  } catch {
    // localStorage unavailable
  }
  return null;
}

export function storeUiLocale(locale: UiLocale): void {
  try {
    localStorage.setItem(UI_LOCALE_STORAGE_KEY, locale);
  } catch {
    // quota / disabled
  }
}

/**
 * Stored preference wins; otherwise Chinese.
 *
 * Deliberately not "whatever the browser claims": WebView2 inside the desktop
 * shell reports en-US on a Chinese Windows, so browser detection opened every
 * installed client in English -- and `applyGuestLocale` used to persist that
 * guess, which made it stick. `detectBrowserLocale` is kept for surfaces that
 * genuinely want the browser's opinion.
 */
export function resolveInitialLocale(): UiLocale {
  return readStoredUiLocale() ?? "zh";
}

export function syncDocumentLang(locale: UiLocale): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
}

/** BCP-47 tag for STT / SpeechRecognition from dashboard UI locale. */
export function speechLocaleFromUi(locale: string | null | undefined): string {
  return normalizeUiLocale(locale) === "zh" ? "zh-CN" : "en-US";
}
