/**
 * Locale Mapping Utilities
 *
 * Provides bidirectional conversion between frontend locale codes (used in URLs/UI)
 * and backend language codes (stored in database for email notifications).
 *
 * Frontend codes: ['fr', 'en', 'es', 'de', 'it', 'zh']
 * Backend codes:  ['fr', 'en', 'es', 'de', 'it', 'zh-CN']
 *
 * Examples:
 * - Frontend 'zh' → Backend 'zh-CN'
 * - Backend 'zh-CN' → Frontend 'zh'
 * - Frontend 'fr' → Backend 'fr' (no transformation)
 */

import { LOCALE_MAP, type Language, fallbackLng } from '@/i18n/settings';

/**
 * Convert frontend locale code to backend language code
 *
 * @param frontendCode - Frontend locale code (e.g., 'zh', 'fr')
 * @returns Backend language code (e.g., 'zh-CN', 'fr')
 *
 * @example
 * frontendToBackendLocale('zh') // 'zh-CN'
 * frontendToBackendLocale('fr') // 'fr'
 * frontendToBackendLocale('en') // 'en'
 */
export function frontendToBackendLocale(frontendCode: Language): string {
  // For most languages, frontend and backend codes are identical
  // Exception: 'zh' (frontend) → 'zh-CN' (backend)
  const backendCode = LOCALE_MAP[frontendCode];

  // Extract backend code: 'fr-FR' → 'fr', 'zh-CN' → 'zh-CN'
  // Keep zh-CN as is, but simplify others to 2-letter codes
  if (backendCode === 'zh-CN') {
    return 'zh-CN';
  }

  // For other locales, extract first 2 characters
  return backendCode.split('-')[0];
}

/**
 * Convert backend language code to frontend locale code
 *
 * @param backendCode - Backend language code (e.g., 'zh-CN', 'fr')
 * @returns Frontend locale code (e.g., 'zh', 'fr')
 *
 * @example
 * backendToFrontendLocale('zh-CN') // 'zh'
 * backendToFrontendLocale('fr') // 'fr'
 * backendToFrontendLocale('en') // 'en'
 */
export function backendToFrontendLocale(backendCode: string): Language {
  // Handle special case: 'zh-CN' → 'zh'
  if (backendCode === 'zh-CN') {
    return 'zh';
  }

  // For other codes, try to find matching frontend locale
  // Search for the locale whose LOCALE_MAP value starts with the backend code
  const entry = Object.entries(LOCALE_MAP).find(([_, mappedCode]) => {
    // Check if mapped code matches backend code
    // e.g., backend 'fr' matches frontend 'fr' (mapped to 'fr-FR')
    return mappedCode.startsWith(backendCode);
  });

  if (entry) {
    return entry[0] as Language;
  }

  // Fallback to default language if no match found
  return fallbackLng;
}

/**
 * Get browser language and convert to backend format
 *
 * Reads navigator.language and converts to backend-compatible code.
 * Falls back to default language if browser language is not supported.
 *
 * @returns Backend language code (e.g., 'zh-CN', 'fr')
 *
 * @example
 * // Browser language: zh-CN
 * getBrowserLanguageForBackend() // 'zh-CN'
 *
 * // Browser language: en-US
 * getBrowserLanguageForBackend() // 'en'
 *
 * // Browser language: ja-JP (not supported)
 * getBrowserLanguageForBackend() // 'fr' (fallback)
 */
export function getBrowserLanguageForBackend(): string {
  if (typeof navigator === 'undefined') {
    // Server-side rendering
    return frontendToBackendLocale(fallbackLng);
  }

  const browserLang = navigator.language; // e.g., 'zh-CN', 'en-US', 'fr-FR'

  // Try exact match first (for zh-CN)
  if (browserLang === 'zh-CN') {
    return 'zh-CN';
  }

  // Extract language code (first 2 chars)
  const langCode = browserLang.split('-')[0].toLowerCase();

  // Check if it's a supported frontend language
  const supportedLanguages = Object.keys(LOCALE_MAP);
  if (supportedLanguages.includes(langCode)) {
    return frontendToBackendLocale(langCode as Language);
  }

  // Fallback to default
  return frontendToBackendLocale(fallbackLng);
}
