/**
 * i18next initialization
 *
 * Server-side i18next configuration for Next.js 15 App Router.
 * Loads translation resources directly from JSON files.
 */

import { createInstance, type i18n as I18nInstance } from 'i18next';
import { initReactI18next } from 'react-i18next/initReactI18next';
import { getOptions, type Language, languages, fallbackLng } from './settings';

/**
 * Validate and normalize a language parameter to a supported Language type
 * @param lngParam - Raw language string from URL params
 * @returns Validated Language type (falls back to default if invalid)
 */
export function validateLanguage(lngParam: string): Language {
  return languages.includes(lngParam as Language) ? (lngParam as Language) : fallbackLng;
}

// Import translation files directly
import translationFR from '../../locales/fr/translation.json';
import translationEN from '../../locales/en/translation.json';
import translationES from '../../locales/es/translation.json';
import translationDE from '../../locales/de/translation.json';
import translationIT from '../../locales/it/translation.json';
import translationZH from '../../locales/zh/translation.json';

// Cache i18n instances per language to avoid recreation
const i18nInstances = new Map<string, I18nInstance>();

// Map of all translations
const translations = {
  fr: { translation: translationFR },
  en: { translation: translationEN },
  es: { translation: translationES },
  de: { translation: translationDE },
  it: { translation: translationIT },
  zh: { translation: translationZH },
};

/**
 * Initialize i18next instance for a specific language
 *
 * Server-side only. Creates or returns cached i18n instance with
 * translations loaded from JSON files.
 *
 * @param lngParam - Language code string (validated against supported languages)
 * @param ns - Namespace (default: 'translation')
 * @returns Initialized i18n instance
 */
export async function initI18next(lngParam: string, ns?: string) {
  // Validate and fallback to default language if not supported
  const lng: Language = languages.includes(lngParam as Language)
    ? (lngParam as Language)
    : fallbackLng;

  const cacheKey = `${lng}-${ns || 'translation'}`;

  if (i18nInstances.has(cacheKey)) {
    return i18nInstances.get(cacheKey)!;
  }

  const i18nInstance = createInstance();

  await i18nInstance.use(initReactI18next).init({
    ...getOptions(lng, ns),
    resources: {
      [lng]: translations[lng],
    },
  });

  i18nInstances.set(cacheKey, i18nInstance);
  return i18nInstance;
}
