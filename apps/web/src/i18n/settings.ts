/**
 * i18n configuration settings
 *
 * Defines supported languages, fallback language, and configuration options
 * for react-i18next internationalization.
 */

export const fallbackLng = 'fr' as const;
export const languages = ['fr', 'en', 'es', 'de', 'it', 'zh'] as const;
export const defaultNS = 'translation' as const;
export const cookieName = 'NEXT_LOCALE';
/** Cookie max age in seconds (1 year) */
export const COOKIE_MAX_AGE_SECONDS = 31536000;

export type Language = (typeof languages)[number];

/**
 * Language display names (native and English)
 * Centralized to avoid duplication across components
 */
export const languageNames: Record<Language, { native: string; english: string }> = {
  fr: { native: 'Français', english: 'French' },
  en: { native: 'English', english: 'English' },
  es: { native: 'Español', english: 'Spanish' },
  de: { native: 'Deutsch', english: 'German' },
  it: { native: 'Italiano', english: 'Italian' },
  zh: { native: '简体中文', english: 'Chinese (Simplified)' },
};

/**
 * Language flag emojis
 * Centralized to avoid duplication across components
 */
export const languageFlags: Record<Language, string> = {
  fr: '🇫🇷',
  en: '🇬🇧',
  es: '🇪🇸',
  de: '🇩🇪',
  it: '🇮🇹',
  zh: '🇨🇳',
};

/**
 * Set the locale cookie for i18n routing
 * Used by LanguageSelector and LanguageSettings to persist user's language choice
 *
 * @param locale - The language code to set
 */
export function setLocaleCookie(locale: Language): void {
  if (typeof document !== 'undefined') {
    document.cookie = `${cookieName}=${locale}; path=/; max-age=${COOKIE_MAX_AGE_SECONDS}; SameSite=Lax`;
  }
}

/**
 * Mapping of Language codes to Intl.DateTimeFormat locales
 * Centralized to avoid duplication across formatting utilities
 */
export const LOCALE_MAP: Record<Language, string> = {
  fr: 'fr-FR',
  en: 'en-US',
  es: 'es-ES',
  de: 'de-DE',
  it: 'it-IT',
  zh: 'zh-CN',
} as const;

/**
 * Get the Intl-compatible locale string for a given Language
 *
 * @param lng Language code (e.g., 'fr', 'en')
 * @returns Intl locale string (e.g., 'fr-FR', 'en-US')
 *
 * @example
 * getIntlLocale('fr') // 'fr-FR'
 * getIntlLocale('en') // 'en-US'
 */
export function getIntlLocale(lng: Language): string {
  return LOCALE_MAP[lng];
}

export function getOptions(lng: Language = fallbackLng, ns: string = defaultNS) {
  return {
    // debug: true, // Enable for development
    supportedLngs: languages,
    fallbackLng,
    lng,
    fallbackNS: defaultNS,
    defaultNS,
    ns,
    interpolation: {
      escapeValue: false, // React already escapes values, no need for double escaping
    },
    // Enable returnObjects globally for t() calls with { returnObjects: true }
    // Required for GeolocationPrompt detection keywords/patterns arrays
    returnObjects: true,
  };
}
