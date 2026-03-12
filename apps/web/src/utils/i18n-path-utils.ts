/**
 * i18n Path Utilities
 *
 * Shared utilities for language-aware path manipulation.
 * Used by useLocalizedRouter hook and dashboard layout.
 *
 * These utilities handle the prefixDefault: false middleware configuration
 * where the default language (fr) has no URL prefix.
 */

import { languages, fallbackLng, type Language } from '@/i18n/settings';

/**
 * Extract the current language from a pathname.
 *
 * Handles both prefixed (/en/dashboard) and unprefixed (/dashboard) patterns.
 * With prefixDefault: false, unprefixed paths are the default language.
 *
 * @param pathname - Current pathname from usePathname()
 * @returns Current language code
 *
 * @example
 * getLanguageFromPath('/en/dashboard') // → 'en'
 * getLanguageFromPath('/dashboard')    // → 'fr' (fallback)
 * getLanguageFromPath('/es/login')     // → 'es'
 */
export function getLanguageFromPath(pathname: string): Language {
  const segments = pathname.split('/').filter(Boolean);
  const firstSegment = segments[0];

  // Check if first segment is a valid language code
  if (languages.includes(firstSegment as Language)) {
    return firstSegment as Language;
  }

  // No language prefix found → default language
  return fallbackLng;
}

/**
 * Build a localized path with language prefix if needed.
 *
 * Respects prefixDefault: false middleware configuration:
 * - Default language (fr): no prefix → /dashboard
 * - Other languages: with prefix → /en/dashboard
 *
 * @param path - Path to localize (must start with /)
 * @param lang - Target language
 * @returns Localized path
 *
 * @example
 * // Default language (fr) - no prefix
 * buildLocalizedPath('/dashboard', 'fr') // → '/dashboard'
 *
 * // Non-default language - add prefix
 * buildLocalizedPath('/dashboard', 'en') // → '/en/dashboard'
 */
export function buildLocalizedPath(path: string, lang: Language): string {
  // For default language, no prefix (middleware uses prefixDefault: false)
  if (lang === fallbackLng) {
    return path;
  }
  return `/${lang}${path}`;
}

/**
 * Switch the language in a pathname.
 *
 * Handles both prefixed and unprefixed paths:
 * - If path has language prefix: replaces it with new language
 * - If path has no prefix: adds the new language prefix (unless it's fallbackLng)
 *
 * Used by LanguageSelector and LanguageSettings for language switching.
 *
 * @param pathname - Current pathname
 * @param newLang - Target language to switch to
 * @returns New pathname with updated language
 *
 * @example
 * // Replace existing language
 * switchLanguageInPath('/en/dashboard', 'es') // → '/es/dashboard'
 *
 * // Add language to unprefixed path
 * switchLanguageInPath('/dashboard', 'en') // → '/en/dashboard'
 *
 * // Switch to default language (removes prefix)
 * switchLanguageInPath('/en/dashboard', 'fr') // → '/dashboard'
 */
export function switchLanguageInPath(pathname: string, newLang: Language): string {
  const segments = pathname.split('/').filter(Boolean);
  const hasLangPrefix = segments.length > 0 && languages.includes(segments[0] as Language);

  if (hasLangPrefix) {
    // Replace existing locale: /en/dashboard → /es/dashboard or /dashboard (for default)
    if (newLang === fallbackLng) {
      // Default language: remove prefix
      segments.shift();
      return '/' + segments.join('/') || '/';
    }
    segments[0] = newLang;
    return '/' + segments.join('/');
  } else {
    // Add locale prefix: /dashboard → /en/dashboard (or keep as-is for default)
    return buildLocalizedPath(pathname, newLang);
  }
}

/**
 * Add language prefix to a path, handling edge cases.
 *
 * Extended version that also handles:
 * - External URLs (unchanged)
 * - Paths already with language prefix (unchanged)
 * - Paths without leading slash (normalized)
 *
 * @param path - Path to localize
 * @param currentLang - Current language from pathname
 * @returns Localized path
 *
 * @example
 * // External URL - unchanged
 * localizePath('https://example.com', 'en') // → 'https://example.com'
 *
 * // Already prefixed - unchanged
 * localizePath('/en/dashboard', 'en') // → '/en/dashboard'
 *
 * // Default language (fr) - no prefix
 * localizePath('/dashboard', 'fr') // → '/dashboard'
 *
 * // Non-default language - add prefix
 * localizePath('/dashboard', 'en') // → '/en/dashboard'
 */
export function localizePath(path: string, currentLang: Language): string {
  // Don't modify external URLs
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }

  // Ensure path starts with /
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;

  // Check if path already has a language prefix
  const segments = normalizedPath.split('/').filter(Boolean);
  const hasLangPrefix = segments.length > 0 && languages.includes(segments[0] as Language);

  if (hasLangPrefix) {
    // Path already localized, return as-is
    return normalizedPath;
  }

  // Use buildLocalizedPath for the actual prefix logic
  return buildLocalizedPath(normalizedPath, currentLang);
}
